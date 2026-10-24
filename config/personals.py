'''
License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html

version:    2024.11.28.16.00
'''


# DEFAULTS ONLY. Your details go in the dashboard (user_data/settings.json), never in this file: it is shared in git.
###################################################### CONFIGURE YOUR TOOLS HERE ######################################################


# >>>>>>>>>>> Easy Apply Questions & Inputs <<<<<<<<<<<

# Your legal name
first_name = "First"                 
middle_name = ""            
last_name = "Last"                

# Phone number (required), make sure it's valid.
email = ""                          # Email for company websites (Normal Apply). If "", your LinkedIn login email from secrets.py is used

phone_number = "9876543210"       

# What is your current city?
current_city = ""          # "City Name" or "" to leave this question unanswered
'''
Note: If left empty as "", the bot will fill in location of jobs location.
'''

# Address, not so common question but some job applications make it required!
street = ""
state = ""
zipcode = ""
country = ""

## US Equal Opportunity questions
# What is your ethnicity or race? If left empty as "", tool will not answer the question. However, note that some companies make it compulsory to be answered
ethnicity = "Decline"              # "Decline", "Hispanic/Latino", "American Indian or Alaska Native", "Asian", "Black or African American", "Native Hawaiian or Other Pacific Islander", "White", "Other"

# How do you identify yourself? If left empty as "", tool will not answer the question. However, note that some companies make compulsory to be answered
gender = "Decline"                 # "Male", "Female", "Other", "Decline" or ""

# Are you physically disabled or have a history/record of having a disability? If left empty as "", tool will not answer the question. However, note that some companies make it compulsory to be answered
disability_status = "Decline"      # "Yes", "No", "Decline"

veteran_status = "Decline"         # "Yes", "No", "Decline"
##


'''
For string variables followed by comments with options, only use the answers from given options.
Some valid examples are:
* variable1 = "option1"         # "option1", "option2", "option3" or ("" to not select). Answers are case sensitive.#
* variable2 = ""                # "option1", "option2", "option3" or ("" to not select). Answers are case sensitive.#

Other variables are free text. No restrictions other than compulsory use of quotes.
Some valid examples are:
* variable3 = "Random Answer 5"         # Enter your answer. Eg: "Answer1", "Answer2"

Invalid inputs will result in an error!
'''




############################################################################################################
'''
Thank you for using Apply & Pray! Wishing you the best in your job hunt.

Project: https://github.com/saif-siddiqui06/Apply-and-Pray
It builds on the open-source work of Shubham and other contributors: see CREDITS.md.
'''
############################################################################################################


# Your own values (user_data/settings.json, passwords in the keyring) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "personals")
