'''
Search helpers, kept small on purpose:
* `plan_searches()`       - the positions to search this run: one position per search, in a new random order every run
* `linkedin_search_url()` - a LinkedIn job search with all filters in the address (Easy Apply, date, experience...), no clicking needed
* `skip_word_in()`        - does a job title contain one of your `skip_title_words` (Eg: "Senior")? Checked on the job list
'''

import re
import random
from urllib.parse import urlencode, quote, urlparse, parse_qsl, urlunparse

# LinkedIn's own codes for its search filters (they appear in the address bar when you pick filters on linkedin.com)
DATE_CODES = {"Past 24 hours": "r86400", "Past week": "r604800", "Past month": "r2592000"}
EXPERIENCE_CODES = {"Internship": "1", "Entry level": "2", "Associate": "3", "Mid-Senior level": "4", "Director": "5", "Executive": "6"}
JOB_TYPE_CODES = {"Full-time": "F", "Part-time": "P", "Contract": "C", "Temporary": "T", "Volunteer": "V", "Internship": "I", "Other": "O"}
WORKPLACE_CODES = {"On-site": "1", "Remote": "2", "Hybrid": "3"}
SORT_CODES = {"Most recent": "DD", "Most relevant": "R"}
JOBS_PER_PAGE = 25
_COUNTRIES = {"india", "united states", "usa", "united kingdom", "uk", "canada", "germany", "australia", "singapore", "united arab emirates", "uae",
              "netherlands", "ireland", "france"}


def _normalize(text: str) -> str:
    return " ".join(re.sub(r'[^a-z0-9+#]+', ' ', (text or "").lower()).split())


def covering_positions(terms: list[str]) -> list[str]:
    '''Drops terms already covered by a shorter one: "Python Developer Intern" is covered by "Python Developer". Keeps the given order.'''
    cleaned = []
    for term in terms:
        term = " ".join(term.replace('"', '').split())
        if term and term.lower() not in [t.lower() for t in cleaned]: cleaned.append(term)
    return [term for term in cleaned if not any(other != term and re.search(r'\b' + re.escape(other.lower()) + r'\b', term.lower()) for other in cleaned)]


def plan_searches(terms: list[str], randomize: bool, rng: random.Random | None = None) -> list[str]:
    '''One position per search ("Python Developer Intern" is covered by "Python Developer"), in a new random order every run.'''
    positions = covering_positions(terms)
    if randomize: (rng or random.SystemRandom()).shuffle(positions)
    return positions


def location_for_search(location: str) -> str:
    '''
    LinkedIn's address takes one place. "Delhi, India" or "Bengaluru" are used as they are; a list of places
    like "Delhi, Noida, Gurgaon, India, Bengaluru" becomes its country ("India"), which covers them all.
    '''
    parts = [part.strip() for part in (location or "").split(",") if part.strip()]
    if len(parts) <= 2: return ", ".join(parts)
    countries = [part for part in parts if part.lower() in _COUNTRIES]
    return countries[0] if countries else parts[0]


def linkedin_search_url(keywords: str, location: str = "", easy_apply: bool = False, date_posted: str = "", experience: list[str] = (),
                        job_type: list[str] = (), on_site: list[str] = (), sort_by: str = "", under_10_applicants: bool = False,
                        in_your_network: bool = False, fair_chance: bool = False, page: int = 0, plain_words: bool = False) -> str:
    '''
    The LinkedIn job search address with every filter set in it. `page` 0 is the first page of 25 jobs.
    `plain_words`: LinkedIn's 2026 search ignores location / level in the address, they go in the words: "Python Developer entry level jobs in India".
    '''
    place = location_for_search(location)
    words = keywords
    if plain_words:
        if experience and all(level in ("Internship", "Entry level") for level in experience): words += " entry level"
        if place: words += f" jobs in {place}"
    params = [("keywords", words)]
    if place: params.append(("location", place))
    if easy_apply: params.append(("f_AL", "true"))
    if date_posted in DATE_CODES: params.append(("f_TPR", DATE_CODES[date_posted]))
    for name, values, codes in (("f_E", experience, EXPERIENCE_CODES), ("f_JT", job_type, JOB_TYPE_CODES), ("f_WT", on_site, WORKPLACE_CODES)):
        chosen = [codes[value] for value in values if value in codes]
        if chosen: params.append((name, ",".join(chosen)))
    if sort_by in SORT_CODES: params.append(("sortBy", SORT_CODES[sort_by]))
    if under_10_applicants: params.append(("f_EA", "true"))
    if in_your_network: params.append(("f_JIYN", "true"))
    if fair_chance: params.append(("f_FCE", "true"))
    if page > 0: params.append(("start", str(page * JOBS_PER_PAGE)))
    return ("https://www.linkedin.com/jobs/search-results/?" if plain_words else "https://www.linkedin.com/jobs/search/?") + urlencode(params, quote_via=quote)


def with_page(url: str, page: int) -> str:
    '''The same search on another page (keeps any filters LinkedIn added to the address).'''
    parts = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in ("start", "currentJobId")]
    if page > 0: query.append(("start", str(page * JOBS_PER_PAGE)))
    return urlunparse(parts._replace(query=urlencode(query, quote_via=quote)))


def skip_word_in(title: str, words: list[str]) -> str | None:
    '''The first of `words` found in `title` as a whole word ("Senior" matches "Senior Data Analyst", not "Seniority"), or None.'''
    text = f" {_normalize(title)} "
    for word in words:
        word = _normalize(word)
        if word and f" {word} " in text: return word
    return None
