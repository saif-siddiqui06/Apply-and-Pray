'''
Author:     Shubham
LinkedIn:   https://www.linkedin.com/in/shubham-sunil-kumar-333547133/

Copyright (C) 2024 Shubham

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html

GitHub:     https://github.com/theturkishangorashiro-art/apply-and-pray

Support me: https://github.com/sponsors/theturkishangorashiro-art

Reads your resume and builds the "about me" text the AI uses to answer application questions and fill sign-up forms.
'''

import os

from config.personals import *
from config.questions import default_resume_path, years_of_experience, require_visa, website, linkedIn, desired_salary, current_ctc, notice_period, linkedin_headline, linkedin_summary, recent_employer, user_information_all
from modules.helpers import print_lg

_cache: dict[str, str] = {}


def extract_resume_text(path: str, limit: int = 8000) -> str:
    '''Text of a .pdf or .docx resume (first `limit` characters), "" if it can't be read.'''
    if not path or not os.path.isfile(path): return ""
    if path in _cache: return _cache[path]
    text = ""
    try:
        if path.lower().endswith(".pdf"):
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        elif path.lower().endswith(".docx"):
            from docx import Document
            text = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    except Exception as e:
        print_lg(f'Could not read the resume "{path}":', e)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:limit]
    _cache[path] = text
    return text


def user_profile_text(resume_path: str) -> str:
    '''Everything the AI may use about you: your config details, `user_information_all` (if filled) and your resume.'''
    full_name = " ".join(part for part in (first_name.strip(), middle_name.strip(), last_name.strip()) if part)
    details = [
        f"Name: {full_name}",
        f"Email: {email}" if email else "",
        f"Phone: {phone_number}",
        f"Location: {', '.join(part for part in (current_city, state, country) if part)}",
        f"Years of experience: {years_of_experience}",
        f"Current or most recent employer: {recent_employer}",
        f"Headline: {linkedin_headline}",
        f"LinkedIn: {linkedIn}",
        f"Website: {website}" if website else "",
        f"Needs visa sponsorship: {require_visa}",
        f"Notice period (days): {notice_period}",
        f"Current yearly salary (CTC): {current_ctc}",
        f"Expected yearly salary (CTC): {desired_salary}",
        f"Summary: {linkedin_summary.strip()}",
    ]
    information = (user_information_all or "").strip()
    if information and information.lower() != "user information": details.append(f"More about me:\n{information}")
    resume = extract_resume_text(resume_path)
    if resume: details.append(f"My resume:\n{resume}")
    return "\n".join(line for line in details if line)
