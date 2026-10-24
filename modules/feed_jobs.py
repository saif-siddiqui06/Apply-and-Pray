'''
Feed jobs: finds jobs posted as LinkedIn posts and applies to them.

For each of your job titles, searches LinkedIn posts ("<title> hiring", recent first), reads each new post and decides:
* "link"  - an application form / careers link   -> Normal Apply fills it
* "email" - "send your CV to hr@..."              -> an email with your resume (Review Queue first, unless you turned review off)
* "lead"  - "DM me" / "comment interested"        -> the author is saved for Networking
* "skip"  - not a job post, too senior, bad word... (the reason is saved)
Every post is recorded once (feed_posts table), so it's never handled twice.

`read_post()` holds all the rules and needs no browser, `FeedJobs` does the LinkedIn part.
'''

import re
import json
import html
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Callable

from modules import db
from modules.helpers import print_lg

#< Rules: what a post says
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}')
HIRING_RE = re.compile(r'\b(hiring|we are looking|we\'re looking|looking for (an? )?(talented|passionate|skilled|motivated|experienced)?|opening|openings|vacanc|job opportunit|'
                       r'join our team|join us|position|positions|role|roles|internship|interns?\b|recruiting|apply|freshers?)\b', re.I)
JOB_SEEKER_RE = re.compile(r'#opentowork|\bopen to work\b|\bi am (actively )?(looking|seeking) for\b|\bi\'m (actively )?(looking|seeking)\b|\bseeking (new )?opportunit|'
                           r'\bmy (job )?search\b|\bplease help me (find|get)\b|\blooking for (a )?(job|opportunit|referral)', re.I)
# "DM me", "DM us your profile", "send your resume via DM", "comment “Interested”", "comment #Interested below", "Comment PYTHON"...
LEAD_RE = re.compile(r'\bDMs?\b|\b(direct message|message me|message us|inbox (me|us)|in (my|our) inbox|reach out to (me|us)|ping me|connect with me|drop (a |your )?(comment|cv|resume))\b'
                     r'|\bcomment\b[^.\n]{0,30}?(interested|below|your|#|["“\'”]|\b[A-Z]{3,}\b)')
ROLE_LINE_RE = re.compile(r'\b(?:job\s*)?(?:position|role|job title|designation|opening|profile|hiring)\s*(?:name)?\s*[:\-–—|]\s*(.{3,80})$', re.I | re.M)
ROLE_PHRASE_RE = re.compile(r'\b(?:hiring\s+for|looking\s+for|opening\s+for|vacancy\s+for|hiring)\s*(?:an?\s+|the\s+|a\s+few\s+|multiple\s+|\d+\s+)?'
                            r'([A-Za-z][A-Za-z0-9/&+#.\- ]{2,60}?)(?=\s*(?:\(|-|–|—|!|\.|,|:|\||\n|$|\bat\b|\bin\b|\bwith\b|\bfor\b|\bto\b|\bwho\b))', re.I)
FORM_HOSTS = ("forms.gle", "docs.google.com/forms", "forms.office.com", "form.jotform", "typeform.com", "tally.so", "airtable.com", "zfrmz.", "forms.zohopublic")
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "workday.com", "smartrecruiters.com", "workable.com", "icims.com", "taleo.net",
             "bamboohr.com", "jobvite.com", "recruitee.com", "keka.com", "darwinbox", "zohorecruit", "freshteam.com", "naukri.com", "instahyre.com",
             "wellfound.com", "cutshort.io", "internshala.com", "hirist", "iimjobs", "unstop.com", "breezy.hr", "teamtailor.com", "personio",
             "ripplehire.com", "turbohire", "zwayam", "skillate", "peoplestrong", "superset", "hackerearth", "mettl", "jobsforher", "foundit.in")
NOT_APPLY_HOSTS = ("linkedin.com", "licdn.com", "youtube.com", "youtu.be", "instagram.com", "facebook.com", "twitter.com", "x.com", "t.me", "wa.me",
                   "whatsapp.com", "medium.com", "bit.ly/subscribe", "spotify.com", "github.com", "calendly.com")
APPLY_PATH_RE = re.compile(r'apply|career|job|form|vacanc|opening|recruit|hiring|position|talent', re.I)
FAKE_EMAILS = ("example.com", "domain.com", "email.com", "noreply", "no-reply", "sentry", "wixpress")


