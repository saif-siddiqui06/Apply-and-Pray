'''
Remembers every job the bot has handled, from the applied and failed jobs excels, so it doesn't apply to the same job twice:
* the same LinkedIn job (Job ID) again,
* the same job reposted by the company under a new Job ID (same company + same title),
* the same company more than `max_per_company` times within `avoid_same_company_days`,
* jobs that failed or were skipped in an earlier run (unless `retry_failed_jobs = True`).
'''

import csv
import re
from datetime import datetime, timedelta

from modules.helpers import print_lg


# "Assumed Reason" values in the failed jobs excel that mean the job doesn't fit you: never tried again.
# Every other reason is an error (page didn't load, a bug, a question that couldn't be answered...): tried again up to MAX_ERROR_TRIES times.
NOT_FOR_YOU_REASONS = [
    ("Required experience is high", "experience too high"),
    ("Found a Bad Word", "bad word in description"),
    ("Asking for Security clearance", "security clearance"),
    ("Found Blacklisted words", "blacklisted company"),
    ("Discarded by you", "you discarded it"),
    ("Skipped by you", "you skipped it"),
    ("Job is closed", "no longer accepting applications"),
    ("Employer flagged by LinkedIn", "LinkedIn shows a safety reminder for this employer"),
]
MAX_ERROR_TRIES = 2
# Reasons that say nothing about the job itself (LinkedIn paused Easy Apply, the page didn't load in time): always tried again, never counted as errors
ALWAYS_RETRY_REASONS = ("Easy Apply paused by LinkedIn", "Job details didn't load")

_COMPANY_SUFFIXES =r'\b(private|pvt|limited|ltd|llp|llc|inc|incorporated|corp|corporation|co|company|technologies|technology|solutions|services|group|india)\b'


def normalize_company(name: str) -> str:
    name = re.sub(r'[^a-z0-9& ]+', ' ', (name or "").lower())
    name = re.sub(_COMPANY_SUFFIXES, ' ', name)
    return " ".join(name.split())


def normalize_title(title: str) -> str:
    title = re.sub(r'\(.*?\)|\[.*?\]', ' ', (title or "").lower())   # "(Remote)", "[Hiring]"
    title = re.sub(r'[^a-z0-9+#]+', ' ', title)
    return " ".join(title.split())


_LEVEL_AT_END = re.compile(r'\b(i{1,3}|iv|vi{0,3}|ix|x|\d+)$')   # "Software Engineer II", "Analyst 2": a different job, not a lost letter


def _same(a: str, b: str) -> bool:
    '''
    Equal, or one is the other minus its last letter: older history rows lost the last letter of names ("hrm counse").
    Never when the longer one ends in a level ("Software Engineer I" vs "Software Engineer II").
    '''
    if a == b: return True
    if not a or not b: return False
    short, long = sorted((a, b), key=len)
    if len(long) - len(short) != 1 or not long.startswith(short) or len(short) < 4: return False
    return long[-1].isalpha() and not _LEVEL_AT_END.search(long)


