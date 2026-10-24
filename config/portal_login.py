'''
Email and password the bot uses to SIGN UP and SIGN IN on company job websites (Normal Apply).

DEFAULTS ONLY: set your portal email and password in the dashboard. The password is kept in Windows Credential Manager.

IMPORTANT:
* Use a NEW password that you don't use anywhere else (NOT your Gmail or LinkedIn password). The bot types it into many different job websites.
* The bot only types it on secure (https) pages, never on "Sign in with Google / LinkedIn" pages.
* Websites that send a verification code or link to your email: the bot shows a popup, type the code there or click the link in your email.
* The list of websites where an account was created is kept in user_data/portal_accounts.json (no passwords in it).
'''

# Email for the accounts. If "", your `email` from personals.py is used (or your LinkedIn login email).
portal_email = ""

# Password for new accounts and for signing in. If "", the bot doesn't sign up or sign in: those jobs are saved for you to apply by hand.
# Many websites need 8+ characters with a capital letter, a number and a symbol, Eg: "Jobs#2026apply"
portal_password = ""


# Your own values (user_data/settings.json, passwords in the keyring) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "portal_login")
