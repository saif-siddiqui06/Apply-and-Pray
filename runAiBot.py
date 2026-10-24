'''
Original author: Shubham
LinkedIn:   https://www.linkedin.com/in/shubham-sunil-kumar-333547133/

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html

Project:    https://github.com/saif-siddiqui06/Apply-and-Pray
Modified and maintained by: Saif Siddiqui (https://github.com/saif-siddiqui06), 2026
Credits:    see CREDITS.md

'''


# Imports
import os
import csv
import re
import time
import pyautogui

# Set CSV field size limit to prevent field size errors
csv.field_size_limit(1000000)  # Set to 1MB instead of default 131KB

import random
from random import choice, shuffle, randint
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse, parse_qs

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, NoSuchWindowException, ElementNotInteractableException, WebDriverException, StaleElementReferenceException, InvalidSessionIdException, TimeoutException

from config.personals import *
from config.questions import *
from config.search import *
from config.secrets import use_AI, username, password, ai_provider
from config.settings import *

from modules.open_chrome import *
from modules.helpers import *
from modules.clickers_and_finders import *
from modules.validator import validate_config
from modules.answer_store import AnswerStore, match_option
from modules.answer_resolver import AnswerResolver
from modules.external.normal_apply import NormalApplier, ApplyResult
from modules import db
from modules.external.form import read_fields, fill_field
from modules.external.profile import resolve_resume_path, profile_answer, EMAIL as profile_email
from modules.external.accounts import AccountBook
from modules.job_history import JobHistory
from modules.resumes.extractor import user_profile_text
from modules.bot_control import BotControl, SkipJob, QuitBot
from modules.pending_links import PendingLinks
from modules.smart_search import plan_searches, covering_positions, linkedin_search_url, with_page, skip_word_in, JOBS_PER_PAGE
from modules.external.form import focus_browser
from collections import Counter
try:
    from config.portal_login import portal_email, portal_password
except ImportError:
    portal_email, portal_password = "", ""

if use_AI:
    from modules.ai.openaiConnections import ai_create_openai_client, ai_extract_skills, ai_answer_question, ai_close_openai_client
    from modules.ai.deepseekConnections import deepseek_create_client, deepseek_extract_skills, deepseek_answer_question
    from modules.ai.geminiConnections import gemini_create_client, gemini_extract_skills, gemini_answer_question

from typing import Literal


pyautogui.FAILSAFE = False
# if use_resume_generator:    from resume_generator import is_logged_in_GPT, login_GPT, open_resume_chat, create_custom_resume


#< Global Variables and logics

if run_in_background == True:
    pause_at_failed_question = False
    pause_before_submit = False
    run_non_stop = False

first_name = first_name.strip()
middle_name = middle_name.strip()
last_name = last_name.strip()
full_name = first_name + " " + middle_name + " " + last_name if middle_name else first_name + " " + last_name

useNewResume = True
randomly_answered_questions = set()

tabs_count = 1
easy_applied_count = 0
normal_applied_count = 0
normal_applier = None
job_history = None     # Jobs handled in earlier runs, see modules/job_history.py
control = BotControl(logs_folder_path)   # Control window: Pause / Resume, Skip this job, Stop after this job, Quit now
pending_links = PendingLinks(os.path.dirname(file_name) or "all excels")   # Jobs to apply by hand, kept after the browser closes
skip_reasons = Counter()   # Why jobs were skipped in this run, shown in the summary
stopwatch = Counter()      # Seconds spent per stage (applied / failed applications / opened then skipped), the rest is searching
run_started = time.time()
quick_skip_count = 0   # Jobs skipped from the job list without opening them
external_jobs_count = 0
failed_count = 0
skip_count = 0
dailyEasyApplyLimitReached = False   # True ends the run (Easy Apply mode): LinkedIn paused Easy Apply or its daily limit is reached
easy_apply_stopped = ""    # LinkedIn's reason for stopping Easy Apply in this run, shown in the summary
applications_since_break = 0

re_experience = re.compile(r'[(]?\s*(\d+)\s*[)]?\s*[-to]*\s*\d*[+]*\s*year[s]?', re.IGNORECASE)

# Monthly amounts are whole numbers: LinkedIn number fields reject "55000.0" or "8333.33" with "Enter a whole number"
desired_salary_lakhs = str(round(desired_salary / 100000, 2))
desired_salary_monthly = str(round(desired_salary/12))
desired_salary = str(desired_salary)

current_ctc_lakhs = str(round(current_ctc / 100000, 2))
current_ctc_monthly = str(round(current_ctc/12))
current_ctc = str(current_ctc)

