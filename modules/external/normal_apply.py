'''
Normal Apply: opens a job's application link, fills the company's form and submits it.

Websites in `normal_apply_sites` (config/settings.py) are filled automatically: Greenhouse, Lever, Ashby, Google Forms,
and with "other" any website that shows a plain application form. Websites that need an account are signed up / signed in to
with the email and password from config/portal_login.py. Closed forms, pages without a form and websites that only offer
"Sign in with Google" are returned as "manual" so the link is saved for you to apply by hand.

Nothing waits for you forever: a form page gets `max_fill_attempts` tries, then the bot moves to the next application.
'''

import os
import re
import json
import traceback
from time import sleep, time
from urllib.parse import urlparse
from dataclasses import dataclass, field as dataclass_field
from typing import Callable

import pyautogui
from selenium.common.exceptions import NoAlertPresentException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from modules.helpers import print_lg
from modules.answer_store import match_option
from modules.answer_resolver import AnswerResolver
from modules.external.sites import (detect_site, application_form_url, SUBMIT_BUTTONS, GENERIC_SUBMIT_BUTTONS, NEXT_BUTTONS, OPEN_FORM_BUTTONS, APPLY_LINKS, APPLY_TEXTS,
                                    CONTACT_FORM_WORDS, SEARCH_FIELD_WORDS, SIDE_FORM_BUTTONS, CONFIRMATION_PHRASES, CONFIRMATION_URL_WORDS, LOGIN_URL_WORDS, UNAVAILABLE_PHRASES, MAYBE_FINAL_TEXTS,
                                    SIGNUP_LINKS, SIGNIN_LINKS, SIGNIN_BUTTONS, SIGNUP_BUTTONS, NO_ACCOUNT_PHRASES, ACCOUNT_EXISTS_PHRASES)
from modules.external.form import read_fields, fill_field, read_combobox_options, visible_errors, captcha_visible, focus_browser, _click
from modules.external.profile import profile_answer, profile_alternatives, fallback_answer, international_phone, CONSENT_WORDS, MARKETING_WORDS
from modules.external.accounts import AccountBook, auth_page_kind, site_key
from modules.bot_control import SkipJob


TEXT_KINDS = ("text", "email", "tel", "url", "number", "textarea", "date")
MAX_PAGES = 12          # Multi-page forms (Google Forms sections, step-by-step forms)
MAX_LINK_HOPS = 2       # "Apply" links followed to reach the form (Eg: job page -> forms.gle -> Google Form)
MAX_ACCOUNT_STEPS = 8   # Screens in one sign-up / sign-in (email, password, verification...)
MAX_FORM_FAILURES = 2   # A form that failed this many times (for any job) is saved for you to apply by hand, not tried again


def form_key(url: str) -> str:
    '''The form's address without the query, so the same form is recognised for every job that links to it.'''
    parsed = urlparse(url or "")
    return (parsed.netloc.lower().removeprefix("www.") + parsed.path.rstrip("/").lower()) or (url or "")


def is_secure_page(url: str) -> bool:
    '''Your portal password is only typed on https pages.'''
    return (url or "").lower().startswith("https://")


@dataclass
class ApplyResult:
    status: str                 # "submitted", "manual" (saved for you to apply by hand), "discarded" (you chose not to submit) or "failed"
    url: str                    # Final application page address
    site: str | None = None
    message: str = ""
    questions: set = dataclass_field(default_factory=set)
    screenshot: str = "Not Available"


