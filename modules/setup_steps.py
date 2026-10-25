'''
The dashboard's setup: 6 steps, what each one asks, its how-to guide, its check, and which features it unlocks.

Values are read from / saved to user_data (modules/user_settings.py). Passwords and keys are never sent back to the page,
only whether they are set. Steps with a check (LinkedIn, AI, Gmail) are done only after the check passed with the current values.
'''

import os
import re
import json
import runpy
import hashlib
from datetime import datetime

from modules.runtime import bundle_path, home_path
from modules.user_settings import SECRET_NAMES, load_section, save_section, get_secret

# Field: section (config file), name (setting), label, type, and optional: help, required, options, placeholder, show_if
# Types: text, email, tel, url, number, textarea, select, multiselect, list (one per line), checkbox, password, resume
STEPS = [
    {
        "id": "basics", "title": "Your basics", "icon": "👤",
        "why": "Used in every application form and to search jobs for you.",
        "fields": [
            {"section": "personals", "name": "first_name", "label": "First name", "type": "text", "required": True},
            {"section": "personals", "name": "middle_name", "label": "Middle name", "type": "text"},
            {"section": "personals", "name": "last_name", "label": "Last name", "type": "text", "required": True},
            {"section": "personals", "name": "email", "label": "Email for applications", "type": "email", "required": True, "help": "Recruiters reply here."},
            {"section": "personals", "name": "phone_number", "label": "Phone number", "type": "tel", "required": True, "help": "Without the country code, Eg: 9876543210"},
            {"section": "personals", "name": "current_city", "label": "City", "type": "text", "required": True},
            {"section": "personals", "name": "state", "label": "State", "type": "text", "required": True},
            {"section": "personals", "name": "country", "label": "Country", "type": "text", "required": True},
            {"section": "personals", "name": "zipcode", "label": "PIN / ZIP code", "type": "text"},
            {"section": "personals", "name": "street", "label": "Street address", "type": "text", "help": "Only some forms ask for it."},
            {"section": "questions", "name": "default_resume_path", "label": "Resume (PDF)", "type": "resume", "required": True},
            {"section": "search", "name": "search_terms", "label": "Job titles to search", "type": "list", "required": True, "placeholder": "Data Analyst\nPython Developer",
             "help": "One per line. The bot searches each of them on LinkedIn."},
            {"section": "search", "name": "search_location", "label": "Where", "type": "text", "required": True, "placeholder": "India", "help": "A country, state or city."},
            {"section": "search", "name": "experience_level", "label": "Experience levels", "type": "multiselect",
             "options": ["Internship", "Entry level", "Associate", "Mid-Senior level", "Director", "Executive"]},
            {"section": "search", "name": "current_experience", "label": "Your years of experience", "type": "number", "required": True,
             "help": "0 if you're a fresher."},
            {"section": "search", "name": "experience_tolerance", "label": "Also apply when a job asks for up to ... more years", "type": "number",
             "help": "1 = a fresher also applies to \"0-1 year\" jobs. Jobs asking for more are skipped."},
        ],
    },
    {
        "id": "linkedin", "title": "LinkedIn login", "icon": "🔗", "check": "linkedin",
        "why": "The bot works inside its own Chrome window, logged in to your LinkedIn.",
        "guide": """
<ol>
<li>Close any Chrome window the bot opened before.</li>
<li>Click <b>Open LinkedIn</b>. A separate Chrome window opens: this is the bot's own browser, not your normal Chrome.</li>
<li>Log in to LinkedIn there as usual, including the code LinkedIn may send you.</li>
<li>When your LinkedIn feed shows, this step turns green by itself and the window closes.</li>
</ol>
<p>You stay logged in for future runs. <b>Your LinkedIn password is never asked for or saved by the app.</b></p>""",
        "fields": [],
    },
    {
        "id": "ai", "title": "AI assistant", "icon": "✨", "check": "ai",
        "why": "Answers new questions in forms, and writes cover notes and personal messages from your resume.",
        "guide": """
<p><b>Google Gemini (free, recommended)</b></p>
<ol>
<li>Open <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener">aistudio.google.com/app/apikey</a> and sign in with your Google account.</li>
<li>Click <b>Create API key</b>, then copy it.</li>
<li>Paste it below and click <b>Save and test</b>.</li>
</ol>
<p>The free plan has a daily limit. When a model's limit is used up, the bot switches to another model by itself. For long runs, add
<b>backup keys</b> made with other Google accounts (each account has its own free limit): the bot moves to the next key when one runs out.</p>
<p><b>OpenAI (paid)</b>: create a key at <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">platform.openai.com/api-keys</a>
and add credit under Settings → Billing. Model example: <code>gpt-4o-mini</code>.</p>
<p><b>DeepSeek (paid, low cost)</b>: create a key at <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener">platform.deepseek.com/api_keys</a>
and top up your balance. Model: <code>deepseek-chat</code>.</p>
<p><b>Your own computer (free, advanced)</b>: run <a href="https://ollama.com" target="_blank" rel="noopener">Ollama</a> or
<a href="https://lmstudio.ai" target="_blank" rel="noopener">LM Studio</a>, choose “Local model”, address <code>http://localhost:11434/v1/</code> (Ollama)
or <code>http://localhost:1234/v1/</code> (LM Studio).</p>
<p><b>Backup AI (recommended, free)</b>: used automatically when your main AI can't answer. <b>Groq</b>: sign in at
<a href="https://console.groq.com/keys" target="_blank" rel="noopener">console.groq.com/keys</a> → <b>Create API Key</b> → copy it.
<b>OpenRouter</b>: <a href="https://openrouter.ai/keys" target="_blank" rel="noopener">openrouter.ai/keys</a> → <b>Create Key</b> (its ":free" models cost nothing).</p>
<p>Your keys are kept in Windows Credential Manager on this computer, never in a file.</p>""",
        "fields": [
            {"section": "secrets", "name": "ai_provider", "label": "AI provider", "type": "select", "required": True,
             "options": [["gemini", "Google Gemini (free)"], ["openai", "OpenAI"], ["deepseek", "DeepSeek"], ["local", "Local model (Ollama / LM Studio)"]]},
            {"section": "secrets", "name": "gemini_api_key", "label": "Gemini API key", "type": "password", "required": True, "show_if": ["ai_provider", ["gemini"]]},
            {"section": "secrets", "name": "gemini_backup_keys", "label": "Backup Gemini keys (optional)", "type": "password", "show_if": ["ai_provider", ["gemini"]],
             "help": "More keys, Eg: made with other Google accounts, separated by commas. When one key's free daily limit is used up, the bot switches to the next."},
            {"section": "secrets", "name": "fallback_ai", "label": "Backup AI (free, used when the main AI runs out)", "type": "select",
             "options": [["", "None"], ["groq", "Groq (free)"], ["openrouter", "OpenRouter (free models)"]]},
            {"section": "secrets", "name": "fallback_api_key", "label": "Backup AI key", "type": "password", "show_if": ["fallback_ai", ["groq", "openrouter"]]},
            {"section": "secrets", "name": "gemini_model", "label": "Gemini model", "type": "text", "placeholder": "gemini-3.8-flash", "show_if": ["ai_provider", ["gemini"]],
             "help": "Leave as it is unless you know you need another one."},
            {"section": "secrets", "name": "llm_api_key", "label": "API key", "type": "password", "required": True, "show_if": ["ai_provider", ["openai", "deepseek"]]},
            {"section": "secrets", "name": "llm_api_url", "label": "API address", "type": "url", "required": True, "show_if": ["ai_provider", ["openai", "deepseek", "local"]],
             "placeholder": "https://api.openai.com/v1/"},
            {"section": "secrets", "name": "llm_model", "label": "Model", "type": "text", "required": True, "show_if": ["ai_provider", ["openai", "deepseek", "local"]],
             "placeholder": "gpt-4o-mini"},
        ],
    },
    {
        "id": "details", "title": "Application details", "icon": "📝",
        "why": "Common questions on company websites, and an account for job sites that need one (Normal Apply).",
        "guide": """
<p><b>Job-site password</b>: many company career sites need an account. The bot creates and signs in to them with the email and password below.</p>
<ul>
<li>Use a <b>new password you don't use anywhere else</b> (not your Gmail or LinkedIn password): it is typed into many different websites.</li>
<li>Most sites need 8+ characters with a capital letter, a number and a symbol, Eg: <code>Jobs#2026apply</code>.</li>
<li>The bot only types it on secure (https) pages, never on “Sign in with Google” pages.</li>
<li>Leave it empty and those jobs are saved for you to apply by hand instead.</li>
</ul>""",
        "fields": [
            {"section": "questions", "name": "years_of_experience", "label": "Years of experience (answer in forms)", "type": "text", "required": True, "placeholder": "0"},
            {"section": "questions", "name": "require_visa", "label": "Need visa sponsorship?", "type": "select", "required": True, "options": ["No", "Yes"]},
            {"section": "questions", "name": "desired_salary", "label": "Expected salary per year", "type": "number", "required": True, "help": "Numbers only, Eg: 600000"},
            {"section": "questions", "name": "current_ctc", "label": "Current salary per year", "type": "number", "help": "0 if you're a fresher."},
            {"section": "questions", "name": "notice_period", "label": "Notice period (days)", "type": "number", "required": True},
            {"section": "questions", "name": "linkedIn", "label": "Your LinkedIn profile link", "type": "url", "required": True, "placeholder": "https://www.linkedin.com/in/your-name"},
            {"section": "questions", "name": "website", "label": "Portfolio / GitHub link", "type": "url"},
            {"section": "questions", "name": "recent_employer", "label": "Most recent employer", "type": "text", "help": "Empty if you haven't worked yet."},
            {"section": "questions", "name": "highest_degree", "label": "Highest degree", "type": "text", "placeholder": "B.Tech in Computer Science"},
            {"section": "questions", "name": "graduation_year", "label": "Graduation year", "type": "text", "placeholder": "2026", "help": "The expected year if you're still studying."},
            {"section": "questions", "name": "cgpa", "label": "CGPA (out of 10)", "type": "text", "placeholder": "8.2"},
            {"section": "questions", "name": "percentage_12th", "label": "12th percentage", "type": "text", "placeholder": "85"},
            {"section": "questions", "name": "percentage_10th", "label": "10th percentage", "type": "text", "placeholder": "90",
             "help": "Many Indian job forms ask these. Leave empty to let the AI / a popup handle them."},
            {"section": "questions", "name": "linkedin_headline", "label": "Headline", "type": "text", "placeholder": "Final-year CSE student | Python, SQL, ML"},
            {"section": "questions", "name": "linkedin_summary", "label": "Short summary about you", "type": "textarea"},
            {"section": "settings", "name": "max_applications_per_day", "label": "Most applications per day", "type": "number",
             "help": "LinkedIn restricts accounts that apply too much. 30 is a safe default; 0 = no limit (not recommended)."},
            {"section": "portal_login", "name": "portal_email", "label": "Email for job-site accounts", "type": "email", "help": "Empty = your application email."},
            {"section": "portal_login", "name": "portal_password", "label": "Password for job-site accounts", "type": "password"},
        ],
    },
    {
        "id": "gmail", "title": "Gmail", "icon": "✉️", "check": "gmail",
        "why": "Many jobs are posted as “send your CV to hr@company.com”. The bot emails your resume from your Gmail.",
        "guide": """
<ol>
<li>Open <a href="https://myaccount.google.com/security" target="_blank" rel="noopener">myaccount.google.com/security</a> and turn on <b>2-Step Verification</b> (Google requires it for app passwords).</li>
<li>Open <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener">myaccount.google.com/apppasswords</a>.</li>
<li>Type a name, Eg: <b>Apply and Pray</b>, and click <b>Create</b>.</li>
<li>Copy the 16-letter password Google shows (spaces don't matter) and paste it below.</li>
<li>Click <b>Save and test</b>: you'll get a test email from yourself.</li>
</ol>
<p>This is <b>not</b> your Gmail password. You can delete it on the same Google page any time, and the bot can no longer send email.
School or work Google accounts may not allow app passwords.</p>""",
        "fields": [
            {"section": "gmail", "name": "gmail_address", "label": "Gmail address", "type": "email", "required": True, "placeholder": "you@gmail.com"},
            {"section": "gmail", "name": "gmail_app_password", "label": "App password", "type": "password", "required": True},
            {"section": "gmail", "name": "email_signature", "label": "Email signature", "type": "textarea", "placeholder": "Asha Verma\n+91 98765 43210\nlinkedin.com/in/asha"},
            {"section": "gmail", "name": "review_before_send", "label": "Show me every email before it's sent (Review tab)", "type": "checkbox"},
            {"section": "gmail", "name": "max_emails_per_day", "label": "Most emails per day", "type": "number", "required": True},
        ],
    },
    {
        "id": "networking", "title": "Networking", "icon": "🤝",
        "why": "Connection requests to recruiters and hiring managers, and personal messages after they accept.",
        "guide": """
<p><b>What LinkedIn allows</b></p>
<ul>
<li><b>Free account</b>: a personal note on only a few invitations a month, and messages only to people you're connected to.
So the bot sends the request first, and the personal message after they accept.</li>
<li><b>Premium</b>: many more invitation notes, and InMail to people you're not connected to.</li>
</ul>
<p><b>Why limits</b>: LinkedIn restricts accounts that send too many invitations. The defaults stay well under its limits.
Raising them raises the risk to your account.</p>
<p><b>Your pitch</b> is what every note and message is written from, so make it specific: what you study or do, your top skills,
the roles you want, and one result you're proud of.</p>""",
        "fields": [
            {"section": "outreach", "name": "pitch", "label": "Your pitch (2-3 lines)", "type": "textarea", "required": True,
             "placeholder": "Final-year B.Tech CSE student skilled in Python, ML and SQL, looking for data / ML roles. Built a resume-screening model used by 200+ students."},
            {"section": "outreach", "name": "has_premium", "label": "I have LinkedIn Premium", "type": "checkbox"},
            {"section": "outreach", "name": "monthly_note_limit", "label": "Invitation notes per month", "type": "number", "help": "Free: about 5. Premium: much more."},
            {"section": "outreach", "name": "college", "label": "Your college (to reach alumni first)", "type": "text"},
            {"section": "outreach", "name": "message_tone", "label": "Message tone", "type": "select", "options": ["professional", "friendly", "formal"]},
            {"section": "outreach", "name": "review_before_send", "label": "Show me every request and message before it's sent", "type": "checkbox"},
            {"section": "outreach", "name": "connect_with_hirers", "label": "Connect with people who posted jobs I applied to", "type": "checkbox"},
            {"section": "outreach", "name": "connect_with_feed_leads", "label": "Connect with people whose job posts said \"DM me\"", "type": "checkbox"},
            {"section": "outreach", "name": "hirer_days", "label": "Only jobs I applied to in the last ... days", "type": "number"},
            {"section": "outreach", "name": "search_recruiters", "label": "Also find recruiters at those companies", "type": "checkbox"},
            {"section": "outreach", "name": "search_alumni", "label": "Also find people from my college at those companies", "type": "checkbox"},
            {"section": "outreach", "name": "max_invites_per_day", "label": "Invitations per day", "type": "number", "required": True},
            {"section": "outreach", "name": "max_invites_per_week", "label": "Invitations per week", "type": "number", "required": True},
            {"section": "outreach", "name": "max_messages_per_day", "label": "Messages per day", "type": "number", "required": True},
        ],
    },
]