notice_period_months = str(notice_period//30)
notice_period_weeks = str(notice_period//7)
notice_period = str(notice_period)

aiClient = None
about_company_for_ai = None # TODO extract about company for AI

# Saved answers + "missing detail" popup, shared by Easy Apply and Normal Apply
answer_resolver = AnswerResolver(AnswerStore(saved_answers_file), popups_enabled=not run_in_background)

#>


#< Login Functions
def is_logged_in_LN() -> bool:
    '''
    Function to check if user is logged-in in LinkedIn
    * Returns: `True` if user is logged-in or `False` if not
    '''
    if driver.current_url == "https://www.linkedin.com/feed/": return True
    if try_linkText(driver, "Sign in"): return False
    if try_xp(driver, '//button[@type="submit" and contains(text(), "Sign in")]'):  return False
    if try_linkText(driver, "Join now"): return False
    print_lg("Didn't find Sign in link, so assuming user is logged in!")
    return True


def login_LN() -> None:
    '''
    Function to login for LinkedIn
    * Tries to login using given `username` and `password` from `secrets.py`
    * If failed, tries to login using saved LinkedIn profile button if available
    * If both failed, asks user to login manually
    '''
    # Find the username and password fields and fill them with user credentials
    driver.get("https://www.linkedin.com/login")
    if username == "username@example.com" and password == "example_password":
        pyautogui.alert("User did not configure username and password in secrets.py, hence can't login automatically! Please login manually!", "Login Manually","Okay")
        print_lg("User did not configure username and password in secrets.py, hence can't login automatically! Please login manually!")
        manual_login_retry(is_logged_in_LN, 2)
        return
    try:
        wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Forgot password?")))
        try:
            text_input_by_ID(driver, "username", username, 1)
        except Exception as e:
            print_lg("Couldn't find username field.")
            # print_lg(e)
        try:
            text_input_by_ID(driver, "password", password, 1)
        except Exception as e:
            print_lg("Couldn't find password field.")
            # print_lg(e)
        # Find the login submit button and click it
        driver.find_element(By.XPATH, '//button[@type="submit" and contains(text(), "Sign in")]').click()
    except Exception as e1:
        try:
            profile_button = find_by_class(driver, "profile__details")
            profile_button.click()
        except Exception as e2:
            # print_lg(e1, e2)
            print_lg("Couldn't Login!")

    try:
        # Wait until successful redirect, indicating successful login
        wait.until(EC.url_to_be("https://www.linkedin.com/feed/")) # wait.until(EC.presence_of_element_located((By.XPATH, '//button[normalize-space(.)="Start a post"]')))
        return print_lg("Login successful!")
    except Exception as e:
        print_lg("Seems like login attempt failed! Possibly due to wrong credentials or already logged in! Try logging in manually!")
        # print_lg(e)
        manual_login_retry(is_logged_in_LN, 2)
#>



def get_applied_job_ids() -> set[str]:
    '''
    Function to get a `set` of applied job's Job IDs
    * Returns a set of Job IDs from existing applied jobs history csv file
    '''
    job_ids: set[str] = set()
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if row: job_ids.add(row[0])
    except FileNotFoundError:
        print_lg(f"The CSV file '{file_name}' does not exist.")
    return job_ids



def get_job_main_details(job: WebElement, blacklisted_companies: set, rejected_jobs: set) -> tuple[str, str, str, str, str, bool]:
    '''
    # Function to get job main details.
    Returns a tuple of (job_id, title, company, work_location, work_style, skip)
    * job_id: Job ID
    * title: Job title
    * company: Company name
    * work_location: Work location of this job
    * work_style: Work style of this job (Remote, On-site, Hybrid)
    * skip: A boolean flag to skip this job
    '''
    global quick_skip_count
    skip = False
    job_id = job.get_dom_attribute('data-occludable-job-id')
    # 1. Job handled before: decided from its ID alone, before even scrolling to the card (most cards end here)
    id_reason = (job_history.skip_reason_by_id(job_id) if job_history else None) or ("rejected earlier in this run" if job_id in rejected_jobs else None)
    if id_reason:
        print_lg(f'Skipping job {job_id}, {id_reason}.')
        skip_reasons[id_reason] += 1
        quick_skip_count += 1
        return (job_id, "", "", "", "", True)
    # LinkedIn draws only the first ~7 cards of a page; the others are empty placeholders until they are scrolled into view
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job)
    try: WebDriverWait(driver, 4, poll_frequency=0.2).until(lambda _: job.find_elements(By.TAG_NAME, 'a'))
    except TimeoutException: pass
    job_details_button = job.find_element(By.TAG_NAME, 'a')  # job.find_element(By.CLASS_NAME, "job-card-list__title")  # Problem in India
    scroll_to_view(driver, job_details_button, True)
    # `find()` returns -1 when the separator is missing, slicing with it cut off the last letter ("Data Science Inter")
    title = job_details_button.text.split("\n")[0].strip()
    # company = job.find_element(By.CLASS_NAME, "job-card-container__primary-description").text
    # work_location = job.find_element(By.CLASS_NAME, "job-card-container__metadata-item").text
    other_details = job.find_element(By.CLASS_NAME, 'artdeco-entity-lockup__subtitle').text
    company, _, work_location = other_details.partition(' · ')
    company = company.strip()
    if not work_location:   # Newer job cards show the place on its own line
        captions = job.find_elements(By.CLASS_NAME, 'artdeco-entity-lockup__caption')
        work_location = captions[0].text.split("\n")[0] if captions else ""
    work_style = ""
    if '(' in work_location and ')' in work_location:
        work_style = work_location[work_location.rfind('(')+1:work_location.rfind(')')]
        work_location = work_location[:work_location.rfind('(')]
    work_location = work_location.strip()
    
    # 2. Decided from the card's text, still without opening the job
    try: card_text = (job.text or "").lower()
    except Exception: card_text = ""
    reason = None
    if company in blacklisted_companies: reason = "blacklisted company"
    elif any(line.strip() == "applied" for line in card_text.split("\n")) or job.find_elements(By.XPATH, ".//*[contains(@class,'footer-job-state') and normalize-space()='Applied']"):
        reason = "already applied (shown on the card)"   # Exact line, so titles like "Applied AI Engineer" aren't skipped
    elif apply_mode == "easy" and card_text and "easy apply" not in card_text: reason = "no Easy Apply on the card"
    elif apply_mode == "normal" and "easy apply" in card_text: reason = "Easy Apply job (Normal Apply mode)"
    elif job_history and (history := job_history.skip_reason(job_id, company, title)):
        reason = history.split(" (")[0] if history.startswith("applied to this company") else history
    elif skip_word_in(title, skip_title_words):
        reason = "senior title"
    if reason:
        print_lg(f'Skipping "{title} | {company}", {reason}. Job ID: {job_id}')
        skip_reasons[reason] += 1
        quick_skip_count += 1
        return (job_id, title, company, work_location, work_style, True)
    wait_for_hourly_limit()
    wait_for(delay_before_opening_job)
    if control.stop_requested: return (job_id, title, company, work_location, work_style, True)   # "Stop" clicked meanwhile: no new job
    try:
        job_details_button.click()
    except Exception as e:
        print_lg(f'Failed to click "{title} | {company}" job on details button. Job ID: {job_id}!')
        close_linkedin_dialogs()
        job_details_button.click() # To pass the error outside
    return (job_id,title,company,work_location,work_style,skip)


# Function to check for Blacklisted words in About Company
def check_blacklist(rejected_jobs: set, job_id: str, company: str, blacklisted_companies: set) -> tuple[set, set, WebElement] | ValueError:
    try: jobs_top_card = try_find_by_classes(driver, ["job-details-jobs-unified-top-card__primary-description-container","job-details-jobs-unified-top-card__primary-description","jobs-unified-top-card__primary-description","jobs-details__main-content"])
    except ValueError: jobs_top_card = None   # Must not look like "blacklisted" (ValueError) when LinkedIn renames this box
    if not about_company_bad_words: return rejected_jobs, blacklisted_companies, jobs_top_card   # Nothing to look for: no scrolling, no waiting
    boxes = driver.find_elements(By.CLASS_NAME, "jobs-company__box")   # No waiting: if LinkedIn didn't show the box, there's nothing to check
    if not boxes: return rejected_jobs, blacklisted_companies, jobs_top_card
    about_company_org = boxes[0].get_attribute("textContent") or ""
    about_company = about_company_org.lower()
    skip_checking = False
    for word in about_company_good_words:
        if word.lower() in about_company:
            print_lg(f'Found the word "{word}". So, skipped checking for blacklist words.')
            skip_checking = True
            break
    if not skip_checking:
        for word in about_company_bad_words: 
            if word.lower() in about_company: 
                rejected_jobs.add(job_id)
                blacklisted_companies.add(company)
                raise ValueError(f'About Company contains "{word}".')
    return rejected_jobs, blacklisted_companies, jobs_top_card



# Function to extract years of experience required from About Job
def extract_years_of_experience(text: str) -> int:
    # Extract all patterns like '10+ years', '5 years', '3-5 years', etc.
    matches = re.findall(re_experience, text)
    if len(matches) == 0: return 0   # No "X years" in the description
    return max([int(match) for match in matches if int(match) <= 12], default=0)



def get_job_description(
) -> tuple[
    str | Literal['Unknown'],
    int | Literal['Unknown'],
    bool,
    str | None,
    str | None
    ]:
    '''
    # Job Description
    Function to extract job description from About the Job.
    ### Returns:
    - `jobDescription: str | 'Unknown'`
    - `experience_required: int | 'Unknown'`
    - `skip: bool`
    - `skipReason: str | None`
    - `skipMessage: str | None`
    '''
    jobDescription = "Unknown"
    experience_required = "Unknown"
    skip = False
    skipReason = None
    skipMessage = None
    try:
        found_masters = 0
        jobDescription = find_by_class(driver, "jobs-box__html-content").text
        jobDescriptionLow = jobDescription.lower()
        for word in bad_words:
            if word.lower() in jobDescriptionLow:
                skipMessage = f'\n{jobDescription}\n\nContains bad word "{word}". Skipping this job!\n'
                skipReason = "Found a Bad Word in About Job"
                skip = True
                break
        if not skip and security_clearance == False and ('polygraph' in jobDescriptionLow or 'clearance' in jobDescriptionLow or 'secret' in jobDescriptionLow):
            skipMessage = f'\n{jobDescription}\n\nFound "Clearance" or "Polygraph". Skipping this job!\n'
            skipReason = "Asking for Security clearance"
            skip = True
        if not skip:
            if did_masters and 'master' in jobDescriptionLow:
                print_lg('Found the word "master" in the description, allowing 2 more years of experience')
                found_masters = 2
            experience_required = extract_years_of_experience(jobDescription)
            if current_experience > -1 and experience_required > current_experience + found_masters:
                skipMessage = f'\n{jobDescription}\n\nExperience required {experience_required} > Current Experience {current_experience + found_masters}. Skipping this job!\n'
                skipReason = "Required experience is high"
                skip = True
    except Exception as e:
        if jobDescription == "Unknown":    print_lg("Unable to extract job description!")
        else:
            experience_required = "Error in extraction"
            print_lg("Unable to extract years of experience required!")
            # print_lg(e)
    return jobDescription, experience_required, skip, skipReason, skipMessage


# Function to upload resume
def upload_resume(modal: WebElement, resume: str) -> tuple[bool, str]:
    try:
        modal.find_element(By.NAME, "file").send_keys(os.path.abspath(resume))
        return True, os.path.basename(default_resume_path)
    except: return False, "Previous resume"

# Returns `text` stripped, or "" if it's empty or still the placeholder from the config template
def real_text(text: str, placeholder: str = "") -> str:
    text = (text or "").strip()
    return "" if placeholder and text.lower() == placeholder.lower() else text


ai_profile_text = ""    # Your config details + resume text, built in main() once the resume path is known


# Function to answer a question with the configured AI provider, returns `None` if AI is off or has no answer
def ai_answer_any(question: str, question_type: str = "text", options: list[str] | None = None, job_description: str | None = None, company: str = "", job_title: str = "") -> str | None:
    answer = ai_raw_answer(question, question_type, options, job_description, company, job_title)
    if isinstance(answer, dict) and answer.get("error"): print_lg("AI could not answer:", answer["error"])
    return answer if isinstance(answer, str) else None


# "Write with AI" in the popup: your short notes -> a complete answer. Raises with the reason when AI can't write it.
def ai_write_from_notes(question: str, notes: str, question_type: str = "textarea", company: str = "", job_title: str = "", job_description: str | None = None) -> str:
    if not (use_AI and aiClient): raise RuntimeError("AI is off. Set use_AI = True and add your API key in config/secrets.py")
    prompt = (f"{question}\n\nTHE CANDIDATE'S OWN NOTES FOR THIS ANSWER: {notes}\n"
              "Turn these notes into the candidate's complete answer to the question above, in the first person. Keep every fact from the notes, "
              "you may add matching details from the candidate information, but never invent projects, numbers, employers or results.")
    answer = ai_raw_answer(prompt, "textarea" if question_type == "textarea" or len(notes) > 60 else question_type, None, job_description, company, job_title)
    if isinstance(answer, dict): raise RuntimeError(answer.get("error") or "no answer")
    if not answer or not answer.strip(): raise RuntimeError("empty answer")
    return answer.strip()


def ai_raw_answer(question: str, question_type: str = "text", options: list[str] | None = None, job_description: str | None = None, company: str = "", job_title: str = "") -> str | dict | None:
    '''The provider's answer: text, {"error": ...}, or None if AI is off.'''
    if not (use_AI and aiClient): return None
    provider = ai_provider.lower()
    information = ai_profile_text or real_text(user_information_all, "User Information")
    about_job = " - ".join(part for part in (company, job_title) if part) or None   # Lets "Why do you want to work here?" answers name the company and role
    if provider == "openai":
        # OpenAI prompt doesn't include options by itself
        if options: question = question + "\nPick exactly one of these options and answer with its text only: " + " | ".join(options)
        answer = ai_answer_question(aiClient, question, options, question_type, job_description, about_job, information)
    elif provider == "deepseek":
        answer = deepseek_answer_question(aiClient, question, options, question_type, job_description, about_job, information)
    elif provider == "gemini":
        answer = gemini_answer_question(aiClient, question, options, question_type, job_description, about_job, information)
    else: return None
    return answer


# Function to answer common questions for Easy Apply
def answer_common_questions(label: str, answer: str) -> str:
    if 'sponsorship' in label or 'visa' in label: answer = require_visa
    return answer


# Visible text, or the text of "visually-hidden" labels (Selenium's .text returns "" for hidden text, which made blank popups)
def element_text(element: WebElement) -> str:
    try: return (element.text or "").strip() or " ".join((element.get_attribute("textContent") or "").split())
    except Exception: return ""


# Function to answer the questions for Easy Apply
def answer_questions(modal: WebElement, questions_list: set, work_location: str, job_description: str | None = None, company: str = "", job_title: str = "") -> set:
    '''
    Answers every question on the current Easy Apply page. For each question:
    saved answers (from earlier popups) -> your config -> AI -> popup asking you (if `ask_instead_of_guessing`) -> old guessing.
    '''
    # Get all questions from the page
    all_questions = modal.find_elements(By.XPATH, ".//div[@data-test-form-element]")
    job_context = {"company": company, "job_title": job_title, "job_description": job_description}

    for Question in all_questions:
        if not Question.is_displayed(): continue   # Questions of other pages that are only hidden, not removed
        # Check if it's a select Question
        select = try_xp(Question, ".//select", False)
        if select:
            label_org = "Unknown"
            try:
                label = Question.find_element(By.TAG_NAME, "label")
                label_org = element_text(label.find_element(By.TAG_NAME, "span"))
            except: pass
            answer = 'Yes'
            label = label_org.lower()
            select = Select(select)
            selected_option = select.first_selected_option.text
            optionsText = []
            options = '"List of phone country codes"'
            if label != "phone country code":
                optionsText = [option.text for option in select.options]
                options = "".join([f' "{option}",' for option in optionsText])
            choices = [option for option in optionsText if option.strip() and option != "Select an option"]
            prev_answer = selected_option
            if overwrite_previous_answers or selected_option == "Select an option":
                saved = answer_resolver.find_saved(label_org, choices) if choices else None
                if saved: answer = saved
                elif ('email' in label or 'phone' in label) and prev_answer != "Select an option":   # Email address / phone country code: keep LinkedIn's choice
                    answer = prev_answer
                elif 'gender' in label or 'sex' in label:
                    answer = gender
                elif 'disability' in label:
                    answer = disability_status
                elif 'proficiency' in label:
                    answer = 'Professional'
                # Add location handling
                elif any(loc_word in label for loc_word in ['location', 'city', 'state', 'country']):
                    if 'country' in label:
                        answer = country
                    elif 'state' in label:
                        answer = state
                    elif 'city' in label:
                        answer = current_city if current_city else work_location
                    else:
                        answer = work_location
                elif 'sponsorship' in label or 'visa' in label:
                    answer = require_visa
                elif choices and (from_profile := match_option(profile_answer({"label": label_org, "kind": "select", "options": choices}, job_title=job_title) or "", choices)):
                    answer = from_profile   # Eg: "total years of professional experience" -> years_of_experience
                elif ask_instead_of_guessing or (use_AI and aiClient):
                    answer = answer_resolver.resolve_unknown(label_org, "single_select", choices, allow_popup=ask_instead_of_guessing, **job_context)
                    if answer is None and not ask_instead_of_guessing: answer = 'Yes'   # Old behaviour when AI had no answer
                if answer is None:
                    print_lg(f'Left "{label_org}" unanswered.')
                    questions_list.add((f'{label_org} [ {options} ]', "Unanswered", "select", prev_answer))
                    continue
                matched = match_option(answer, choices) if choices else None
                if matched:
                    select.select_by_visible_text(matched)
                    answer = matched
                else:
                    try:
                        select.select_by_visible_text(answer)
                    except NoSuchElementException as e:
                        # Define similar phrases for common answers
                        possible_answer_phrases = []
                        if answer == 'Decline':
                            possible_answer_phrases = ["Decline", "not wish", "don't wish", "Prefer not", "not want"]
                        elif 'yes' in answer.lower():
                            possible_answer_phrases = ["Yes", "Agree", "I do", "I have"]
                        elif 'no' in answer.lower():
                            possible_answer_phrases = ["No", "Disagree", "I don't", "I do not"]
                        else:
                            # Try partial matching for any answer
                            possible_answer_phrases = [answer]
                            # Add lowercase and uppercase variants
                            possible_answer_phrases.append(answer.lower())
                            possible_answer_phrases.append(answer.upper())
                            # Try without special characters
                            possible_answer_phrases.append(''.join(c for c in answer if c.isalnum()))
                        foundOption = False
                        for phrase in possible_answer_phrases:
                            for option in optionsText:
                                # Check if phrase is in option or option is in phrase (bidirectional matching)
                                if phrase.lower() in option.lower() or option.lower() in phrase.lower():
                                    select.select_by_visible_text(option)
                                    answer = option
                                    foundOption = True
                                    break
                            if foundOption: break
                        if not foundOption:
                            asked = answer_resolver.ask_user(label_org, "single_select", choices, company, job_title, note=f'Your answer "{answer}" is not one of the choices.') if ask_instead_of_guessing and choices else None
                            if asked:
                                select.select_by_visible_text(asked)
                                answer = asked
                            elif len(select.options) > 1:
                                print_lg(f'Failed to find an option with text "{answer}" for question labelled "{label_org}", answering randomly!')
                                select.select_by_index(randint(1, len(select.options)-1))
                                answer = select.first_selected_option.text
                                randomly_answered_questions.add((f'{label_org} [ {options} ]',"select"))
            questions_list.add((f'{label_org} [ {options} ]', answer, "select", prev_answer))
            continue

        # Check if it's a radio Question
        radio = try_xp(Question, './/fieldset[@data-test-form-builder-radio-button-form-component="true"]', False)
        if radio:
            prev_answer = None
            label = try_xp(radio, './/span[@data-test-form-builder-radio-button-form-component__title]', False)
            try: label = find_by_class(label, "visually-hidden", 2.0)
            except: pass
            label_org = element_text(label) if label else "Unknown"
            question_text = label_org
            answer = 'Yes'
            label = label_org.lower()

            label_org += ' [ '
            options = radio.find_elements(By.TAG_NAME, 'input')
            options_labels = []
            option_texts = []

            for option in options:
                id = option.get_attribute("id")
                option_label = try_xp(radio, f'.//label[@for="{id}"]', False)
                option_texts.append(option_label.text.strip() if option_label else "Unknown")
                options_labels.append( f'"{option_texts[-1]}"<{option.get_attribute("value")}>' ) # Saving option as "label <value>"
                if option.is_selected(): prev_answer = options_labels[-1]
                label_org += f' {options_labels[-1]},'

            if overwrite_previous_answers or prev_answer is None:
                saved = answer_resolver.find_saved(question_text, option_texts)
                if saved: answer = saved
                elif 'citizenship' in label or 'employment eligibility' in label: answer = us_citizenship
                elif 'veteran' in label or 'protected' in label: answer = veteran_status
                elif 'disability' in label or 'handicapped' in label:
                    answer = disability_status
                elif 'sponsorship' in label or 'visa' in label: answer = require_visa
                elif (from_profile := match_option(profile_answer({"label": question_text, "kind": "radio", "options": option_texts}, job_title=job_title) or "", option_texts)):
                    answer = from_profile
                elif ask_instead_of_guessing or (use_AI and aiClient):
                    answer = answer_resolver.resolve_unknown(question_text, "single_select", option_texts, allow_popup=ask_instead_of_guessing, **job_context)
                    if answer is None and not ask_instead_of_guessing: answer = 'Yes'   # Old behaviour when AI had no answer
                if answer is None:
                    print_lg(f'Left "{question_text}" unanswered.')
                    questions_list.add((label_org+" ]", "Unanswered", "radio", prev_answer))
                    continue
                matched = match_option(answer, option_texts)
                if matched:
                    ele = options[option_texts.index(matched)]
                    answer = options_labels[option_texts.index(matched)]
                    foundOption = try_xp(radio, f'.//label[@for="{ele.get_attribute("id")}"]', False)
                    actions.move_to_element(foundOption if foundOption else ele).click().perform()
                else:
                    possible_answer_phrases = ["Decline", "not wish", "don't wish", "Prefer not", "not want"] if answer == 'Decline' else [answer]
                    ele = options[0]
                    answer = options_labels[0]
                    foundOption = False
                    for phrase in possible_answer_phrases:
                        for i, option_label in enumerate(options_labels):
                            if phrase in option_label:
                                foundOption = options[i]
                                ele = foundOption
                                answer = f'Decline ({option_label})' if len(possible_answer_phrases) > 1 else option_label
                                break
                        if foundOption: break
                    if not foundOption and ask_instead_of_guessing:
                        asked = answer_resolver.ask_user(question_text, "single_select", option_texts, company, job_title)
                        if asked:
                            foundOption = options[option_texts.index(asked)]
                            ele = foundOption
                            answer = options_labels[option_texts.index(asked)]
                    actions.move_to_element(ele).click().perform()
                    if not foundOption: randomly_answered_questions.add((f'{label_org} ]',"radio"))
            else: answer = prev_answer
            questions_list.add((label_org+" ]", answer, "radio", prev_answer))
            continue

        # Check if it's a text question
        text = try_xp(Question, ".//input[@type='text']", False)
        if text:
            do_actions = False
            label = try_xp(Question, ".//label[@for]", False)
            try: label = label.find_element(By.CLASS_NAME,'visually-hidden')
            except: pass
            label_org = element_text(label) if label else "Unknown"
            answer = "" # years_of_experience
            label = label_org.lower()

            prev_answer = text.get_attribute("value")
            if not prev_answer or overwrite_previous_answers:
                saved = answer_resolver.find_saved(label_org)
                if saved: answer = saved
                elif 'experience' in label or 'years' in label: answer = years_of_experience
                elif 'phone' in label or 'mobile' in label: answer = phone_number
                elif 'street' in label: answer = street
                elif 'city' in label or 'location' in label or 'address' in label:
                    answer = current_city if current_city else work_location
                    do_actions = True
                elif 'signature' in label: answer = full_name # 'signature' in label or 'legal name' in label or 'your name' in label or 'full name' in label: answer = full_name     # What if question is 'name of the city or university you attend, name of referral etc?'
                elif 'name' in label:
                    if 'full' in label: answer = full_name
                    elif 'first' in label and 'last' not in label: answer = first_name
                    elif 'middle' in label and 'last' not in label: answer = middle_name
                    elif 'last' in label and 'first' not in label: answer = last_name
                    elif 'employer' in label: answer = recent_employer
                    else: answer = full_name
                elif 'notice' in label:
                    if 'month' in label:
                        answer = notice_period_months
                    elif 'week' in label:
                        answer = notice_period_weeks
                    else: answer = notice_period
                elif 'salary' in label or 'compensation' in label or 'ctc' in label or 'pay' in label:
                    if 'current' in label or 'present' in label:
                        if 'month' in label:
                            answer = current_ctc_monthly
                        elif 'lakh' in label:
                            answer = current_ctc_lakhs
                        else:
                            answer = current_ctc
                    else:
                        if 'month' in label:
                            answer = desired_salary_monthly
                        elif 'lakh' in label:
                            answer = desired_salary_lakhs
                        else:
                            answer = desired_salary
                elif 'linkedin' in label: answer = linkedIn
                elif 'website' in label or 'blog' in label or 'portfolio' in label or 'link' in label: answer = website if website else linkedIn
                elif 'scale of 1-10' in label: answer = confidence_level
                elif 'headline' in label: answer = linkedin_headline
                elif ('hear' in label or 'come across' in label) and 'this' in label and ('job' in label or 'position' in label): answer = "LinkedIn"
                elif 'state' in label or 'province' in label: answer = state
                elif 'zip' in label or 'postal' in label or 'code' in label: answer = zipcode
                elif 'country' in label: answer = country
                else: answer = answer_common_questions(label,answer)
                if answer == "":
                    answer = profile_answer({"label": label_org, "kind": "text"}, job_title=job_title) or ""
                if answer == "":
                    answer = answer_resolver.resolve_unknown(label_org, "text", None, allow_popup=ask_instead_of_guessing, **job_context) or ""
                    if answer == "" and not ask_instead_of_guessing:
                        randomly_answered_questions.add((label_org, "text"))
                        answer = years_of_experience
                if answer != "":
                    text.clear()
                    text.send_keys(answer)
                    if do_actions:
                        sleep(2)
                        actions.send_keys(Keys.ARROW_DOWN)
                        actions.send_keys(Keys.ENTER).perform()
                else: print_lg(f'Left "{label_org}" unanswered.')
            questions_list.add((label, text.get_attribute("value"), "text", prev_answer))
            continue

        # Check if it's a textarea question
        text_area = try_xp(Question, ".//textarea", False)
        if text_area:
            label = try_xp(Question, ".//label[@for]", False)
            label_org = element_text(label) if label else "Unknown"
            label = label_org.lower()
            answer = ""
            prev_answer = text_area.get_attribute("value")
            if not prev_answer or overwrite_previous_answers:
                saved = answer_resolver.find_saved(label_org)
                if saved: answer = saved
                elif 'summary' in label: answer = real_text(linkedin_summary)
                elif 'cover' in label: answer = real_text(cover_letter, "Cover Letter")
                if answer == "":
                    answer = answer_resolver.resolve_unknown(label_org, "textarea", None, allow_popup=ask_instead_of_guessing, **job_context) or ""
                    if answer == "": randomly_answered_questions.add((label_org, "textarea"))
                if answer != "":
                    text_area.clear()
                    text_area.send_keys(answer)
                else: print_lg(f'Left "{label_org}" unanswered.')
            questions_list.add((label, text_area.get_attribute("value"), "textarea", prev_answer))
            continue

        # Check if it's a checkbox question
        checkbox = try_xp(Question, ".//input[@type='checkbox']", False)
        if checkbox:
            label = try_xp(Question, ".//span[@class='visually-hidden']", False)
            label_org = element_text(label) if label else "Unknown"
            label = label_org.lower()
            answer = try_xp(Question, ".//label[@for]", False)  # Sometimes multiple checkboxes are given for 1 question, Not accounted for that yet
            answer = answer.text if answer else "Unknown"
            prev_answer = checkbox.is_selected()
            checked = prev_answer
            if not prev_answer:
                try:
                    actions.move_to_element(checkbox).click().perform()
                    checked = True
                except Exception as e: 
                    print_lg("Checkbox click failed!", e)
                    pass
            questions_list.add((f'{label} ([X] {answer})', checked, "checkbox", prev_answer))
            continue


    # Select todays date
    try_xp(driver, "//button[contains(@aria-label, 'This is today')]")

    # Collect important skills
    # if 'do you have' in label and 'experience' in label and ' in ' in label -> Get word (skill) after ' in ' from label
    # if 'how many years of experience do you have in ' in label -> Get word (skill) after ' in '

    return questions_list




def wait_for_real_url(timeout: float = 10) -> str:
    '''Waits until the new tab has left "about:blank" (new tabs start there) and LinkedIn's redirect page, returns its URL.'''
    try: WebDriverWait(driver, timeout).until(lambda d: d.current_url not in ("", "about:blank") and "linkedin.com" not in d.current_url)
    except Exception: pass
    url = driver.current_url
    if "linkedin.com" in url:   # Still on LinkedIn's redirect page: the company's address is in its "url" parameter
        target = (parse_qs(urlparse(url).query).get("url") or [""])[0]
        if target.startswith("http"): url = target
    return "" if url in ("", "about:blank") else url



def open_external_link(button: WebElement) -> str | None:
    '''
    Clicks the job's "Apply" (company website) button and returns the company's application address, or None.
    The new tab is closed again (Normal Apply opens the address in its own tab); the browser always ends on the LinkedIn tab.
    '''
    before = set(driver.window_handles)
    try:
        click_button(button)
        wait_span_click(driver, "Continue", 1, True, False)   # LinkedIn's "Share your profile?" notice
        end = time.time() + 8
        while time.time() < end and len(driver.window_handles) <= len(before): sleep(0.5)
        opened = [handle for handle in driver.window_handles if handle not in before]
        if opened:
            driver.switch_to.window(opened[-1])
            link = wait_for_real_url()
            if close_tabs or apply_mode in ("normal", "both"): driver.close()
        elif "linkedin.com" not in driver.current_url:   # Opened in the same tab
            link = driver.current_url
            driver.back()
        else:
            link = None
    except Exception as e:
        print_lg("   couldn't open the company's Apply link:", str(e).splitlines()[0][:150] if str(e) else e)
        link = None
    try: driver.switch_to.window(linkedIn_tab)
    except Exception: pass
    if link: print_lg(f'   company application link: {link}')
    return link



def follow_company(modal: WebDriver = driver) -> None:
    '''
    Function to follow or un-follow easy applied companies based om `follow_companies`
    '''
    try:
        follow_checkbox_input = try_xp(modal, ".//input[@id='follow-company-checkbox' and @type='checkbox']", False)
        if follow_checkbox_input and follow_checkbox_input.is_selected() != follow_companies:
            try_xp(modal, ".//label[@for='follow-company-checkbox']")
    except Exception as e:
        print_lg("Failed to update follow companies checkbox!", e)
    


#< Failed attempts logging
def failed_job(job_id: str, job_link: str, resume: str, date_listed, error: str, exception: Exception, application_link: str, screenshot_name: str) -> None:
    '''
    Function to update failed jobs list in excel
    '''
    if job_history: job_history.record_failed(job_id, error)   # Errors are tried again later (up to 2 times), jobs that don't fit you never
    try:
        with open(failed_file_name, 'a', newline='', encoding='utf-8') as file:
            fieldnames = ['Job ID', 'Job Link', 'Resume Tried', 'Date listed', 'Date Tried', 'Assumed Reason', 'Stack Trace', 'External Job link', 'Screenshot Name']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if file.tell() == 0: writer.writeheader()
            writer.writerow({'Job ID':truncate_for_csv(job_id), 'Job Link':truncate_for_csv(job_link), 'Resume Tried':truncate_for_csv(resume), 'Date listed':truncate_for_csv(date_listed), 'Date Tried':datetime.now(), 'Assumed Reason':truncate_for_csv(error), 'Stack Trace':truncate_for_csv(exception), 'External Job link':truncate_for_csv(application_link), 'Screenshot Name':truncate_for_csv(screenshot_name)})
            file.close()
    except Exception as e:
        print_lg("Failed to update failed jobs list!", e)
        pyautogui.alert("Failed to update the excel of failed jobs!\nProbably because of 1 of the following reasons:\n1. The file is currently open or in use by another program\n2. Permission denied to write to the file\n3. Failed to find the file", "Failed Logging")
    try: db.record_failure(job_id, job_link, error, exception, application_link, screenshot_name)   # The dashboard's database
    except Exception as e: print_lg("Couldn't save the failure in the database:", e)


def screenshot(driver: WebDriver, job_id: str, failedAt: str) -> str:
    '''
    Function to to take screenshot for debugging
    - Returns screenshot name as String
    '''
    screenshot_name = "{} - {} - {}.png".format( job_id, failedAt, str(datetime.now()) )
    path = logs_folder_path+"/screenshots/"+screenshot_name.replace(":",".")
    # special_chars = {'*', '"', '\\', '<', '>', ':', '|', '?'}
    # for char in special_chars:  path = path.replace(char, '-')
    driver.save_screenshot(path.replace("//","/"))
    return screenshot_name
#>



def submitted_jobs(job_id: str, title: str, company: str, work_location: str, work_style: str, description: str, experience_required: int | Literal['Unknown', 'Error in extraction'], 
                   skills: list[str] | Literal['In Development'], hr_name: str | Literal['Unknown'], hr_link: str | Literal['Unknown'], resume: str, 
                   reposted: bool, date_listed: datetime | Literal['Unknown'], date_applied:  datetime | Literal['Pending'], job_link: str, application_link: str, 
                   questions_list: set | None, connect_request: Literal['In Development']) -> None:
    '''
    Function to create or update the Applied jobs CSV file, once the application is submitted successfully
    '''
    if job_history: job_history.record_applied(job_id, company, title, applied=isinstance(date_applied, datetime))
    try:
        with open(file_name, mode='a', newline='', encoding='utf-8') as csv_file:
            fieldnames = ['Job ID', 'Title', 'Company', 'Work Location', 'Work Style', 'About Job', 'Experience required', 'Skills required', 'HR Name', 'HR Link', 'Resume', 'Re-posted', 'Date Posted', 'Date Applied', 'Job Link', 'External Job link', 'Questions Found', 'Connect Request']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            if csv_file.tell() == 0: writer.writeheader()
            writer.writerow({'Job ID':truncate_for_csv(job_id), 'Title':truncate_for_csv(title), 'Company':truncate_for_csv(company), 'Work Location':truncate_for_csv(work_location), 'Work Style':truncate_for_csv(work_style), 
                            'About Job':truncate_for_csv(description), 'Experience required': truncate_for_csv(experience_required), 'Skills required':truncate_for_csv(skills), 
                                'HR Name':truncate_for_csv(hr_name), 'HR Link':truncate_for_csv(hr_link), 'Resume':truncate_for_csv(resume), 'Re-posted':truncate_for_csv(reposted), 
                                'Date Posted':truncate_for_csv(date_listed), 'Date Applied':truncate_for_csv(date_applied), 'Job Link':truncate_for_csv(job_link), 
                                'External Job link':truncate_for_csv(application_link), 'Questions Found':truncate_for_csv(questions_list), 'Connect Request':truncate_for_csv(connect_request)})
        csv_file.close()
    except Exception as e:
        print_lg("Failed to update submitted jobs list!", e)
        pyautogui.alert("Failed to update the excel of applied jobs!\nProbably because of 1 of the following reasons:\n1. The file is currently open or in use by another program\n2. Permission denied to write to the file\n3. Failed to find the file", "Failed Logging")
    try:   # The dashboard's database
        applied = isinstance(date_applied, datetime)
        db.record_application(job_id, title, company, "easy" if application_link == "Easy Applied" else ("normal" if applied else "link"),
                              "applied" if applied else "link_saved", location=work_location, work_style=work_style, job_link=job_link,
                              apply_link="" if application_link == "Easy Applied" else application_link, hr_name=hr_name, hr_link=hr_link, resume=resume,
                              date_posted=date_listed, applied_at=date_applied if applied else "", experience_required=experience_required,
                              skills=skills, description=description, questions=questions_list or "")
    except Exception as e:
        print_lg("Couldn't save the application in the database:", e)



# Function to find the Easy Apply modal (LinkedIn keeps changing its class names)
def find_easy_apply_modal(time: float = 5.0) -> WebElement:
    '''
    The Easy Apply form: LinkedIn's popup dialog, or (LinkedIn's newer flow) a separate apply page, then the page's main area is used
    once it shows a Next / Review / Submit button. Raises TimeoutException if neither appears within `time` seconds.
    '''
    xpaths = ["//div[contains(@class,'jobs-easy-apply-modal')]", "//div[@role='dialog' and .//form]", "//div[@role='dialog' and contains(@class,'artdeco-modal')]"]
    def first_match(d):
        for xpath in xpaths:
            for found in d.find_elements(By.XPATH, xpath):
                try:
                    if found.is_displayed(): return found
                except Exception: pass
        url = d.current_url.lower()
        if "/apply" in url or "opensduiapplyflow" in url:
            areas = d.find_elements(By.TAG_NAME, "main") or d.find_elements(By.TAG_NAME, "body")
            if areas and easy_apply_button(areas[0])[0]: return areas[0]
        return False
    return WebDriverWait(driver, time).until(first_match)


# Function to check if the Easy Apply form is showing validation errors (Eg: "Please enter a valid answer")
def modal_has_errors(modal: WebElement) -> bool:
    try:
        errors = modal.find_elements(By.XPATH, ".//*[contains(@class,'artdeco-inline-feedback--error')]")
        return any(error.is_displayed() for error in errors)
    except Exception: return False



#< Easy Apply form
class EasyApplyStopped(Exception):
    '''An Easy Apply form that couldn't be finished. `kind`: "error", "skipped" (you, from the control window) or "discarded" (you, before Submit).'''
    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


_EASY_APPLY_BUTTONS = [   # Checked in this order: the last page has Submit, the one before it Review, the others Next / Continue
    ("submit", ("submit application", "submit")),
    ("review", ("review", "review your application")),
    ("next", ("next", "continue", "continue to next step")),
]


def easy_apply_button(modal: WebElement) -> tuple[str | None, WebElement | None]:
    '''
    The form's forward button on the current page, found by its visible text or its aria-label (LinkedIn's old and new forms differ in
    how the text is wrapped, which made the old "span" lookup miss "Next"). Returns ("submit" | "review" | "next", button) or (None, None).
    '''
    found = {}
    for button in modal.find_elements(By.XPATH, ".//button"):
        try:
            if not button.is_displayed() or not button.is_enabled(): continue
            text = " ".join((button.text or "").lower().split())
            label = " ".join((button.get_attribute("aria-label") or "").lower().split())
            for kind, names in _EASY_APPLY_BUTTONS:
                if text in names or label in names or any(label.startswith(name + " ") for name in names[:1]):
                    found.setdefault(kind, button)
        except Exception: pass
    for kind, _ in _EASY_APPLY_BUTTONS:
        if kind in found: return kind, found[kind]
    return None, None


def click_button(button: WebElement) -> None:
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', button)
    try: button.click()
    except Exception: driver.execute_script("arguments[0].click();", button)


def close_entry_editors(modal: WebElement) -> None:
    '''
    "Work experience" / "Education" entries open for editing (with Save / Cancel, like "3 of 3") block the form when something is missing.
    Saves them; if the entry still has an error, removes or cancels it. Never ticks "I currently work here": that could be untrue.
    '''
    for _ in range(4):
        saves = [b for b in modal.find_elements(By.XPATH, ".//button[normalize-space()='Save']") if b.is_displayed()]
        if not saves: return
        click_button(saves[0])
        sleep(1)
        still_open = [b for b in modal.find_elements(By.XPATH, ".//button[normalize-space()='Save']") if b.is_displayed()]
        if not still_open: continue
        editor = driver.execute_script('''let e = arguments[0];
            for (let i = 0; i < 8 && e; i++) { e = e.parentElement; if (e && [...e.querySelectorAll('button')].some(b => /^(cancel|remove|delete)$/i.test(b.innerText.trim()))) return e; }
            return null;''', still_open[0])
        if editor is None: return
        buttons = {b.text.strip().lower(): b for b in editor.find_elements(By.XPATH, ".//button") if b.is_displayed() and b.text.strip()}
        target = buttons.get("remove") or buttons.get("delete") or buttons.get("cancel")
        if target is None: return
        print_lg(f'A work experience / education entry is incomplete, clicking "{target.text.strip()}" on it')
        click_button(target)
        sleep(1)
        confirm = [b for b in driver.find_elements(By.XPATH, "//div[@role='alertdialog' or @role='dialog']//button[normalize-space()='Remove' or normalize-space()='Delete' or normalize-space()='Discard']") if b.is_displayed()]
        if confirm: click_button(confirm[-1]); sleep(1)


def save_form_html(modal: WebElement, job_id: str) -> str:
    '''Keeps the HTML of a form the bot couldn't finish, so that exact form type can be fixed. Returns the file path.'''
    folder = os.path.join(logs_folder_path, "easy_apply_forms")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{job_id}.html")
        with open(path, "w", encoding="utf-8") as file: file.write(modal.get_attribute("outerHTML") or "")
        return path
    except Exception:
        return "(not saved)"


def submit_easy_apply(modal: WebElement, button: WebElement) -> None:
    '''Last page: optional "pause before submit", click Submit, wait for LinkedIn's confirmation, close it.'''
    global pause_before_submit
    follow_company(modal)
    if pause_before_submit:
        decision = pyautogui.confirm('1. Please verify your information.\n2. If you edited something, please return to this final screen.\n3. DO NOT CLICK "Submit Application".\n\n\nYou can turn off "Pause before submit" in config/questions.py\nTo TEMPORARILY disable pausing, click "Disable Pause"', "Confirm your information", ["Disable Pause", "Discard Application", "Submit Application"])
        if decision == "Discard Application": raise EasyApplyStopped("Job application discarded by user!", "discarded")
        pause_before_submit = "Disable Pause" != decision
        modal = find_easy_apply_modal(3)
        kind, button = easy_apply_button(modal)
        if kind != "submit": raise EasyApplyStopped("The Submit button was gone after your review.")
    in_dialog = (modal.get_attribute("role") == "dialog") or "jobs-easy-apply-modal" in (modal.get_attribute("class") or "")
    click_button(button)
    end = time.time() + 10
    while time.time() < end:
        sleep(0.7)
        done = [b for b in driver.find_elements(By.XPATH, "//button[normalize-space()='Done' or .//span[normalize-space()='Done']]") if b.is_displayed()]
        if done:
            click_button(done[0])
            return
        page_text = (driver.execute_script("return document.body ? document.body.innerText.slice(0, 5000) : ''") or "").lower()
        if "application was sent" in page_text or "application submitted" in page_text or "your application was submitted" in page_text: return
        blocked = easy_apply_blocked_by_linkedin()
        if blocked:
            stop_easy_apply(blocked)
            raise EasyApplyStopped(easy_apply_stopped, "blocked")
        if in_dialog:
            if not driver.find_elements(By.XPATH, "//div[contains(@class,'jobs-easy-apply-modal')] | //div[@role='dialog' and .//form]"): return   # The form closed: sent
        else:   # LinkedIn's separate apply page: sent once its Submit button is gone
            areas = driver.find_elements(By.TAG_NAME, "main") or driver.find_elements(By.TAG_NAME, "body")
            if not areas or easy_apply_button(areas[0])[0] != "submit": return
    try: still_waiting = easy_apply_button(find_easy_apply_modal(2))[0] == "submit"
    except Exception: still_waiting = False
    if still_waiting: raise EasyApplyStopped("Clicked Submit, but the form is still waiting (probably an error on the last page).")
    if in_dialog: actions.send_keys(Keys.ESCAPE).perform()   # Confirmation without a Done button


easy_form_filler = None   # General form filler (the one used for company websites), for Easy Apply forms without LinkedIn's usual question boxes


def fill_any_form(root: WebElement, title: str, company: str, description: str, work_location: str) -> set:
    '''Fills every field inside `root` with the usual answers (config, saved answers, AI, popup). Returns the questions answered.'''
    global easy_form_filler
    if easy_form_filler is None:
        easy_form_filler = NormalApplier(driver, answer_resolver, enabled_sites=[], resume_path=default_resume_path if os.path.exists(default_resume_path) else None,
                                         popups_enabled=not run_in_background, confirm_submit=lambda job: True, screenshot=lambda job_id, reason: "",
                                         max_fill_attempts=max_fill_attempts, control=control)
    result = ApplyResult("failed", "")
    context = {"job_link": "", "job_location": work_location, "job": {"company": company, "job_title": title, "job_description": description}}
    for field in read_fields(driver, root):
        if field["kind"] == "file": continue   # The resume is handled by upload_resume
        if field["kind"] == "radio" and field["options"] and all(re.match(r'(de)?select resume\b', option.lower()) for option in field["options"]):
            # LinkedIn's list of your uploaded resumes: not a question (asking AI used up its daily quota), pick the default resume, else the first
            if not field["value"]:
                name = os.path.basename(default_resume_path).lower()
                fill_field(driver, field, next((option for option in field["options"] if name in option.lower()), field["options"][0]))
            continue
        easy_form_filler._answer_field(field, context, result)
    return result.questions


def run_easy_apply(job_id: str, title: str, company: str, work_location: str, description: str) -> tuple[datetime, set, str, bool]:
    '''
    Fills and sends one Easy Apply form, page by page. Returns (date applied, questions, resume, uploaded).
    Raises EasyApplyStopped when a page can't be passed after `max_fill_attempts` tries, or you skip / discard it.
    '''
    questions, resume, uploaded = set(), "Previous resume", False
    stuck = 0
    for page in range(1, 16):
        if control.checkpoint(allow_skip=False) == "skip": raise EasyApplyStopped("Skipped by you from the control window.", "skipped")
        modal = find_easy_apply_modal(5)
        if modal.find_elements(By.XPATH, ".//div[@data-test-form-element]"):
            questions = answer_questions(modal, questions, work_location, job_description=description, company=company, job_title=title)
        else:   # A form without LinkedIn's usual question boxes (newer apply page): the general form filler, kept inside the form
            questions |= fill_any_form(modal, title, company, description, work_location)
        if useNewResume and not uploaded: uploaded, resume = upload_resume(modal, default_resume_path)
        close_entry_editors(modal)
        kind, button = easy_apply_button(modal)
        if kind is None:   # The form may still be drawing the next page
            sleep(1.5)
            modal = find_easy_apply_modal(3)
            kind, button = easy_apply_button(modal)
        if kind is None:
            blocked = easy_apply_blocked_by_linkedin()   # LinkedIn's "applying at a fast pace" message instead of the form
            if blocked:
                stop_easy_apply(blocked)
                raise EasyApplyStopped(easy_apply_stopped, "blocked")
            raise EasyApplyStopped(f"No Next / Review / Submit button on page {page} (form saved in {save_form_html(modal, job_id)}).")
        # Your delay (config/settings.py), then the button again: the page may have changed if you paused and filled something
        wait_for(delay_before_submit if kind == "submit" else delay_between_form_pages, in_application=True, count=False)
        modal = find_easy_apply_modal(3)
        kind, button = easy_apply_button(modal)
        if kind is None: continue
        if kind == "submit":
            submit_easy_apply(modal, button)
            return datetime.now(), questions, resume, uploaded
        click_button(button)
        buffer(click_gap)
        if modal_has_errors(find_easy_apply_modal(3)):
            stuck += 1
            if stuck >= max_fill_attempts:
                skipped = answer_resolver.skipped_this_job()
                save_form_html(find_easy_apply_modal(3), job_id)
                raise EasyApplyStopped(f"Couldn't get past page {page} after {max_fill_attempts} tries" + (f", you skipped: {skipped}" if skipped else ""))
        else:
            stuck = 0
    raise EasyApplyStopped("The form has more than 15 pages.")
#>


# Function to discard the job application
def discard_job() -> None:
    '''
    Closes the Easy Apply popup and confirms "Discard". Checks that it's really gone, a popup left open covers the job list
    and makes the next job's click fail ("element click intercepted").
    '''
    for attempt in range(3):
        try:
            if not driver.find_elements(By.XPATH, "//div[contains(@class,'jobs-easy-apply-modal')] | //div[@role='dialog' and .//form]"): return
            # Close button first (Escape does nothing while a dropdown inside the form has focus), then Escape as a fallback
            if not try_xp(driver, "//div[@role='dialog']//button[@aria-label='Dismiss' or contains(@class,'artdeco-modal__dismiss')]"):
                actions.send_keys(Keys.ESCAPE).perform()
            sleep(1)
            if not try_xp(driver, "//button[@data-control-name='discard_application_confirm_btn'] | //button[.//span[normalize-space(.)='Discard']]"):
                wait_span_click(driver, 'Discard', 2)
            sleep(1)
        except Exception as e:
            if session_lost(e): raise
            print_lg("Problem while closing the Easy Apply popup:", str(e).splitlines()[0][:200])
    if driver.find_elements(By.XPATH, "//div[contains(@class,'jobs-easy-apply-modal')] | //div[@role='dialog' and .//form]"):
        print_lg("Easy Apply popup is still open after 3 tries, reloading the search page to get rid of it.")
        try: driver.refresh(); sleep(3)
        except Exception: pass






# True when the browser is gone (closed window, dead session), False for errors that only affect one job or page
def session_lost(error: Exception) -> bool:
    if isinstance(error, (NoSuchWindowException, InvalidSessionIdException)): return True
    message = str(error).lower()
    return any(text in message for text in ("invalid session id", "no such window", "chrome not reachable", "disconnected", "target window already closed", "session deleted", "browser has closed"))


def daily_limit_hit() -> bool:
    return max_applications_per_day > 0 and job_history is not None and job_history.applied_today >= max_applications_per_day


def daily_limit_reached() -> bool:
    if daily_limit_hit():
        print_lg(f"\n###### Reached today's limit of {max_applications_per_day} applications (max_applications_per_day in config/settings.py). Stopping. ######\n")
        return True
    return False


#< Speed: your delays and limits from config/settings.py
def delay_range(delay) -> tuple[float, float]:
    '''(min, max) from a delay setting: (5, 10), [5, 10], (5,) or 5.'''
    values = [max(0.0, float(value)) for value in delay] if isinstance(delay, (list, tuple)) else [max(0.0, float(delay or 0))]
    return (min(values), max(values)) if values else (0.0, 0.0)


def wait_for(delay, label: str = "", in_application: bool = False, count: bool = True) -> None:
    '''
    Waits a random time between the two numbers of `delay` (seconds, from config/settings.py). Pause / Stop / Quit in the control window
    work meanwhile. `in_application`: a wait inside a form, where Skip drops the job (raises `SkipJob`) and "Stop after this job" doesn't
    shorten the wait (the job is finished at the normal pace).
    '''
    low, high = delay_range(delay)
    if high <= 0: return
    seconds = random.uniform(low, high)
    if label:
        shown = f"{seconds / 60:.0f} min" if seconds >= 120 else f"{seconds:.0f}s"
        if seconds >= 20: print_lg(f"   waiting {shown} ({label})")
        control.status(f"Waiting {shown} ({label})")
    started, paused_before = time.time(), control.paused_seconds
    control.wait(seconds, allow_skip=in_application, return_on_stop=not in_application)
    if count: stopwatch["waiting (your delays)"] += time.time() - started - (control.paused_seconds - paused_before)


def after_application() -> None:
    '''After each application sent: `delay_after_application`, or a longer break every `break_every_applications` applications.'''
    global applications_since_break
    applications_since_break += 1
    if break_every_applications and applications_since_break >= break_every_applications:
        applications_since_break = 0
        low, high = delay_range(break_minutes)
        wait_for((low * 60, high * 60), f"break after {break_every_applications} applications")
    else:
        wait_for(delay_after_application, "delay_after_application")


def wait_for_hourly_limit() -> None:
    '''`max_applications_per_hour`: when reached, waits until the oldest application of the last hour is an hour old.'''
    if max_applications_per_hour <= 0 or not job_history: return
    recent = job_history.applied_since(datetime.now() - timedelta(hours=1))
    if len(recent) < max_applications_per_hour: return
    seconds = (recent[len(recent) - max_applications_per_hour] + timedelta(hours=1) - datetime.now()).total_seconds() + random.uniform(10, 60)
    print_lg(f"\n>-> {len(recent)} applications in the last hour (max_applications_per_hour = {max_applications_per_hour}).")
    wait_for((seconds, seconds), "max_applications_per_hour")
#>


# LinkedIn's messages when it stops Easy Apply for your account. All phrases are looked for in LinkedIn's popups; only the ones no job
# description would use are also looked for in the rest of the page (job descriptions and the job list are left out of that text).
_EASY_APPLY_PAUSED_TEXTS = ("applying at a fast pace", "paused easy apply", "inauthentic activit", "safeguard against automated")
_EASY_APPLY_PAUSED_ANYWHERE = ("applying at a fast pace", "paused easy apply")
_EASY_APPLY_LIMIT_TEXTS = ("daily application limit", "daily easy apply limit", "reached the easy apply limit", "limit daily submissions", "reached today's easy apply limit")
_POPUPS = "//*[@role='dialog' or @role='alertdialog' or @role='alert' or contains(@class,'artdeco-toast-item') or contains(@class,'artdeco-modal')]"
_PAGE_TEXT_JS = '''let text = document.body ? document.body.innerText : '';
for (const part of document.querySelectorAll('.jobs-box__html-content, .jobs-description__content, .scaffold-layout__list, .jobs-search-results-list'))
  if (part.innerText) text = text.split(part.innerText).join(' ');
return text;'''


def _plain(text: str) -> str:
    return " ".join((text or "").lower().replace("\u2019", "'").split())


def easy_apply_blocked_by_linkedin() -> str | None:
    '''"paused" when LinkedIn says you're applying too fast ("...we've briefly paused Easy Apply"), "limit" for its daily Easy Apply limit, else None.'''
    popups = []
    for popup in driver.find_elements(By.XPATH, _POPUPS):
        try:
            if popup.is_displayed(): popups.append(_plain(popup.text))
        except Exception: pass
    popups = " ".join(popups)
    try: page = _plain(driver.execute_script(_PAGE_TEXT_JS))
    except Exception: page = ""
    if any(phrase in popups for phrase in _EASY_APPLY_PAUSED_TEXTS) or any(phrase in page for phrase in _EASY_APPLY_PAUSED_ANYWHERE): return "paused"
    if any(phrase in popups or phrase in page for phrase in _EASY_APPLY_LIMIT_TEXTS): return "limit"
    return None


def stop_easy_apply(reason: str) -> None:
    '''
    LinkedIn paused Easy Apply ("We noticed you're applying at a fast pace...") or its daily Easy Apply limit is reached: no more Easy Apply
    in this run. Easy Apply mode ends the run; Both mode carries on with jobs that apply on the company's website.
    '''
    global dailyEasyApplyLimitReached, apply_mode, easy_apply_stopped
    if easy_apply_stopped: return
    if reason == "paused":
        easy_apply_stopped = ('LinkedIn paused Easy Apply ("We noticed you\'re applying at a fast pace"). Wait a few hours before the next run, and make '
                              '`delay_after_application` bigger and `max_applications_per_hour` smaller in config/settings.py.')
    else:
        easy_apply_stopped = "LinkedIn's daily Easy Apply limit is reached. Try again tomorrow."
    try:   # Keep the page with LinkedIn's message
        folder = os.path.join(logs_folder_path, "easy_apply_forms"); os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"linkedin-stopped-easy-apply-{datetime.now():%Y%m%d-%H%M%S}.html"), "w", encoding="utf-8") as file:
            file.write(f"<!-- {driver.current_url} -->\n" + driver.page_source)
    except Exception: pass
    if apply_mode == "both":
        apply_mode = "normal"
        print_lg(f"\n###### {easy_apply_stopped}\n###### No more Easy Apply in this run: continuing with jobs that apply on the company's website. ######\n")
    else:
        dailyEasyApplyLimitReached = True
        print_lg(f"\n###### {easy_apply_stopped}\n###### Stopping this run. ######\n")
    control.status("LinkedIn stopped Easy Apply, see the log")


