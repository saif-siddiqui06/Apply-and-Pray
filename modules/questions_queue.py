'''
Questions the bot can't answer, asked in the dashboard (Questions tab) instead of a desktop popup, when the dashboard started the bot.

The bot puts the question in the database and waits up to `popup_timeout_minutes` for your answer. If you answer in time it's
used right away; if not, the question stays in the Questions tab: answer it there later ("Save for all jobs") and the next run
uses it. Same return values as modules/popup.ask_user, so modules/answer_resolver.py can use either.
'''

import time

from modules import db


def ask(question: str, question_type: str = "text", options: list[str] | None = None, company: str = "", job_title: str = "",
        suggestion: str = "", note: str = "", allow_save: bool = True, timeout_seconds: float = 0, ai_writer=None):
    '''Returns (answer, save_for_all), None if you skipped it, raises TimeoutError if nobody answered in time.'''
    item_id = db.question_ask(question, question_type, options, company, job_title, allow_save, suggestion or note)
    end = time.time() + (timeout_seconds if timeout_seconds and timeout_seconds > 0 else 30 * 60)
    while time.time() < end:
        item = db.question_get(item_id)
        if item and item["status"] == "answered":
            db.question_mark_used(item_id)
            return item["answer"], bool(item["save_for_all"]) and allow_save
        if item and item["status"] == "skipped": return None
        time.sleep(1)
    raise TimeoutError("No answer in the dashboard")
