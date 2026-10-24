# DEFAULTS ONLY. Your choices go in the dashboard (user_data/settings.json), never in this file: it is shared in git.
'''
Author:     Shubham
LinkedIn:   https://www.linkedin.com/in/shubham-sunil-kumar-333547133/

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html

GitHub:     https://github.com/theturkishangorashiro-art/apply-and-pray

Support me: https://github.com/sponsors/theturkishangorashiro-art
'''


###################################################### CONFIGURE YOUR BOT HERE ######################################################

# >>>>>>>>>>> LinkedIn Settings <<<<<<<<<<<

# Keep the External Application tabs open?
close_tabs = False                  # True or False, Note: True or False are case-sensitive
'''
Note: RECOMMENDED TO LEAVE IT AS `True`, if you set it `False`, be sure to CLOSE ALL TABS BEFORE CLOSING THE BROWSER!!!
'''

# Follow easy applied companies
follow_companies = False            # True or False, Note: True or False are case-sensitive

## Upcoming features (In Development)
# # Send connection requests to HR's 
# connect_hr = True                  # True or False, Note: True or False are case-sensitive

# # What message do you want to send during connection request? (Max. 200 Characters)
# connect_request_message = ""       # Leave Empty to send connection request without personalized invitation (recommended to leave it empty, since you only get 10 per month without LinkedIn Premium*)

# Do you want the program to run continuously until you stop it? (Beta)
run_non_stop = False                # True or False, Note: True or False are case-sensitive
'''
Note: Will be treated as False if `run_in_background = True`
'''
alternate_sortby = True             # True or False, Note: True or False are case-sensitive
cycle_date_posted = True            # True or False, Note: True or False are case-sensitive
stop_date_cycle_at_24hr = True      # True or False, Note: True or False are case-sensitive





# >>>>>>>>>>> APPLY MODES <<<<<<<<<<<

# Which applications should the bot do?
apply_mode = "ask"                 # "easy", "normal", "both" or "ask"
'''
* "easy"   - Only LinkedIn Easy Apply jobs (the form opens inside LinkedIn).
* "normal" - Only jobs where Apply opens the company's own website. The bot fills that form.
* "both"   - Easy Apply when LinkedIn shows it, Normal Apply otherwise.
* "ask"    - Shows a popup at startup to choose one of the above.
Note: "easy" overrides `easy_apply_only` in search.py to True, "normal" and "both" override it to False.
'''

# Company hiring websites the bot fills automatically in Normal Apply.
normal_apply_sites = ["greenhouse", "lever", "ashby", "googleforms", "other"]     # Any of "greenhouse", "lever", "ashby", "googleforms", "other" or [] to only collect links
'''
* "googleforms" - Google Forms (very common for internships in India).
* "other"       - Any other website that shows a plain application form. The bot follows "Apply" links to find it.
Websites that need a login or an account (Workday, iCIMS, Taleo, sign-up pages...), closed forms and pages without a form
are never filled: the link is saved in the applied jobs excel so you can apply by hand.
'''

# If the bot doesn't know an answer, should it ask you in a popup instead of guessing?
ask_instead_of_guessing = True      # True or False, Note: True or False are case-sensitive
'''
Note: Answers you give with "Save for all jobs" are saved in `saved_answers_file` and reused automatically next time.
If False, the bot guesses like before (Eg: "Yes" for unknown dropdowns, `years_of_experience` for unknown text questions).
Popups are disabled when `run_in_background = True`, so unknown questions are left unanswered.
'''

# How long should a popup wait for your answer? After that the question is skipped and the bot moves on (the job is saved to apply by hand).
popup_timeout_minutes = 1           # Only numbers 0 or more... Don't put in quotes, 0 = wait for ever (the whole run waits for you)

# File where your popup answers are saved. You can open and edit it by hand (it's JSON).
saved_answers_file = "user_data/saved_answers.json"

# Show the small control window with Pause / Resume, Skip this job, Stop after this job and Quit now?
show_control_panel = True           # True or False, Note: True or False are case-sensitive
'''
Note: Pause lets you fill a form yourself in the browser at any stage, click Resume and the bot continues from there.
'''

# Let AI list each job's skills in the applied jobs excel? It uses one AI request per job (Gemini's free tier has a daily limit).
ai_skill_extraction = False          # True or False, Note: True or False are case-sensitive

# Show long AI-written answers (Eg: "Why do you want to work here?") in a popup so you can read / edit them before they're used?
review_ai_answers = False          # True or False, Note: True or False are case-sensitive

