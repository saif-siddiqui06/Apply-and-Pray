'''
Feed jobs: jobs posted as LinkedIn posts ("We're hiring! Fill this form / send your CV to hr@...").

DEFAULTS ONLY. Your values go in user_data/settings.json (section "feed").

The bot searches posts for each of your job titles (`search_terms` in config/search.py) plus `hiring_words`, reads them, and:
* a form / careers link    -> fills it with Normal Apply
* "send your CV to email"  -> writes an email with your resume attached (shown to you first, see config/gmail.py)
* "DM me" / "comment"      -> saves the person for Networking (connection request + message, coming next)
* senior / unrelated       -> skipped, with the reason
Your experience, bad words and blacklisted companies (config/search.py) apply to posts too.
'''

# Added to each job title when searching posts, Eg: "Data Analyst hiring"
hiring_words = "hiring"

# Add your country (from `search_location`) to the post search, so posts from other countries are mostly left out
add_location_to_search = True

# Only posts from this period
date_posted = "past-week"               # "past-24h", "past-week" or "past-month"

# Posts read per job title
max_posts_per_search = 25               # Only numbers greater than 0... Don't put in quotes

# What to do with what's found
apply_to_links = True                   # Fill application forms linked in posts (Normal Apply)
email_applications = True               # Write emails for "send your CV to ..." posts
save_leads = True                       # Save "DM me / comment" posts' authors for Networking


# Your own values (user_data/settings.json) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "feed")
