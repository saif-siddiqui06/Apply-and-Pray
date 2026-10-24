'''
Finds more people to connect with through LinkedIn's people search, at companies you applied to recently:
* recruiters ("recruiter <company>")            -> source "recruiter"
* alumni of your college ("<college> <company>") -> source "alumni" (people from your college reply more often)

Each company is searched once, ever (`searches` table), at most `max_searches_per_run` searches per Networking run.
People found go into the usual flow: connection request (Review) -> message after they accept. Someone already
connected (1st) goes straight to "connected", so they get a message instead of a request.
'''

import re
import urllib.parse
from datetime import datetime, timedelta

from modules import db
from modules.helpers import print_lg

RECRUITER_WORDS = re.compile(r'recruit|talent|\bhr\b|human resources|hiring|people (partner|operations|team)|acquisition|staffing|campus', re.I)
SENIOR_LEADERS = re.compile(r'\b(ceo|cto|cfo|founder|co-founder|chairman|president|vp|vice president)\b', re.I)

_RESULTS_JS = r'''
const out = [], seen = new Set();
for (const a of document.querySelectorAll('main a[href*="/in/"]')) {
  const href = a.href.split('?')[0];
  if (seen.has(href) || /\/in\/[^/]+\/(detail|recent-activity|overlay)/.test(href)) continue;
  const box = a.closest('li, [data-chameleon-result-urn], [data-view-name="search-entity-result-universal-template"]') || a.parentElement;
  const hidden = a.querySelector('span[aria-hidden="true"]');
  const name = ((hidden ? hidden.innerText : a.innerText) || '').split('\n')[0].trim();
  if (!name || /^view .* profile/i.test(name) || name.length > 80) continue;
  seen.add(href);
  // Name, the hidden "View ... profile" and "• 2nd" run together on one line: take them out of every line
  const clean = t => t.split(name).join(' ').replace(/view\s.*?profile/ig, ' ').replace(/[•·]?\s*\b(1st|2nd|3rd)\+?(\s*degree connection)?/ig, ' ')
                      .replace(/[•·]/g, ' ').replace(/\s+/g, ' ').trim();
  const text = box.innerText || '';
  const lines = text.split('\n').map(clean).filter(t => /[a-z]/i.test(t) && !/^(connect|message|follow|pending|status is \w+)$/i.test(t));
  const degree = text.match(/\b(1st|2nd|3rd)\b/);
  const subtitle = box.querySelector('.entity-result__primary-subtitle, [class*="primary-subtitle"]');
  const headline = subtitle ? clean(subtitle.innerText) : (lines[0] || '');
  const rest = lines.filter(t => t !== headline);
  out.push({profile_url: href, name, headline, location: rest[0] || '', degree: degree ? degree[1] : ''});
}
return out;
'''


def pick(results: list[dict], kind: str, company: str, how_many: int, known: set[str]) -> list[dict]:
    '''The best people from one search: recruiters must look like recruiters; everyone should mention the company.'''
    chosen = []
    company_words = [word for word in re.findall(r'[a-z0-9]+', (company or "").lower()) if len(word) > 2 and word not in ("pvt", "ltd", "private", "limited", "inc", "llc", "technologies", "solutions", "india")]
    for person in results:
        key = db.profile_key(person["profile_url"])
        if key in known or not person.get("name") or person["name"].lower() == "linkedin member": continue
        headline = person.get("headline", "")
        if kind == "recruiter" and not RECRUITER_WORDS.search(headline): continue
        if SENIOR_LEADERS.search(headline) and kind == "alumni": continue   # Founders / CXOs rarely answer cold requests
        if company_words and not any(word in headline.lower() for word in company_words): continue
        chosen.append(dict(person, profile_url=key))
        known.add(key)
        if len(chosen) >= how_many: break
    return chosen


def companies_to_search(days: int) -> list[dict]:
    '''Companies you applied to recently, newest first, with the job title that connects you.'''
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out, seen = [], set()
    with db.session() as connection:
        for row in connection.execute("SELECT company, title, job_link FROM applications WHERE status = 'applied' AND applied_at >= ? AND company != '' ORDER BY applied_at DESC", (since,)):
            name = re.sub(r'\s+', ' ', row["company"]).strip()
            if name.lower() in seen or len(name) < 2: continue
            seen.add(name.lower())
            out.append({"company": name, "role": row["title"] or "", "job_link": row["job_link"] or ""})
    return out


class PeopleSearch:
    def __init__(self, driver, wait, checkpoint=None, status=None):
        self.driver, self.wait, self.checkpoint, self.status = driver, wait, checkpoint or (lambda: None), status or (lambda text: None)


    def _search(self, query: str) -> list[dict]:
        self.driver.get("https://www.linkedin.com/search/results/people/?keywords=" + urllib.parse.quote(query) + "&origin=GLOBAL_SEARCH_HEADER")
        self.wait(4)
        self.checkpoint()
        try: return self.driver.execute_script(_RESULTS_JS) or []
        except Exception: return []


    def run(self) -> int:
        '''Adds new people from recruiter / alumni searches. Returns how many were added.'''
        from config import outreach
        searches = [kind for kind, on in (("recruiter", outreach.search_recruiters), ("alumni", outreach.search_alumni and (outreach.college or "").strip())) if on]
        if not searches: return 0
        with db.session() as connection: known = {row[0] for row in connection.execute("SELECT profile_url FROM people")}
        added, done = 0, 0
        for target in companies_to_search(int(outreach.hirer_days)):
            for kind in searches:
                if done >= int(outreach.max_searches_per_run): return added
                key = f"{kind}|{target['company'].lower()}"
                if db.search_done(key): continue
                query = f"recruiter {target['company']}" if kind == "recruiter" else f"{outreach.college} {target['company']}"
                self.status(f"Networking: searching {kind}s at {target['company']}")
                found = pick(self._search(query), kind, target["company"], int(outreach.people_per_search), known)
                done += 1
                db.record_search(key, len(found))
                for person in found:
                    connected = person.get("degree") == "1st"
                    if db.add_person(person["profile_url"], name=person["name"], headline=person.get("headline", "")[:200], company=target["company"],
                                     role=target["role"], job_link=target["job_link"], source=kind, priority=2 if kind == "alumni" else 3,
                                     status="connected" if connected else "new"):
                        if connected: db.update_person(person["profile_url"], connected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), detail="Already connected.")
                        added += 1
                print_lg(f'   {kind.title()} search at {target["company"]}: {len(found)} new ' + (", ".join(p["name"] for p in found) if found else ""))
        return added