# Features and the steps they need. "ready": built already; otherwise shown with its milestone.
FEATURES = [
    {"id": "easy", "title": "Easy Apply", "needs": ["basics", "linkedin"], "ready": True, "about": "Applies inside LinkedIn."},
    {"id": "ai", "title": "AI answers", "needs": ["ai"], "ready": True, "about": "Answers new questions from your resume."},
    {"id": "normal", "title": "Normal Apply", "needs": ["basics", "linkedin", "details"], "ready": True, "about": "Fills forms on company websites."},
    {"id": "feed", "title": "Feed jobs", "needs": ["basics", "linkedin"], "ready": True,
     "about": "Jobs posted in the LinkedIn feed: fills their forms, and emails your resume (needs Gmail)."},
    {"id": "connect", "title": "Connection requests", "needs": ["basics", "linkedin", "networking"], "ready": True, "about": "To hiring managers and recruiters, with a work note."},
    {"id": "dm", "title": "Personal messages", "needs": ["basics", "linkedin", "networking"], "ready": True, "about": "After they accept, then one follow-up. Stops when they reply."},
]

PLACEHOLDER_VALUES = {"First", "Last", "9876543210", "username@example.com", "example_password", "not-needed", "user_data/resumes/resume.pdf"}
STATUS_SECTION = "status"   # Results of the checks, in settings.json