class NormalApplier:
    def __init__(self, driver: WebDriver, resolver: AnswerResolver, *, enabled_sites: list[str], resume_path: str | None,
                 popups_enabled: bool, confirm_submit: Callable[[str], bool], screenshot: Callable[[str, str], str], close_tabs: bool = False,
                 max_fill_attempts: int = 2, portal_email: str = "", portal_password: str = "", accounts: AccountBook | None = None, control=None,
                 failed_forms_file: str | None = None):
        '''
        * `confirm_submit(description) -> bool`: Shows "pause before submit" if enabled, returns False if you chose to discard.
        * `screenshot(job_id, reason) -> str`: Saves a screenshot and returns its file name.
        * `portal_email` / `portal_password` / `accounts`: For signing up / signing in on job websites. No password = never does it.
        * `failed_forms_file`: JSON file counting failures per form, so a broken form isn't tried again for every job that links to it.
        '''
        self.driver = driver
        self.resolver = resolver
        self.enabled_sites = enabled_sites
        self.resume_path = resume_path
        self.popups_enabled = popups_enabled
        self.confirm_submit = confirm_submit
        self.screenshot = screenshot
        self.close_tabs = close_tabs
        self.max_fill_attempts = max(1, max_fill_attempts)
        self.portal_email = portal_email
        self.portal_password = portal_password
        self.accounts = accounts
        self.control = control      # Control window (Pause / Skip / Quit), see modules/bot_control.py
        self._typed: dict[str, tuple[str, str]] = {}   # What was typed on the current page: label -> (kind, answer)
        self._last_alert: str | None = None            # Text of a JavaScript alert Selenium closed by itself
        self.failed_forms_file = failed_forms_file
        self.failed_forms: dict[str, int] = {}
        if failed_forms_file and os.path.exists(failed_forms_file):
            try:
                with open(failed_forms_file, encoding="utf-8") as file: self.failed_forms = {key: int(count) for key, count in json.load(file).items()}
            except Exception as e: print_lg(f"Couldn't read {failed_forms_file}, starting a new one:", e)


    def _note_form_result(self, urls: list[str], failed: bool) -> None:
        '''Counts a failure for these form addresses, or forgets them after a success.'''
        if not self.failed_forms_file: return
        for key in {form_key(url) for url in urls if url}:
            if failed: self.failed_forms[key] = self.failed_forms.get(key, 0) + 1
            else: self.failed_forms.pop(key, None)
        try:
            os.makedirs(os.path.dirname(self.failed_forms_file) or ".", exist_ok=True)
            with open(self.failed_forms_file, "w", encoding="utf-8") as file: json.dump(self.failed_forms, file, indent=1)
        except Exception as e: print_lg(f"Couldn't save {self.failed_forms_file}:", e)


    def _take_alert(self) -> str | None:
        '''
        A JavaScript alert ("Please acknowledge the terms.") blocks the page and every later command fails on it.
        Returns its text and closes it, or the text of one Selenium already closed; None if there was none.
        '''
        text, self._last_alert = self._last_alert, None
        try:
            alert = self.driver.switch_to.alert
            text = alert.text or text or "The website showed an alert."
            alert.accept()
        except NoAlertPresentException: pass
        except UnexpectedAlertPresentException as e: text = e.alert_text or text
        except Exception: pass
        if text: print_lg(f'The website showed an alert: "{text}"')
        return text


    def _tick_consent_boxes(self, alert: str) -> bool:
        '''After an alert like "Please acknowledge the terms": ticks the empty terms / consent checkboxes. True if it ticked one.'''
        if not re.search(r'terms|agree|acknowledg|consent|accept|declar|privacy|confirm|tick|check', (alert or "").lower()): return False
        ticked = False
        for field in read_fields(self.driver):
            if field["kind"] != "checkbox" or field["value"]: continue
            try:   # The words next to the box too: often only a "T&C" link, not a real label
                element = self.driver.find_element(By.CSS_SELECTOR, f'[data-aap="{field["aap"]}"]')
                around = self.driver.execute_script("const p = arguments[0].closest('label, li, p, div, td'); return p ? p.innerText : '';", element) or ""
            except Exception: around = ""
            text = f'{field["label"] or ""} {around}'.lower()
            if MARKETING_WORDS.search(text) or (text.strip() and not CONSENT_WORDS.search(text)): continue
            if fill_field(self.driver, field, "check"):
                print_lg(f'Ticked "{field["label"] or "the terms checkbox"}" because the website asked for it')
                ticked = True
        if ticked: return True
        # Checkboxes drawn without an <input> (Eg: <label><div class="box"></div><span>I agree...</span></label>): click the label once
        try: fakes = self.driver.execute_script(self._FAKE_CONSENT_JS, CONSENT_WORDS.pattern, MARKETING_WORDS.pattern) or []
        except Exception: fakes = []
        for label in fakes:
            try:
                self.driver.execute_script("arguments[0].setAttribute('data-aap-ticked', '1')", label)
                _click(self.driver, label)
                print_lg(f'Ticked "{label.text.strip()[:80]}" because the website asked for it')
                ticked = True
            except Exception: pass
        return ticked


    _FAKE_CONSENT_JS = r'''
    const root = document.querySelector('[data-aap-form]') || document;
    const consent = new RegExp(arguments[0], 'i'), marketing = new RegExp(arguments[1], 'i');
    const out = [];
    for (const label of root.querySelectorAll('label, [role=checkbox]')) {
      if (label.hasAttribute('data-aap-ticked') || label.querySelector('input, select, textarea')) continue;   // Clicked before, or a real checkbox's label
      if (label.tagName === 'LABEL' && label.htmlFor && document.getElementById(label.htmlFor)) continue;
      if (label.getAttribute('aria-checked') === 'true') continue;
      const r = label.getBoundingClientRect(); if (!r.width || !r.height) continue;
      const text = (label.innerText || '').replace(/\s+/g, ' ').trim();
      if (text && text.length < 400 && consent.test(text) && !marketing.test(text)) out.push(label);
    }
    return out;
    '''


    #< Helpers
    def _checkpoint(self) -> None:
        '''Waits here while paused from the control window, raises SkipJob / QuitBot when you click those.'''
        if self.control is not None: self.control.checkpoint()
    def _wait_until_loaded(self, timeout: float = 15) -> None:
        end = time() + timeout
        while time() < end:
            try:
                if self.driver.execute_script("return document.readyState") == "complete": break
            except UnexpectedAlertPresentException as e:   # Selenium closed the alert, keep its text for _take_alert
                self._last_alert = e.alert_text or "The website showed an alert."
            except Exception: pass
            sleep(0.5)
        sleep(2)   # Let JavaScript forms render


    def _human_help(self, message: str) -> bool:
        '''Asks you to do something in the browser. Returns False if popups are disabled.'''
        if not self.popups_enabled: return False
        print_lg(message)
        pyautogui.alert(message + '\n\nClick "Continue" when done.', "Help Needed", "Continue")
        return True


    def _visible(self, xpaths: list[str]) -> WebElement | None:
        for xpath in xpaths:
            for element in self.driver.find_elements(By.XPATH, xpath):
                try:
                    if element.is_displayed() and element.is_enabled(): return element
                except Exception: pass
        return None


    def _button_with_text(self, texts: list[str], exact: bool = True) -> WebElement | None:
        '''Visible button / link whose text (lowercase) equals, or with `exact=False` contains, one of `texts`.'''
        for element in self.driver.find_elements(By.XPATH, "//button | //a | //*[@role='button'] | //input[@type='submit' or @type='button']"):
            try:
                if not element.is_displayed(): continue
                text = " ".join((element.text or element.get_attribute("value") or element.get_attribute("aria-label") or "").lower().split())
                if not text or len(text) > 50: continue
                if exact and text in texts: return element
                # Loose match never picks "Sign up with Google / LinkedIn": the bot can't use those
                if not exact and any(word in text for word in texts) and not re.search(r'google|linkedin|apple|facebook|microsoft|github', text): return element
            except Exception: pass
        return None


    def _submit_button(self, site: str) -> WebElement | None:
        return self._visible(SUBMIT_BUTTONS.get(site, []) + GENERIC_SUBMIT_BUTTONS)


    def _page_text(self) -> str:
        try: return (self.driver.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
        except Exception: return ""


    # Page widgets that aren't an application: chat windows, "save job" / "add to cart" boxes, cookie settings
    _NOT_A_QUESTION = re.compile(r'chatbot|chat window|chat input|type (your )?message|message box|send button|add to cart|save (this )?job|bookmark|cookie', re.I)

    @classmethod
    def _fillable(cls, fields: list[dict]) -> list[dict]:
        return [field for field in fields if field["kind"] not in ("file", "password") and not cls._NOT_A_QUESTION.search(field["label"] or "")]


    def _is_form(self, fields: list[dict], site: str) -> bool:
        '''
        Enough to be an application form: 2 different questions (1 on Google Forms), or 1 question plus a resume upload.
        Copies of the same field (Eg: a chat window drawn twice) count once.
        '''
        distinct = {(field["label"] or field["name"] or field["aap"]).strip().lower() for field in self._fillable(fields)}
        has_resume = any(field["kind"] == "file" and profile_answer(field, self.resume_path or "resume") for field in fields)
        return len(distinct) >= (1 if site == "googleforms" or has_resume else 2)


    @staticmethod
    def _is_contact_form(fields: list[dict]) -> bool:
        '''A small "Name, Email, Phone, Message" form with nothing about a job or a resume.'''
        labels = [(field["label"] or field["name"] or "").lower() for field in fields]
        if any(field["kind"] == "file" for field in fields): return False
        if any(re.search(r'resume|\bcv\b|experience|ctc|salary|notice|linkedin|qualification|skill|position|role|portfolio|cover', label) for label in labels): return False
        has_message = any(any(re.search(r'\b' + re.escape(word) + r'\b', label) for word in CONTACT_FORM_WORDS) for label in labels)
        return has_message and len([field for field in fields if field["kind"] not in ("file", "password")]) <= 6


    _FORM_BUTTONS_JS = r'''
    const form = document.querySelector('[data-aap-form]');
    if (!form) return [];
    return [...form.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')]
      .map(b => (b.innerText || b.value || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().toLowerCase()).filter(t => t && t.length < 60);
    '''


    def _side_form(self, fields: list[dict]) -> str | None:
        '''
        Job pages often have other forms next to the job: the job search box ("Keyword", "Location"), "Join our Talent Community",
        job alerts, "Contact us". Filling those sent nothing useful (and showed "No confirmation page after Submit").
        Returns what kind of form it is, or None if it may be the application.
        '''
        if any(field["kind"] == "file" for field in fields): return None
        if self._is_contact_form(fields): return "a contact form"
        labels = [(field["label"] or field["name"] or "").lower() for field in self._fillable(fields)]
        if labels and all(re.search(SEARCH_FIELD_WORDS, label) for label in labels): return "a job search box"
        try: buttons = self.driver.execute_script(self._FORM_BUTTONS_JS) or []
        except Exception: buttons = []
        if any(re.search(SIDE_FORM_BUTTONS, text) for text in buttons) and not any(re.search(r'submit|apply|send', text) for text in buttons):
            return "a talent community / job alert form"
        return None


    def _signature(self) -> tuple:
        '''Identifies the current page of a multi-page form, to tell whether "Next" moved on.'''
        try: return (self.driver.current_url, tuple(field["label"] for field in read_fields(self.driver)))
        except Exception: return (None, ())
    #>


    #< Finding the form
    def _blocked_reason(self) -> tuple[str, str] | None:
        '''`("login" | "unavailable", reason)` when this page can't be filled as it is, or None.'''
        url = self.driver.current_url.lower()
        text = self._page_text()[:3000]
        for phrase in UNAVAILABLE_PHRASES:
            if phrase in text: return "unavailable", f'The page says "{phrase}".'
        if any(word in url for word in LOGIN_URL_WORDS) or self._visible(["//input[@type='password']"]):
            return "login", "This website needs you to sign in or create an account."
        return None


    def _wait_for_fields(self, site: str, timeout: float = 10) -> list[dict]:
        end = time() + timeout
        fields = []
        while time() < end:
            fields = read_fields(self.driver)
            if self._is_form(fields, site): return fields
            sleep(1)
        return fields


    _CANDIDATE_JS = r'''
    const el = arguments[0];
    const form = el.closest('form');
    const vis = e => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
    const formFields = form ? [...form.querySelectorAll('input:not([type=hidden]):not([type=search]):not([type=submit]):not([type=button]), textarea, select')].filter(vis).length : 0;
    return {formFields, inMenu: !!el.closest('nav, header, footer, [role=navigation], [class*="menu"], [class*="navbar"]')};
    '''


    def _best_apply_button(self, site: str) -> WebElement | None:
        '''
        The page's main "Apply" button. Exact texts ("Apply", "Apply Job", "I'm interested") beat longer ones ("Apply for Jobs"),
        links in menus / headers come last. Never a button of a form that has fields: that would be its submit button.
        '''
        xpaths = OPEN_FORM_BUTTONS + ([APPLY_LINKS] if site == "other" else [])
        scored = []
        for xpath in xpaths:
            for candidate in self.driver.find_elements(By.XPATH, xpath):
                try:
                    text = " ".join((candidate.text or candidate.get_attribute("value") or "").lower().split())
                    if not candidate.is_displayed() or not text or len(text) > 60 or re.search(r'\b(applied|easy apply|how to apply|apply filter|applying)\b', text): continue
                    tag = candidate.tag_name.lower()
                    href = (candidate.get_attribute("href") or "").lower() if tag == "a" else ""
                    if tag == "a" and (href.startswith(("mailto:", "tel:", "javascript:")) or "linkedin.com" in href): continue
                    info = self.driver.execute_script(self._CANDIDATE_JS, candidate) or {}
                    if tag != "a" and info.get("formFields", 0) > 0: continue     # A real form's own button, would send it empty
                    score = 0 if text.rstrip("!").replace("’", "'") in APPLY_TEXTS else (1 if len(text.split()) <= 4 else 2)
                    if info.get("inMenu"): score += 3
                    if re.search(r'/jobs/?$|/careers/?$', href): score += 2   # Links back to the list of jobs
                    scored.append((score, len(scored), candidate))
                except Exception: pass
        return min(scored)[2] if scored else None


    def _follow_apply_link(self, site: str) -> bool:
        '''
        Clicks "Apply" on pages that only describe the job. Links are opened directly, new tabs are followed.
        Never clicks a button inside a form: that would be the form's own submit button and would send an empty application.
        '''
        element = self._best_apply_button(site)
        if element is None: return False
        text = element.text.strip()
        href = element.get_attribute("href") if element.tag_name.lower() == "a" else None
        before = set(self.driver.window_handles)
        if href and href.startswith("http") and href.split("#")[0] != self.driver.current_url.split("#")[0]:
            print_lg(f'Following "{text}": {href}')
            self.driver.get(href)
        else:
            print_lg(f'Clicking "{text}"')
            _click(self.driver, element)
            sleep(2)
            opened = [handle for handle in self.driver.window_handles if handle not in before]
            if opened: self.driver.switch_to.window(opened[-1])
        self._wait_until_loaded()
        return True


    def _find_form(self, result: ApplyResult, context: dict) -> tuple[str | None, list[dict], str | None]:
        '''
        Opens the application form: follows up to `MAX_LINK_HOPS` "Apply" links and gets past a sign-in wall once.
        Returns `(site, fields, manual_reason)`. `manual_reason` is set when the link should be saved for you instead.
        '''
        site, fields = None, []
        hops, signed_in = 0, False
        while True:
            site, form_url = detect_site(self.driver)
            site = site or "other"
            result.site, result.url = site, self.driver.current_url
            if site not in self.enabled_sites:
                host = urlparse(result.url).netloc or result.url
                return site, [], f'{host} ({site}) is not filled automatically.'
            blocked = self._blocked_reason()
            if blocked:
                kind, reason = blocked
                if kind == "unavailable" or signed_in: return site, [], reason
                problem = self._get_past_login(context)
                if problem: return site, [], problem
                signed_in = True
                if self._blocked_reason() is None and self._is_form(read_fields(self.driver), site): continue   # Landed on the form
                print_lg("Signed in, opening the job link again")
                self.driver.get(context["job_link"])
                self._wait_until_loaded()
                continue
            target = application_form_url(site, form_url)
            if target != self.driver.current_url:
                self.driver.get(target)
                self._wait_until_loaded()
                result.url = self.driver.current_url
            self._checkpoint()
            fields = self._wait_for_fields(site)
            if self._is_form(fields, site):
                side_form = self._side_form(fields) if site == "other" else None
                if side_form:
                    # A search box / "Join our Talent Community" / "Send us a message" form next to the job: the application is behind the Apply button
                    print_lg(f"This form is {side_form}, looking for the Apply button instead")
                    if hops < MAX_LINK_HOPS and self._follow_apply_link(site):
                        hops += 1
                        continue
                    return site, [], f"Only {side_form} on this page, no application form."
                return site, fields, None
            late_site, _ = detect_site(self.driver)   # Embedded forms (Eg: Greenhouse on a company page) can load late
            if late_site and late_site != site and hops < MAX_LINK_HOPS:
                hops += 1
                continue
            if hops >= MAX_LINK_HOPS or not self._follow_apply_link(site): break
            hops += 1
        if site == "other": return site, [], "No application form found on this page."
        return site, fields, None
    #>


    #< Signing up / signing in
    def _get_past_login(self, context: dict) -> str | None:
        '''Signs in, or creates an account if there isn't one yet. Returns None when past the sign-in wall, else why not.'''
        url = self.driver.current_url
        if not (self.portal_password and self.portal_email and self.accounts is not None):
            return "This website needs an account. Add an email and password in config/portal_login.py to let the bot sign up and sign in."
        if not is_secure_page(url):
            return "This sign-in page isn't secure (not https), the bot won't type your password there."
        tried = {"signin": 0, "email": 0, "signup": 0, "verify": 0}
        wants_signup = not self.accounts.has_account(url)
        for step in range(MAX_ACCOUNT_STEPS):
            self._checkpoint()
            kind = auth_page_kind(self.driver)
            if kind is None:
                if self._blocked_reason() is None:
                    self.accounts.mark(url, self.portal_email, "created" if tried["signup"] and not tried["signin"] else "signed_in")
                    print_lg(f"Signed in on {site_key(url)}")
                    return None
                return "Couldn't get past the sign-in page."
            if kind == "oauth_only": return "This website only offers 'Sign in with Google / LinkedIn', the bot can't use that."
            if kind == "verify":
                if tried["verify"] >= self.max_fill_attempts or not self._verify_email(): return "Email verification wasn't completed."
                tried["verify"] += 1
                continue
            if kind in ("signin", "email_first"):
                # No account yet: look for the "Create account" link first
                if wants_signup and tried["signup"] == 0 and self._open_link(SIGNUP_LINKS): continue
                counter = "email" if kind == "email_first" else "signin"   # Email on one screen, password on the next
                if tried[counter] >= self.max_fill_attempts: return "Couldn't sign in (wrong password, or the account doesn't exist)."
                tried[counter] += 1
                self._sign_in()
                if any(phrase in self._page_text() for phrase in NO_ACCOUNT_PHRASES) and tried["signup"] == 0:
                    wants_signup = True
                    self._open_link(SIGNUP_LINKS)
                continue
            if kind == "signup":
                if tried["signup"] >= self.max_fill_attempts: return "Couldn't create an account."
                tried["signup"] += 1
                problem = self._sign_up(context)
                if problem: return problem
                if any(phrase in self._page_text() for phrase in ACCOUNT_EXISTS_PHRASES):
                    wants_signup = False
                    self.accounts.mark(url, self.portal_email, "created")
                    self._open_link(SIGNIN_LINKS)
                continue
        return "Too many sign-in steps."


    def _open_link(self, texts: list[str]) -> bool:
        link = self._button_with_text(texts) or self._button_with_text(texts, exact=False)
        if link is None: return False
        print_lg(f'Clicking "{link.text.strip() or texts[0]}"')
        _click(self.driver, link)
        self._wait_until_loaded(10)
        return True


    def _account_field(self, kinds: tuple, pattern: str) -> WebElement | None:
        for element in self.driver.find_elements(By.XPATH, "//input"):
            try:
                if not element.is_displayed(): continue
                kind = (element.get_attribute("type") or "text").lower()
                hints = " ".join(element.get_attribute(a) or "" for a in ("name", "id", "placeholder", "autocomplete", "aria-label")).lower()
                if kind in kinds or (kind in ("text", "") and re.search(pattern, hints)): return element
            except Exception: pass
        return None


    def _press_primary(self, texts: list[str], near: WebElement | None) -> None:
        '''Clicks the form's main button (its submit button, else a button with one of `texts`), or presses Enter.'''
        button = None
        if near is not None:
            try: button = self.driver.execute_script("const f = arguments[0].closest('form'); return f ? f.querySelector('button[type=submit], input[type=submit], button:not([type])') : null", near)
            except Exception: button = None
        button = button or self._button_with_text(texts)
        if button is not None: _click(self.driver, button)
        elif near is not None: near.send_keys(Keys.ENTER)
        self._wait_until_loaded(10)
        sleep(2)


    def _sign_in(self) -> None:
        email_box = self._account_field(("email",), r'e-?mail|user|login')
        password_box = self._account_field(("password",), r'$^')
        if email_box is not None:
            email_box.send_keys(Keys.CONTROL, "a"); email_box.send_keys(Keys.DELETE); email_box.send_keys(self.portal_email)
        if password_box is not None:
            password_box.send_keys(Keys.CONTROL, "a"); password_box.send_keys(Keys.DELETE); password_box.send_keys(self.portal_password)
        print_lg(f"Signing in on {site_key(self.driver.current_url)} as {self.portal_email}")
        self._press_primary(SIGNIN_BUTTONS, password_box or email_box)


    def _sign_up(self, context: dict) -> str | None:
        '''Fills the create-account form (password boxes get your portal password, the rest the usual answers) and sends it.'''
        host = site_key(self.driver.current_url)
        result = ApplyResult("failed", self.driver.current_url)
        account_context = dict(context, account=True)
        password_box = None
        for field in read_fields(self.driver):
            if field["kind"] == "password":
                try:
                    password_box = self.driver.find_element(By.CSS_SELECTOR, f'[data-aap="{field["aap"]}"]')
                    fill_field(self.driver, field, self.portal_password)
                except Exception: pass
                continue
            self._answer_field(field, account_context, result)
        if not self._fill_missing_required(account_context, result): return f"Couldn't fill the sign-up form on {host}."
        if not self.confirm_submit(f"Create an account on {host} with {self.portal_email} (needed before applying)"):
            return "You chose not to create an account."
        print_lg(f"Creating an account on {host} with {self.portal_email}")
        self._press_primary(SIGNUP_BUTTONS, password_box)
        return None


    def _verify_email(self) -> bool:
        '''The website emailed a code or a link. Asks you for the code, or to click the link. Skipping moves on to the next job.'''
        host = site_key(self.driver.current_url)
        code_box = self._account_field(("tel", "number"), r'code|otp|token|pin|verif')
        boxes = [b for b in self.driver.find_elements(By.XPATH, "//input[@maxlength='1']") if b.is_displayed()]
        if code_box is not None or boxes:
            code = self.resolver.ask_user(f"{host} sent a verification code to {self.portal_email}. Type it here (or Skip to move on):", "text", allow_save=False)
            if not code: return False
            target = code_box if code_box is not None else boxes[0]
            target.send_keys(code.strip())   # Single-letter boxes move to the next box by themselves
            self._press_primary(["verify", "submit", "continue", "confirm", "next"], target)
            return True
        if not self.popups_enabled: return False
        choice = pyautogui.confirm(f"{host} sent a verification link to {self.portal_email}.\n\nOpen your email, click the link, then click \"Done\".",
                                   "Verify your email", ["Done", "Skip this job"])
        if choice != "Done": return False
        self.driver.get(self.driver.current_url)
        self._wait_until_loaded()
        return True
    #>


    #< Filling
    def _upload_resume(self, fields: list[dict], result: ApplyResult) -> bool:
        for field in fields:
            if field["kind"] != "file": continue
            path = profile_answer(field, self.resume_path)
            if not path: continue
            if fill_field(self.driver, field, path):
                print_lg(f'Uploaded resume to "{field["label"] or "file field"}"')
                result.questions.add((field["label"] or "Resume", path, "file", "profile"))
                self._wait_until_stable()   # Some websites read the resume and fill the form a few seconds later
                return True
        return False


    def _wait_until_stable(self, timeout: float = 25, quiet: float = 4, minimum: float = 6) -> None:
        '''Waits until the form stops changing (at least `minimum` seconds), so the bot doesn't type before the website overwrites the fields.'''
        start = time()
        last, same_since = None, time()
        while time() - start < timeout:
            self._checkpoint()
            snapshot = tuple((field["label"], field["value"]) for field in read_fields(self.driver))
            busy = re.search(r'\b(parsing|uploading|analy[sz]ing|processing) (your )?(resume|cv|file)', self._page_text()[:4000])
            if snapshot != last or busy: last, same_since = snapshot, time()
            elif time() - start >= minimum and time() - same_since >= quiet: return
            sleep(1)


    def _restore_cleared(self) -> None:
        '''Some websites clear what was typed (Eg: when they finish reading the resume, or re-render). Types those fields again once.'''
        if not self._typed: return
        sleep(1.5)
        for field in read_fields(self.driver):
            key = field["label"] or field["name"]
            if key not in self._typed or field["value"]: continue
            kind, answer = self._typed[key]
            if kind != field["kind"] or kind not in TEXT_KINDS: continue
            print_lg(f'The page cleared "{key}", typing it again')
            fill_field(self.driver, field, answer)


    def _answer_field(self, field: dict, context: dict, result: ApplyResult) -> None:
        self._checkpoint()
        kind = field["kind"]
        label = field["label"] or field.get("placeholder") or ""
        if not label and kind == "tel": label = "Phone"   # Phone boxes with only a country-code flag next to them
        if not label or kind in ("file", "password"): return   # Passwords are only typed by the sign-up / sign-in step
        profile = profile_answer(field, self.resume_path, context.get("job_location", ""), context["job"].get("job_title", ""))
        if context.get("account") and profile is not None and (kind == "email" or re.search(r'\be-?mail\b', label.lower())):
            profile = self.portal_email   # Accounts use the portal email, so sign in works next time
        elif context.get("account") and profile is None and self.portal_email and re.search(r'\buser ?name\b|\buser ?id\b|\blogin id\b', label.lower()):
            profile = self.portal_email.split("@")[0]

        # Keep what's already filled (Eg: pre-filled from your resume), unless it's a profile detail we know better
        if field["value"]:
            if profile is None or kind not in TEXT_KINDS or field["value"].strip() == str(profile).strip(): return

        if kind == "checkbox":
            if profile == "check" and fill_field(self.driver, field, "check"):
                result.questions.add((label, "Checked", kind, "profile"))
            return

        options = field["options"]
        if kind == "combobox" and not options:
            # Searchable dropdowns: try typing a known answer first, only read the options if needed
            answer = self.resolver.resolve(label, "text", None, profile_answer=profile, required=False, **context["job"])
            if answer and fill_field(self.driver, field, answer):
                result.questions.add((label, answer, kind, self.resolver.last_source))
                return
            options = read_combobox_options(self.driver, field)
            if not options and not field["required"]: return
            field = dict(field, options=options)

        question_type = "single_select" if options else ("textarea" if kind == "textarea" else "text")
        if options and profile is not None and match_option(str(profile), options) is None:
            # "Delhi" isn't a choice of "Region of Residence": try "India", "Asia"...; "0" years isn't one of "Fresher / 1-2 years..."
            profile = next((alt for alt in profile_alternatives(field, context.get("job_location", "")) if match_option(alt, options)), profile)
        job = context["job"]
        # Saved answers, profile, AI. Then a safe default ("Yes" to "Are you willing to work from the office?") before asking you
        answer = self.resolver.resolve(label, question_type, options or None, profile_answer=profile, required=field["required"], popup=False, **job)
        if answer is None:
            answer = fallback_answer(field, options or None, context.get("job_location", ""))
            if answer is not None:
                self.resolver.last_source = "default"
                print_lg(f'Answered "{label}" with the usual answer: "{answer}"')
        if answer is None and field["required"]:
            answer = self.resolver.ask_user(label, question_type, options or None, job.get("company", ""), job.get("job_title", ""))
        if answer is None:
            if field["required"]: print_lg(f'No answer for required question "{label}"')
            result.questions.add((label, "Unanswered", kind, None))
            return
        if options and kind != "combobox":
            answer = match_option(answer, options) or answer
        # Phone boxes that show a "+1" / "+91" country code want the number with its country code
        if (kind == "tel" or re.search(r'\b(phone|mobile)\b', label.lower())) and not str(answer).startswith("+") \
                and ((field["value"] or "").strip().startswith("+") or (field.get("placeholder") or "").strip().startswith("+")):
            answer = international_phone(answer)
        if fill_field(self.driver, field, answer):
            result.questions.add((label, answer, kind, self.resolver.last_source))
            self._typed[field["label"] or field["name"] or label] = (field["kind"], answer)
        else:
            print_lg(f'Could not fill "{label}" with "{answer}"')
            result.questions.add((label, f"Failed to fill: {answer}", kind, self.resolver.last_source))


    def _missing_required(self) -> list[dict]:
        missing = []
        for field in read_fields(self.driver):
            if not field["required"] or field["value"] or field["kind"] == "password": continue
            if field["kind"] == "button_choice": continue   # Selected state isn't reliable to read
            if field["kind"] == "file" and "resume" not in field["label"].lower() and "cv" not in field["label"].lower(): continue
            missing.append(field)
        return missing


    def _fill_missing_required(self, context: dict, result: ApplyResult) -> bool:
        '''
        Tries again (up to `max_fill_attempts` in total) for required fields that are still empty. Never waits for you:
        returns False when some can't be filled, so the bot moves to the next application.
        '''
        for attempt in range(1, self.max_fill_attempts):
            missing = self._missing_required()
            if not missing: return True
            for field in missing:
                self._answer_field(field, context, result)
        missing = self._missing_required()
        if not missing: return True
        names = ", ".join(f'"{field["label"] or field["name"] or field["kind"]}"' for field in missing)
        print_lg(f"Couldn't fill required fields after {self.max_fill_attempts} tries: {names}. Moving to the next application.")
        result.message = f"Couldn't fill required fields: {names}."
        return False


    def _needs_upload(self, site: str) -> bool:
        '''Google Forms file questions only work when signed in to Google, the bot can't do those.'''
        return site == "googleforms" and self._visible(["//*[@role='button'][normalize-space(.)='Add file']"]) is not None


    def _fill_pages(self, site: str, fields: list[dict], context: dict, result: ApplyResult) -> tuple[str, str]:
        '''
        Fills every page of the form until its Submit button shows. Returns `(state, message)`:
        "ready" (Submit is showing), "submitted" (a step button already sent it), "discarded" (you said no) or "error".
        '''
        uploaded = self._upload_resume(fields, result)
        if uploaded: fields = read_fields(self.driver)
        elif self.resume_path is None and any(field["kind"] == "file" for field in fields): print_lg("Resume file not found, check `default_resume_path` in config/questions.py")
        for page in range(1, MAX_PAGES + 1):
            self._checkpoint()
            focus_browser(self.driver)
            self._typed = {}
            for field in fields:
                self._answer_field(field, context, result)
            self._restore_cleared()
            if not self._fill_missing_required(context, result): return "error", result.message or "Required fields left empty."
            if self._needs_upload(site): return "error", "The Google Form asks for a file upload, which needs a Google sign-in."
            if self._submit_button(site) is not None: return "ready", ""
            next_button = self._visible(NEXT_BUTTONS)
            if next_button is None: return "error", "Couldn't find the Submit or Next button."
            # "Continue" / "Proceed" may be the final button that sends the application: ask first, like before Submit
            button_text = " ".join((next_button.text or next_button.get_attribute("value") or "").lower().split())
            maybe_final = button_text in MAYBE_FINAL_TEXTS
            if maybe_final and not self.confirm_submit(f'{context["job"]["job_title"]} @ {context["job"]["company"]} ({site}). The "{button_text.title()}" button may send the application.'):
                return "discarded", "You chose not to submit."
            start_url = self.driver.current_url
            for attempt in range(self.max_fill_attempts):
                signature = self._signature()
                _click(self.driver, next_button)
                self._wait_until_loaded(8)
                alert = self._take_alert()
                if alert and not self._tick_consent_boxes(alert) and attempt == self.max_fill_attempts - 1:
                    return "error", f'The website said: "{alert}"'
                if self._confirmed(start_url, site):
                    print_lg(f'The "{button_text}" button sent the application.')
                    return "submitted", ""
                if self._signature() != signature: break
                if attempt == self.max_fill_attempts - 1: return "error", f"Stuck on page {page}, the form didn't accept the answers after {self.max_fill_attempts} tries."
                print_lg("Form didn't move to the next page:", visible_errors(self.driver))
                if not self._fill_missing_required(context, result): return "error", result.message or "Required fields left empty."
                next_button = self._visible(NEXT_BUTTONS)
                if next_button is None: return "error", "Couldn't find the Next button."
            print_lg(f"Moved to page {page + 1} of the form")
            fields = read_fields(self.driver)
            if not uploaded and self._upload_resume(fields, result):
                uploaded = True
                fields = read_fields(self.driver)
        return "error", f"The form has more than {MAX_PAGES} pages."
    #>


    #< Submitting
    def _handle_verification_code(self) -> bool:
        '''Some websites (Greenhouse) email a code after Submit. Asks you for it and types it in.'''
        text = self._page_text()
        if "code" not in text or not any(word in text for word in ("verification", "security code", "sent to", "check your email", "enter the code")): return False
        code_fields = [f for f in read_fields(self.driver) if f["kind"] in TEXT_KINDS and not f["value"] and re.search(r'code', f"{f['label']} {f['name']} {f['id']} {f.get('placeholder', '')}", re.I)]
        if not code_fields: return False
        code = self.resolver.ask_user("The website emailed you a verification code. Please type it here:", "text", allow_save=False)
        if not code: return False
        fill_field(self.driver, code_fields[0], code)
        sleep(1)
        button = self._visible(["//button[contains(., 'Verify') or contains(., 'Submit') or contains(., 'Confirm') or contains(., 'Continue')]"])
        if button: _click(self.driver, button)
        return True


    def _confirmed(self, start_url: str, site: str) -> bool:
        url = self.driver.current_url.lower()
        if url != start_url.lower() and any(word in url for word in CONFIRMATION_URL_WORDS): return True
        text = self._page_text()
        if any(phrase in text for phrase in CONFIRMATION_PHRASES):
            return url != start_url.lower() or self._submit_button(site) is None
        return False


    def _submit(self, site: str, context: dict, result: ApplyResult) -> bool:
        start_url = self.driver.current_url
        for attempt in range(self.max_fill_attempts):
            button = self._submit_button(site)
            if not button:
                result.message = "Couldn't find the Submit button."
                return self._confirmed(start_url, site)
            _click(self.driver, button)
            end, alert = time() + 20, None
            while time() < end:
                sleep(1)
                try:
                    alert = self._take_alert()
                    if alert: break
                    if self._confirmed(start_url, site): return True
                    if captcha_visible(self.driver):
                        if not self._human_help("Please solve the CAPTCHA in the browser tab, and click Submit again if needed."):
                            result.message = "CAPTCHA needed and popups are disabled."
                            return False
                        end = time() + 20
                    elif self._handle_verification_code():
                        end = time() + 20
                except UnexpectedAlertPresentException as e:
                    alert = e.alert_text or "The website showed an alert."
                    break
            if alert:   # Eg: "Please acknowledge the terms.": tick the box and press Submit again
                if attempt < self.max_fill_attempts - 1 and self._tick_consent_boxes(alert): continue
                result.message = f'The website said: "{alert}"'
                return False
            # Only retry when the form is clearly still waiting for input, never re-click after a possible success
            errors = visible_errors(self.driver)
            missing = self._missing_required()
            if errors: print_lg("Form shows errors after Submit:", errors)
            ticked = bool(errors) and attempt < self.max_fill_attempts - 1 and self._tick_consent_boxes(" ".join(errors))   # "You must accept the terms"
            if attempt == self.max_fill_attempts - 1 or not (errors or missing or ticked) or self._submit_button(site) is None: break
            if not self._fill_missing_required(context, result): break
        result.message = result.message or "No confirmation page after Submit."
        return False
    #>


    def apply(self, link: str, *, job_id: str, title: str, company: str, description: str | None = None, job_location: str = "") -> ApplyResult:
        '''Opens `link` in a new tab and applies. Closes the tabs it opened and returns to the tab that was active before.'''
        driver = self.driver
        home_tab = driver.current_window_handle
        start_tabs = set(driver.window_handles)
        result = ApplyResult("failed", link)
        context = {"job_link": link, "job_location": job_location, "job": {"company": company, "job_title": title, "job_description": description}}
        keep_tab = not self.close_tabs      # Keep the tab open for you when the bot couldn't finish
        self.resolver.start_job()
        if self.failed_forms.get(form_key(link), 0) >= MAX_FORM_FAILURES:
            result.status = "manual"
            result.message = f"This form failed {self.failed_forms[form_key(link)]} times before (for other jobs too). Saved the link for you to apply by hand."
            print_lg(result.message, link)
            return result
        try:
            driver.switch_to.new_window("tab")
            driver.get(link)
            self._wait_until_loaded()

            site, fields, manual_reason = self._find_form(result, context)
            if manual_reason:
                result.status = "discarded" if manual_reason.startswith("You chose") else "manual"
                result.message = manual_reason if result.status == "discarded" else manual_reason + " Saved the link for you to apply by hand."
                print_lg(result.message, result.url)
                return result
            if not self._fillable(fields):
                result.message = "Couldn't find the application form."
                result.screenshot = self.screenshot(job_id, "Normal Apply - form not found")
                return result

            print_lg(f'Normal Apply on {site}: {result.url}')
            if captcha_visible(driver) and not self._human_help("Please solve the CAPTCHA in the browser tab."):
                result.message = "CAPTCHA needed and popups are disabled."
                return result

            state, problem = self._fill_pages(site, fields, context, result)
            result.url = driver.current_url
            if state == "submitted":
                result.status = "submitted"
                keep_tab = False
                return result
            if state == "discarded":
                result.status, result.message, keep_tab = "discarded", problem, False
                return result
            if state == "error":
                result.message = problem
                result.screenshot = self.screenshot(job_id, "Normal Apply - " + re.sub(r'[^\w ,-]', '', problem)[:60])
                return result

            if not self.confirm_submit(f"{title} @ {company} ({site})"):
                result.status = "discarded"
                result.message = "You chose not to submit."
                keep_tab = False
                return result

            if self._submit(site, context, result):
                result.status = "submitted"
                keep_tab = False
                print_lg(f'Submitted application on {site} for "{title} | {company}"')
                return result

            # Couldn't confirm by ourselves, the user can see the tab
            if self.popups_enabled and pyautogui.confirm(f"Couldn't confirm the application for {title} @ {company} went through.\n\nLook at the browser tab. Was it submitted?", "Did it submit?", ["Yes", "No"]) == "Yes":
                result.status = "submitted"
                keep_tab = False
                return result
            result.screenshot = self.screenshot(job_id, "Normal Apply - not confirmed")
            return result
        except SkipJob:
            result.status, result.message = "skipped", "You skipped this job from the control window."
            print_lg(result.message)
            return result
        except UnexpectedAlertPresentException as e:
            result.message = f'The website said: "{e.alert_text}"'
            print_lg(result.message)
            return result
        except Exception as e:
            result.message = f"Normal Apply error: {str(e).splitlines()[0][:200] if str(e) else type(e).__name__}"
            ours = [frame for frame in traceback.extract_tb(e.__traceback__) if "site-packages" not in frame.filename]   # Our line, not Selenium's
            where = f" (at {os.path.basename(ours[-1].filename)}:{ours[-1].lineno}, {ours[-1].name})" if ours else ""
            print_lg(result.message + where)
            try: result.screenshot = self.screenshot(job_id, "Normal Apply - error")
            except Exception: pass
            return result
        finally:
            if result.status in ("failed", "submitted") and not re.search(r'session|no such window|internet|disconnected', result.message, re.I):
                self._note_form_result([link, result.url], failed=result.status == "failed")
            try: current = driver.current_window_handle
            except Exception: current = None
            for handle in list(driver.window_handles):
                if handle in start_tabs or (keep_tab and handle == current): continue
                try:
                    driver.switch_to.window(handle)
                    driver.close()
                except Exception: pass
            try: driver.switch_to.window(home_tab)
            except Exception: pass