def plain(text: str) -> str:
    '''Fancy letters some posts use ("𝐇𝐈𝐑𝐈𝐍𝐆", "𝘗𝘺𝘵𝘩𝘰𝘯") as normal ones, so the rules can read them.'''
    return unicodedata.normalize("NFKC", text or "")


def emails_in(text: str) -> list[str]:
    text = plain(text)
    found = []
    for email in EMAIL_RE.findall(text or ""):
        email = email.strip(".").lower()
        if any(fake in email for fake in FAKE_EMAILS) or email in found: continue
        if re.search(r'\.(png|jpe?g|gif|svg|webp)$', email): continue
        found.append(email)
    return found


def link_score(url: str) -> int:
    '''How likely a link is the application: 3 a form, 2 a hiring website, 1 a careers / apply page, 0 not an application.'''
    lower = (url or "").lower()
    host = urllib.parse.urlparse(lower).netloc
    if not host or any(bad in lower for bad in NOT_APPLY_HOSTS if "/" in bad) or any(host == bad or host.endswith("." + bad) for bad in NOT_APPLY_HOSTS): return 0
    if any(form in lower for form in FORM_HOSTS): return 3
    if any(ats in host for ats in ATS_HOSTS): return 2
    return 1 if APPLY_PATH_RE.search(urllib.parse.urlparse(lower).path + "?" + urllib.parse.urlparse(lower).query) else 0


def role_of(text: str, fallback: str) -> str:
    '''The job title the post is about, else `fallback` (the title it was found with).'''
    text = plain(text)
    # "AI Engineer (Fresher)!" -> "AI Engineer", "Data Analyst. Apply at..." -> "Data Analyst"
    tidy = lambda role: re.sub(r'\s*\([^)]*\)\s*$', '', re.sub(r'[\s|•*#!]+$', '', re.split(r'[.!|•]\s|\s[-–—]\s', role)[0])).strip(" -–:.!")
    for match in ROLE_LINE_RE.finditer(text or ""):
        role = tidy(match.group(1))
        if role.isupper(): role = role.title()   # "PYTHON DEVELOPER" -> "Python Developer"
        if 2 < len(role) <= 70 and not EMAIL_RE.search(role) and "http" not in role and not re.search(r'(?i)^(now|alert|update|drive)$|immediate|joiners?|required|urgent|opportunit|walk-?in', role): return role
    for match in ROLE_PHRASE_RE.finditer(text or ""):
        role = tidy(match.group(1))
        words = role.lower().split()
        if words and words[0] not in ("you", "your", "someone", "people", "candidates", "talent", "talented", "passionate", "the", "our", "a", "an", "folks") and len(words) <= 7:
            return role.title() if role.islower() else role
    return fallback


def read_post(text: str, links: list[str], found_with: str, *, current_experience: int = -1, experience_of: Callable[[str], int] | None = None,
              bad_words: list[str] = (), skip_title_words: list[str] = (), extra_years: int = 0) -> dict:
    '''
    Decides what to do with a post. Returns {"kind": "link" | "email" | "lead" | "skip", "reason", "role", "links", "emails"}.
    `links` should already be resolved to their real address (see `resolve_link`).
    '''
    text = plain(text)
    role = role_of(text, found_with)
    decision = {"kind": "skip", "reason": "", "role": role, "links": [], "emails": emails_in(text)}
    lower = text.lower()
    if len(text.strip()) < 40: return dict(decision, reason="Post text too short to tell.")
    if JOB_SEEKER_RE.search(text) and not re.search(r'\bwe (are|\'re) hiring\b|\bwe have (an )?opening', lower): return dict(decision, reason="Someone looking for a job, not hiring.")
    if not HIRING_RE.search(text): return dict(decision, reason="Not a job post.")
    for word in bad_words:
        if word and word.lower() in lower: return dict(decision, reason=f'Has the bad word "{word}".')
    for word in skip_title_words:
        if word and re.search(r'\b' + re.escape(word.lower()) + r'\b', role.lower()): return dict(decision, reason=f'Senior role ("{word}" in "{role}").')
    if experience_of and current_experience > -1:
        years = experience_of(text)
        if years > current_experience + extra_years: return dict(decision, reason=f"Asks for {years} years of experience.")

    apply_links = sorted({link for link in links if link_score(link) > 0}, key=link_score, reverse=True)
    decision["links"] = apply_links
    if apply_links: return dict(decision, kind="link", reason=f"Application link: {apply_links[0]}")
    if decision["emails"]: return dict(decision, kind="email", reason=f"Apply by email: {decision['emails'][0]}")
    if LEAD_RE.search(text): return dict(decision, kind="lead", reason="Asks to message / comment: saved for Networking.")
    return dict(decision, reason="No way to apply in the post (no link, email or 'DM me').")


