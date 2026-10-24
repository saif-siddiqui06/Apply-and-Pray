'''
The app's database: one SQLite file, user_data/app.db (git ignores user_data/).

* `applications`  - jobs applied to (Easy Apply, Normal Apply) or whose link was saved
* `failures`      - attempts that failed or were skipped after opening, with the reason
* `apply_by_hand` - links the bot couldn't finish, for you to apply yourself

The bot still writes its CSV files too (CSV / Excel export keeps working). `import_csvs()` copies old CSV rows in once,
and is safe to run again: rows already in the database are skipped.
Later features (feed posts, people, messages, limits) add their tables through `_MIGRATIONS`.
'''

import os
import re
import csv
import sqlite3
from urllib.parse import unquote
from contextlib import contextmanager
from datetime import datetime

from modules.user_settings import user_path

DB_FILE = user_path("app.db")

# Each entry upgrades the database by one version (PRAGMA user_version). Never edit an old entry, add a new one.
_MIGRATIONS = [
    '''
    CREATE TABLE applications (
        id INTEGER PRIMARY KEY,
        job_id TEXT NOT NULL UNIQUE,
        title TEXT, company TEXT, location TEXT, work_style TEXT,
        method TEXT,                 -- easy, normal, link (link saved, not applied), feed, email
        status TEXT,                 -- applied, link_saved
        job_link TEXT, apply_link TEXT,
        hr_name TEXT, hr_link TEXT,
        resume TEXT, date_posted TEXT, applied_at TEXT,
        experience_required TEXT, skills TEXT, description TEXT, questions TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE failures (
        id INTEGER PRIMARY KEY,
        job_id TEXT, job_link TEXT, reason TEXT, details TEXT, apply_link TEXT, screenshot TEXT,
        tried_at TEXT NOT NULL,
        UNIQUE (job_id, tried_at)
    );
    CREATE TABLE apply_by_hand (
        id INTEGER PRIMARY KEY,
        job_id TEXT NOT NULL UNIQUE,
        title TEXT, company TEXT, reason TEXT, apply_link TEXT, job_link TEXT,
        added_at TEXT NOT NULL,
        done_at TEXT                 -- set when you mark it applied
    );
    CREATE INDEX failures_job ON failures (job_id);
    ''',
    # 2: Feed jobs, and the Review Queue (outbox) shared by emails, invitations and messages
    '''
    CREATE TABLE feed_posts (
        urn TEXT PRIMARY KEY,        -- LinkedIn's id of the post, Eg: urn:li:activity:7123...
        author TEXT, author_url TEXT, author_headline TEXT,
        text TEXT, links TEXT, emails TEXT,   -- links / emails: JSON lists found in the post
        role TEXT, found_with TEXT,
        action TEXT,                 -- applied, apply_failed, saved_for_you, email_drafted, email_sent, lead, skipped
        detail TEXT, apply_link TEXT,
        seen_at TEXT NOT NULL
    );
    CREATE TABLE outbox (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,          -- email, invite, message
        status TEXT NOT NULL,        -- draft (waits for you), sent, skipped, failed
        to_address TEXT NOT NULL,    -- email address, or LinkedIn profile link
        to_name TEXT, subject TEXT, body TEXT, attachment TEXT,
        role_key TEXT NOT NULL DEFAULT '',   -- never the same person twice for the same role
        source TEXT,                 -- Eg: feed:<urn>
        error TEXT,
        created_at TEXT NOT NULL, sent_at TEXT,
        UNIQUE (kind, to_address, role_key)
    );
    CREATE INDEX outbox_status ON outbox (kind, status);
    ''',
    # 3: Networking: everyone the bot may contact, and where they are in the sequence
    '''
    CREATE TABLE people (
        profile_url TEXT PRIMARY KEY,     -- https://www.linkedin.com/in/<name>
        name TEXT, headline TEXT, company TEXT,
        role TEXT, job_link TEXT,         -- the job that connects you (applied to it, or they posted it)
        source TEXT,                      -- hirer (posted a job you applied to), feed (their post), search
        priority INTEGER DEFAULT 5,       -- lower first: who gets the few invitation notes
        status TEXT NOT NULL,             -- invite_drafted, invite_approved, invited, connected, messaged, replied, skipped, failed
        detail TEXT,
        invited_at TEXT, connected_at TEXT, last_message_at TEXT, follow_ups INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE INDEX people_status ON people (status);
    ''',
    # 4: People searches already done (Eg: "recruiter|acme"), so each company is searched once
    '''
    CREATE TABLE searches (
        key TEXT PRIMARY KEY,
        found INTEGER DEFAULT 0,
        done_at TEXT NOT NULL
    );
    ''',
]


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=15)   # The bot and the dashboard may write at the same time
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(_MIGRATIONS[version:], start=version + 1):
        connection.executescript(script)
        connection.execute(f"PRAGMA user_version = {number}")
        connection.commit()
    return connection


