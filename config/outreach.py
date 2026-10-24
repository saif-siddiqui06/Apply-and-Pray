'''
Networking on LinkedIn: connection requests and personal messages (DMs).

DEFAULTS ONLY. Set these in the dashboard (Setup -> Networking).

Why limits: LinkedIn restricts accounts that send too many invitations or messages. The defaults stay well under its limits.
Free accounts can add a personal note to only a few invitations a month, and can message only people they're connected to.
'''

# Do you have LinkedIn Premium? Premium allows many more invitation notes, and InMail to people you're not connected to.
has_premium = False

# Invitation notes you can send in a month. Free accounts get only a few (LinkedIn changes this), Premium many more.
monthly_note_limit = 5              # Only numbers 0 or more... Don't put in quotes

# Who you are and what you're looking for, in 2-3 lines. Every note and message is written from this.
# Eg: "Final-year B.Tech CSE student skilled in Python, ML and SQL, looking for data / ML roles. Built a resume-screening model used by 200+ students."
pitch = ""

# Your college, to find alumni first (people from your college reply more often). "" to skip
college = ""

# How messages sound
message_tone = "professional"       # "professional", "friendly" or "formal"

# Show every invitation / message to you before it's sent (Review Queue). Recommended: True
review_before_send = True           # True or False, Note: True or False are case-sensitive

## Who to connect with
connect_with_hirers = True          # People who posted a job you applied to (the job page's "Meet the hiring team")
connect_with_feed_leads = True      # People whose job post said "DM me / comment" (found by Feed jobs)
hirer_days = 30                     # Only for jobs you applied to in the last ... days
search_recruiters = True            # Search LinkedIn for recruiters at companies you applied to
search_alumni = True                # Search for people from your `college` working at those companies (needs `college`)
max_searches_per_run = 4            # People searches per Networking run (each company is searched once, ever)
people_per_search = 2               # People taken from each search

## Limits
invite_gap_seconds = (40, 120)      # (min, max) random wait between two invitations, like a person
max_invites_per_day = 15            # Only numbers 0 or more... Don't put in quotes
max_invites_per_week = 80           # LinkedIn's own limit is around 100 a week
max_messages_per_day = 20
follow_up_after_days = 6            # One follow-up if there's no reply after this many days, then stop
active_hours = (9, 21)              # (start hour, end hour), 24-hour clock: nothing is sent outside these hours


# Your own values (user_data/settings.json) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "outreach")
