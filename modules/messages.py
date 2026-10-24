'''
Personal messages to people who accepted your connection request, one follow-up, and stop when they reply.

`draft_messages()`  - writes the first message for each new connection (your pitch, the job that connects you, a clear ask),
                      and ONE follow-up for anyone who hasn't replied after `follow_up_after_days`. Into the Review Queue
                      (outbox, kind "message"), or approved straight away when review is off.
`NetworkRun.run()`  - the whole Networking run in the bot's browser:
                      1. reads your recent connections and marks who accepted
                      2. drafts messages (and new connection requests)
                      3. sends approved messages within your daily limit. Before a follow-up it opens the conversation:
                         if they replied, the follow-up is cancelled and they're marked "replied: your turn"
                      4. sends approved connection requests (modules/connections.py)
Nobody gets more than one first message and one follow-up (the outbox keeps one of each per person).
'''

import re
import random
from datetime import datetime, timedelta

from selenium.webdriver.common.keys import Keys

from modules import db
from modules.helpers import print_lg
from modules.connections import Connector, first_name, _outreach, _me, _MARK_TOP_JS, _TOP

MESSAGE_LIMIT = 1900       # Characters: LinkedIn allows much more, short messages get answered
CONNECTIONS_PAGE = "https://www.linkedin.com/mynetwork/invite-connect/connections/"


#< Limits
def message_limits() -> dict:
    o = _outreach()
    now = datetime.now()
    today = db.sent_today("message")
    start, end = (list(o.active_hours) + [9, 21])[:2]
    left = max(0, int(o.max_messages_per_day) - today)
    reason = ""
    if not (int(start) <= now.hour < int(end)): reason, left = f"Outside your active hours ({start}:00-{end}:00).", 0
    elif left <= 0: reason = f"Today's limit of {o.max_messages_per_day} messages is reached."
    return {"left": left, "today": today, "reason": reason}
#>


#< Writing
def template_message(person: dict) -> str:
    me, pitch = _me()
    hello = f"Hi {first_name(person['name'])}," if first_name(person["name"]) else "Hi,"
    role, company = person.get("role") or "the open role", person.get("company")
    about = f" {pitch.rstrip('.')}." if pitch else ""
    if person.get("source") in ("hirer", "recruiter", "alumni"):
        opener = "great to connect with a fellow alum!" if person.get("source") == "alumni" else "thank you for connecting!"
        return (f"{hello} {opener}\n\nI recently applied for the {role} role{' at ' + company if company else ''}.{about}\n\n"
                f"Could you let me know if my profile fits what the team is looking for, or point me to the right person? I'd be happy to share anything else.\n\nThanks,\n{me}")
    return (f"{hello} thank you for connecting!\n\nI saw your post about the {role} opening and I'm very interested.{about}\n\n"
            f"Could I share my resume with you, or apply through the right channel? Happy to answer any questions.\n\nThanks,\n{me}")


def template_follow_up(person: dict) -> str:
    me, _ = _me()
    hello = f"Hi {first_name(person['name'])}," if first_name(person["name"]) else "Hi,"
    return f"{hello} just following up on my message about the {person.get('role') or 'open'} role. I'd really appreciate any update or advice. Thank you!\n{me}"


def ai_message(person: dict) -> str | None:
    from modules.ai.simple import write
    o = _outreach()
    me, pitch = _me()
    hello = f"Hi {first_name(person['name'])}," if first_name(person["name"]) else "Hi,"
    from modules.connections import why_text
    why = why_text(person) + (f" Job link: {person['job_link']}" if person.get("job_link") and person.get("source") == "hirer" else "")
    ask = {"hirer": "ask whether their profile fits the role, or who the right person to talk to is",
           "recruiter": "ask whether their profile fits the role or other openings, and if they could pass it to the hiring team",
           "alumni": "ask for a quick tip about the team or a referral if they think the profile fits, without pressure"}.get(person.get("source"),
           "ask if they can share their resume, or how best to apply")
    prompt = (f"Write a LinkedIn message from a job candidate to {person.get('name') or 'a recruiter'}"
              f"{' (' + person['headline'] + ')' if person.get('headline') else ''}, who just accepted their connection request.\n{why}\n"
              f"About the candidate: {pitch}\n\nRules: 3 to 5 short sentences, under 600 characters. Tone: {o.message_tone}. Start with '{hello}', thank them for connecting, "
              f"mention the role, one or two specific skills of the candidate that fit it, then {ask}. Sign with '{me}'. Plain text, no subject line, "
              "no emojis, no hashtags, no placeholders like [Name], don't invent facts. Reply with the message only.")
    text = write(prompt, max_tokens=400)
    if not text or "[" in text or len(text) < 80: return None
    return text.strip().strip('"')[:MESSAGE_LIMIT]