# >>>>>>>>>>> SPEED AND DELAYS (change these by hand) <<<<<<<<<<<
'''
Every delay is (min, max) in SECONDS: the bot waits a random time between the two numbers, so it never waits the same time twice.
(0, 0) = no wait. Bigger numbers = slower, but safer for your LinkedIn account.

If LinkedIn shows "We noticed you're applying at a fast pace ... we've briefly paused Easy Apply", the bot stops Easy Apply by itself
(see README). Before the next run, make `delay_after_application` bigger and lower `max_applications_per_hour` / `max_applications_per_day`.
'''
delay_after_application    = (1, 2)  # After each application is sent (Easy Apply or company website)
delay_after_skipped_job    = (1, 2)     # After a job was opened and then skipped or failed (experience too high, form problem...)
delay_before_opening_job   = (1, 2)     # Before clicking the next job in the list, like a person reading the list
delay_between_form_pages   = (1, 2)     # Before clicking Next / Review on each Easy Apply page
delay_before_submit        = (1, 2)     # Before clicking Submit (Easy Apply and company websites)
delay_between_result_pages = (1, 2)    # Before loading the next page of search results
delay_between_searches     = (1, 2)   # Before searching the next job position

# A longer break after every few applications, 0 = never.
break_every_applications = 0          # Only numbers 0 or more... Don't put in quotes
break_minutes = (1, 2)              # (min, max) in MINUTES

# Limits (Easy Apply + Normal Apply together), 0 = no limit.
max_applications_per_hour = 0      # When reached, the bot waits until the oldest application of the last hour is 1 hour old
max_applications_per_day = 0        # When reached, the bot stops for today

# Open the list of jobs to apply by hand (all excels/apply_by_hand.html) at the end of a run if new ones were saved?
open_apply_by_hand_page = True      # True or False, Note: True or False are case-sensitive

# How many times should the bot try to get a form page accepted before giving up and moving to the next application?
max_fill_attempts = 3               # Only numbers greater than 0... Don't put in quotes
'''
Note: Each question is asked at most once per application. If you click "Skip" on a required question, or a field can't be filled
after `max_fill_attempts` tries, the application is skipped (saved in the failed jobs excel) and the bot moves on without waiting for you.
'''





# >>>>>>>>>>> RESUME GENERATOR (Experimental & In Development) <<<<<<<<<<<

# Give the path to the folder where all the generated resumes are to be stored
generated_resume_path = "all resumes/" # (In Development)





# >>>>>>>>>>> Global Settings <<<<<<<<<<<

# Directory and name of the files where history of applied jobs is saved (Sentence after the last "/" will be considered as the file name).
file_name = "all excels/all_applied_applications_history.csv"
failed_file_name = "all excels/all_failed_applications_history.csv"
logs_folder_path = "logs/"

# Set the maximum amount of time allowed to wait between each click in secs
click_gap = 1                       # Enter max allowed secs to wait approximately. (Only Non Negative Integers Eg: 0,1,2,3,....)

# If you want to see Chrome running then set run_in_background as False (May reduce performance). 
run_in_background = False           # True or False, Note: True or False are case-sensitive ,   If True, this will make pause_at_failed_question, pause_before_submit and run_in_background as False

# If you want to disable extensions then set disable_extensions as True (Better for performance)
disable_extensions = False          # True or False, Note: True or False are case-sensitive

# Run in safe mode. Set this true if chrome is taking too long to open or if you have multiple profiles in browser. This will open chrome in guest profile!
safe_mode = True                    # True or False, Note: True or False are case-sensitive

# Do you want scrolling to be smooth or instantaneous? (Can reduce performance if True)
smooth_scroll = False               # True or False, Note: True or False are case-sensitive

# If enabled (True), the program would keep your screen active and prevent PC from sleeping. Instead you could disable this feature (set it to false) and adjust your PC sleep settings to Never Sleep or a preferred time. 
keep_screen_awake = True            # True or False, Note: True or False are case-sensitive (Note: Will temporarily deactivate when any application dialog boxes are present (Eg: Pause before submit, Help needed for a question..))

# Run in undetected mode to bypass anti-bot protections (Preview Feature, UNSTABLE. Recommended to leave it as False)
stealth_mode = True                # True or False, Note: True or False are case-sensitive

# Do you want to get alerts on errors related to AI API connection?
showAiErrorAlerts = False            # True or False, Note: True or False are case-sensitive

# Use ChatGPT for resume building (Experimental Feature can break the application. Recommended to leave it as False) 
# use_resume_generator = False       # True or False, Note: True or False are case-sensitive ,   This feature may only work with 'stealth_mode = True'. As ChatGPT website is hosted by CloudFlare which is protected by Anti-bot protections!











############################################################################################################
'''
THANK YOU for using my tool 😊! Wishing you the best in your job hunt 🙌🏻!

Sharing is caring! If you found this tool helpful, please share it with your peers 🥺. Your support keeps this project alive.

Support my work on <PATREON_LINK>. Together, we can help more job seekers.

As an independent developer, I pour my heart and soul into creating tools like this, driven by the genuine desire to make a positive impact.

Your support, whether through donations big or small or simply spreading the word, means the world to me and helps keep this project alive and thriving.

Gratefully yours 🙏🏻,
Shubham
'''
############################################################################################################


# Your own values (user_data/settings.json) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "settings")