#< Values
_defaults_cache: dict[str, dict] = {}

def defaults(section: str) -> dict:
    '''The default values of a config file, without your settings.'''
    if section not in _defaults_cache:
        os.environ["APPLY_AND_PRAY_DEFAULTS_ONLY"] = "1"
        try: namespace = runpy.run_path(bundle_path("config", section + ".py"))
        finally: os.environ.pop("APPLY_AND_PRAY_DEFAULTS_ONLY", None)
        _defaults_cache[section] = {key: value for key, value in namespace.items() if not key.startswith("_")}
    return _defaults_cache[section]


def _is_secret(field: dict) -> bool:
    return field["name"] in SECRET_NAMES.get(field["section"], [])


def value_of(field: dict):
    '''Your value, else the default. Passwords: True / False (set or not), never the value itself.'''
    if _is_secret(field): return bool(get_secret(field["name"]))
    section, name = field["section"], field["name"]
    if name == "ai_provider":   # "Local model" is saved as the OpenAI-compatible provider with an address on this computer
        mine = load_section("secrets")
        url = str(mine.get("llm_api_url", ""))
        if mine.get("ai_provider", defaults("secrets").get("ai_provider")) == "openai" and ("localhost" in url or "127.0.0.1" in url): return "local"
    mine = load_section(section)
    value = mine[name] if name in mine else defaults(section).get(name, "")
    return list(value) if isinstance(value, tuple) else value