@contextmanager
def session():
    '''A connection that commits at the end of the block (rolls back on an error) and is always closed.'''
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text(value) -> str:
    if value is None: return ""
    if isinstance(value, datetime): return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


#< Written by the bot
def record_application(job_id: str, title: str, company: str, method: str, status: str, *, location: str = "", work_style: str = "",
                       job_link: str = "", apply_link: str = "", hr_name: str = "", hr_link: str = "", resume: str = "", date_posted="",
                       applied_at="", experience_required="", skills="", description: str = "", questions="") -> None:
    '''Adds a job, or updates it (Eg: a saved link you applied to later).'''
    with session() as connection:
        connection.execute('''
            INSERT INTO applications (job_id, title, company, location, work_style, method, status, job_link, apply_link, hr_name, hr_link,
                                      resume, date_posted, applied_at, experience_required, skills, description, questions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_id) DO UPDATE SET
                method = excluded.method, status = excluded.status, apply_link = excluded.apply_link,
                applied_at = CASE WHEN excluded.applied_at != '' THEN excluded.applied_at ELSE applications.applied_at END
        ''', (_text(job_id), _text(title), _text(company), _text(location), _text(work_style), method, status, _text(job_link), _text(apply_link),
              _text(hr_name), _text(hr_link), _text(resume), _text(date_posted), _text(applied_at), _text(experience_required), _text(skills),
              _text(description), _text(questions), _now()))


