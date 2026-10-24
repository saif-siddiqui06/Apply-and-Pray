'''
Detects which hiring website a job link belongs to, and how to open its application form.
'''

from urllib.parse import urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver


# Hiring websites we recognise. Only the ones in `normal_apply_sites` (config/settings.py) are filled automatically.
# Websites not listed here are "other", filled when "other" is in `normal_apply_sites`.
_HOST_PATTERNS = [
    ("greenhouse", ["greenhouse.io"]),
    ("lever", ["lever.co"]),
    ("ashby", ["ashbyhq.com"]),
    ("googleforms", ["forms.gle"]),
    # These need an account per company, so they're always left for you to apply by hand
    ("workday", ["myworkdayjobs.com", "myworkdaysite.com", "workday.com"]),
    ("icims", ["icims.com"]),
    ("taleo", ["taleo.net"]),
    ("smartrecruiters", ["smartrecruiters.com"]),
    ("workable", ["workable.com"]),
    ("bamboohr", ["bamboohr.com"]),
    ("jobvite", ["jobvite.com"]),
    ("successfactors", ["successfactors.com", "successfactors.eu"]),
    ("oracle", ["oraclecloud.com"]),   # Oracle "Candidate Experience": emailed code + dropdowns the bot can't fill, every try failed
]

# Company career pages often embed the real form in an iframe
_EMBED_PATTERNS = [
    ("greenhouse", "greenhouse.io"),
    ("lever", "lever.co"),
    ("ashby", "ashbyhq.com"),
    ("googleforms", "docs.google.com/forms"),
]


def site_from_url(url: str) -> str | None:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    if (host == "docs.google.com" and parsed.path.startswith("/forms")) or host == "forms.gle": return "googleforms"
    for site, patterns in _HOST_PATTERNS:
        if any(host == pattern or host.endswith("." + pattern) for pattern in patterns): return site
    return None


def detect_site(driver: WebDriver) -> tuple[str | None, str]:
    '''
    Returns `(site, form_url)` for the page currently open in `driver`.
    * `site` is None for websites we don't recognise.
    * `form_url` is the embedded form's own address if the form is inside an iframe, else the current URL.
    '''
    url = driver.current_url
    site = site_from_url(url)
    if site: return site, url
    for site, pattern in _EMBED_PATTERNS:
        for frame in driver.find_elements(By.XPATH, f"//iframe[contains(@src, '{pattern}')]"):
            src = frame.get_attribute("src") or ""
            if src and not src.startswith(("about:", "javascript:", "data:")): return site, src
    return None, url


