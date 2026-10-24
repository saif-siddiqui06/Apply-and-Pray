'''
Gmail, used to apply to jobs posted as "send your CV to hr@company.com" (Feed jobs).

DEFAULTS ONLY. Set your Gmail in the dashboard (Setup -> Gmail). The app password is kept in Windows Credential Manager, never in a file.
'''

# Your Gmail address. Emails are sent from it, with your resume attached.
gmail_address = ""

# A Gmail "app password": 16 letters, made at https://myaccount.google.com/apppasswords (needs 2-Step Verification on).
# It is NOT your normal Gmail password, and you can delete it there any time to cut the bot off.
gmail_app_password = ""

# Added at the end of every email
email_signature = ""

# Show every email to you (dashboard -> Review) before it's sent. Recommended: True
review_before_send = True           # True or False, Note: True or False are case-sensitive

# Most emails the bot may send in one day
max_emails_per_day = 20             # Only numbers greater than 0... Don't put in quotes


# Your own values (user_data/settings.json, the app password in the keyring) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "gmail")