def record_failure(job_id: str, job_link: str, reason: str, details="", apply_link: str = "", screenshot: str = "", tried_at=None) -> None:
    with session() as connection:
        connection.execute("INSERT OR IGNORE INTO failures (job_id, job_link, reason, details, apply_link, screenshot, tried_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (_text(job_id), _text(job_link), _text(reason), _text(details)[:4000], _text(apply_link), _text(screenshot), _text(tried_at) or _now()))


def record_apply_by_hand(job_id: str, title: str, company: str, reason: str, apply_link: str, job_link: str, added_at=None) -> None:
    with session() as connection:
        connection.execute("INSERT OR IGNORE INTO apply_by_hand (job_id, title, company, reason, apply_link, job_link, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (_text(job_id), _text(title), _text(company), _text(reason), _text(apply_link), _text(job_link), _text(added_at) or _now()))
#>


#< Import of the old CSV files
def _rows(path: str) -> list[dict]:
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8", errors="replace", newline="") as file: return list(csv.DictReader(file))


def import_csvs(folder: str = "all excels") -> dict:
    '''Copies the bot's CSV history into the database. Safe to run again: existing rows are kept as they are.'''
    counts = {"applications": 0, "failures": 0, "apply_by_hand": 0}
    with session() as connection:
        for row in _rows(os.path.join(folder, "all_applied_applications_history.csv")):
            job_id = (row.get("Job ID") or "").strip()
            if not job_id: continue
            link = row.get("External Job link") or ""
            applied = (row.get("Date Applied") or "").strip()
            is_applied = bool(applied) and applied != "Pending"
            method = "easy" if link == "Easy Applied" else ("normal" if is_applied else "link")
            cursor = connection.execute('''
                INSERT OR IGNORE INTO applications (job_id, title, company, location, work_style, method, status, job_link, apply_link, hr_name, hr_link,
                                                    resume, date_posted, applied_at, experience_required, skills, description, questions, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (job_id, row.get("Title"), row.get("Company"), row.get("Work Location"), row.get("Work Style"), method,
                 "applied" if is_applied else "link_saved", row.get("Job Link"), "" if link == "Easy Applied" else link,
                 row.get("HR Name"), row.get("HR Link"), row.get("Resume"), row.get("Date Posted"), applied if is_applied else "",
                 row.get("Experience required"), row.get("Skills required"), row.get("About Job"), row.get("Questions Found"),
                 applied if is_applied else _now()))
            counts["applications"] += cursor.rowcount
        for row in _rows(os.path.join(folder, "all_failed_applications_history.csv")):
            if not (row.get("Job ID") or "").strip(): continue
            cursor = connection.execute("INSERT OR IGNORE INTO failures (job_id, job_link, reason, details, apply_link, screenshot, tried_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                        (row.get("Job ID"), row.get("Job Link"), row.get("Assumed Reason"), (row.get("Stack Trace") or "")[:4000],
                                         row.get("External Job link"), row.get("Screenshot Name"), row.get("Date Tried") or _now()))
            counts["failures"] += cursor.rowcount
        for row in _rows(os.path.join(folder, "apply_by_hand.csv")):
            if not (row.get("Job ID") or "").strip(): continue
            cursor = connection.execute("INSERT OR IGNORE INTO apply_by_hand (job_id, title, company, reason, apply_link, job_link, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                        (row.get("Job ID"), row.get("Job Title"), row.get("Company"), row.get("Reason"), row.get("Apply Link"),
                                         row.get("LinkedIn Job"), row.get("Date") or _now()))
            counts["apply_by_hand"] += cursor.rowcount
    return counts
#>


#< Read by the dashboard
def applications(limit: int = 1000) -> list[dict]:
    with session() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT job_id, title, company, location, method, status, job_link, apply_link, hr_name, hr_link, applied_at, created_at "
            "FROM applications ORDER BY COALESCE(NULLIF(applied_at, ''), created_at) DESC LIMIT ?", (limit,))]


def apply_by_hand_list(include_done: bool = False) -> list[dict]:
    with session() as connection:
        where = "" if include_done else "WHERE done_at IS NULL"
        return [dict(row) for row in connection.execute(f"SELECT * FROM apply_by_hand {where} ORDER BY added_at DESC")]


def mark_applied(job_id: str) -> bool:
    '''You applied to a saved link yourself.'''
    with session() as connection:
        now = _now()
        changed = connection.execute("UPDATE applications SET status = 'applied', applied_at = ? WHERE job_id = ? AND status != 'applied'", (now, job_id)).rowcount
        changed += connection.execute("UPDATE apply_by_hand SET done_at = ? WHERE job_id = ? AND done_at IS NULL", (now, job_id)).rowcount
        return changed > 0


def stats() -> dict:
    with session() as connection:
        one = lambda sql, *args: connection.execute(sql, args).fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "applied_total": one("SELECT COUNT(*) FROM applications WHERE status = 'applied'"),
            "applied_today": one("SELECT COUNT(*) FROM applications WHERE status = 'applied' AND applied_at LIKE ?", today + "%"),
            "easy": one("SELECT COUNT(*) FROM applications WHERE status = 'applied' AND method = 'easy'"),
            "normal": one("SELECT COUNT(*) FROM applications WHERE status = 'applied' AND method = 'normal'"),
            "links_saved": one("SELECT COUNT(*) FROM applications WHERE status = 'link_saved'"),
            "apply_by_hand": one("SELECT COUNT(*) FROM apply_by_hand WHERE done_at IS NULL"),
            "failed_today": one("SELECT COUNT(*) FROM failures WHERE tried_at LIKE ?", today + "%"),
            "feed": one("SELECT COUNT(*) FROM applications WHERE status = 'applied' AND method IN ('feed', 'email')"),
            "to_review": one("SELECT COUNT(*) FROM outbox WHERE status = 'draft'"),
        }


#< Feed jobs
def post_seen(urn: str) -> bool:
    with session() as connection:
        return connection.execute("SELECT 1 FROM feed_posts WHERE urn = ?", (urn,)).fetchone() is not None


def record_post(post: dict, action: str, detail: str = "", role: str = "", apply_link: str = "", found_with: str = "") -> None:
    import json
    with session() as connection:
        connection.execute('''
            INSERT INTO feed_posts (urn, author, author_url, author_headline, text, links, emails, role, found_with, action, detail, apply_link, seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (urn) DO UPDATE SET action = excluded.action, detail = excluded.detail, apply_link = excluded.apply_link''',
            (post["urn"], post.get("author", ""), post.get("author_url", ""), post.get("author_headline", ""), post.get("text", "")[:6000],
             json.dumps(post.get("links", [])), json.dumps(post.get("emails", [])), role, found_with, action, _text(detail)[:500], apply_link, _now()))


def feed_posts(limit: int = 200) -> list[dict]:
    with session() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT urn, author, author_url, role, action, detail, apply_link, seen_at, substr(text, 1, 400) AS text FROM feed_posts ORDER BY seen_at DESC LIMIT ?", (limit,))]
#>


#< Review Queue (outbox): emails now, invitations and messages later
def queue_message(kind: str, to_address: str, *, to_name: str = "", subject: str = "", body: str = "", attachment: str = "",
                  role_key: str = "", source: str = "", status: str = "draft") -> int | None:
    '''Adds a message. Returns its id, or None if this person already has one for this role (never contacted twice).'''
    with session() as connection:
        cursor = connection.execute('''
            INSERT OR IGNORE INTO outbox (kind, status, to_address, to_name, subject, body, attachment, role_key, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (kind, status, to_address.strip().lower() if kind == "email" else to_address.strip(),
                                                      to_name, subject, body, attachment, role_key, source, _now()))
        return cursor.lastrowid if cursor.rowcount else None


def outbox(status: str | None = "draft", kind: str | None = None, limit: int = 300) -> list[dict]:
    where, args = [], []
    if status: where.append("status = ?"); args.append(status)
    if kind: where.append("kind = ?"); args.append(kind)
    sql = "SELECT * FROM outbox" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC LIMIT ?"
    with session() as connection:
        return [dict(row) for row in connection.execute(sql, (*args, limit))]


def outbox_item(item_id: int) -> dict | None:
    with session() as connection:
        row = connection.execute("SELECT * FROM outbox WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None


def update_outbox(item_id: int, **fields) -> None:
    allowed = {key: value for key, value in fields.items() if key in ("status", "subject", "body", "error", "sent_at")}
    if not allowed: return
    with session() as connection:
        connection.execute(f"UPDATE outbox SET {', '.join(key + ' = ?' for key in allowed)} WHERE id = ?", (*allowed.values(), item_id))


def sent_today(kind: str) -> int:
    with session() as connection:
        return connection.execute("SELECT COUNT(*) FROM outbox WHERE kind = ? AND status = 'sent' AND sent_at LIKE ?",
                                  (kind, datetime.now().strftime("%Y-%m-%d") + "%")).fetchone()[0]
#>


#< People (Networking)
def profile_key(url: str) -> str:
    '''One spelling per profile: https://www.linkedin.com/in/<name>, no query, no trailing slash, lowercase.'''
    found = re.search(r'linkedin\.com/in/([^/?#]+)', url or "", re.I)
    return f"https://www.linkedin.com/in/{unquote(found.group(1)).lower()}" if found else (url or "").split("?")[0].rstrip("/").lower()


def person(profile_url: str) -> dict | None:
    with session() as connection:
        row = connection.execute("SELECT * FROM people WHERE profile_url = ?", (profile_key(profile_url),)).fetchone()
        return dict(row) if row else None


def add_person(profile_url: str, *, name: str = "", headline: str = "", company: str = "", role: str = "", job_link: str = "",
               source: str = "", priority: int = 5, status: str = "invite_drafted") -> bool:
    '''Adds someone once. False if they're already known (never contacted twice).'''
    with session() as connection:
        cursor = connection.execute('''INSERT OR IGNORE INTO people (profile_url, name, headline, company, role, job_link, source, priority, status, created_at)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (profile_key(profile_url), name.strip(), headline, company, role, job_link, source, priority, status, _now()))
        return cursor.rowcount > 0


def update_person(profile_url: str, **fields) -> None:
    allowed = {key: value for key, value in fields.items()
               if key in ("name", "headline", "company", "status", "detail", "invited_at", "connected_at", "last_message_at", "follow_ups")}
    if not allowed: return
    with session() as connection:
        connection.execute(f"UPDATE people SET {', '.join(key + ' = ?' for key in allowed)} WHERE profile_url = ?", (*allowed.values(), profile_key(profile_url)))


def people(status: str | None = None, limit: int = 500) -> list[dict]:
    with session() as connection:
        if status: rows = connection.execute("SELECT * FROM people WHERE status = ? ORDER BY priority, created_at LIMIT ?", (status, limit))
        else: rows = connection.execute("SELECT * FROM people ORDER BY COALESCE(invited_at, created_at) DESC LIMIT ?", (limit,))
        return [dict(row) for row in rows]


def search_done(key: str) -> bool:
    with session() as connection: return connection.execute("SELECT 1 FROM searches WHERE key = ?", (key,)).fetchone() is not None


def record_search(key: str, found: int) -> None:
    with session() as connection: connection.execute("INSERT OR REPLACE INTO searches (key, found, done_at) VALUES (?, ?, ?)", (key, found, _now()))


def invites_sent_since(since: str, with_note: bool | None = None) -> int:
    '''Invitations sent since `since` ("YYYY-MM-DD..."), optionally only those with / without a note.'''
    sql = "SELECT COUNT(*) FROM outbox WHERE kind = 'invite' AND status = 'sent' AND sent_at >= ?"
    if with_note is True: sql += " AND body != ''"
    if with_note is False: sql += " AND body = ''"
    with session() as connection: return connection.execute(sql, (since,)).fetchone()[0]
#>


def export_csv(table: str) -> str:
    '''The whole table as CSV text, for download.'''
    if table not in ("applications", "failures", "apply_by_hand", "feed_posts", "outbox", "people"): raise ValueError(table)
    import io
    with session() as connection:
        cursor = connection.execute(f"SELECT * FROM {table} ORDER BY id")
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([column[0] for column in cursor.description])
        writer.writerows(cursor)
        return out.getvalue()
#>
