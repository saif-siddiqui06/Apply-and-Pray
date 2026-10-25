'''
Apply & Pray dashboard: runs on YOUR computer only (http://127.0.0.1:5000), opened in your browser.

* Setup        - 6 steps with how-to guides and checks. Each step unlocks features.
* Run          - start the bot in a mode you've unlocked, Pause / Skip / Stop / Quit it, see what it's doing.
* Applications - everything applied to, links saved for you to apply by hand, CSV export.

Start it with:  python app.py   (or python apply_and_pray.py, or the Windows app)
'''

import os
import sys
import csv
import json
import secrets
import threading
import subprocess
import webbrowser
from datetime import datetime

from flask import Flask, request, jsonify, render_template, abort, Response
from werkzeug.utils import secure_filename

from modules import db
from modules import setup_steps
from modules import gmail
from modules.runtime import APP_HOME, bundle_path, home_path, command
from modules.user_settings import save_section, user_path

HOST, PORT = "127.0.0.1", int(os.environ.get("APPLY_AND_PRAY_PORT", "5000"))
LOGS_DIR = home_path("logs")
CONTROL_STATE = os.path.join(LOGS_DIR, "control_state.json")
CONTROL_STATUS = os.path.join(LOGS_DIR, "control_status.txt")
LOG_FILE = os.path.join(LOGS_DIR, "log.txt")
APPLIED_CSV = home_path("all excels", "all_applied_applications_history.csv")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

app = Flask(__name__, template_folder=bundle_path("templates"), static_folder=bundle_path("static"))
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # Resume uploads
TOKEN = secrets.token_urlsafe(24)   # New every start. Only this page knows it, so other websites can't use the dashboard


#< Security: only this computer, only this page
@app.before_request
def only_this_page():
    host = (request.host or "").split(":")[0]
    if host not in ("127.0.0.1", "localhost"): abort(403)   # Stops "DNS rebinding" tricks from other websites
    if request.path.startswith("/api/") and request.headers.get("X-Token") != TOKEN: abort(403)


