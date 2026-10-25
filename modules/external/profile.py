'''
Answers common application fields from your config files (personals.py, questions.py).
Returns `None` when the field isn't a known profile detail, the answer finder then tries saved answers, AI and the popup.
'''

import os
import re

from config.personals import first_name, middle_name, last_name, phone_number, current_city, street, state, zipcode, country, gender, ethnicity, disability_status, veteran_status
from config.questions import years_of_experience, require_visa, website, linkedIn, desired_salary, current_ctc, notice_period, linkedin_headline, linkedin_summary, cover_letter, recent_employer
from config import questions as _questions   # Education answers (newer settings, read with getattr so older configs still work)
from config.secrets import username as linkedin_login_email
from modules.answer_store import match_option

try:
    from config.personals import email as configured_email
except ImportError:
    configured_email = ""

EMAIL = (configured_email or "").strip() or (linkedin_login_email if "@" in linkedin_login_email and linkedin_login_email != "username@example.com" else "")
FIRST, MIDDLE, LAST = first_name.strip(), middle_name.strip(), last_name.strip()
FULL_NAME = " ".join(part for part in (FIRST, MIDDLE, LAST) if part)

_YES_NO_START = re.compile(r'^(are|do|did|does|would|will|can|could|have|has|is|were|should)\b')


_COUNTRY_CODES = {"india": "91", "united states": "1", "usa": "1", "us": "1", "canada": "1", "united kingdom": "44", "uk": "44", "australia": "61",
                  "germany": "49", "france": "33", "singapore": "65", "united arab emirates": "971", "uae": "971", "netherlands": "31", "ireland": "353"}


def international_phone(number: str) -> str:
    '''Phone number with your country code, Eg: "+919876543210", for phone boxes that start with a "+" country code.'''
    digits = re.sub(r'\D', '', number or "")
    code = _COUNTRY_CODES.get((country or "").strip().lower(), "")
    if not code or digits.startswith(code) and len(digits) > 10: return "+" + digits
    return "+" + code + digits


def with_https(url: str) -> str:
    url = (url or "").strip()
    if url and not url.lower().startswith(("http://", "https://")): url = "https://" + url
    return url


def _salary(label: str, amount: int) -> str:
    if "lakh" in label or "lpa" in label: return str(round(amount / 100000, 2))
    if "month" in label: return str(round(amount / 12))
    return str(amount)


def _placeholder(text: str, placeholder: str) -> str:
    text = (text or "").strip()
    return "" if text.lower() == placeholder.lower() else text


def resolve_resume_path(path: str) -> str | None:
    '''Finds the resume file whether `path` is absolute, relative to where the bot runs, or relative to the project's parent folder.'''
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [path, os.path.join(project_dir, path), os.path.join(os.path.dirname(project_dir), path)]
    project_name = os.path.basename(project_dir)
    normalized = path.replace("\\", "/")
    if normalized.startswith(project_name + "/"): candidates.append(os.path.join(project_dir, normalized[len(project_name) + 1:]))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate): return os.path.abspath(candidate)
    return None


# "I agree to the terms" boxes (ticked) and newsletter / job-alert boxes (never ticked)
CONSENT_WORDS = re.compile(r'agree|consent|acknowledg|privacy|terms|t&c|certify|confirm|i understand|accurate|i have read|declar|accept')
MARKETING_WORDS = re.compile(r'newsletter|marketing|promotion|job alert|round-up|roundup|subscribe|updates about|sms|text message|similar jobs|future (jobs|opportunities|openings)')