def draft_messages() -> dict:
    '''First messages for new connections, follow-ups for people who didn't reply. Returns counts.'''
    o = _outreach()
    status = "draft" if o.review_before_send else "approved"
    counts = {"first": 0, "follow_up": 0}
    with db.session() as connection:
        sent_first = {row[0] for row in connection.execute("SELECT to_address FROM outbox WHERE kind = 'message' AND role_key = 'first'")}
        had_follow_up = {row[0] for row in connection.execute("SELECT to_address FROM outbox WHERE kind = 'message' AND role_key = 'follow_up'")}
    for person in db.people("connected"):
        if person["profile_url"] in sent_first: continue
        body = ai_message(person) or template_message(person)
        if db.queue_message("message", person["profile_url"], to_name=person["name"], subject=person.get("role", ""), body=body, role_key="first",
                            source=person.get("source", ""), status=status):
            counts["first"] += 1
    due = (datetime.now() - timedelta(days=int(o.follow_up_after_days))).strftime("%Y-%m-%d %H:%M:%S")
    for person in db.people("messaged"):
        if person["profile_url"] in had_follow_up or (person.get("follow_ups") or 0) > 0: continue
        if not person.get("last_message_at") or person["last_message_at"] > due: continue
        if db.queue_message("message", person["profile_url"], to_name=person["name"], subject=person.get("role", ""), body=template_follow_up(person),
                            role_key="follow_up", source=person.get("source", ""), status=status):
            counts["follow_up"] += 1
    if any(counts.values()): print_lg(f"Messages written: {counts['first']} first message(s), {counts['follow_up']} follow-up(s).")
    return counts
#>


#< The LinkedIn part
_BOX = "//div[@contenteditable='true' and (contains(@class,'msg-form__contenteditable') or @role='textbox')]"
_SEND = "//button[contains(@class,'msg-form__send-button') or (@type='submit' and normalize-space(.)='Send') or normalize-space(.)='Send']"
_THREAD_JS = r'''
const items = [...document.querySelectorAll('.msg-s-event-listitem, [data-event-urn], .msg-s-message-list__event')];
return {total: items.length,
        theirs: items.filter(e => /msg-s-event-listitem--other/.test(e.className) || e.querySelector('.msg-s-event-listitem--other')).length,
        texts: [...document.querySelectorAll('.msg-s-event-listitem__body, .msg-s-event__content')].map(e => (e.innerText || '').trim()).slice(-6)};
'''