_DETAILS_PANE = "//*[contains(@class,'jobs-search__job-details') or contains(@class,'jobs-details__main-content') or contains(@class,'job-view-layout')]"
# The open job's apply button. Never the "Easy Apply" search filter above the job list (aria-label "Easy Apply filter."), a job card or a popup.
_APPLY_BUTTONS = (".//*[(self::button or self::a) and (@id='jobs-apply-button-id' or contains(@class,'jobs-apply-button') or contains(@href,'openSDUIApplyFlow=true')"
                  " or contains(@aria-label,'Easy Apply') or contains(@aria-label,'Apply to') or contains(@aria-label,'company website') or normalize-space()='Easy Apply' or normalize-space()='Apply')"
                  " and not(ancestor::li[@data-occludable-job-id]) and not(ancestor::*[contains(@class,'search-reusables') or @role='dialog'])"
                  " and not(starts-with(@id,'searchFilter')) and not(@aria-label='Easy Apply filter.') and not(contains(@class,'filter-pill'))]")
# The job the details pane is showing: its title link (/jobs/view/<id>) and its Easy Apply button (data-job-id)
_PANE_JOB_LINKS = "//*[contains(@class,'top-card__job-title') or contains(@class,'top-card__title')]//a[contains(@href,'/jobs/view/')] | //*[@id='jobs-apply-button-id' and @data-job-id]"