def _base(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def application_form_url(site: str, url: str) -> str:
    '''Lever and Ashby show the job description first, the form lives on its own page. Embedded Google Forms open as a normal form.'''
    base = _base(url)
    if site == "lever" and not base.endswith("/apply"): return base + "/apply"
    if site == "ashby" and not base.endswith("/application"): return base + "/application"
    if site == "googleforms" and "docs.google.com" in base and base.endswith("/viewform") and "embedded=true" in url: return base
    return url


# XPaths tried in order to find the final submit button
SUBMIT_BUTTONS = {
    "lever": ["//button[@id='btn-submit']", "//button[@type='submit' and contains(., 'Submit')]"],
    "greenhouse": ["//*[@id='submit_app']", "//button[@type='submit' and contains(., 'Submit')]", "//button[contains(., 'Submit application') or contains(., 'Submit Application')]"],
    "ashby": ["//button[contains(@class, 'submit-button')]", "//button[contains(., 'Submit Application') or contains(., 'Submit application')]"],
    "googleforms": ["//*[@role='button'][normalize-space(.)='Submit']"],
}
# Button text compared in lowercase, so "SUBMIT" and "Submit" both match
_LOWER = "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
_LOWER_VALUE = "translate(normalize-space(@value), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
_BUTTON = "(self::button or @role='button' or self::input[@type='submit' or @type='button'] or self::div[contains(@class, 'btn') or contains(@class, 'button')])"

def _text_is(texts: list[str], attribute: str = _LOWER) -> str:
    return " or ".join(f"{attribute}='{text}'" for text in texts)

_SUBMIT_TEXTS = ["submit", "submit application", "submit form", "send application", "submit my application", "send", "submit now", "send now", "submit details", "complete application"]
_NOT_SUBMIT = f"not(contains({_LOWER}, 'next') or contains({_LOWER}, 'continue') or contains({_LOWER}, 'back') or contains({_LOWER}, 'previous') or contains({_LOWER}, 'upload') or contains({_LOWER}, 'add') or contains({_LOWER}, 'remove') or contains({_LOWER}, 'search'))"
# `data-aap-form` marks the form with the most fields (set by form.read_fields), so its buttons win over other forms on the page
GENERIC_SUBMIT_BUTTONS = [
    "//*[@data-aap-form]//button[@type='submit']", "//*[@data-aap-form]//input[@type='submit']",
    f"//*[{_BUTTON}][{_text_is(_SUBMIT_TEXTS)} or {_text_is(_SUBMIT_TEXTS, _LOWER_VALUE)}]",
    f"//*[@data-aap-form]//button[contains({_LOWER}, 'submit')]",
    f"//form//button[@type='submit' and contains({_LOWER}, 'submit')]",
    "//*[@data-aap-form]//*[contains(@class, 's_website_form_send')]",   # Odoo job forms: <a role=button class="s_website_form_send">
    f"//*[@data-aap-form]//*[self::button or self::a or @role='button'][contains({_LOWER}, 'apply')]",   # "Apply Now" as the form's own button
    f"//*[@data-aap-form]//*[self::button or self::a[@role='button'] or @role='button'][(contains(@class, 'submit') or contains(@id, 'submit')) and {_NOT_SUBMIT}]",
]

# Buttons that only go to the next page of a multi-page form. Exact text only, so "Continue with Google" never matches.
SAFE_NEXT_TEXTS = ["next", "next step", "next page", "save and next", "save & next", "save and continue", "save & continue", "next >", "next →"]
# Buttons that may move to the next page OR send the application, the bot asks before clicking them ("pause before submit")
MAYBE_FINAL_TEXTS = ["continue", "proceed"]
NEXT_BUTTONS = [
    f"//*[@data-aap-form]//*[self::a or {_BUTTON}][{_text_is(SAFE_NEXT_TEXTS + MAYBE_FINAL_TEXTS)} or {_text_is(SAFE_NEXT_TEXTS + MAYBE_FINAL_TEXTS, _LOWER_VALUE)}]",
    f"//*[{_BUTTON}][{_text_is(SAFE_NEXT_TEXTS + MAYBE_FINAL_TEXTS)} or {_text_is(SAFE_NEXT_TEXTS + MAYBE_FINAL_TEXTS, _LOWER_VALUE)}]",   # Links outside the form are never used (Eg: a carousel "Next")
]

# Buttons that reveal the form on pages that show the description first
OPEN_FORM_BUTTONS = [
    "//a[normalize-space()='Apply' or normalize-space()='Apply Now' or normalize-space()='Apply now' or normalize-space()='Apply for this job' or normalize-space()='Apply for this Job']",
    "//button[normalize-space()='Apply' or normalize-space()='Apply Now' or normalize-space()='Apply now' or normalize-space()='Apply for this job' or normalize-space()='Apply for this Job']",
]
# Any link or button mentioning "apply" (Eg: "Click Here to Apply for job"), "I'm interested" (Zoho Recruit) or "submit resume", used on unknown websites
_APPLY_WORDS = " or ".join(f"contains({_LOWER}, '{word}')" for word in ("apply", "interested", "submit resume", "submit your resume", "submit cv", "send cv", "send your cv"))
APPLY_LINKS = f"//a[{_APPLY_WORDS}] | //button[{_APPLY_WORDS}] | //*[@role='button'][{_APPLY_WORDS}] | //input[(@type='button' or @type='submit') and contains({_LOWER_VALUE}, 'apply')]"
# Exact texts of the main Apply button (preferred over menu links like "Apply for Jobs")
APPLY_TEXTS = ["apply", "apply now", "apply job", "apply for job", "apply for this job", "apply for this position", "apply to job", "apply to this job",
               "apply for this role", "i'm interested", "i am interested", "interested", "quick apply", "apply online", "apply here", "submit resume", "submit your resume"]
# Labels that make a small form a "contact us" form, not an application
CONTACT_FORM_WORDS = ["message", "your message", "comment", "comments", "subject", "enquiry", "inquiry", "query", "how can we help"]
# Other forms on job pages that aren't the application: the job search box, "Join our Talent Community", job alerts, newsletters
SEARCH_FIELD_WORDS = r'search|keyword|job title|title|location|where|what|category|categories|radius|distance|department|function|career area|sort'
SIDE_FORM_BUTTONS = r'\b(search|find jobs?|go|talent (community|network)|join (our )?(talent|community)|job alerts?|create (a )?(job )?alert|subscribe|newsletter|stay in touch|keep me (posted|updated)|sign up for)\b'

CONFIRMATION_PHRASES = [
    "thank you for applying", "thanks for applying", "application has been submitted", "application was submitted",
    "application submitted", "application has been received", "we've received your application", "we have received your application",
    "successfully submitted", "application was successfully", "your application is in", "thank you for your application",
    "thanks for your application", "your response has been recorded", "thank you for submitting", "thanks for submitting",
    "form submitted", "submitted successfully", "application received",
]
CONFIRMATION_URL_WORDS = ["thank", "confirmation", "success", "submitted", "formresponse"]

# Pages the bot can't fill: sign-in / sign-up walls, closed forms, errors. Checked in the URL and in the page text.
LOGIN_URL_WORDS = ["accounts.google.com", "/login", "/signin", "/sign-in", "/signup", "/sign-up", "/register", "/auth/", "/oauth", "candidatelogin", "/sso"]
# Third-party sign-in pages the bot never types a password into
OAUTH_HOSTS = ["accounts.google.com", "login.microsoftonline.com", "linkedin.com", "appleid.apple.com", "facebook.com", "github.com"]

# Links / buttons on a sign-in page that lead to creating an account, and the other way round
SIGNUP_LINKS = ["sign up", "signup", "create account", "create an account", "register", "join now", "new user", "create profile", "don't have an account", "new candidate"]
SIGNIN_LINKS = ["sign in", "signin", "log in", "login", "already have an account", "existing user"]
SIGNIN_BUTTONS = ["sign in", "log in", "login", "continue", "next", "submit", "sign in with email", "log in with email", "continue with email"]
SIGNUP_BUTTONS = ["sign up", "create account", "create an account", "register", "join", "continue", "next", "submit", "get started", "sign up with email", "continue with email"]
# Messages after a failed sign in / sign up
NO_ACCOUNT_PHRASES = ["no account", "not registered", "doesn't exist", "does not exist", "user not found", "account not found", "incorrect", "invalid email or password", "invalid credentials", "wrong password", "couldn't find your account"]
ACCOUNT_EXISTS_PHRASES = ["already exists", "already registered", "already in use", "already have an account", "email is taken", "already taken"]
VERIFY_PHRASES = ["verification code", "verify your email", "check your email", "check your inbox", "otp", "one-time", "one time password", "enter the code", "confirmation link", "verify your account", "activation link", "sent a code", "sent you a link"]
UNAVAILABLE_PHRASES = [
    "no longer accepting responses", "is no longer accepting", "this job is no longer available", "job has expired", "position has been filled",
    "job is closed", "no longer active", "403 forbidden", "access denied", "404 not found", "page not found",
]