def _read_rows(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return list(csv.DictReader(file))
    except FileNotFoundError:
        return []
    except Exception as e:
        print_lg(f'Could not read "{path}" for the job history:', e)
        return []


def _parse_date(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try: return datetime.strptime((text or "").strip(), fmt)
        except ValueError: pass
    return None


class JobHistory:
    def __init__(self, applied_file: str, failed_file: str, avoid_same_company_days: int = 30, retry_failed_jobs: bool = False, max_per_company: int = 1,
                 experience_limit: int | None = None):
        '''`experience_limit`: the most years you apply for now. Jobs skipped earlier for asking more, but not more than this, are tried again.'''
        self.avoid_same_company_days = avoid_same_company_days
        self.retry_failed_jobs = retry_failed_jobs
        self.max_per_company = max(1, max_per_company)
        self.applied_ids: set[str] = set()
        self.failed_ids: set[str] = set()
        self.not_for_you: dict[str, str] = {}   # Job ID -> why it doesn't fit you (never tried again)
        self.error_count: dict[str, int] = {}   # Job ID -> times it failed because of an error (tried again up to MAX_ERROR_TRIES)
        self.jobs: list[tuple[str, str]] = []                  # (company, title) already applied or saved
        self.company_dates: dict[str, list[datetime]] = {}      # company -> dates of real applications
        self.applied_times: list[datetime] = []                 # Dates of real applications, for `max_applications_per_hour`
        self.applied_today = 0                                  # Real applications sent today, for `max_applications_per_day`
        for row in _read_rows(applied_file):
            self._add_applied(row.get("Job ID", ""), row.get("Company", ""), row.get("Title", ""), _parse_date(row.get("Date Applied", "")))
        reopened = 0
        for row in _read_rows(failed_file):
            if not row.get("Job ID"): continue
            reason = row.get("Assumed Reason", "")
            if experience_limit is not None and reason.startswith("Required experience is high"):
                asked = re.search(r'Experience required (\d+) >', row.get("Stack Trace", "") or "")
                if asked and int(asked.group(1)) <= experience_limit:   # Fits your experience tolerance now: try it again
                    reopened += 1
                    continue
            self.record_failed(row["Job ID"], reason)
        if reopened: print_lg(f"{reopened} jobs skipped earlier for experience fit your experience tolerance now: they'll be tried again.")
        retry = len([job for job, count in self.error_count.items() if count < MAX_ERROR_TRIES and job not in self.not_for_you])
        print_lg(f"Job history: {len(self.applied_ids)} applied or saved, {len(self.not_for_you)} not for you, {retry} failed because of an error (will be tried again).")


    def _add_applied(self, job_id: str, company: str, title: str, date: datetime | None) -> None:
        if job_id: self.applied_ids.add(str(job_id).strip())
        company, title = normalize_company(company), normalize_title(title)
        if company: self.jobs.append((company, title))
        if company and date: self.company_dates.setdefault(company, []).append(date)
        if date: self.applied_times.append(date)
        if date and date.date() == datetime.now().date(): self.applied_today += 1


    def skip_reason_by_id(self, job_id: str) -> str | None:
        '''Why to skip, from the Job ID alone (no need to read the job card), or None.'''
        job_id = str(job_id).strip()
        if job_id in self.applied_ids: return "already applied"
        if not self.retry_failed_jobs:
            if job_id in self.not_for_you: return f"skipped before ({self.not_for_you[job_id]})"
            # Failures caused by an error (Eg: a bug in an older version, a page that didn't load) get another try
            if self.error_count.get(job_id, 0) >= MAX_ERROR_TRIES: return f"failed {self.error_count[job_id]} times before"
        return None


    def skip_reason(self, job_id: str, company: str, title: str) -> str | None:
        '''Why this job should be skipped, or None if it's new.'''
        by_id = self.skip_reason_by_id(job_id)
        if by_id: return by_id
        company_key, title_key = normalize_company(company), normalize_title(title)
        if company_key:
            for seen_company, seen_title in self.jobs:
                if _same(seen_company, company_key) and _same(seen_title, title_key): return "same company and job title already applied (reposted job)"
            if self.avoid_same_company_days > 0:
                limit = datetime.now() - timedelta(days=self.avoid_same_company_days)
                recent = sorted(date for seen_company, dates in self.company_dates.items() if _same(seen_company, company_key) for date in dates if date >= limit)
                if len(recent) >= self.max_per_company:
                    times = "once" if len(recent) == 1 else f"{len(recent)} times"
                    return f"applied to this company ({times} since {recent[0]:%d %b}, limit {self.max_per_company} in {self.avoid_same_company_days} days)"
        return None


    def applied_since(self, since: datetime) -> list[datetime]:
        '''Dates of real applications sent after `since` (oldest first).'''
        return sorted(date for date in self.applied_times if date >= since)


    def record_applied(self, job_id: str, company: str, title: str, applied: bool) -> None:
        '''`applied`: True if the application was really sent (counts for `avoid_same_company_days`), False if the link was only saved.'''
        self._add_applied(job_id, company, title, datetime.now() if applied else None)


    def record_failed(self, job_id: str, reason: str = "") -> None:
        '''`reason`: the "Assumed Reason" of the failed jobs excel. Jobs that don't fit you are never tried again, errors are retried.'''
        if not job_id: return
        job_id = str(job_id).strip()
        self.failed_ids.add(job_id)
        reason = (reason or "").strip()
        if reason.startswith(ALWAYS_RETRY_REASONS): return
        short = next((label for prefix, label in NOT_FOR_YOU_REASONS if reason.startswith(prefix)), None)
        if short: self.not_for_you[job_id] = short
        else: self.error_count[job_id] = self.error_count.get(job_id, 0) + 1