def shown_job_ids() -> set[str]:
    '''Job IDs the details pane is showing right now.'''
    ids = set()
    for element in driver.find_elements(By.XPATH, _PANE_JOB_LINKS):
        try:
            job = element.get_attribute("data-job-id")
            if not job:
                found = re.search(r'/jobs/view/(\d+)', element.get_attribute("href") or "")
                job = found.group(1) if found else None
        except Exception: continue
        if job: ids.add(job)
    return ids


def wait_for_job_details(job_id: str, timeout: float = 10) -> bool:
    '''
    After a click on a job card, LinkedIn draws its details a moment later. Until then the pane still shows the previous job, with its
    description and its Apply button (an applied job's "Applied" made the next job look applied). Waits until the pane shows `job_id`.
    False if it still shows another job after `timeout`.
    '''
    end, empty_since = time.time() + timeout, None
    while time.time() < end:
        shown = shown_job_ids()
        if job_id in shown: return True
        if shown: empty_since = None
        else:
            empty_since = empty_since or time.time()
            if time.time() - empty_since > 3: return True   # None of LinkedIn's usual title links (its page changed): can't check, carry on
        sleep(0.3)
    return job_id in shown_job_ids()


def open_job_page(job_id: str) -> None:
    '''
    LinkedIn sometimes leaves the job's details pane empty, or draws it in a layout the bot can't read ("Unable to extract job description!",
    then "No Apply button or link"). The job's own page shows the same details, so it's opened instead. The next job reopens the job list (`back_to_results`).
    '''
    print_lg("   the job's details didn't load in the list, opening the job's own page")
    try:
        driver.get(f"https://www.linkedin.com/jobs/view/{job_id}/")
        WebDriverWait(driver, 12, poll_frequency=0.5).until(lambda d: d.find_elements(By.CLASS_NAME, "jobs-box__html-content") or apply_button(job_id)[0] or job_closed())
        buffer(1)
    except Exception: pass