def resolve_link(url: str, timeout: float = 10) -> str:
    '''LinkedIn wraps links in posts (lnkd.in, /redir/redirect): returns the real address, or `url` if it can't tell.'''
    try:
        parsed = urllib.parse.urlparse(url)
        if "linkedin.com" in parsed.netloc and ("/redir/" in parsed.path or "/safety/go" in parsed.path):   # LinkedIn's "you're leaving" wrappers
            target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
            return resolve_link(target, timeout) if target else url
        if parsed.netloc.lower() not in ("lnkd.in", "www.lnkd.in"): return url
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final = response.geturl()
            if "lnkd.in" not in final and "linkedin.com" not in final: return final
            page = response.read(200000).decode("utf-8", errors="replace")
        # The "You're leaving LinkedIn" page: the real address is its external link
        found = re.search(r'<a[^>]+data-tracking-control-name="external_url_click"[^>]*>', page)
        href = re.search(r'href="([^"]+)"', found.group(0)) if found else None
        if href: return html.unescape(href.group(1))
        for candidate in re.findall(r'href="(https?://[^"]+)"', page):
            candidate = html.unescape(candidate)
            if not re.search(r'linkedin\.com|licdn\.com|lnkd\.in', candidate): return candidate
    except Exception as e:
        print_lg(f"Couldn't open the short link {url}:", str(e)[:120])
    return url
#>


#< Email applications
def email_role_key(role: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (role or "").lower()).strip()


def post_url(urn: str, author_url: str = "") -> str:
    '''Link to a post: its own page when LinkedIn showed its id, else the author's recent posts.'''
    if (urn or "").startswith("urn:li:"): return f"https://www.linkedin.com/feed/update/{urn}/"
    return (author_url.rstrip("/") + "/recent-activity/all/") if author_url else "https://www.linkedin.com/feed/"


def send_queued_email(item_id: int, subject: str | None = None, body: str | None = None) -> dict:
    '''
    Sends an email from the Review Queue (you clicked "Approve and send" in the dashboard), with your edits.
    Keeps the daily limit, and records the application. Returns {"ok": bool, "detail": str}.
    '''
    from modules import gmail
    from modules.user_settings import load_section
    item = db.outbox_item(item_id)
    if not item or item["kind"] != "email": return {"ok": False, "detail": "Not found."}
    if item["status"] == "sent": return {"ok": True, "detail": "Already sent."}
    subject = (subject if subject is not None else item["subject"]).strip()
    body = (body if body is not None else item["body"]).strip()
    if not subject or len(body) < 20: return {"ok": False, "detail": "Write a subject and a message first."}
    limit = int(load_section("gmail").get("max_emails_per_day", 20) or 20)
    if db.sent_today("email") >= limit: return {"ok": False, "detail": f"Today's limit of {limit} emails is reached (Setup → Gmail). It stays here for tomorrow."}
    attachments = [item["attachment"]] if item["attachment"] else []
    db.update_outbox(item_id, subject=subject, body=body)
    try:
        gmail.send_email(item["to_address"], subject, body, attachments)
    except Exception as e:
        db.update_outbox(item_id, error=str(e)[:300])
        return {"ok": False, "detail": str(e)}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.update_outbox(item_id, status="sent", sent_at=now, error="")
    source = item.get("source") or ""
    if source.startswith("feed:"):
        urn = source[5:]
        with db.session() as connection:
            post = connection.execute("SELECT * FROM feed_posts WHERE urn = ?", (urn,)).fetchone()
            connection.execute("UPDATE feed_posts SET action = 'email_sent', detail = ? WHERE urn = ?", (f"Emailed {item['to_address']}.", urn))
        if post:
            db.record_application("feed:" + urn.split(":")[-1], post["role"], post["author"], "email", "applied", job_link=post_url(urn, post["author_url"]),
                                  apply_link="mailto:" + item["to_address"], hr_name=post["author"], hr_link=post["author_url"], applied_at=now, description=post["text"])
    return {"ok": True, "detail": f"Sent to {item['to_address']}."}


