'''
Connection requests: to people who posted jobs you applied to, and to people whose job posts said "DM me".

1. `draft_invites()`  - finds new people, writes a short work note for the most valuable ones while this month's notes last
                        (free LinkedIn accounts get only a few), and puts each request in the Review Queue (outbox, kind "invite").
                        With review turned off they're approved straight away.
2. `Connector.run()`  - in the bot's browser: sends the approved requests, within your daily / weekly limits and active hours,
                        with a random wait between two. Stops at once if LinkedIn warns about the invitation limit.
Everyone is in the `people` table once, so nobody is contacted twice.

Run `python -m modules.connections draft` to only prepare requests (the dashboard's "Find people" button).
'''

import re
import sys
import json
import random
from datetime import datetime, timedelta

from modules import db
from modules.helpers import print_lg
from modules.feed_jobs import post_url

NOTE_LIMIT_FREE, NOTE_LIMIT_PREMIUM = 200, 300   # Characters LinkedIn allows in an invitation note
PRIORITY = {"hirer": 1, "feed": 2, "alumni": 2, "recruiter": 3}


#< Limits
def _outreach():
    from config import outreach
    return outreach


def invite_limits() -> dict:
    '''How many invitations may still go out now, and why not if none.'''
    o = _outreach()
    now = datetime.now()
    today = db.invites_sent_since(now.strftime("%Y-%m-%d"))
    week = db.invites_sent_since((now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"))
    start, end = (list(o.active_hours) + [9, 21])[:2]
    left = max(0, min(int(o.max_invites_per_day) - today, int(o.max_invites_per_week) - week))
    reason = ""
    if not (int(start) <= now.hour < int(end)): reason, left = f"Outside your active hours ({start}:00-{end}:00).", 0
    elif int(o.max_invites_per_day) - today <= 0: reason = f"Today's limit of {o.max_invites_per_day} invitations is reached."
    elif int(o.max_invites_per_week) - week <= 0: reason = f"This week's limit of {o.max_invites_per_week} invitations is reached."
    return {"left": left, "today": today, "week": week, "reason": reason}


def notes_left_this_month() -> int:
    o = _outreach()
    used = db.invites_sent_since(datetime.now().strftime("%Y-%m-01"), with_note=True)
    with db.session() as connection:   # Approved notes not sent yet will use the allowance too
        waiting = connection.execute("SELECT COUNT(*) FROM outbox WHERE kind = 'invite' AND status IN ('draft', 'approved') AND body != ''").fetchone()[0]
    return max(0, int(o.monthly_note_limit) - used - waiting)
#>


#< Who and what
def first_name(name: str) -> str:
    parts = [part for part in re.split(r'\s+', (name or "").strip()) if part]
    if not parts: return ""
    first = parts[0].strip(".,")
    if len(first) <= 2 and len(parts) > 1: first = parts[1]   # "D Nayak" -> "Nayak"
    return first[:1].upper() + first[1:] if first.islower() else first


def candidates() -> list[dict]:
    '''New people to invite, best first: hirers of jobs you applied to (most recent job each), then feed leads.'''
    o = _outreach()
    found: dict[str, dict] = {}
    with db.session() as connection:
        if o.connect_with_hirers:
            since = (datetime.now() - timedelta(days=int(o.hirer_days))).strftime("%Y-%m-%d")
            for row in connection.execute('''SELECT hr_name, hr_link, title, company, job_link, applied_at FROM applications
                                             WHERE status = 'applied' AND hr_link LIKE '%/in/%' AND applied_at >= ? ORDER BY applied_at DESC''', (since,)):
                key = db.profile_key(row["hr_link"])
                if key not in found:
                    found[key] = {"profile_url": key, "name": (row["hr_name"] or "").strip(), "company": row["company"] or "", "role": row["title"] or "",
                                  "job_link": row["job_link"] or "", "source": "hirer"}
        if o.connect_with_feed_leads:
            for row in connection.execute("SELECT author, author_url, author_headline, role, urn FROM feed_posts WHERE action = 'lead' AND author_url LIKE '%/in/%' ORDER BY seen_at DESC"):
                key = db.profile_key(row["author_url"])
                if key not in found:
                    found[key] = {"profile_url": key, "name": row["author"] or "", "headline": row["author_headline"] or "", "company": "",
                                  "role": row["role"] or "", "job_link": post_url(row["urn"], row["author_url"]), "source": "feed"}
        known = {row[0] for row in connection.execute("SELECT profile_url FROM people")}
    return sorted((person for key, person in found.items() if key not in known), key=lambda p: PRIORITY.get(p["source"], 9))


def _me() -> tuple[str, str]:
    from config import personals, questions
    o = _outreach()
    return personals.first_name, (o.pitch or questions.linkedin_headline or "").strip()


def fit(text: str, limit: int) -> str:
    '''Shortens a note to LinkedIn's limit at a sentence or word end.'''
    text = re.sub(r'\s+', ' ', (text or "").strip().strip('"')).strip()
    if len(text) <= limit: return text
    cut = text[:limit]
    sentence = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if sentence > limit * 0.6: return cut[:sentence + 1]
    return cut[:cut.rfind(" ")].rstrip(",;:-") + "…" if " " in cut else cut[:limit - 1] + "…"


def template_note(person: dict, limit: int) -> str:
    me, _ = _me()
    hello = f"Hi {first_name(person['name'])}," if first_name(person["name"]) else "Hi,"
    role, company = person.get("role") or "the open role", person.get("company")
    at = f" at {company}" if company else ""
    from config import outreach
    if person["source"] == "hirer":
        text = f"{hello} I recently applied for the {role} role{at} and would love to connect and learn more about the team. Thanks! {me}"
    elif person["source"] == "recruiter":
        text = f"{hello} I recently applied for the {role} role{at} and would love to connect and hear about openings on your team. Thanks! {me}"
    elif person["source"] == "alumni":
        text = f"{hello} fellow {outreach.college} alum here! I applied for the {role} role{at} and would love to connect and hear about your experience there. {me}"
    else:
        text = f"{hello} I saw your post about the {role} opening and I'm very interested. I'd love to connect and share my profile. Thanks! {me}"
    return fit(text, limit)


def ai_note(person: dict, limit: int) -> str | None:
    from modules.ai.simple import write
    o = _outreach()
    me, pitch = _me()
    why = why_text(person)
    prompt = (f"Write a LinkedIn connection request note from a job candidate to {person['name'] or 'a recruiter'}"
              f"{' (' + person['headline'] + ')' if person.get('headline') else ''}.\n{why}\nAbout the candidate: {pitch}\n\n"
              f"Rules: at most {limit - 20} characters. Tone: {o.message_tone}. Start with '{'Hi ' + first_name(person['name']) + ',' if first_name(person['name']) else 'Hi,'}'. "
              "Mention the role, and one specific skill "
              f"of the candidate that fits it. End with a light ask to connect and sign with the candidate's first name ({me}). "
              "No emojis, no hashtags, no placeholders like [Name], no quotes, don't invent facts. Reply with the note only.")
    note = write(prompt, max_tokens=200)
    if not note or "[" in note: return None
    return fit(note, limit)


def why_text(person: dict) -> str:
    '''One sentence for the AI: how the candidate and this person are connected.'''
    at = f" at {person['company']}" if person.get("company") else ""
    source = person.get("source")
    if source == "hirer": return f"The candidate applied for the {person.get('role')} job{at} that this person posted."
    if source == "recruiter": return f"This person is a recruiter{at}, where the candidate recently applied for the {person.get('role')} role."
    if source == "alumni":
        from config import outreach
        return f"This person studied at {outreach.college}, like the candidate, and works{at}, where the candidate applied for the {person.get('role')} role."
    return f"This person posted that they are hiring for {person.get('role')} and asked people to reach out."


def draft_invites(max_new: int = 40) -> dict:
    '''Finds new people and queues their invitations. Returns counts.'''
    o = _outreach()
    limit = NOTE_LIMIT_PREMIUM if o.has_premium else NOTE_LIMIT_FREE
    notes_left = notes_left_this_month()
    status = "draft" if o.review_before_send else "approved"
    counts = {"found": 0, "with_note": 0, "without_note": 0}
    found_by_search = [dict(p, from_search=True) for p in db.people("new")]   # Recruiters / alumni found by modules/people_search.py
    people = sorted(candidates() + found_by_search, key=lambda p: PRIORITY.get(p["source"], 9))
    for person in people[:max_new]:
        note = ""
        if notes_left > 0:
            note = ai_note(person, limit) or template_note(person, limit)
            notes_left -= 1
        person_status = "invite_drafted" if status == "draft" else "invite_approved"
        if person.get("from_search"): db.update_person(person["profile_url"], status=person_status)
        elif not db.add_person(person["profile_url"], name=person["name"], headline=person.get("headline", ""), company=person.get("company", ""),
                               role=person.get("role", ""), job_link=person.get("job_link", ""), source=person["source"], priority=PRIORITY.get(person["source"], 9),
                               status=person_status):
            continue
        db.queue_message("invite", person["profile_url"], to_name=person["name"], subject=person.get("role", ""), body=note,
                         role_key="", source=person["source"], status=status)
        counts["found"] += 1
        counts["with_note" if note else "without_note"] += 1
    print_lg(f"Connection requests prepared: {counts['found']} ({counts['with_note']} with a note, {counts['without_note']} without).")
    return counts
#>


#< The LinkedIn part
_TOP = "(//*[@data-aap-top])[1]"
LIMIT_WARNING = re.compile(r"weekly invitation limit|reached the (weekly )?limit for (connection )?invitations|you.ve reached the weekly|too many invitations|invitation limit", re.I)
NOTE_UPSELL = re.compile(r"personali[sz]ed invitations|premium to send|try premium|out of personalized|used all .* invitations|unlimited personalized", re.I)

# The profile's top card: LinkedIn's 2026 layout has scrambled class names and the name in an <h2>. The card is found from the
# heading that matches the page title (the person's name), walking up to the box with the action buttons. It's marked data-aap-top,
# and every button is then looked for inside it (`_TOP`).
_MARK_TOP_JS = r'''
document.querySelectorAll('[data-aap-top]').forEach(e => e.removeAttribute('data-aap-top'));
const name = (document.title.split('|')[0] || '').replace(/^\(\d+\+?\)\s*/, '').trim();
const main = document.querySelector('main') || document.body;
const heading = [...main.querySelectorAll('h1, h2')].find(h => (h.innerText || '').trim() === name) || main.querySelector('h1');
if (!heading) return null;
let box = heading;
for (let i = 0; i < 15 && box; i++, box = box.parentElement) {
  const labels = [...box.querySelectorAll('button, a')].map(b => ((b.innerText || '').trim() || b.getAttribute('aria-label') || '').trim());
  if (labels.some(t => /^(message|connect|follow|pending|more)$/i.test(t) || /to connect|^pending/i.test(t))) { box.setAttribute('data-aap-top', '1'); return box; }
}
return null;
'''

_TOP_CARD_JS = _MARK_TOP_JS.replace("return box; }", "break; }").rsplit("return null;", 1)[0] + r'''
const card = document.querySelector('[data-aap-top]') || main;
const text = (card.innerText || '').replace(/\s+/g, ' ');
const lines = (card.innerText || '').split('\n').map(t => t.trim()).filter(Boolean);
const headlineLine = lines.find(t => t !== name && !/^[\u00b7•\s]*(1st|2nd|3rd\+?)$/.test(t) && !/^(contact info|follow|message|connect|more|pending)$/i.test(t) && t.length > 3);
const headline = {innerText: headlineLine || ''};
const h1 = heading;
// "1st" is its own small label (texts next to each other run together, Eg: "1stMessage"), or a screen-reader "1st degree connection"
const firstDegree = /1st degree connection/i.test(card.textContent) ||
  [...card.querySelectorAll('span, div, p')].some(e => e.children.length === 0 && /^[·•\s]*1st$/.test((e.textContent || '').trim()));
return {name: h1 ? h1.innerText.trim() : '', headline: headline ? headline.innerText.trim() : '', first_degree: firstDegree,
        pending: [...card.querySelectorAll('button, a')].some(b => /^pending\b/i.test((b.innerText || '').trim()) || /^pending/i.test(b.getAttribute('aria-label') || ''))};
'''


class Connector:
    def __init__(self, driver, control=None, save_page=None):
        self.driver, self.control, self.save_page = driver, control, save_page
        self.counts = {"sent": 0, "with_note": 0, "already": 0, "failed": 0}
        self.stop_reason = ""


    def _checkpoint(self) -> None:
        if self.control is not None: self.control.checkpoint()


    def _wait(self, seconds: float) -> None:
        if self.control is not None: self.control.wait(seconds)
        else:
            from time import sleep
            sleep(seconds)


    def _visible(self, xpath: str, root=None):
        for element in (root or self.driver).find_elements("xpath", xpath):
            try:
                if element.is_displayed() and element.is_enabled(): return element
            except Exception: pass
        return None


    def _click(self, element) -> None:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)


    def _page_text(self) -> str:
        try: return self.driver.execute_script("return document.body.innerText") or ""
        except Exception: return ""


    def _dialog(self):
        return self._visible("//div[@role='dialog' or @role='alertdialog'] | //*[contains(@class,'artdeco-modal')][@role='dialog' or @aria-modal='true']")


    def _open_connect(self) -> bool:
        '''Clicks Connect on the profile: the main button, the new "custom invite" link, or More -> Connect.'''
        try: self.driver.execute_script(_MARK_TOP_JS)
        except Exception: pass
        top = _TOP
        connect = (self._visible(f"{top}//*[(self::button or self::a)][contains(@aria-label,'to connect') or normalize-space(.)='Connect']")
                   or self._visible(f"{top}//a[contains(@href,'/preload/custom-invite/')]"))
        if connect is None:
            more = self._visible(f"{top}//button[contains(@aria-label,'More actions') or normalize-space(.)='More']")
            if more is None: return False
            self._click(more)
            self._wait(1)
            connect = self._visible("//*[contains(@class,'artdeco-dropdown__content') or @role='menu' or @role='listbox' or @role='dialog']"
                                    "//*[(@role='button' or @role='menuitem' or self::div or self::span or self::a or self::button)]"
                                    "[contains(@aria-label,'to connect') or normalize-space(.)='Connect']")
            if connect is None:
                try: self.driver.find_element("tag name", "body").send_keys("")   # Escape: close the menu
                except Exception: pass
                return False
        self._click(connect)
        self._wait(2)
        return True


    def _send_from_dialog(self, note: str) -> tuple[bool, bool, str]:
        '''In the invitation dialog (or the custom-invite page): adds the note if possible and sends. Returns (sent, with_note, problem).'''
        root = self._dialog()
        if root is not None and root.find_elements("xpath", ".//input[@type='email']"):
            self._close_dialog()
            return False, False, "LinkedIn asks for their email address to connect."
        with_note = False
        if note:
            add = self._visible(".//button[contains(@aria-label,'Add a note') or normalize-space(.)='Add a note']", root)
            if add is not None:
                self._click(add)
                self._wait(1.5)
            box = self._visible("//div[@role='dialog']//textarea | //textarea[@name='message' or @id='custom-message']")
            if box is not None:
                box.clear()
                box.send_keys(note)
                with_note = True
            elif NOTE_UPSELL.search(self._page_text()):
                print_lg("   LinkedIn won't take more notes this month (Premium only): sending without a note")
                self._close_dialog()
                if not self._open_connect(): return False, False, "Couldn't open Connect again after the note was refused."
        root = self._dialog()
        send = (self._visible(".//button[contains(@aria-label,'Send invitation') or contains(@aria-label,'Send now') or normalize-space(.)='Send']", root) if with_note
                else self._visible(".//button[contains(@aria-label,'Send without a note') or normalize-space(.)='Send without a note' or normalize-space(.)='Send']", root))
        if send is None:
            send = self._visible("//button[contains(@aria-label,'Send invitation') or contains(@aria-label,'Send without a note') or normalize-space(.)='Send' or normalize-space(.)='Send without a note']")
        if send is None: return False, False, "Couldn't find the Send button."
        self._click(send)
        self._wait(2.5)
        if LIMIT_WARNING.search(self._page_text()):
            self._close_dialog()
            return False, False, "limit"
        return True, with_note, ""


    def _close_dialog(self) -> None:
        close = self._visible("//div[@role='dialog']//button[contains(@aria-label,'Dismiss') or contains(@aria-label,'Close') or normalize-space(.)='Cancel']")
        if close is not None: self._click(close)
        self._wait(1)


    def invite(self, item: dict) -> str:
        '''Sends one invitation. Returns "sent", "already" (pending / connected), "failed" or "limit".'''
        url = item["to_address"]
        self.driver.get(url)
        self._wait(4)
        self._checkpoint()
        if "/in/" not in self.driver.current_url or "unavailable" in self.driver.current_url:
            return self._done(item, "failed", "Profile not available.")
        try: card = self.driver.execute_script(_TOP_CARD_JS) or {}
        except Exception: card = {}
        if card.get("name") and not item.get("to_name"): db.update_person(url, name=card["name"])
        if card.get("headline"): db.update_person(url, headline=card["headline"][:200])
        if card.get("first_degree"): return self._done(item, "already", "Already connected.", person_status="connected")
        if card.get("pending"): return self._done(item, "already", "Invitation already pending.", person_status="invited")
        if not self._open_connect():
            if self.save_page: self.save_page(f"connect-no-button-{datetime.now():%Y%m%d-%H%M%S}.html")
            return self._done(item, "failed", "No Connect button on this profile (they may only allow Follow).")
        sent, with_note, problem = self._send_from_dialog(item.get("body") or "")
        if problem == "limit":
            self.stop_reason = "LinkedIn says the invitation limit is reached. Stopped for now: try again in a few days."
            db.update_outbox(item["id"], error="LinkedIn invitation limit reached; will retry.")
            return "limit"
        if not sent: return self._done(item, "failed", problem)
        if not with_note and item.get("body"): db.update_outbox(item["id"], body="")   # Sent without the note: keep the month's note count right
        if with_note: self.counts["with_note"] += 1
        return self._done(item, "sent", "Invitation sent" + (" with a note." if with_note else "."))


    def _done(self, item: dict, result: str, detail: str, person_status: str | None = None) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if result == "sent":
            db.update_outbox(item["id"], status="sent", sent_at=now, error="")
            db.update_person(item["to_address"], status="invited", invited_at=now, detail=detail)
        elif result == "already":
            db.update_outbox(item["id"], status="skipped", error=detail)
            db.update_person(item["to_address"], status=person_status or "invited", detail=detail, **({"connected_at": now} if person_status == "connected" else {}))
        else:
            db.update_outbox(item["id"], status="failed", error=detail)
            db.update_person(item["to_address"], status="failed", detail=detail)
        self.counts[result] = self.counts.get(result, 0) + 1
        print_lg(f'   {item.get("to_name") or item["to_address"]}: {detail}')
        return result


    def run(self) -> dict:
        '''Prepares new requests, then sends the approved ones within your limits.'''
        o = _outreach()
        draft_invites()
        with db.session() as connection:
            queue = [dict(row) for row in connection.execute('''SELECT o.* FROM outbox o LEFT JOIN people p ON p.profile_url = o.to_address
                                                                WHERE o.kind = 'invite' AND o.status = 'approved' ORDER BY COALESCE(p.priority, 9), o.created_at''')]
        waiting = len(db.outbox("draft", "invite"))
        if not queue:
            print_lg("No approved connection requests to send." + (f" {waiting} wait for you in the dashboard (Review)." if waiting else ""))
            return self.counts
        print_lg(f"\n>>>> Connection requests: {len(queue)} approved <<<<")
        for number, item in enumerate(queue):
            if self.control is not None and self.control.stop_requested: break
            limits = invite_limits()
            if limits["left"] <= 0:
                self.stop_reason = limits["reason"]
                print_lg(f"Stopped: {limits['reason']}")
                break
            if self.control is not None: self.control.status(f"Connection requests: {item.get('to_name') or item['to_address']} ({number + 1}/{len(queue)})")
            try: result = self.invite(item)
            except Exception as e:
                if type(e).__name__ in ("QuitBot", "SkipJob"): raise
                result = self._done(item, "failed", f"Error: {str(e).splitlines()[0][:150] if str(e) else type(e).__name__}")
            if result == "limit":
                print_lg(self.stop_reason)
                break
            if result == "sent" and number < len(queue) - 1:
                low, high = (list(o.invite_gap_seconds) + [40, 120])[:2]
                self._wait(random.uniform(float(low), float(high)))
        return self.counts
#>


if __name__ == "__main__" and sys.argv[1:] == ["draft"]:
    from modules.messages import draft_messages   # Messages for people already connected, and follow-ups
    result = draft_invites()
    result["messages"] = draft_messages()
    print(json.dumps(result), flush=True)