def job_closed() -> bool:
    '''The open job says "No longer accepting applications".'''
    try:
        panes = driver.find_elements(By.XPATH, _DETAILS_PANE)
        return "no longer accepting applications" in (panes[0].text if panes else "").lower()
    except Exception: return False


def close_linkedin_dialogs() -> None:
    '''
    Closes popups LinkedIn leaves over the job list between jobs (an Easy Apply form left open, "Did you apply?", safety notices):
    they block the next click. A popup saying LinkedIn paused Easy Apply stops Easy Apply first.
    '''
    discard_job()
    for dialog in driver.find_elements(By.XPATH, "//div[@role='dialog' or @role='alertdialog']"):
        try:
            if not dialog.is_displayed(): continue
            if apply_mode != "normal" and any(phrase in _plain(dialog.text) for phrase in _EASY_APPLY_PAUSED_TEXTS): stop_easy_apply("paused")
            close = dialog.find_elements(By.XPATH, ".//button[@aria-label='Dismiss' or @aria-label='Close' or contains(@class,'artdeco-modal__dismiss')]")
            if close:
                click_button(close[0])
                sleep(0.5)
        except Exception: pass


#< Job loop: search -> filters -> job list -> open job -> apply -> save
class RunState:
    '''What one round of searches remembers.'''
    def __init__(self):
        self.applied_ids = get_applied_job_ids()
        self.rejected: set[str] = set()       # Jobs opened and skipped in this round (experience, bad words...)
        self.blacklisted: set[str] = set()    # Companies with about_company_bad_words