def template_email(role: str, author: str, pitch: str, signature: str) -> str:
    first = (author or "").split()[0] if author and not re.search(r'\b(pvt|ltd|inc|llc|technologies|solutions|careers|hr|team)\b', author, re.I) else ""
    greeting = f"Hi {first}," if first else "Hello,"
    about = f"\n\n{pitch.strip()}" if pitch and pitch.strip() else ""
    return (f"{greeting}\n\nI came across your LinkedIn post about the {role} opening and would like to apply.{about}\n\n"
            f"My resume is attached. I'd be glad to share anything else you need or to have a quick call.\n\nThank you for your time,\n{signature}")
#>


#< The LinkedIn part
_READ_POSTS_JS = r'''
// LinkedIn's 2026 layout: no post ids in the page and scrambled class names. Each post is the box around its hidden "Feed post"
// label that also holds the Like button. The older layout (data-urn attributes) is read too.
const clean = t => (t || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
const URN = /urn:li:(activity|ugcPost|share):\d+/;
const boxes = new Set();
for (const label of document.querySelectorAll('h1, h2, h3, span')) {
  if (label.children.length || (label.textContent || '').trim() !== 'Feed post') continue;
  let box = label;
  for (let i = 0; i < 8 && box; i++, box = box.parentElement) {
    if ([...box.querySelectorAll('button')].some(b => /^like$/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()))) { boxes.add(box); break; }
  }
}
for (const el of document.querySelectorAll('[data-urn*="urn:li:"], [data-id*="urn:li:"]')) {
  if (URN.test(el.getAttribute('data-urn') || el.getAttribute('data-id') || '') && ![...boxes].some(b => b.contains(el) || el.contains(b))) boxes.add(el);
}
const outer = [...boxes].filter(el => ![...boxes].some(other => other !== el && other.contains(el)));
// "... more": show the whole text first
for (const el of outer) for (const b of el.querySelectorAll('button')) {
  const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
  if (/(…|\.\.\.)\s*more|see more/.test(t) && !/comment|repl|reaction/.test(t)) { try { b.click(); } catch (e) {} }
}
const END = /^(like|comment|repost|send|reply|\d[\d,.]*\s*(reactions?|comments?|reposts?)|(…|\.\.\.)\s*more|see more|show translation)$/i;
const TIME = /^\d+\s*(s|m|h|d|w|mo|yr)\b|^\d+\s*(second|minute|hour|day|week|month|year)s?\b|^edited$/i;
return outer.map(el => {
  const attr = el.getAttribute('data-urn') || el.getAttribute('data-id') || '';
  const urn = (attr.match(URN) || (el.innerHTML.match(URN) || []))[0] || '';
  const authorLink = [...el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')].find(a => (a.innerText || '').trim());
  const author_url = authorLink ? authorLink.href.split('?')[0] : '';
  const author = authorLink ? clean(authorLink.innerText).split('\n')[0].replace(/\s*[•·].*$/, '').trim() : '';
  const lines = (el.innerText || '').split('\n').map(t => t.trim()).filter(Boolean);
  // Header: "Feed post", name, "• 3rd+", headline, time, Follow. The text starts after the time / Follow / Connect line
  let startAt = 0;
  for (let i = 0; i < Math.min(lines.length, 10); i++) if (TIME.test(lines[i].replace(/\s*[•·].*$/, '')) || /^(follow|connect|\+ follow)$/i.test(lines[i])) startAt = i + 1;
  const headline = lines.slice(1, startAt).find(t => t !== author && t !== 'Feed post' && !/^[•·]?\s*(1st|2nd|3rd\+?)$/.test(t.replace(author, '').trim()) && !TIME.test(t) && !/^(follow|connect)$/i.test(t) && t.length > 3) || '';
  const body = [];
  for (const line of lines.slice(startAt)) { if (END.test(line)) break; body.push(line); }
  const old = el.querySelector('.update-components-text, .feed-shared-update-v2__description, .feed-shared-inline-show-more-text');
  const text = clean(old ? old.innerText : body.join('\n'));
  const links = [...el.querySelectorAll('a[href]')].map(a => a.href).filter(h => /^https?:/.test(h) && !/linkedin\.com\/(in|company|search|feed\/hashtag)\//.test(h));
  return {urn, text, author, author_url, author_headline: clean(headline), links: [...new Set(links)]};
}).filter(p => p.text.length > 0);
'''