@app.after_request
def no_caching(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    return response
#>


@app.route("/")
def home():
    return render_template("index.html", token=TOKEN)


#< Setup
@app.get("/api/setup")
def get_setup():
    return jsonify(setup_steps.overview())


@app.post("/api/setup/<step_id>")
def save_setup(step_id):
    try:
        setup_steps.save_step(step_id, request.get_json(force=True) or {})
    except KeyError: abort(404)
    except setup_steps.InvalidValue as e:
        return jsonify({"error": str(e), "field": e.field}), 400
    return jsonify(setup_steps.overview())


@app.post("/api/resume")
def upload_resume():
    file = request.files.get("resume")
    if not file or not file.filename: return jsonify({"error": "Choose your resume file."}), 400
    name = secure_filename(file.filename) or "resume.pdf"
    if not name.lower().endswith((".pdf", ".docx")): return jsonify({"error": "Use a PDF (best) or a .docx file."}), 400
    path = user_path("resumes", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file.save(path)
    save_section("questions", {"default_resume_path": os.path.relpath(path, APP_HOME).replace("\\", "/")})
    preview = ""
    try:
        from modules.resumes.extractor import extract_resume_text
        preview = (extract_resume_text(path, limit=600) or "").strip()
    except Exception: pass
    return jsonify({"overview": setup_steps.overview(), "preview": preview,
                    "warning": "" if preview else "Saved, but no text could be read from it. A scanned / image PDF can't be read by job websites either: export your resume as a text PDF if you can."})


_checks: dict[str, dict] = {}       # step id -> {"running": bool, "result": {...}}
_checks_lock = threading.Lock()


def _run_script(task: str, timeout: int) -> dict:
    try:
        finished = subprocess.run(command(task), cwd=APP_HOME, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, creationflags=NO_WINDOW)
        for line in reversed(finished.stdout.strip().splitlines()):
            if line.startswith("{"): return json.loads(line)
        return {"ok": False, "detail": (finished.stderr.strip().splitlines() or ["The check stopped without an answer."])[-1][:250]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "The check took too long."}


def _check_worker(step_id: str) -> None:
    if step_id == "pages":   # "Check LinkedIn": not a setup step, just shown
        result = _run_script("check-linkedin-pages", 360)
        with _checks_lock: _checks[step_id] = {"running": False, "result": result}
        return
    if step_id == "linkedin": result = _run_script("check-linkedin", 360)
    elif step_id == "ai": result = _run_script("check-ai", 120)
    else: result = gmail.check()
    setup_steps.record_check(step_id, bool(result.get("ok")), str(result.get("detail", "")))
    with _checks_lock: _checks[step_id] = {"running": False, "result": result}


@app.post("/api/check/<step_id>")
def start_check(step_id):
    if step_id not in ("linkedin", "ai", "gmail", "pages"): abort(404)
    if step_id in ("linkedin", "pages") and _bot_running(): return jsonify({"error": "Stop the bot first: it's using the LinkedIn window."}), 409
    with _checks_lock:
        if _checks.get(step_id, {}).get("running"): return jsonify({"running": True})
        _checks[step_id] = {"running": True, "result": None}
    threading.Thread(target=_check_worker, args=(step_id,), daemon=True).start()
    return jsonify({"running": True})


@app.get("/api/check/<step_id>")
def check_status(step_id):
    with _checks_lock: state = dict(_checks.get(step_id, {"running": False, "result": None}))
    return jsonify(state)
#>


#< Run the bot
_bot = {"process": None, "mode": None, "started": None, "log_start": 0}


def _bot_running() -> bool:
    process = _bot["process"]
    return process is not None and process.poll() is None


def _write_control(change: dict) -> None:
    try:
        with open(CONTROL_STATE, encoding="utf-8") as file: state = json.load(file)
    except Exception: state = {"paused": False, "skip": 0, "stop": False, "quit": False}
    for key, value in change.items():
        state[key] = state.get(key, 0) + 1 if value == "+1" else value
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(CONTROL_STATE + ".tmp", "w", encoding="utf-8") as file: json.dump(state, file)
    os.replace(CONTROL_STATE + ".tmp", CONTROL_STATE)


@app.post("/api/run/start")
def start_bot():
    data = request.get_json(force=True) or {}
    mode, test_run = data.get("mode"), bool(data.get("test"))
    feature = {"easy": "easy", "normal": "normal", "both": "normal", "feed": "feed", "connect": "connect"}.get(mode)
    if not feature: return jsonify({"error": "Choose a mode."}), 400
    if not setup_steps.unlocked(feature) or (mode == "both" and not setup_steps.unlocked("easy")):
        return jsonify({"error": "Finish the setup steps this mode needs first."}), 409
    if _bot_running(): return jsonify({"error": "The bot is already running."}), 409
    if any(check.get("running") for check in _checks.values()): return jsonify({"error": "Wait for the setup check to finish."}), 409
    for path in (CONTROL_STATE, CONTROL_STATUS):
        try: os.remove(path)
        except OSError: pass
    _bot["log_start"] = os.path.getsize(LOG_FILE) if os.path.exists(LOG_FILE) else 0
    environment = dict(os.environ, APPLY_AND_PRAY_MODE=mode, APPLY_AND_PRAY_DASHBOARD="1", PYTHONIOENCODING="utf-8", APPLY_AND_PRAY_TEST_RUN="1" if test_run else "0")
    _bot["process"] = subprocess.Popen(command("bot"), cwd=APP_HOME, env=environment,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    _bot["mode"], _bot["started"], _bot["test"] = mode, datetime.now().strftime("%H:%M"), test_run
    return jsonify(_run_status())


@app.post("/api/run/control")
def control_bot():
    action = (request.get_json(force=True) or {}).get("action")
    changes = {"pause": {"paused": True}, "resume": {"paused": False}, "skip": {"skip": "+1", "paused": False}, "stop": {"stop": True}, "quit": {"quit": True}}
    if action not in changes: abort(400)
    if not _bot_running(): return jsonify({"error": "The bot isn't running."}), 409
    _write_control(changes[action])
    return jsonify(_run_status())


def _log_tail(max_lines: int = 60) -> list[str]:
    if not os.path.exists(LOG_FILE): return []
    try:
        with open(LOG_FILE, "rb") as file:
            start = _bot["log_start"]
            size = os.path.getsize(LOG_FILE)
            file.seek(max(start, size - 20000))
            lines = file.read().decode("utf-8", errors="replace").splitlines()
        return [line for line in lines if line.strip()][-max_lines:]
    except Exception: return []


def _run_status() -> dict:
    running = _bot_running()
    try:
        with open(CONTROL_STATE, encoding="utf-8") as file: control = json.load(file)
    except Exception: control = {}
    try:
        with open(CONTROL_STATUS, encoding="utf-8") as file: status = file.read().strip()
    except Exception: status = ""
    return {"running": running, "mode": _bot["mode"], "started": _bot["started"], "test": _bot.get("test", False), "paused": bool(control.get("paused")) and running,
            "stopping": bool(control.get("stop")) and running, "status": "" if status == "__exit__" else status,
            "log": _log_tail() if _bot["started"] else [], "stats": db.stats()}


@app.get("/api/run")
def run_status():
    return jsonify(_run_status())
#>


#< Applications
@app.get("/api/applications")
def list_applications():
    return jsonify({"applications": db.applications(), "apply_by_hand": db.apply_by_hand_list(), "stats": db.stats()})


@app.post("/api/applications/<job_id>/applied")
def mark_applied(job_id):
    '''You applied to a saved link yourself. Also updates the CSV the bot reads, so it isn't tried again.'''
    found = db.mark_applied(job_id)
    try:
        if os.path.exists(APPLIED_CSV):
            with open(APPLIED_CSV, encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                fields, rows = reader.fieldnames, list(reader)
            for row in rows:
                if row.get("Job ID") == job_id and row.get("Date Applied") in ("Pending", ""):
                    row["Date Applied"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(APPLIED_CSV, "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
    except PermissionError:
        return jsonify({"error": "Close the applied-jobs Excel file, then try again."}), 409
    return jsonify({"ok": found})


#< Review Queue and feed posts
@app.get("/api/review")
def review_queue():
    from modules.user_settings import load_section
    gmail_ready = setup_steps.step_state(setup_steps.get_step("gmail"))["done"]
    from modules import connections, messages
    def with_person(items):
        out = []
        for item in items:
            person = db.person(item["to_address"]) or {}
            out.append(dict(item, headline=person.get("headline", ""), company=person.get("company", ""), source=person.get("source", item.get("source", "")),
                            job_link=person.get("job_link", ""), person_status=person.get("status", "")))
        return out
    invites = with_person(db.outbox("draft", "invite") + db.outbox("approved", "invite"))
    dms = with_person(db.outbox("draft", "message") + db.outbox("approved", "message"))
    outreach = load_section("outreach")
    return jsonify({"drafts": db.outbox("draft", "email"), "sent": db.outbox("sent", "email", limit=50), "posts": db.feed_posts(150), "gmail_ready": gmail_ready,
                    "sent_today": db.sent_today("email"), "daily_limit": int(load_section("gmail").get("max_emails_per_day", 20) or 20),
                    "invites": invites, "invite_limits": connections.invite_limits(), "notes_left": connections.notes_left_this_month(),
                    "messages": dms, "message_limits": messages.message_limits(), "message_limit": messages.MESSAGE_LIMIT,
                    "note_limit": connections.NOTE_LIMIT_PREMIUM if outreach.get("has_premium") else connections.NOTE_LIMIT_FREE,
                    "networking_ready": setup_steps.step_state(setup_steps.get_step("networking"))["done"]})


@app.post("/api/review/<int:item_id>")
def review_item(item_id):
    data = request.get_json(force=True) or {}
    action = data.get("action")
    item = db.outbox_item(item_id)
    if not item: abort(404)
    if action == "skip":
        db.update_outbox(item_id, status="skipped")
        if item["kind"] == "invite": db.update_person(item["to_address"], status="skipped", detail="Skipped by you.")
        if item["kind"] == "message" and item["role_key"] == "follow_up": db.update_person(item["to_address"], follow_ups=1, detail="Follow-up skipped by you.")
        return jsonify({"ok": True, "detail": "Skipped."})
    if action == "save":
        db.update_outbox(item_id, subject=str(data.get("subject", item["subject"] or "")), body=str(data.get("body", item["body"] or "")))
        return jsonify({"ok": True, "detail": "Saved."})
    if action == "approve" and item["kind"] in ("invite", "message"):
        from modules import connections, messages
        from modules.user_settings import load_section
        text = str(data.get("body", item["body"] or "")).strip()
        if item["kind"] == "invite":
            limit = connections.NOTE_LIMIT_PREMIUM if load_section("outreach").get("has_premium") else connections.NOTE_LIMIT_FREE
        else:
            limit = messages.MESSAGE_LIMIT
            if len(text) < 20: return jsonify({"ok": False, "detail": "Write the message first."}), 400
        if len(text) > limit: return jsonify({"ok": False, "detail": f"It's {len(text)} characters, the limit is {limit}."}), 400
        db.update_outbox(item_id, status="approved", body=text)
        if item["kind"] == "invite": db.update_person(item["to_address"], status="invite_approved")
        return jsonify({"ok": True, "detail": "Approved: sent on the next Networking run."})
    if action == "send" and item["kind"] == "email":
        if not setup_steps.step_state(setup_steps.get_step("gmail"))["done"]:
            return jsonify({"ok": False, "detail": "Finish Setup → Gmail first (the test email must pass)."}), 409
        from modules.feed_jobs import send_queued_email
        result = send_queued_email(item_id, data.get("subject"), data.get("body"))
        return jsonify(result), 200 if result["ok"] else 409
    abort(400)
#>


@app.post("/api/connect/find")
def find_people():
    '''Prepares connection requests now (Review shows them), without starting the bot.'''
    if not setup_steps.step_state(setup_steps.get_step("networking"))["done"]:
        return jsonify({"error": "Finish Setup → Networking first."}), 409
    try:
        finished = subprocess.run(command("draft"), cwd=APP_HOME, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                                  creationflags=NO_WINDOW)
        line = next((l for l in reversed(finished.stdout.strip().splitlines()) if l.startswith("{")), None)
        if not line: return jsonify({"error": (finished.stderr.strip().splitlines() or ["Couldn't prepare requests."])[-1][:250]}), 500
        return jsonify(json.loads(line))
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Writing the notes took too long. Try again."}), 500


@app.post("/api/connect/approve-all")
def approve_all_invites():
    kind = (request.get_json(force=True) or {}).get("kind", "invite")
    if kind not in ("invite", "message"): abort(400)
    count = 0
    for item in db.outbox("draft", kind):
        if kind == "message" and len((item["body"] or "").strip()) < 20: continue
        db.update_outbox(item["id"], status="approved")
        if kind == "invite": db.update_person(item["to_address"], status="invite_approved")
        count += 1
    noun = "request(s)" if kind == "invite" else "message(s)"
    return jsonify({"ok": True, "detail": f"{count} {noun} approved: sent on the next Networking run."})


@app.get("/api/people")
def list_people():
    everyone = db.people(limit=2000)
    counts = {}
    for person in everyone: counts[person["status"]] = counts.get(person["status"], 0) + 1
    return jsonify({"people": everyone, "counts": counts})


@app.get("/api/questions")
def list_questions():
    return jsonify({"questions": db.questions_pending(), "bot_running": _bot_running()})


@app.post("/api/questions/<int:item_id>")
def answer_question(item_id):
    data = request.get_json(force=True) or {}
    item = db.question_get(item_id)
    if not item: abort(404)
    if data.get("action") == "skip":
        db.question_skip(item_id)
        return jsonify({"ok": True, "detail": "Skipped."})
    answer = str(data.get("answer", "")).strip()
    if not answer: return jsonify({"ok": False, "detail": "Type an answer first."}), 400
    save_for_all = bool(data.get("save_for_all", True)) and bool(item["can_save"])
    db.question_answer(item_id, answer, save_for_all)
    if save_for_all:   # Saved now as well, so the next run uses it even if the bot already moved on
        import json as _json
        from config.settings import saved_answers_file
        from modules.answer_store import AnswerStore
        options = _json.loads(item["options"] or "[]")
        AnswerStore(saved_answers_file).save(item["question"], answer, item["qtype"] or "text", options or None)
    return jsonify({"ok": True, "detail": "Saved: used for this and future applications." if save_for_all else "Sent to the bot."})


@app.get("/api/version")
def version_info():
    from modules.version import latest_release
    return jsonify(latest_release())


@app.get("/api/export/<table>.csv")
def export(table):
    try: data = db.export_csv(table)
    except ValueError: abort(404)
    return Response(data, mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{table}-{datetime.now():%Y%m%d}.csv"'})
#>


def _already_running(url: str) -> bool:
    import socket
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, PORT)) == 0


def main() -> None:
    url = f"http://{HOST}:{PORT}/"
    if _already_running(url):   # Started twice (Eg: double-clicked the app again): just show the open one
        print(f"The dashboard is already running: {url}")
        webbrowser.open(url)
        return
    try:
        counts = db.import_csvs(home_path("all excels"))
        if any(counts.values()): print("Imported job history into the database:", counts)
    except Exception as e:
        print("Couldn't import the job history CSV files:", e)
    print(f"\nApply & Pray dashboard: {url}\nIt runs only on this computer. Keep this window open while you use it, close it to stop.\n")
    if not os.environ.get("APPLY_AND_PRAY_NO_BROWSER"): threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    from modules.runtime import enter_home
    enter_home()
    main()