class NetworkRun(Connector):
    def __init__(self, driver, control=None, save_page=None):
        super().__init__(driver, control, save_page)
        self.counts.update({"accepted": 0, "messages_sent": 0, "follow_ups_sent": 0, "replied": 0, "messages_failed": 0})
        self.message_stop = ""


    def check_new_connections(self) -> int:
        '''Reads your most recent connections and marks invited people who are now connected.'''
        invited = {person["profile_url"]: person for person in db.people("invited")}
        if not invited: return 0
        self._checkpoint()
        if self.control is not None: self.control.status("Networking: checking who accepted")
        self.driver.get(CONNECTIONS_PAGE)
        self._wait(4)
        seen: set[str] = set()
        for _ in range(5):   # The newest connections come first: a few screens are enough
            for link in self.driver.find_elements("xpath", "//main//a[contains(@href,'/in/')]"):
                try: seen.add(db.profile_key(link.get_attribute("href") or ""))
                except Exception: pass
            if invited.keys() <= seen: break
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self._wait(2)
        if not seen and self.save_page: self.save_page(f"connections-unread-{datetime.now():%Y%m%d-%H%M%S}.html")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        accepted = [url for url in invited if url in seen]
        for url in accepted:
            db.update_person(url, status="connected", connected_at=now, detail="Accepted your request.")
            print_lg(f"   {invited[url]['name'] or url} accepted your connection request")
        self.counts["accepted"] += len(accepted)
        return len(accepted)


    def _open_conversation(self, url: str) -> str:
        '''Opens the message box with this person. Returns "" when it's open, else why not.'''
        self.driver.get(url)
        self._wait(4)
        self._checkpoint()
        try: self.driver.execute_script(_MARK_TOP_JS)
        except Exception: pass
        button = self._visible(f"{_TOP}//*[(self::button or self::a)][starts-with(@aria-label,'Message') or normalize-space(.)='Message']")
        if button is None: return "No Message button: you're not connected (yet)."
        href = button.get_attribute("href") or "" if button.tag_name.lower() == "a" else ""
        if "/messaging/" in href:   # LinkedIn's 2026 layout: "Message" is a link to the messaging page, not a pop-up
            self.driver.get(href)
            self._wait(6)
        else:
            self._click(button)
            self._wait(3)
        if self._visible(_BOX) is None:
            if re.search(r"\bInMail\b", self._page_text()): return "LinkedIn offers only InMail (Premium): you're not connected."
            if self.save_page: self.save_page(f"message-box-missing-{datetime.now():%Y%m%d-%H%M%S}.html")
            return "The message box didn't open."
        return ""


    def _thread(self) -> dict:
        try: return self.driver.execute_script(_THREAD_JS) or {}
        except Exception: return {}


    def _close_conversation(self) -> None:
        close = self._visible("//button[contains(@aria-label,'Close your conversation') or contains(@class,'msg-overlay-bubble-header__control--close') "
                              "or (contains(@class,'msg-overlay') and contains(@aria-label,'Close'))]")
        if close is not None: self._click(close)


    def _type(self, box, text: str) -> None:
        box.click()
        lines = text.replace("\r", "").split("\n")
        for number, line in enumerate(lines):
            if line: box.send_keys(line)
            if number < len(lines) - 1: box.send_keys(Keys.SHIFT, Keys.ENTER)   # Plain Enter may send the message


    def send_message(self, item: dict) -> str:
        '''Sends one approved message. Returns "sent", "replied" (follow-up cancelled: they answered), or "failed".'''
        url = item["to_address"]
        problem = self._open_conversation(url)
        if problem: return self._message_done(item, "failed", problem)
        thread = self._thread()
        if thread.get("theirs"):   # They wrote to you: never send a follow-up (or a first message) on top
            self._close_conversation()
            return self._message_done(item, "replied", "They replied: your turn.")
        box = self._visible(_BOX)
        self._type(box, item["body"])
        self._wait(1)
        send = self._visible(_SEND)
        if send is None:
            self._close_conversation()
            return self._message_done(item, "failed", "Couldn't find the Send button.")
        self._click(send)
        self._wait(2.5)
        after = self._thread()
        start = re.sub(r'\s+', ' ', item["body"])[:25]
        box_after = self._visible(_BOX)
        delivered = any(start in re.sub(r'\s+', ' ', text) for text in after.get("texts", [])) or (box_after is not None and not (box_after.text or "").strip())
        self._close_conversation()
        if not delivered: return self._message_done(item, "failed", "The message didn't show in the conversation after Send.")
        return self._message_done(item, "sent", "Follow-up sent." if item["role_key"] == "follow_up" else "Message sent.")


    def _message_done(self, item: dict, result: str, detail: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = item["to_address"]
        if result == "sent":
            db.update_outbox(item["id"], status="sent", sent_at=now, error="")
            person = db.person(url) or {}
            follow_ups = (person.get("follow_ups") or 0) + (1 if item["role_key"] == "follow_up" else 0)
            db.update_person(url, status="messaged", last_message_at=now, follow_ups=follow_ups, detail=detail)
            self.counts["follow_ups_sent" if item["role_key"] == "follow_up" else "messages_sent"] += 1
        elif result == "replied":
            db.update_outbox(item["id"], status="skipped", error=detail)
            db.update_person(url, status="replied", detail=detail)
            self.counts["replied"] += 1
        else:
            db.update_outbox(item["id"], status="failed", error=detail)
            db.update_person(url, detail=detail)
            self.counts["messages_failed"] += 1
        print_lg(f'   {item.get("to_name") or url}: {detail}')
        return result


    def send_messages(self) -> None:
        o = _outreach()
        with db.session() as connection:
            queue = [dict(row) for row in connection.execute('''SELECT o.* FROM outbox o LEFT JOIN people p ON p.profile_url = o.to_address
                                                                WHERE o.kind = 'message' AND o.status = 'approved' ORDER BY o.role_key = 'follow_up', COALESCE(p.priority, 9), o.created_at''')]
        if not queue: return
        print_lg(f"\n>>>> Messages: {len(queue)} approved <<<<")
        for number, item in enumerate(queue):
            if self.control is not None and self.control.stop_requested: break
            limits = message_limits()
            if limits["left"] <= 0:
                self.message_stop = limits["reason"]
                print_lg(f"Messages stopped: {limits['reason']}")
                break
            if self.control is not None: self.control.status(f"Networking: message to {item.get('to_name') or item['to_address']} ({number + 1}/{len(queue)})")
            try: result = self.send_message(item)
            except Exception as e:
                if type(e).__name__ in ("QuitBot", "SkipJob"): raise
                result = self._message_done(item, "failed", f"Error: {str(e).splitlines()[0][:150] if str(e) else type(e).__name__}")
            if result == "sent" and number < len(queue) - 1:
                low, high = (list(o.invite_gap_seconds) + [40, 120])[:2]
                self._wait(random.uniform(float(low), float(high)))


    def run(self) -> dict:
        try: self.check_new_connections()
        except Exception as e:
            if type(e).__name__ in ("QuitBot",): raise
            print_lg("Couldn't check new connections:", str(e).splitlines()[0][:150] if str(e) else type(e).__name__)
        try:   # More people: recruiters and alumni at companies you applied to (each company once, a few searches per run)
            from modules.people_search import PeopleSearch
            added = PeopleSearch(self.driver, self._wait, self._checkpoint, lambda text: self.control.status(text) if self.control else None).run()
            if added: print_lg(f"People search: {added} new people to connect with.")
        except Exception as e:
            if type(e).__name__ in ("QuitBot",): raise
            print_lg("People search stopped:", str(e).splitlines()[0][:150] if str(e) else type(e).__name__)
        draft_messages()
        self.send_messages()
        waiting = len(db.outbox("draft", "message"))
        if waiting: print_lg(f"{waiting} message(s) wait for you in the dashboard (Review).")
        super().run()   # Connection requests: drafts new ones, sends the approved ones
        return self.counts
#>