def apply_button(job_id: str = "") -> tuple[str | None, WebElement | None]:
    '''
    The open job's own apply button: ("easy", button) for Easy Apply, ("external", button) for "Apply" on the company's website, or (None, None).
    Looked for in the job's details pane only: the "Easy Apply" filter above the job list was taken for it before (clicking it switched the
    filter on / off instead of opening the form, and made every job look like an Easy Apply job).
    '''
    elements = []
    for _ in range(2):
        try:
            panes = [pane for pane in driver.find_elements(By.XPATH, _DETAILS_PANE) if pane.is_displayed()]
            root, xpath = (panes[0], _APPLY_BUTTONS) if panes else (driver, _APPLY_BUTTONS.lstrip("."))
            elements = root.find_elements(By.XPATH, xpath)
            break
        except StaleElementReferenceException:   # LinkedIn redrew the pane while it was read
            sleep(0.5)
    easy, external = None, None
    for element in elements:
        try:
            if not element.is_displayed(): continue
            shown_job = element.get_attribute("data-job-id")
            if job_id and shown_job and shown_job != job_id: continue   # Still the previous job's button
            text = " ".join(f"{element.text} {element.get_attribute('aria-label') or ''}".lower().split())
            if "easy apply" in text or "opensduiapplyflow=true" in (element.get_attribute("href") or "").lower():
                easy = easy or element
            elif "apply" in text:
                external = external or element
        except Exception: pass
    if easy is not None: return "easy", easy
    if external is not None: return "external", external
    return None, None


def start_easy_apply(button: WebElement) -> bool:
    '''
    Clicks Easy Apply and waits for the form. False if it didn't open. If LinkedIn says you're applying too fast ("we've briefly paused
    Easy Apply") or its daily limit is reached, Easy Apply is stopped for this run (see `stop_easy_apply`).
    '''
    click_button(button)
    end = time.time() + 10
    while time.time() < end:
        blocked = easy_apply_blocked_by_linkedin()
        if blocked:
            stop_easy_apply(blocked)
            return False
        # LinkedIn sometimes shows a safety / "share your profile" notice before the form
        notice = [b for b in driver.find_elements(By.XPATH, "//button[normalize-space()='Continue applying' or .//span[normalize-space()='Continue applying'] or normalize-space()='Continue' and ancestor::div[@role='dialog' and not(.//form)]]") if b.is_displayed()]
        if notice:
            click_button(notice[0])
            sleep(1)
        try:
            find_easy_apply_modal(1)
            return True
        except Exception:
            pass
    blocked = easy_apply_blocked_by_linkedin()
    if blocked:
        stop_easy_apply(blocked)
        return False
    try:   # Keep this page, so the form type can be fixed
        folder = os.path.join(logs_folder_path, "easy_apply_forms"); os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"not-opened-{datetime.now():%Y%m%d-%H%M%S}.html")
        with open(path, "w", encoding="utf-8") as file: file.write(f"<!-- {driver.current_url} -->\n" + driver.page_source)
        print_lg(f"   page saved for fixing: {path}")
    except Exception: pass
    return False


def on_results_page() -> bool:
    return "/jobs/search" in driver.current_url


def back_to_results(page_url: str) -> None:
    '''Easy Apply sometimes opens its own page (LinkedIn's newer flow): reopen the job list so the next jobs aren't lost.'''
    if on_results_page(): return
    print_lg("   back to the job list")
    driver.get(page_url)
    try: wait.until(EC.presence_of_all_elements_located((By.XPATH, "//li[@data-occludable-job-id]")))
    except Exception: pass
    buffer(1)


def handle_job(listing_id: str, state: RunState, page_url: str) -> str:
    '''
    One job from the list: check it, open it, apply, save the result.
    Returns "list-skip" (decided from the list, not opened), "skipped" (opened, doesn't fit), "failed", "applied" (sent), "saved" (external link saved) or "stop".
    '''
    global failed_count, skip_count, easy_applied_count, normal_applied_count, external_jobs_count, tabs_count, useNewResume
    # 1. The job card: handled before? senior title? Easy Apply? (no click needed)
    back_to_results(page_url)
    close_linkedin_dialogs()
    if dailyEasyApplyLimitReached: return "stop"
    for attempt in range(3):   # LinkedIn redraws the list now and then: find the card again, then load the page again once
        try:
            if attempt == 1: sleep(1)
            if attempt == 2:
                driver.get(page_url)
                wait.until(EC.presence_of_all_elements_located((By.XPATH, "//li[@data-occludable-job-id]")))
                buffer(1)
            cards = driver.find_elements(By.XPATH, f"//li[@data-occludable-job-id='{listing_id}']")
            if not cards:
                if attempt < 2: continue
                print_lg(f"Job {listing_id} is no longer in the list, skipping it.")
                return "list-skip"
            job_id, title, company, work_location, work_style, skip = get_job_main_details(cards[0], state.blacklisted, state.rejected)
            break
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException):
            if attempt == 2:
                print_lg(f"Job card {listing_id} changed or disappeared, skipping it.")
                return "list-skip"
        except WebDriverException as e:   # Eg: "element click intercepted" when a popup covers the list: one job must not end the run
            if session_lost(e): raise
            close_linkedin_dialogs()
            if dailyEasyApplyLimitReached: return "stop"
            if attempt == 2:
                print_lg(f"Couldn't open job card {listing_id}, skipping it. ({str(e).splitlines()[0][:150]})")
                return "list-skip"
    if skip: return "list-skip"
    if dailyEasyApplyLimitReached: return "stop"
    if not wait_for_job_details(job_id):   # The pane still shows the previous job: click once more
        try: click_button(driver.find_element(By.XPATH, f"//li[@data-occludable-job-id='{job_id}']//a"))
        except Exception: pass
        if not wait_for_job_details(job_id):
            print_lg(f'The details of "{title} | {company}" did not load, skipping it for now (tried again next run).')
            failed_job(job_id, "https://www.linkedin.com/jobs/view/" + job_id, "Pending", "Unknown", "Job details didn't load", "The details pane kept showing another job", "Unknown", "Not Available")
            failed_count += 1
            return "failed"
    if job_id in state.applied_ids or driver.find_elements(By.CLASS_NAME, "jobs-s-apply__application-link"):
        print_lg(f'Already applied to "{title} | {company}". Job ID: {job_id}')
        return "list-skip"

    print_lg(f'\n-> "{title} | {company}"  (Job ID {job_id})')
    control.status(f"Applying: {title} @ {company}")
    answer_resolver.start_job()     # Each question is asked at most once per application
    started, paused_at_start = time.time(), control.paused_seconds
    spent = lambda: time.time() - started - (control.paused_seconds - paused_at_start)   # Time paused from the control window left out
    job_link = "https://www.linkedin.com/jobs/view/" + job_id
    application_link, date_applied, date_listed, resume, screenshot_name = "Easy Applied", "Pending", "Unknown", "Pending", "Not Available"
    skills, reposted, questions_list, uploaded, normal_applied = "Needs an AI", False, None, False, False

    # 2. The description: experience / bad words / clearance (the company box only if you set about_company_bad_words)
    description, experience_required, skip, reason, message = get_job_description()
    if description == "Unknown":   # The details pane stayed empty: read the job's own page
        open_job_page(job_id)
        description, experience_required, skip, reason, message = get_job_description()
    if not skip:
        try:
            state.rejected, state.blacklisted, jobs_top_card = check_blacklist(state.rejected, job_id, company, state.blacklisted)
        except ValueError as e:
            skip, reason, message = True, "Found Blacklisted words in About Company", str(e)
        except Exception:
            jobs_top_card = None
    if skip:
        print_lg(f'   skipped: {reason}' + (f" ({experience_required} years required)" if reason == "Required experience is high" else ""))
        failed_job(job_id, job_link, resume, date_listed, reason, message, "Skipped", screenshot_name)
        state.rejected.add(job_id)
        skip_count += 1
        skip_reasons[reason] += 1
        stopwatch["opened, then skipped"] += spent()
        return "skipped"

    # Details for the excel, only what's already on the page (no waiting)
    hr_cards = driver.find_elements(By.CLASS_NAME, "hirer-card__hirer-information")
    try:
        hr_link = hr_cards[0].find_element(By.TAG_NAME, "a").get_attribute("href") if hr_cards else ""
        hr_name = hr_cards[0].find_element(By.TAG_NAME, "span").text if hr_cards else ""
    except Exception: hr_link, hr_name = "", ""
    try:
        posted = jobs_top_card.find_element(By.XPATH, './/span[contains(normalize-space(), " ago")]').text
        reposted = "Reposted" in posted
        date_listed = calculate_date_posted(posted.replace("Reposted", "").strip())
    except Exception: pass
    if use_AI and ai_skill_extraction and description != "Unknown":
        try:
            if ai_provider.lower() == "openai": skills = ai_extract_skills(aiClient, description)
            elif ai_provider.lower() == "deepseek": skills = deepseek_extract_skills(aiClient, description)
            elif ai_provider.lower() == "gemini": skills = gemini_extract_skills(aiClient, description)
        except Exception as e:
            skills = "Error extracting skills"

    # 3. Apply
    kind, button = apply_button(job_id)
    if kind is None and not job_closed() and "/jobs/view/" not in driver.current_url:   # Apply button not drawn in the list: try the job's own page
        open_job_page(job_id)
        kind, button = apply_button(job_id)
    if kind is None and job_closed():
        print_lg("   skipped: no longer accepting applications")
        failed_job(job_id, job_link, resume, date_listed, "Job is closed", "No longer accepting applications", "Skipped", screenshot_name)
        skip_count += 1
        skip_reasons["job closed"] += 1
        return "skipped"
    if kind == "easy" and apply_mode == "normal":
        reason = "Easy Apply job (LinkedIn paused Easy Apply)" if easy_apply_stopped else "Easy Apply job (Normal Apply mode)"
        print_lg(f"   skipped: {reason}")
        skip_reasons[reason] += 1
        return "skipped"
    if kind == "easy":
        if easy_apply_stopped: return "stop" if dailyEasyApplyLimitReached else "skipped"   # Never click Easy Apply after LinkedIn paused it
        if not start_easy_apply(button):
            if easy_apply_stopped:   # LinkedIn stopped Easy Apply: this job is tried again next run. Both mode carries on with company websites
                failed_job(job_id, job_link, resume, date_listed, "Easy Apply paused by LinkedIn", easy_apply_stopped, application_link, screenshot_name)
                pending_links.add(job_id, title, company, "Easy Apply paused by LinkedIn", job_link, job_link)
                return "stop" if dailyEasyApplyLimitReached else "skipped"
            print_lg("   the Easy Apply form didn't open")
            failed_job(job_id, job_link, resume, date_listed, "Problem in Easy Applying", "The Easy Apply form didn't open", application_link, screenshot_name)
            failed_count += 1
            return "failed"
        try:
            try: date_applied, questions_list, resume, uploaded = run_easy_apply(job_id, title, company, work_location, description)
            except SkipJob: raise EasyApplyStopped("Skipped by you from the control window.", "skipped")
            stopwatch["applied (Easy Apply)"] += spent()
        except Exception as e:
            if session_lost(e): raise
            kind = e.kind if isinstance(e, EasyApplyStopped) else "error"
            message = str(e).splitlines()[0][:250] if str(e) else type(e).__name__
            print_lg(f'   Easy Apply stopped: {message}')
            if not isinstance(e, EasyApplyStopped): critical_error_log("Somewhere in Easy Apply process", e)
            failed_job(job_id, job_link, resume, date_listed, {"discarded": "Discarded by you", "skipped": "Skipped by you", "blocked": "Easy Apply paused by LinkedIn"}.get(kind, "Problem in Easy Applying"), message, application_link, screenshot_name)
            failed_count += kind == "error"
            if kind != "discarded": pending_links.add(job_id, title, company, f"Easy Apply: {message}", job_link, job_link)
            discard_job()
            stopwatch["failed applications"] += spent()
            if dailyEasyApplyLimitReached: return "stop"
            return "skipped" if kind != "error" else "failed"
    else:
        if apply_mode == "easy":
            print_lg("   skipped: no Easy Apply button on this job")
            failed_job(job_id, job_link, resume, date_listed, "No Easy Apply button", "No Easy Apply button on the job page", application_link, screenshot_name)
            return "skipped"
        # Company website (Normal Apply mode, or Both)
        application_link = open_external_link(button) if button is not None else None
        tabs_count = len(driver.window_handles)
        if not application_link:
            failed_job(job_id, job_link, resume, date_listed, "No Apply button or link", "Couldn't open the Apply button or the company's link", "Unknown", screenshot_name)
            failed_count += 1
            return "failed"
        if normal_applier:
            outcome = normal_applier.apply(application_link, job_id=job_id, title=title, company=company, description=description, job_location=work_location)
            stopwatch["applied (Normal Apply)" if outcome.status == "submitted" else "failed applications"] += spent()
            application_link = outcome.url
            tabs_count = len(driver.window_handles)
            if outcome.questions: questions_list = outcome.questions
            if outcome.status == "submitted":
                date_applied = datetime.now()
                resume = os.path.basename(normal_applier.resume_path) if normal_applier.resume_path else "Not uploaded"
                normal_applied = True
            elif outcome.status == "discarded":
                print_lg("   you chose not to submit it")
                failed_job(job_id, job_link, resume, date_listed, "Discarded by you", outcome.message, application_link, outcome.screenshot)
                return "skipped"
            elif outcome.status in ("failed", "skipped"):
                print_lg(f'   Normal Apply {outcome.status}: {outcome.message}')
                failed_job(job_id, job_link, resume, date_listed, "Skipped by you" if outcome.status == "skipped" else "Normal Apply failed", outcome.message, application_link, outcome.screenshot)
                failed_count += outcome.status == "failed"
                pending_links.add(job_id, title, company, outcome.message, application_link, job_link)
                return "failed" if outcome.status == "failed" else "skipped"
            else:   # "manual": saved in the applied jobs excel like before, and in the apply-by-hand list
                pending_links.add(job_id, title, company, outcome.message, application_link, job_link)
        else:
            pending_links.add(job_id, title, company, "External application link collected", application_link, job_link)

    # 4. Save
    submitted_jobs(job_id, title, company, work_location, work_style, description, experience_required, skills, hr_name, hr_link, resume, reposted, date_listed, date_applied, job_link, application_link, questions_list, connect_request="In Development")
    if uploaded: useNewResume = False
    state.applied_ids.add(job_id)
    if application_link == "Easy Applied": easy_applied_count += 1
    elif normal_applied: normal_applied_count += 1
    else: external_jobs_count += 1
    print_lg(f'   {"APPLIED" if isinstance(date_applied, datetime) else "link saved"}: "{title} | {company}"')
    return "applied" if isinstance(date_applied, datetime) else "saved"


