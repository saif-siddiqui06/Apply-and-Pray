'''
Accounts on company job websites: remembers where an account was created, and recognises sign-in / sign-up / verification pages.

The email and password come from the dashboard (user_data/, password in the keyring). The record of websites lives in user_data/portal_accounts.json
(git-ignored, no passwords in it).
'''

import os
import json
from datetime import datetime
from urllib.parse import urlparse

from selenium.webdriver.remote.webdriver import WebDriver

from modules.helpers import print_lg
from modules.external.sites import OAUTH_HOSTS, VERIFY_PHRASES, LOGIN_URL_WORDS


ACCOUNTS_FILE = "user_data/portal_accounts.json"
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}


def site_key(url: str) -> str:
    '''Website a page belongs to, so "app.alignerr.com" and "www.alignerr.com" share one account: "alignerr.com".'''
    host = urlparse(url or "").netloc.lower().split(":")[0]
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL: return ".".join(parts[-3:])   # Eg: company.co.in
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


class AccountBook:
    '''Websites where the bot created an account or signed in, so next time it signs in instead of signing up.'''
    def __init__(self, path: str = ACCOUNTS_FILE):
        self.path = path
        self._data: dict[str, dict] = {}
        try:
            with open(path, "r", encoding="utf-8") as file:
                self._data = json.load(file).get("accounts", {})
        except FileNotFoundError: pass
        except Exception as e: print_lg(f'Could not read "{path}", starting a new list of accounts.', e)


    def has_account(self, url: str) -> bool:
        return self._data.get(site_key(url), {}).get("status") in ("created", "signed_in")


    def mark(self, url: str, email: str, status: str) -> None:
        '''`status`: "created", "signed_in" or "failed".'''
        key = site_key(url)
        entry = self._data.setdefault(key, {"email": email, "first_seen": datetime.now().isoformat(timespec="seconds")})
        entry.update({"email": email, "status": status, "updated": datetime.now().isoformat(timespec="seconds")})
        try:
            folder = os.path.dirname(self.path)
            if folder: os.makedirs(folder, exist_ok=True)
            with open(self.path + ".tmp", "w", encoding="utf-8") as file:
                json.dump({"version": 1, "accounts": self._data}, file, indent=2)
            os.replace(self.path + ".tmp", self.path)
        except Exception as e:
            print_lg(f'Could not save "{self.path}"', e)



_AUTH_PAGE_JS = r'''
const vis = el => { if (!el) return false; const s = getComputedStyle(el), r = el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
const low = t => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
const inputs = [...document.querySelectorAll('input')].filter(vis);
const passwords = inputs.filter(i => i.type === 'password').length;
const emailLike = inputs.filter(i => i.type === 'email' || /e-?mail|user|login|phone|mobile/i.test((i.name || '') + ' ' + (i.id || '') + ' ' + (i.placeholder || '') + ' ' + (i.getAttribute('autocomplete') || '') + ' ' + (i.getAttribute('aria-label') || ''))).length;
const codeLike = inputs.filter(i => /code|otp|token|pin/i.test((i.name || '') + ' ' + (i.id || '') + ' ' + (i.placeholder || '') + ' ' + (i.getAttribute('autocomplete') || '') + ' ' + (i.getAttribute('aria-label') || '')) || i.maxLength === 1).length;
const buttons = [...document.querySelectorAll('button, [role=button], input[type=submit], a')].filter(vis).map(b => low(b.innerText || b.value || b.getAttribute('aria-label')));
const fields = inputs.filter(i => !['hidden', 'checkbox', 'radio', 'submit', 'button', 'search'].includes(i.type)).length;
return {passwords, emailLike, codeLike, fields, buttons: buttons.filter(b => b && b.length < 50).slice(0, 60), text: low(document.body ? document.body.innerText : '').slice(0, 4000)};
'''


def auth_page_kind(driver: WebDriver) -> str | None:
    '''
    What kind of account page is showing:
    * "oauth_only": only "Sign in with Google / LinkedIn" (or a third-party sign-in page), the bot can't use it
    * "verify": asks for a code or a click on a link sent by email
    * "signup": create-account form (2 password boxes, or 1 with sign-up wording)
    * "signin": email + password form
    * "email_first": sign-in that asks for the email first and the password on the next screen
    * None: not an account page
    '''
    url = driver.current_url.lower()
    host = urlparse(url).netloc
    if any(host == oauth or host.endswith("." + oauth) for oauth in OAUTH_HOSTS): return "oauth_only"
    page = driver.execute_script(_AUTH_PAGE_JS) or {}
    text, buttons = page.get("text", ""), page.get("buttons", [])
    if any(phrase in text for phrase in VERIFY_PHRASES) and page.get("passwords", 0) == 0 and (page.get("codeLike", 0) > 0 or "link" in text):
        return "verify"
    if page.get("passwords", 0) >= 2: return "signup"
    if page.get("passwords", 0) == 1:
        signup_words = ("signup", "sign-up", "register", "create", "join")
        if any(word in url for word in signup_words) or any(b in ("sign up", "create account", "create an account", "register", "join now", "get started") for b in buttons):
            # A sign-in page also often shows a "Create account" link, a separate sign-up form has name fields too
            if page.get("fields", 0) >= 3 or any(word in url for word in signup_words): return "signup"
        return "signin"
    on_login_url = any(word in url for word in LOGIN_URL_WORDS)
    if on_login_url and page.get("emailLike", 0) >= 1 and page.get("fields", 0) <= 2: return "email_first"
    if on_login_url and page.get("fields", 0) == 0 and any(("google" in b or "linkedin" in b or "microsoft" in b) for b in buttons): return "oauth_only"
    return None