DATE_FILTERS = {"past-24h": "past-24h", "past-week": "past-week", "past-month": "past-month"}


class FeedJobs:
    def __init__(self, driver, *, control=None, normal_applier=None, resume_path: str | None = None,
                 ai_write: Callable[[str, str, str], str | None] | None = None, experience_of: Callable[[str], int] | None = None,
                 save_page: Callable[[str], None] | None = None):
        '''
        * `ai_write(instruction, post_text, role) -> text or None`: writes the email (None without AI, then a template is used)
        * `experience_of(text) -> years`: the bot's own "X years of experience" reader
        * `save_page(name)`: keeps the page's HTML in logs when no post could be read (so LinkedIn's new layout can be fixed)
        '''
        from config import feed, search, gmail, personals, questions, outreach
        self.driver, self.control, self.normal_applier = driver, control, normal_applier
        self.resume_path, self.ai_write, self.experience_of, self.save_page = resume_path, ai_write, experience_of, save_page
        self.feed, self.search, self.gmail, self.outreach = feed, search, gmail, outreach
        name = " ".join(part for part in (personals.first_name, personals.last_name) if part)
        contact = [personals.phone_number, getattr(personals, "email", "") or gmail.gmail_address, questions.linkedIn]
        self.signature = (gmail.email_signature or "").strip() or "\n".join(part for part in [name] + contact if part)
        self.pitch = (outreach.pitch or questions.linkedin_headline or "").strip()
        self.name = name
        self.counts = {"posts": 0, "applied": 0, "saved_for_you": 0, "apply_failed": 0, "emails_drafted": 0, "emails_sent": 0, "leads": 0, "skipped": 0}


    def _checkpoint(self) -> None:
        if self.control is not None: self.control.checkpoint()


    def _status(self, text: str) -> None:
        if self.control is not None: self.control.status(text)


    def _stopping(self) -> bool:
        return self.control is not None and self.control.stop_requested


    def run(self, search_terms: list[str]) -> dict:
        from modules.bot_control import SkipJob
        for term in search_terms:
            if self._stopping(): break
            try: self.search_term(term)
            except SkipJob: print_lg("You skipped this; moving to the next job title.")   # QuitBot goes up to the bot's main loop
            except Exception as e:
                print_lg(f'Feed search for "{term}" stopped:', str(e).splitlines()[0][:200] if str(e) else type(e).__name__)
        return self.counts


    def _search_url(self, term: str) -> str:
        query = f"{term} {self.feed.hiring_words}".strip()
        date = DATE_FILTERS.get(self.feed.date_posted, "past-week")
        return ("https://www.linkedin.com/search/results/content/?keywords=" + urllib.parse.quote(query)
                + f"&datePosted=%22{date}%22&sortBy=%22date_posted%22&origin=FACETED_SEARCH")


    def _load_posts(self, wanted: int) -> list[dict]:
        '''Scrolls until `wanted` posts are on the page (or no more load), then reads them.'''
        from time import sleep
        posts, same = [], 0
        for _ in range(12):
            self._checkpoint()
            try: posts = self.driver.execute_script(_READ_POSTS_JS) or []
            except Exception: posts = []
            if len(posts) >= wanted: break
            before = len(posts)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            for button in self.driver.find_elements("xpath", "//button[contains(., 'Show more results') or contains(., 'See more results')]"):
                try: button.click()
                except Exception: pass
            sleep(2.5)
            try: posts = self.driver.execute_script(_READ_POSTS_JS) or []
            except Exception: pass
            same = same + 1 if len(posts) == before else 0
            if same >= 2: break
        sleep(1)   # "see more" clicks need a moment to show the full text
        try: posts = self.driver.execute_script(_READ_POSTS_JS) or posts
        except Exception: pass
        return posts[:wanted]


    @staticmethod
    def _identify(post: dict) -> None:
        '''LinkedIn no longer shows post ids in search results: a post without one gets "post:<fingerprint of author and text>".'''
        if not post.get("urn"):
            import hashlib
            key = (post.get("author_url") or post.get("author") or "") + "|" + re.sub(r'\s+', ' ', post.get("text", ""))[:300]
            post["urn"] = "post:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


    def search_term(self, term: str) -> None:
        from time import sleep
        print_lg(f'\n>>>> Feed jobs: searching posts for "{term}" <<<<')
        self._status(f'Feed jobs: reading posts about "{term}"')
        self.driver.get(self._search_url(term))
        sleep(4)
        posts = self._load_posts(max(1, int(self.feed.max_posts_per_search)))
        if not posts:
            print_lg("No posts could be read on this page.")
            if self.save_page: self.save_page(f"feed-no-posts-{datetime.now():%Y%m%d-%H%M%S}.html")
            return
        for post in posts: self._identify(post)
        new = [post for post in posts if not db.post_seen(post["urn"])]
        print_lg(f"{len(posts)} posts found, {len(new)} new")
        for post in new:
            if self._stopping(): break
            self._checkpoint()
            self.handle_post(post, term)


    def handle_post(self, post: dict, term: str) -> str:
        self.counts["posts"] += 1
        post["links"] = list(dict.fromkeys(resolve_link(link) for link in post.get("links", [])[:8]))
        decision = read_post(post.get("text", ""), post["links"], term, current_experience=self.search.current_experience, experience_of=self.experience_of,
                             bad_words=self.search.bad_words, skip_title_words=self.search.skip_title_words, extra_years=2 if self.search.did_masters else 0)
        post["emails"] = decision["emails"]
        role, kind = decision["role"], decision["kind"]
        author = post.get("author") or "the poster"
        print_lg(f'\n-> Post by {author}: "{role}" -> {decision["reason"]}')

        if kind == "link" and self.feed.apply_to_links and self.normal_applier is not None: return self._apply_link(post, decision, term)
        if kind in ("link", "email") and decision["emails"] and self.feed.email_applications: return self._email(post, decision, term)
        if kind == "link":   # Normal Apply off: keep the link for you
            db.record_apply_by_hand("feed:" + post["urn"], role, author, "Application link in a LinkedIn post", decision["links"][0], self._post_url(post))
            db.record_post(post, "saved_for_you", decision["reason"], role, decision["links"][0], term)
            self.counts["saved_for_you"] += 1
            return "saved_for_you"
        if kind in ("lead", "link", "email") and self.feed.save_leads and post.get("author_url"):
            db.record_post(post, "lead", decision["reason"], role, "", term)
            self.counts["leads"] += 1
            return "lead"
        db.record_post(post, "skipped", decision["reason"], role, "", term)
        self.counts["skipped"] += 1
        return "skipped"


    @staticmethod
    def _post_url(post: dict) -> str:
        return post_url(post.get("urn", ""), post.get("author_url", ""))


    def _company(self, post: dict) -> str:
        if "/company/" in (post.get("author_url") or ""): return post.get("author", "")
        found = re.search(r'\b(?:at|@)\s+([A-Z][\w&.\- ]{1,40})', post.get("author_headline", ""))
        return found.group(1).strip() if found else (post.get("author") or "LinkedIn post")


    def _apply_link(self, post: dict, decision: dict, term: str) -> str:
        link, role, company = decision["links"][0], decision["role"], self._company(post)
        job_id = "feed:" + post["urn"].split(":")[-1]
        self._status(f"Feed jobs: applying to {role} @ {company}")
        outcome = self.normal_applier.apply(link, job_id=job_id, title=role, company=company, description=post.get("text", ""))
        if outcome.status == "submitted":
            db.record_application(job_id, role, company, "feed", "applied", job_link=self._post_url(post), apply_link=outcome.url, hr_name=post.get("author", ""),
                                  hr_link=post.get("author_url", ""), applied_at=datetime.now(), description=post.get("text", ""), questions=outcome.questions or "")
            db.record_post(post, "applied", "Applied through the link.", role, outcome.url, term)
            self.counts["applied"] += 1
            print_lg(f'   APPLIED (feed): "{role} | {company}"')
            return "applied"
        if decision["emails"] and self.feed.email_applications and outcome.status in ("failed", "manual"):
            print_lg(f"   The link didn't work ({outcome.message[:120]}), the post also has an email: writing that instead")
            return self._email(post, decision, term)
        if outcome.status in ("manual", "failed"):
            db.record_apply_by_hand(job_id, role, company, outcome.message or "Couldn't finish the form", outcome.url, self._post_url(post))
            if outcome.status == "failed": db.record_failure(job_id, self._post_url(post), "Feed job: Normal Apply failed", outcome.message, outcome.url, outcome.screenshot)
            db.record_post(post, "apply_failed" if outcome.status == "failed" else "saved_for_you", outcome.message, role, outcome.url, term)
            self.counts["apply_failed" if outcome.status == "failed" else "saved_for_you"] += 1
            return "saved_for_you"
        db.record_post(post, "skipped", outcome.message or "You skipped it.", role, outcome.url, term)
        self.counts["skipped"] += 1
        return "skipped"


    def _write_email(self, post: dict, role: str) -> str:
        body = None
        if self.ai_write:
            instruction = (f"Write the body of a short email applying for the {role} job described in the LinkedIn post below. The email is sent to the person who posted it, "
                           "with the candidate's resume attached. 90 to 150 words, plain text, first person. Greet the poster by first name if the post shows it, else 'Hello'. "
                           "Mention the role and 2-3 of the candidate's skills or projects that match the post. End by saying the resume is attached. "
                           "No subject line, no signature, no placeholders like [Name], and never invent facts about the candidate.")
            try: body = self.ai_write(instruction, f"Posted by: {post.get('author', '')} ({post.get('author_headline', '')})\n\n{post.get('text', '')}", role)
            except Exception as e: print_lg("AI couldn't write the email, using the template:", str(e)[:150])
        if body and len(body.split()) >= 30:
            body = re.sub(r'^\s*subject:.*\n', '', body.strip(), flags=re.I)
            return f"{body.strip()}\n\n{self.signature}"
        return template_email(role, post.get("author", ""), self.pitch, self.signature)


    def _email(self, post: dict, decision: dict, term: str) -> str:
        from modules import gmail as gmail_sender
        to, role = decision["emails"][0], decision["role"]
        subject = f"Application for {role} - {self.name}".strip(" -")
        body = self._write_email(post, role)
        attachment = self.resume_path or ""
        review = bool(self.gmail.review_before_send) or not self.gmail.gmail_address
        item = db.queue_message("email", to, to_name=post.get("author", ""), subject=subject, body=body, attachment=attachment,
                                role_key=email_role_key(role), source="feed:" + post["urn"], status="draft")
        if item is None:
            db.record_post(post, "skipped", f"Already emailed {to} about this role.", role, "", term)
            self.counts["skipped"] += 1
            return "skipped"
        if not review and db.sent_today("email") < int(self.gmail.max_emails_per_day):
            try:
                gmail_sender.send_email(to, subject, body, [attachment] if attachment else [])
                db.update_outbox(item, status="sent", sent_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                job_id = "feed:" + post["urn"].split(":")[-1]
                db.record_application(job_id, role, self._company(post), "email", "applied", job_link=self._post_url(post), apply_link="mailto:" + to,
                                      hr_name=post.get("author", ""), hr_link=post.get("author_url", ""), applied_at=datetime.now(), description=post.get("text", ""))
                db.record_post(post, "email_sent", f"Emailed {to}.", role, "mailto:" + to, term)
                self.counts["emails_sent"] += 1
                print_lg(f'   EMAILED {to}: "{role}"')
                return "email_sent"
            except Exception as e:
                db.update_outbox(item, error=str(e)[:300])
                print_lg(f"   Couldn't send the email ({str(e)[:150]}), it waits in the Review Queue")
        db.record_post(post, "email_drafted", f"Email to {to} waits for you in Review.", role, "mailto:" + to, term)
        self.counts["emails_drafted"] += 1
        print_lg(f'   Email to {to} written, waiting for you in the dashboard (Review)')
        return "email_drafted"
#>