def apply_extra_filters() -> None:
    '''
    Filters that have no simple code in LinkedIn's address (specific companies, industries, job functions, titles, salary...):
    picked in LinkedIn's "All filters" panel, only when you set any of them in config/search.py.
    '''
    if not (companies or location or industry or job_function or job_titles or benefits or commitments or salary): return
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, '//button[normalize-space()="All filters"]'))).click()
        buffer(1)
        wait_span_click(driver, salary)
        multi_sel_noWait(driver, companies, actions)
        for values in (location, industry, job_function, job_titles, benefits, commitments): multi_sel_noWait(driver, values)
        driver.find_element(By.XPATH, '//button[contains(translate(@aria-label, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "apply current filters to show")]').click()
        buffer(2)
    except Exception as e:
        print_lg("Couldn't set the extra filters (companies, industries...), continuing without them.", str(e).splitlines()[0][:150] if str(e) else "")


def go_through_search(search: str, state: RunState) -> None:
    '''
    One position: a LinkedIn search with all your filters in the address (Easy Apply, date posted, experience level, job type,
    remote, newest first, location), then its job list page by page, until `switch_number` applications or no more new jobs.
    '''
    first_page = linkedin_search_url(search, search_location, easy_apply=(apply_mode == "easy"), date_posted=date_posted, experience=experience_level,
                                     job_type=job_type, on_site=on_site, sort_by=sort_by, under_10_applicants=under_10_applicants,
                                     in_your_network=in_your_network, fair_chance=fair_chance_employer)
    print_lg(f'\n{"_" * 100}\n>>>> Searching for: {search} <<<<\n{first_page}\n')
    control.status(f"Searching: {search}")
    driver.get(first_page)
    if companies or location or industry or job_function or job_titles or benefits or commitments or salary:
        apply_extra_filters()
        first_page = with_page(driver.current_url, 0)   # LinkedIn adds those filters to the address, keep them for the next pages
    applied_here, pages_without_new = 0, 0
    for page in range(40):
        page_url = with_page(first_page, page)
        if page > 0:
            wait_for(delay_between_result_pages)
            print_lg(f"\n>-> Page {page + 1}\n")
            driver.get(page_url)
        try:
            wait.until(EC.presence_of_all_elements_located((By.XPATH, "//li[@data-occludable-job-id]")))
        except TimeoutException:
            print_lg(">-> No more jobs." if page else f'LinkedIn found no jobs for "{search}" with these filters.')
            return
        buffer(2)
        listing_ids = [card.get_dom_attribute('data-occludable-job-id') for card in driver.find_elements(By.XPATH, "//li[@data-occludable-job-id]")]
        new_on_page = 0
        for listing_id in listing_ids:
            # Control window: wait while paused, stop / quit if asked. A "Skip" clicked between jobs is ignored.
            control.checkpoint(allow_skip=False)
            control.clear_skip()
            if control.stop_requested or daily_limit_reached() or dailyEasyApplyLimitReached: return
            if keep_screen_awake: pyautogui.press('shiftright')
            result = handle_job(listing_id, state, page_url)
            if result == "stop": return
            if result != "list-skip": new_on_page += 1
            if result == "applied" and not (control.stop_requested or daily_limit_hit() or dailyEasyApplyLimitReached): after_application()
            elif result != "list-skip": wait_for(delay_after_skipped_job)
            if result in ("applied", "saved"):
                applied_here += 1
                if applied_here >= switch_number:
                    print_lg(f">-> {applied_here} applications for this position (switch_number), next search.")
                    return
        back_to_results(page_url)
        # Newest jobs come first: pages with only jobs you've already handled mean the rest is old too
        pages_without_new = 0 if new_on_page else pages_without_new + 1
        if stop_after_pages_without_new_jobs and pages_without_new >= stop_after_pages_without_new_jobs:
            print_lg(f">-> {pages_without_new} pages in a row without new jobs, next search.")
            return
        # Last page: fewer than a full page of jobs AND no button for the next page (LinkedIn may draw cards late, so not the count alone)
        next_page = driver.find_elements(By.XPATH, f"//button[@aria-label='Page {page + 2}'] | //button[contains(@aria-label, 'next page') or contains(@aria-label, 'Next page') or contains(@class, 'pagination__button--next')]")
        if len(listing_ids) < JOBS_PER_PAGE and not next_page:
            print_lg(">-> Last page of results.")
            return


def apply_to_jobs(search_terms: list[str]) -> None:
    '''One round: one position per search (random order), with a fresh job history.'''
    global job_history
    job_history = JobHistory(file_name, failed_file_name, avoid_same_company_days, retry_failed_jobs, max_applications_per_company)
    state = RunState()
    searches = plan_searches(search_terms, randomize_search_order)
    print_lg(f"Positions for this run, in this order: {searches}")
    for number, search in enumerate(searches):
        if control.stop_requested or daily_limit_reached() or dailyEasyApplyLimitReached: return
        if number:
            wait_for(delay_between_searches, "delay_between_searches")
            if control.stop_requested: return
        try:
            go_through_search(search, state)
        except StaleElementReferenceException:
            print_lg("The page changed while reading it, next search.")
        except TimeoutException:
            print_lg(f"LinkedIn found no jobs for {search} with these filters.")
        except WebDriverException as e:
            if session_lost(e):
                print_lg("Browser window closed or session is invalid. Ending application process.", str(e).splitlines()[0][:200])
                raise
            print_lg("Browser error in this search, next search:", str(e).splitlines()[0][:200])
            discard_job()
        except Exception as e:
            print_lg("Problem in this search, next search:", e)
            critical_error_log("In Applier", e)
#>


def run(total_runs: int) -> int:
    if dailyEasyApplyLimitReached:
        return total_runs
    print_lg("\n########################################################################################################################\n")
    print_lg(f"Date and Time: {datetime.now()}")
    print_lg(f"Cycle number: {total_runs}")
    print_lg(f"Currently looking for jobs posted within '{date_posted}' and sorting them by '{sort_by}'")
    apply_to_jobs(search_terms)
    print_lg("########################################################################################################################\n")
    if run_non_stop and not dailyEasyApplyLimitReached and not control.stop_requested:
        print_lg("Sleeping for 10 min... (the control window can still Pause / Stop / Quit)")
        control.status("Waiting 10 minutes before the next run...")
        control.wait(600)
    buffer(3)
    return total_runs + 1



chatGPT_tab = False
linkedIn_tab = False


def choose_apply_mode() -> None:
    '''Sets `apply_mode` (asking with a popup if it's "ask") and the matching Easy Apply search filter.'''
    global apply_mode, easy_apply_only
    if os.environ.get("APPLY_AND_PRAY_MODE") in ("easy", "normal", "both", "feed", "connect"): apply_mode = os.environ["APPLY_AND_PRAY_MODE"]   # Chosen in the dashboard
    if apply_mode == "ask":
        choices = {"Easy Apply only": "easy", "Normal Apply only": "normal", "Both": "both"}
        if run_in_background: apply_mode = "easy"
        else: apply_mode = choices.get(pyautogui.confirm("Which applications should the bot do?\n\nEasy Apply: the form opens inside LinkedIn.\nNormal Apply: the company's own website opens and the bot fills it (Greenhouse, Lever, Ashby, Google Forms, plain company forms, sign-up if needed). Jobs it can't finish are saved in all excels/apply_by_hand.html.", "Choose apply mode", list(choices)), "easy")
    easy_apply_only = apply_mode == "easy"
    print_lg(f'Apply mode: "{apply_mode}"')


feed_counts: dict = {}   # Feed jobs results, for the summary


def ai_write_text(instruction: str, source_text: str, role: str = "") -> str | None:
    '''Free text from the AI (Eg: an application email), or None without AI.'''
    answer = ai_raw_answer(instruction, "textarea", None, source_text, "", role)
    return answer.strip() if isinstance(answer, str) and answer.strip() else None


def save_page_for_fixing(name: str) -> None:
    '''Keeps the current page's HTML in logs/, so a LinkedIn layout the bot can't read can be fixed.'''
    try:
        folder = os.path.join(logs_folder_path, "easy_apply_forms"); os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as file: file.write(f"<!-- {driver.current_url} -->\n" + driver.page_source)
        print_lg(f"   page saved for fixing: {os.path.join(folder, name)}")
    except Exception: pass


def run_feed_jobs() -> None:
    '''Feed jobs mode: jobs posted as LinkedIn posts (see modules/feed_jobs.py).'''
    global feed_counts
    from modules.feed_jobs import FeedJobs
    terms = list(search_terms)
    if randomize_search_order: random.shuffle(terms)
    print_lg(f"Feed jobs: searching posts for {terms}")
    feed = FeedJobs(driver, control=control, normal_applier=normal_applier,
                    resume_path=default_resume_path if os.path.exists(default_resume_path) else None,
                    ai_write=ai_write_text if (use_AI and aiClient) else None, experience_of=extract_years_of_experience, save_page=save_page_for_fixing)
    feed_counts = feed.run(terms)