def profile_answer(field: dict, resume_path: str | None = None, job_location: str = "", job_title: str = "") -> str | None:
    '''
    Returns your answer for `field` from the config files, or `None` if it's not a profile detail.
    * For file fields returns the resume path, for single consent checkboxes returns "check".
    '''
    label = (field.get("label") or "").lower().strip()
    name = f'{field.get("name", "")} {field.get("id", "")}'.lower()
    auto = field.get("autocomplete", "")
    kind = field.get("kind", "")
    text = f"{label} {name}"
    yes_no_question = bool(_YES_NO_START.match(label))

    if kind == "password": return None   # Only the sign-up / sign-in step types passwords, never the answer finder

    if kind == "file":
        if "autofill" in text or "cover" in text: return None
        if any(word in text for word in ("resume", "résumé", "cv", "curriculum")): return resume_path
        return None

    if kind == "checkbox":
        consent = bool(CONSENT_WORDS.search(label)) and not MARKETING_WORDS.search(label)
        first_person = label.startswith(("i ", "i'", "by checking", "by submitting"))
        # Terms / declaration boxes are often not marked required, the form then refuses to send ("Please acknowledge the terms")
        return "check" if consent and (field.get("required") or first_person or re.search(r'terms|t&c|acknowledg|declar|privacy policy', label)) else None

    # Names
    if not yes_no_question:
        if auto == "given-name" or re.search(r'\bfirst[\s_-]*name\b|\bfirstname\b|\bgiven name\b', text) and "last" not in label: return FIRST
        if auto == "family-name" or re.search(r'\blast[\s_-]*name\b|\blastname\b|\bsurname\b|\bfamily name\b', text) and "first" not in label: return LAST
        if re.search(r'\bmiddle[\s_-]*name\b', text): return MIDDLE or None
        if auto == "name" or label in ("name", "full name", "your name", "legal name", "full legal name", "first and last name", "name (first and last)") or name.strip() in ("name", "full_name", "fullname", "name name"): return FULL_NAME
        if "preferred name" in label: return FIRST

    # Contact
    if auto == "email" or kind == "email" or re.search(r'\be-?mail\b', label): return EMAIL or None
    if "country code" in text or "phone code" in text: return country
    if auto.startswith("tel") or kind == "tel" or re.search(r'\b(phone|mobile|contact number|cell)\b', label): return phone_number

    # Links
    if "linkedin" in text: return with_https(linkedIn) if linkedIn else None
    if "github" in text or "twitter" in text or "x.com" in text: return None
    if re.search(r'\b(website|portfolio|personal site|blog)\b', label): return with_https(website) if website else None

    # Location
    if not yes_no_question:
        if re.search(r'\b(street|address line|address 1|address)\b', label) and "email" not in label: return street or None
        if re.search(r'\b(zip|postal|pin ?code|pincode)\b', label): return zipcode or None
        if re.search(r'\bcity\b', label): return current_city or job_location or None
        if re.search(r'\b(state|province|region)\b', label) and "statement" not in label: return state or None
        if re.search(r'\bcountry\b', label): return country or None
        if re.search(r'\b(location|where are you based|where do you live|currently located|current location)\b', label):
            if "relocat" in label or "willing" in label: return None
            return ", ".join(part for part in (current_city, country) if part) or job_location or None

    # Work
    # "Job Position" / "Which role are you applying for?": the LinkedIn job title, used only if it matches one of the choices
    if job_title and re.search(r'\b(job position|job role|job title|position (you are )?applying|role (you are )?applying|applying for|applied for|desired (role|position)|interested position|select (the )?(position|role|domain|internship))\b|^(position|role|domain|internship|profile)$', label):
        return job_title
    if not yes_no_question:
        if re.search(r'\b(current|present|most recent) (company|employer|organi[sz]ation)\b', label) or name.strip() in ("org", "org org", "company"): return recent_employer or None
        if re.search(r'\bmonths? of (professional |work |relevant |total )?experience\b|\badditional months\b', label): return "0"   # Experience is counted in whole years
        if re.search(r'\byears? of (professional |work |relevant |total )?experience\b|\bhow many years\b|\bexperience \(years\)|\b(total |work )?experience (in|\(in) years\b', label) \
                or re.fullmatch(r'(total |overall |work |relevant )?(work )?experience', label): return years_of_experience
    if re.search(r'^what is your (salary |ctc |pay )?expectations?\??$|^(salary |ctc )?expectations?\??$', label): return _salary(label, desired_salary)
    if re.search(r'how soon can you (join|start)|when can you (join|start)|joining (time|period|date)|availability to (join|start)|days to join|time to join', label):
        if "month" in label: return str(notice_period // 30)
        if "week" in label: return str(notice_period // 7)
        return str(notice_period)
    if "notice period" in label or "notice" in label and "days" in label:
        if "month" in label: return str(notice_period // 30)
        if "week" in label: return str(notice_period // 7)
        return str(notice_period)
    if re.search(r'\b(salary|ctc|compensation|pay expectation|expected pay)\b', label):
        if re.search(r'\b(current|present)\b', label): return _salary(label, current_ctc)
        return _salary(label, desired_salary)
    if "sponsorship" in label or re.search(r'\bvisa\b', label): return require_visa

    # Education
    edu = lambda name: (str(getattr(_questions, name, "") or "").strip() or None) if not yes_no_question else None   # "Is your CGPA above 7?" is a Yes / No
    if re.search(r'(10th|\bx\b|class 10|ssc|matric|secondary school).{0,40}(percent|%|marks|score|cgpa|grade)|percentage in 10', text): return edu("percentage_10th")
    if re.search(r'(12th|\bxii\b|class 12|hsc|higher secondary|intermediate|puc).{0,40}(percent|%|marks|score|cgpa|grade)|percentage in 12', text): return edu("percentage_12th")
    if re.search(r'\b(c?gpa|grade point|cumulative grade)\b', text) and not re.search(r'10th|12th|class', text): return edu("cgpa")
    if re.search(r'(graduat\w*|passing|pass.?out|completion).{0,25}year|year\b.{0,20}(graduat|pass)|year of (graduation|passing|completion)|\bbatch\b', text): return edu("graduation_year")
    if not yes_no_question and re.search(r'highest (degree|qualification|education)|^(degree|qualification|education)$|educational qualification', label): return edu("highest_degree")

    # Voluntary self-identification
    if re.search(r'\bgender\b|\bsex\b', label) and "orientation" not in label: return gender or None
    if re.search(r'\b(race|ethnicity|ethnic)\b', label): return ethnicity or None
    if "veteran" in label: return veteran_status or None
    if "disabilit" in label: return disability_status or None

    # Free text
    if re.search(r'how (did )?you (hear|heard|find|found|learn|learned|come across|came across)|where did you (hear|find)|\b(application|referral|job|candidate) source\b|^source$', label): return "LinkedIn"
    if "headline" in label: return linkedin_headline or None
    if kind == "textarea" and "cover letter" in label: return _placeholder(cover_letter, "Cover Letter") or None
    if kind == "textarea" and re.search(r'\b(summary|about yourself|tell us about you)\b', label): return linkedin_summary.strip() or None
    return None


# Bigger areas a country belongs to, for "Region" dropdowns that list continents instead of states
_WORLD_REGIONS = {"india": ["Asia Pacific", "APAC", "Asia", "South Asia", "APJ", "AMEA"], "singapore": ["Asia Pacific", "APAC", "Asia"],
                  "australia": ["Asia Pacific", "APAC", "Oceania"], "united states": ["North America", "Americas", "NA"], "canada": ["North America", "Americas"],
                  "united kingdom": ["Europe", "EMEA", "UK"], "germany": ["Europe", "EMEA"], "france": ["Europe", "EMEA"], "netherlands": ["Europe", "EMEA"],
                  "ireland": ["Europe", "EMEA"], "united arab emirates": ["Middle East", "EMEA", "MEA"]}
_DEMONYMS = {"india": "Indian", "united states": "American", "united kingdom": "British", "canada": "Canadian", "australia": "Australian",
             "germany": "German", "france": "French", "singapore": "Singaporean", "ireland": "Irish", "netherlands": "Dutch"}
_PLACE_LABEL = re.compile(r'\b(city|state|province|region|country|location|residence|reside|based|nationality|citizenship)\b')


def profile_alternatives(field: dict, job_location: str = "") -> list[str]:
    '''
    Other ways to give your profile answer when the dropdown's choices don't include it, in the order to try:
    "Region of Residence" -> your state, country, "Asia Pacific"...; "Job Location" -> the job's city first; "0" years -> "Fresher".
    '''
    label = (field.get("label") or "").lower()
    if _PLACE_LABEL.search(label):
        job_places = [part.strip() for part in (job_location or "").split(",") if part.strip()]
        mine = [current_city, state, country, _DEMONYMS.get((country or "").strip().lower(), "")] + _WORLD_REGIONS.get((country or "").strip().lower(), [])
        places = (job_places + mine) if re.search(r'\b(job|preferred|work|office|interview) location\b', label) else (mine + job_places)
        return [place for place in places if place]
    if "experience" in label and str(years_of_experience).strip() in ("0", ""):
        return ["0", "Fresher", "Fresh graduate", "Entry level", "No experience", "None", "Less than 1", "0-1", "< 1"]
    return []


# Questions nearly every applicant answers the same way. Used only when your saved answers, profile and AI had no answer, before the popup
_WILLING = re.compile(r'\b(ready|willing|comfortable|open|able|okay|ok|happy|available|fine) (to |with |for )?(work|relocat|commut|travel|join|attend|meet|come|be based|go|report|start)')
_WILLING_CHOICE = re.compile(r'\b(work|working) (from|in|at) (the )?(office|location|site|client)|\bin[- ]person\b|\bon[- ]?site\b|\bhybrid\b|\brelocat')   # Only with Yes / No choices
_AGREE = re.compile(r'\b(agree|acknowledge|confirm|accept|consent|certify|declare|understand)\b')


def fallback_answer(field: dict, options: list[str] | None = None, job_location: str = "") -> str | None:
    '''A safe usual answer ("Yes" to "Are you willing to work from the office?", "Acknowledge" to "Please confirm you read the privacy notice"), or None.'''
    label = (field.get("label") or "").lower()
    kind = field.get("kind", "")
    if not label or kind in ("file", "password", "checkbox"): return None

    def pick(*answers: str) -> str | None:
        if not options: return answers[0]
        for answer in answers:
            for option in options:   # Yes / Acknowledge / I agree style options
                if re.match(r'\s*' + re.escape(answer.lower()) + r'\b', option.lower()): return option
        return None

    if _AGREE.search(label) and not MARKETING_WORDS.search(label):
        return pick("Yes", "I agree", "Agree", "Acknowledge", "I acknowledge", "Confirm", "I confirm", "Accept", "I accept", "I understand", "I have read")
    if _WILLING.search(label) or (options and _WILLING_CHOICE.search(label)):
        return pick("Yes", "I am", "I'm", "Sure", "Definitely")
    # Freshers: no previous employer; nobody applying here worked for this company / a government before (asked as Yes / No)
    if re.search(r'(most recent|current|present|previous|last) (company|employer|organi[sz]ation|job)|recently worked|where (do|did) you (currently )?work', label):
        if str(years_of_experience).strip() in ("0", "") and not (recent_employer or "").strip():
            return pick("Fresher", "None", "Not applicable", "N/A") if options else "Fresher (no previous employer)"
        return pick(recent_employer) if (options and recent_employer) else (recent_employer or None)
    if re.search(r'have you (ever )?(previously )?(worked|been employed|been an employee|interned) (at|for|with|by)|(directly )?employed by .{0,40}government|former employee', label):
        return pick("No", "I have not", "Never")
    if re.search(r'\b(nationality|citizenship)\b', label) and country:
        demonym = _DEMONYMS.get(country.strip().lower(), "")
        if not options: return demonym or country
        return (demonym and match_option(demonym, options)) or match_option(country, options)
    return None
