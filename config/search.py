# DEFAULTS ONLY. Your choices go in the dashboard (user_data/settings.json), never in this file: it is shared in git.



###################################################### LINKEDIN SEARCH PREFERENCES ######################################################

# These Sentences are Searched in LinkedIn
# Enter your search terms inside '[ ]' with quotes ' "searching title" ' for each search followed by comma ', ' Eg: ["Software Engineer", "Software Developer", "Selenium Developer"]
search_terms = ["Software Engineer", "Python Developer"]

'''
Note: Each search uses ONE position from this list, picked at random (randomize_search_order). When it has no more new jobs,
or after `switch_number` applications, the bot searches the next position. "Python Developer Intern" is covered by "Python Developer".
All filters below are put straight into LinkedIn's search address (f_AL=true for Easy Apply, f_E for experience level...), no clicking.
'''

# Newest jobs come first (sort_by = "Most recent"): after this many result pages in a row with no new job, go to the next search. 0 = all pages
stop_after_pages_without_new_jobs = 2   # Only numbers 0 or more... Don't put in quotes

# Skip jobs whose TITLE has one of these words, right from the job list without opening them. [] to turn off.
skip_title_words = ["Senior", "Sr.", "Sr", "Lead", "Manager", "Principal", "Staff", "Architect", "Head", "Director", "VP", "Vice President", "Expert"]

# At most `max_applications_per_company` applications to the same company in the last `avoid_same_company_days` days (0 days = no company limit).
# The same company + same job title (a repost) is always skipped, whatever these say.
avoid_same_company_days = 7        # Only numbers 0 or more... Don't put in quotes
max_applications_per_company = 2   # Only numbers greater than 0... Don't put in quotes

# Try jobs again that were skipped before? If False: jobs that don't fit you (experience, bad words...) are never opened again,
# jobs that failed because of an error (a page that didn't load...) are tried once more.
retry_failed_jobs = False          # True or False, Note: True or False are case-sensitive

# Search location: one place like "India", "Delhi, India" or "Bengaluru". A list of places becomes its country ("Delhi, Noida, India" -> "India"). "" for anywhere.
search_location = "" # "City, state, or zip code" or "" to leave this question unanswered 

# After how many number of applications in current search should the bot switch to next search? 
switch_number = 30                 # Only numbers greater than 0... Don't put in quotes

# Do you want to randomize the search order for search_terms? (Shuffled again on every run, so each run shows different jobs first)
randomize_search_order = True      # True of False, Note: True or False are case-sensitive


# >>>>>>>>>>> Job Search Filters <<<<<<<<<<<
''' 
You could set your preferences or leave them as empty to not select options except for 'True or False' options. Below are some valid examples for leaving them empty:
This is below format: QUESTION = VALID_ANSWER

## Examples of how to leave them empty. Note that True or False options cannot be left empty! 
* question_1 = ""                    # answer1, answer2, answer3, etc.
* question_2 = []                    # (multiple select)
* question_3 = []                    # (dynamic multiple select)

## Some valid examples of how to answer questions:
* question_1 = "answer1"                  # "answer1", "answer2", "answer3" or ("" to not select). Answers are case sensitive.
* question_2 = ["answer1", "answer2"]     # (multiple select) "answer1", "answer2", "answer3" or ([] to not select). Note that answers must be in [] and are case sensitive.
* question_3 = ["answer1", "Random AnswER"]     # (dynamic multiple select) "answer1", "answer2", "answer3" or ([] to not select). Note that answers must be in [] and need not match the available options.

'''

sort_by = "Most recent"                       # "Most recent", "Most relevant" or ("" to not select) 
date_posted = "Past week"         # "Any time", "Past month", "Past week", "Past 24 hours" or ("" to not select)
salary = ""                        # "$40,000+", "$60,000+", "$80,000+", "$100,000+", "$120,000+", "$140,000+", "$160,000+", "$180,000+", "$200,000+"

easy_apply_only = True             # True or False, Note: True or False are case-sensitive

experience_level = ["Internship", "Entry level"]             # (multiple select) "Internship", "Entry level", "Associate", "Mid-Senior level", "Director", "Executive"
job_type = []                      # (multiple select) "Full-time", "Part-time", "Contract", "Temporary", "Volunteer", "Internship", "Other"
on_site = []                       # (multiple select) "On-site", "Remote", "Hybrid"

companies = []                     # (dynamic multiple select) make sure the name you type in list exactly matches with the company name you're looking for, including capitals. 
                                   # Eg: "7-eleven", "Google","X, the moonshot factory","YouTube","CapitalG","Adometry (acquired by Google)","Meta","Apple","Byte Dance","Netflix", "Snowflake","Mineral.ai","Microsoft","JP Morgan","Barclays","Visa","American Express", "Snap Inc", "JPMorgan Chase & Co.", "Tata Consultancy Services", "Recruiting from Scratch", "Epic", and so on...
location = []                      # (dynamic multiple select)
industry = []                      # (dynamic multiple select)
job_function = []                  # (dynamic multiple select)
job_titles = []                    # (dynamic multiple select)
benefits = []                      # (dynamic multiple select)
commitments = []                   # (dynamic multiple select)

under_10_applicants = False        # True or False, Note: True or False are case-sensitive
in_your_network = False            # True or False, Note: True or False are case-sensitive
fair_chance_employer = False       # True or False, Note: True or False are case-sensitive


## >>>>>>>>>>> RELATED SETTING <<<<<<<<<<<


##




## >>>>>>>>>>> SKIP IRRELEVANT JOBS <<<<<<<<<<<
 
# Avoid applying to these companies, and companies with these bad words in their 'About Company' section...
about_company_bad_words = ["Crossover"]       # (dynamic multiple search) or leave empty as []. Ex: ["Staffing", "Recruiting", "Name of Company you don't want to apply to"]

# Skip checking for `about_company_bad_words` for these companies if they have these good words in their 'About Company' section... [Exceptions, For example, I want to apply to "Robert Half" although it's a staffing company]
about_company_good_words = []      # (dynamic multiple search) or leave empty as []. Ex: ["Robert Half", "Dice"]

# Avoid applying to these companies if they have these bad words in their 'Job Description' section...  (In development)
bad_words = ["US Citizen","USA Citizen","No C2C", "No Corp2Corp", ".NET", "Embedded Programming", "PHP", "Ruby", "CNC"]                     # (dynamic multiple search) or leave empty as []. Case Insensitive. Ex: ["word_1", "phrase 1", "word word", "polygraph", "US Citizenship", "Security Clearance"]

# Do you have an active Security Clearance? (True for Yes and False for No)
security_clearance = False         # True or False, Note: True or False are case-sensitive

# Do you have a Masters degree? (True for Yes and False for No). If True, the tool will apply to jobs containing the word 'master' in their job description and if it's experience required <= current_experience + 2 and current_experience is not set as -1. 
did_masters = False                # True or False, Note: True or False are case-sensitive

# Avoid applying to jobs if their required experience is above your current_experience. (Set value as -1 if you want to apply to all ignoring their required experience...)
current_experience = 0             # Integers > -2 (Ex: -1, 0, 1, 2, 3, 4...)

# Still apply when a job asks for up to this many years MORE than you have ("1 year preferred" often accepts freshers)
experience_tolerance = 1           # Only numbers 0 or more... Don't put in quotes
##






############################################################################################################


# Your own values (user_data/settings.json) replace the defaults above. See modules/user_settings.py
from modules.user_settings import apply_user_settings
apply_user_settings(globals(), "search")