connect_counts: dict = {}   # Connection requests results, for the summary


def run_connections() -> None:
    '''Networking mode: who accepted, personal messages and follow-ups, connection requests (modules/messages.py, modules/connections.py).'''
    global connect_counts
    from modules.messages import NetworkRun   # Who accepted -> messages and follow-ups -> connection requests
    network = NetworkRun(driver, control=control, save_page=save_page_for_fixing)
    connect_counts = dict(network.run(), stop_reason=" ".join(reason for reason in (network.message_stop, network.stop_reason) if reason))


def confirm_normal_submit(job: str) -> bool:
    '''"Pause before submit" for Normal Apply. Returns False if the user chose to discard.'''
    global pause_before_submit
    if not pause_before_submit:
        wait_for(delay_before_submit, in_application=True, count=False)
        return True
    decision = pyautogui.confirm(f'{job}\n\n1. Please check the form in the browser tab.\n2. You can fix anything there.\n3. DO NOT click the website\'s Submit button.\n\n\nYou can turn off "Pause before submit" in config/questions.py\nTo TEMPORARILY disable pausing, click "Disable Pause"', "Confirm your information", ["Disable Pause", "Discard Application", "Submit Application"])
    if decision == "Discard Application": return False
    pause_before_submit = "Disable Pause" != decision
    return True

def main() -> None:
    total_runs = 1
    try:
        global linkedIn_tab, tabs_count, useNewResume, aiClient, default_resume_path, normal_applier, ai_profile_text
        alert_title = "Error Occurred. Closing Browser!"
        validate_config()
        global run_started
        run_started = time.time()
        choose_apply_mode()
        if show_control_panel and not run_in_background and not os.environ.get("APPLY_AND_PRAY_DASHBOARD"): control.start_panel()   # Started from the dashboard: its Run page is the control panel
        answer_resolver.review_ai_answers = review_ai_answers
        answer_resolver.popup_timeout_minutes = popup_timeout_minutes
        answer_resolver.on_popup_closed = lambda: focus_browser(driver)   # Popups take the focus, give it back to the browser

        # Find the resume even if the path is relative to the parent folder
        default_resume_path = resolve_resume_path(default_resume_path) or default_resume_path
        
        if not os.path.exists(default_resume_path):
            pyautogui.alert(text='Your default resume "{}" is missing! Please update it\'s folder path "default_resume_path" in config.py\n\nOR\n\nAdd a resume with exact name and path (check for spelling mistakes including cases).\n\n\nFor now the bot will continue using your previous upload from LinkedIn!'.format(default_resume_path), title="Missing Resume", button="OK")
            useNewResume = False
        
        # Login to LinkedIn
        tabs_count = len(driver.window_handles)
        driver.get("https://www.linkedin.com/login")
        if not is_logged_in_LN(): login_LN()
        
        linkedIn_tab = driver.current_window_handle

        # # Login to ChatGPT in a new tab for resume customization
        # if use_resume_generator:
        #     try:
        #         driver.switch_to.new_window('tab')
        #         driver.get("https://chat.openai.com/")
        #         if not is_logged_in_GPT(): login_GPT()
        #         open_resume_chat()
        #         global chatGPT_tab
        #         chatGPT_tab = driver.current_window_handle
        #     except Exception as e:
        #         print_lg("Opening OpenAI chatGPT tab failed!")
        if use_AI:
            if ai_provider == "openai":
                aiClient = ai_create_openai_client()
            # Create DeepSeek client
            elif ai_provider == "deepseek":
                aiClient = deepseek_create_client()
            elif ai_provider == "gemini":
                aiClient = gemini_create_client()
            if aiClient:
                answer_resolver.ai_answer = ai_answer_any
                answer_resolver.ai_writer = ai_write_from_notes

            try:
                about_company_for_ai = " ".join([word for word in (first_name+" "+last_name).split() if len(word) > 3])
                print_lg(f"Extracted about company info for AI: '{about_company_for_ai}'")
            except Exception as e:
                print_lg("Failed to extract about company info!", e)
        
        if apply_mode in ("normal", "both", "feed"):   # Feed jobs fill the forms linked in posts with Normal Apply
            account_email = (portal_email or "").strip() or profile_email
            if not portal_password: print_lg("No password in config/portal_login.py: websites that need an account are saved for you to apply by hand.")
            normal_applier = NormalApplier(driver, answer_resolver, enabled_sites=normal_apply_sites,
                                           resume_path=default_resume_path if os.path.exists(default_resume_path) else None,
                                           popups_enabled=not run_in_background, confirm_submit=confirm_normal_submit,
                                           screenshot=lambda job_id, reason: screenshot(driver, job_id, reason), close_tabs=close_tabs,
                                           max_fill_attempts=max_fill_attempts, portal_email=account_email, portal_password=portal_password,
                                           accounts=AccountBook() if portal_password and account_email else None, control=control,
                                           failed_forms_file=os.path.join(os.path.dirname(file_name) or "all excels", "failed_forms.json"))

        # Everything the AI may use about you: config details + resume text
        ai_profile_text = user_profile_text(default_resume_path)
        if use_AI: print_lg(f"AI will answer using your details and resume ({len(ai_profile_text)} characters).")

        # Start applying to jobs
        driver.switch_to.window(linkedIn_tab)
        if apply_mode == "feed":
            run_feed_jobs()
            return
        if apply_mode == "connect":
            run_connections()
            return
        total_runs = run(total_runs)
        while run_non_stop and not control.stop_requested:
            if cycle_date_posted:
                date_options = ["Any time", "Past month", "Past week", "Past 24 hours"]
                global date_posted
                current_index = date_options.index(date_posted) if date_posted in date_options else -1
                if stop_date_cycle_at_24hr: date_posted = date_options[min(current_index+1, len(date_options)-1)]
                else:                       date_posted = date_options[(current_index+1) % len(date_options)]
            if alternate_sortby:
                global sort_by
                sort_by = "Most recent" if sort_by == "Most relevant" else "Most relevant"
                total_runs = run(total_runs)
                sort_by = "Most recent" if sort_by == "Most relevant" else "Most relevant"
            total_runs = run(total_runs)
            if dailyEasyApplyLimitReached:
                break
        

    except QuitBot:
        print_lg("You clicked 'Quit now' in the control window.")
    except (NoSuchWindowException, WebDriverException) as e:
        print_lg("Browser window closed or session is invalid. Exiting.", str(e).splitlines()[0][:200])
    except Exception as e:
        critical_error_log("In Applier Main", e)
        pyautogui.alert(e,alert_title)
    finally:
        control.close_panel()
        runs_done = total_runs - 1 if total_runs > 1 else 1   # `total_runs` is the number of the next run
        summary = "Runs: {}\nJobs Easy Applied: {}\nJobs Normal Applied: {}\nExternal job links collected: {}\nTotal applied or collected: {}\nFailed jobs: {}\nOpened, then skipped (experience, bad words...): {}\nSkipped from the job list (not opened): {}\nSaved to apply by hand: {}\n".format(runs_done,easy_applied_count,normal_applied_count,external_jobs_count,easy_applied_count + normal_applied_count + external_jobs_count,failed_count,skip_count,quick_skip_count,pending_links.added_this_run)
        # Speed: applications per hour, and where the time went
        minutes = max((time.time() - run_started - control.paused_seconds) / 60, 0.1)   # Time paused from the control window left out
        sent = easy_applied_count + normal_applied_count
        summary += f"\nSpeed: {sent} applications in {minutes:.0f} min = {sent * 60 / minutes:.1f} per hour" + (f" ({minutes / sent:.1f} min each)" if sent else "") + "\n"
        searching = max(0.0, time.time() - run_started - control.paused_seconds - sum(stopwatch.values()))
        summary += "Time spent: " + ", ".join(f"{name} {seconds / 60:.1f} min" for name, seconds in (list(stopwatch.most_common()) + [("searching and skipping from the list", searching), ("paused by you", control.paused_seconds)]) if seconds >= 6) + "\n"
        if easy_apply_stopped: summary += f"\n{easy_apply_stopped}\n"
        if connect_counts:
            c = connect_counts
            summary += (f"\nNetworking: {c.get('accepted', 0)} accepted your request. Messages sent: {c.get('messages_sent', 0)}, follow-ups: {c.get('follow_ups_sent', 0)}, "
                        f"replied (your turn): {c.get('replied', 0)}, failed: {c.get('messages_failed', 0)}.\n"
                        f"Connection requests: {c.get('sent', 0)} sent ({c.get('with_note', 0)} with a note), {c.get('already', 0)} already pending or connected, {c.get('failed', 0)} failed.\n")
            if c.get("stop_reason"): summary += c["stop_reason"] + "\n"
        if feed_counts:
            summary += ("\nFeed jobs: {posts} new posts read. Applied through links: {applied}. Emails sent: {emails_sent}, waiting for you in Review: {emails_drafted}. "
                        "Saved for you: {saved_for_you}. Failed: {apply_failed}. People saved for Networking: {leads}. Skipped: {skipped}.\n").format(**feed_counts)
        if skip_reasons:
            summary += "\nTop skip reasons:\n" + "\n".join(f"  {count} x {reason}" for reason, count in skip_reasons.most_common(6)) + "\n"
        if randomly_answered_questions: print_lg("\n\nQuestions randomly answered:\n  {}  \n\n".format(";\n".join(str(question) for question in randomly_answered_questions)))
        quotes = choice([
            "Never quit. You're one step closer than before. - Shubham", 
            "All the best with your future interviews, you've got this. - Shubham", 
            "Keep up with the progress. You got this. - Shubham", 
            "If you're tired, learn to take rest but never give up. - Shubham",
            "Success is not final, failure is not fatal, It is the courage to continue that counts. - Winston Churchill (Not a sponsor)",
            "Believe in yourself and all that you are. Know that there is something inside you that is greater than any obstacle. - Christian D. Larson (Not a sponsor)",
            "Every job is a self-portrait of the person who does it. Autograph your work with excellence. - Jessica Guidobono (Not a sponsor)",
            "The only way to do great work is to love what you do. If you haven't found it yet, keep looking. Don't settle. - Steve Jobs (Not a sponsor)",
            "Opportunities don't happen, you create them. - Chris Grosser (Not a sponsor)",
            "The road to success and the road to failure are almost exactly the same. The difference is perseverance. - Colin R. Davis (Not a sponsor)",
            "Obstacles are those frightful things you see when you take your eyes off your goal. - Henry Ford (Not a sponsor)",
            "The only limit to our realization of tomorrow will be our doubts of today. - Franklin D. Roosevelt (Not a sponsor)",
            ])
        sponsors = "Be the first to have your name here!"
        timeSaved = (easy_applied_count * 80) + (normal_applied_count * 120) + (external_jobs_count * 20) + (skip_count * 10)
        timeSavedMsg = ""
        if timeSaved > 0:
            timeSaved += 60
            timeSavedMsg = f"In this run, you saved approx {round(timeSaved/60)} mins ({timeSaved} secs), if it helped, star the project on GitHub."
        msg = f"{quotes}\n\n\n{timeSavedMsg}\nProject, help and bug reports: https://github.com/saif-siddiqui06/Apply-and-Pray\n\n\nSummary:\n{summary}\n\n\nBest regards,\nShubham\nhttps://www.linkedin.com/in/shubham-sunil-kumar-333547133/\n\nTop Sponsors:\n{sponsors}"
        print_lg("\n" + "#" * 60 + "\n" + summary + "#" * 60)   # Once in the log; the popup below shows the same summary
        pyautogui.alert(msg, "Exiting..")
        print_lg("Closing the browser...")
        if pending_links.added_this_run:
            print_lg(f"{pending_links.added_this_run} new jobs to apply by hand: {os.path.abspath(pending_links.html_path)}")
            if open_apply_by_hand_page: pending_links.open_page()
        if tabs_count >= 10:
            msg = "NOTE: IF YOU HAVE MORE THAN 10 TABS OPENED, PLEASE CLOSE OR BOOKMARK THEM!\n\nOr it's highly likely that application will just open browser and not do anything next time!" 
            pyautogui.alert(msg,"Info")
            print_lg("\n"+msg)
        if use_AI and aiClient:
            try:
                if ai_provider.lower() == "openai":
                    ai_close_openai_client(aiClient)
                elif ai_provider.lower() == "deepseek":
                    ai_close_openai_client(aiClient)
                elif ai_provider.lower() == "gemini":
                    pass # Gemini client does not need to be closed
                print_lg(f"Closed {ai_provider} AI client.")
            except Exception as e:
                print_lg("Failed to close AI client:", e)
        try:
            if driver:
                driver.quit()
        except WebDriverException as e:
            print_lg("Browser already closed.", e)
        except Exception as e: 
            critical_error_log("When quitting...", e)


if __name__ == "__main__":
    main()