def _filled(field: dict) -> bool:
    if field["type"] == "checkbox": return True
    value = value_of(field)
    if field["type"] == "password": return bool(value)
    if field["type"] == "resume": return bool(value) and os.path.isfile(home_path(value) if not os.path.isabs(value) else value)
    if isinstance(value, list): return len(value) > 0
    text = str(value).strip()
    return text != "" and text not in PLACEHOLDER_VALUES


def visible_fields(step: dict) -> list[dict]:
    '''Fields shown with the current answers (Eg: the Gemini key only when Gemini is chosen).'''
    shown = []
    for field in step["fields"]:
        if "show_if" in field:
            other, allowed = field["show_if"]
            source = next(f for f in step["fields"] if f["name"] == other)
            if value_of(source) not in allowed: continue
        shown.append(field)
    return shown
#>


#< Saving
class InvalidValue(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def _clean(field: dict, raw):
    kind, label = field["type"], field["label"]
    if kind == "checkbox": return bool(raw)
    if kind == "multiselect":
        values = [value for value in (raw or []) if value in field["options"]]
        return values
    if kind == "list":
        items = raw if isinstance(raw, list) else re.split(r'[\n,]', str(raw or ""))
        return [item.strip() for item in items if item.strip()]
    text = str(raw if raw is not None else "").strip()
    if kind == "number":
        if text == "": return 0
        if not re.fullmatch(r'-?\d+', text): raise InvalidValue(field["name"], f"{label}: numbers only.")
        return int(text)
    if text == "": return ""
    if kind == "email" and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', text): raise InvalidValue(field["name"], f"{label}: that doesn't look like an email address.")
    if kind == "tel":
        digits = re.sub(r'\D', '', text)
        if not 7 <= len(digits) <= 15: raise InvalidValue(field["name"], f"{label}: 7 to 15 digits.")
        return digits
    if kind == "url":
        if not re.match(r'https?://', text, re.I): text = "https://" + text
        if " " in text or "." not in text: raise InvalidValue(field["name"], f"{label}: that doesn't look like a link.")
    if kind == "select":
        allowed = [option[0] if isinstance(option, list) else option for option in field["options"]]
        if text not in allowed: raise InvalidValue(field["name"], f"{label}: choose one of the options.")
    if kind == "password" and field["name"] == "gmail_app_password":
        text = text.replace(" ", "")
        if not re.fullmatch(r'[A-Za-z]{16}', text): raise InvalidValue(field["name"], "App password: the 16 letters Google showed you.")
    return text


def save_step(step_id: str, values: dict) -> None:
    '''Checks and saves the values sent from the page. Password fields left empty keep the saved password.'''
    step = get_step(step_id)
    by_section: dict[str, dict] = {}
    for field in step["fields"]:
        if field["name"] not in values or field["type"] == "resume": continue
        raw = values[field["name"]]
        if field["type"] == "password" and not str(raw or "").strip(): continue   # Empty = keep the saved one
        cleaned = _clean(field, raw)
        by_section.setdefault(field["section"], {})[field["name"]] = cleaned
    secrets = by_section.get("secrets")
    if secrets and secrets.get("ai_provider"):   # "Local model" is the OpenAI-compatible API on your computer
        provider = secrets["ai_provider"]
        secrets["use_AI"] = True
        url = secrets.get("llm_api_url", "")
        if provider == "local":
            secrets["ai_provider"] = "openai"
            secrets["llm_api_key"] = "not-needed"
            url = url or "http://localhost:11434/v1/"
        if provider == "deepseek": url = url or "https://api.deepseek.com"
        elif provider in ("openai", "local") and url and not url.endswith("/"): url += "/"   # The OpenAI library needs the trailing /
        if provider != "gemini": secrets["llm_api_url"] = url
    for section, section_values in by_section.items():
        save_section(section, section_values)
#>


#< Checks and progress
def _fingerprint(step_id: str) -> str:
    '''Changes when the values a check depends on change, so the check must pass again.'''
    if step_id == "ai":
        parts = [str(value_of(f)) for f in get_step("ai")["fields"] if not _is_secret(f)] + [get_secret("gemini_api_key"), get_secret("llm_api_key")]
    elif step_id == "gmail":
        parts = [str(value_of(get_step("gmail")["fields"][0])), get_secret("gmail_app_password")]
    else:
        parts = [step_id]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def record_check(step_id: str, ok: bool, detail: str) -> None:
    status = load_section(STATUS_SECTION)
    status[step_id] = {"ok": ok, "detail": detail, "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "fingerprint": _fingerprint(step_id)}
    save_section(STATUS_SECTION, status)


def check_result(step_id: str) -> dict | None:
    result = load_section(STATUS_SECTION).get(step_id)
    if result and result.get("fingerprint") != _fingerprint(step_id): return {"ok": False, "detail": "Details changed since the last check: check again.", "stale": True}
    return result


def get_step(step_id: str) -> dict:
    for step in STEPS:
        if step["id"] == step_id: return step
    raise KeyError(step_id)


def step_state(step: dict) -> dict:
    missing = [field["label"] for field in visible_fields(step) if field.get("required") and not _filled(field)]
    result = check_result(step["id"]) if step.get("check") else None
    done = not missing and (not step.get("check") or bool(result and result.get("ok")))
    return {"done": done, "missing": missing, "check": result}


def overview() -> dict:
    '''Everything the Setup page shows.'''
    steps = []
    for step in STEPS:
        fields = []
        for field in step["fields"]:   # All of them: the page shows / hides `show_if` fields as you change the answers
            item = {key: value for key, value in field.items() if key != "section"}
            if field["type"] == "password": item["value"], item["is_set"] = "", value_of(field)
            else: item["value"] = value_of(field)
            fields.append(item)
        steps.append({"id": step["id"], "title": step["title"], "icon": step["icon"], "why": step["why"], "guide": step.get("guide", ""),
                      "check": step.get("check"), "fields": fields, "state": step_state(step)})
    done = {step["id"] for step in steps if step["state"]["done"]}
    features = [dict(feature, unlocked=all(need in done for need in feature["needs"]),
                     missing=[get_step(need)["title"] for need in feature["needs"] if need not in done]) for feature in FEATURES]
    return {"steps": steps, "features": features, "done": len(done), "total": len(STEPS)}


def unlocked(feature_id: str) -> bool:
    return next(f for f in overview()["features"] if f["id"] == feature_id)["unlocked"]
#>
