# 🙏 Apply & Pray

> **The AI-powered LinkedIn job application bot for people who are tired of clicking "Easy Apply" like it is a part-time job.**

Applying to jobs is a full-time job. This bot works overtime.

---

## 💀 Why This Exists

At some point, humanity collectively agreed that job seekers should upload a resume, manually retype it, answer the same questions, write cover letters, and repeat until motivation reaches critically low battery mode.

Welcome to **Apply & Pray**.

> Apply. Pray. Repeat. Preferably with fewer clicks.

---

## 🚀 What This Bot Does

The bot can search LinkedIn jobs, read job descriptions, fill application forms, answer repetitive screening questions, upload resumes, generate AI-assisted content when configured, and track application history through a local dashboard.

---

## 📦 Requirements

- **Python 3.11.x**
- **Google Chrome** latest stable version
- **Windows 10/11** recommended
- Internet connection
- LinkedIn account
- Resume PDF

> Python 3.11 is recommended because Selenium and `undetected-chromedriver` are more stable there than on newer bleeding-edge Python versions.

---

## ⚙️ Installation

### 1. Install Python 3.11

Install Python 3.11 and enable **Add Python to PATH**.

Verify:

```powershell
py -3.11 --version
```

### 2. Create a Virtual Environment

```powershell
cd C:\Users\Test\Documents\Apply-and-Pray
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Add Your Details

Your details are **never** stored in the code. They live in `user_data/`, which git ignores, so you can update the project or share it safely.

| Where | What |
|---|---|
| `user_data/settings.json` | Your values: name, phone, search terms, answers... One section per config file, Eg: `{"personals": {"first_name": "Asha", "phone_number": "9876543210"}, "search": {"search_terms": ["Data Analyst"]}}` |
| Windows Credential Manager | Passwords and API keys. Save them with `python setup/set_secret.py gemini_api_key` (typed hidden). `python setup/set_secret.py --list` shows which are set |
| `config/*.py` | **Defaults and the explanation of every setting.** Read them to see what you can set, but don't type your details there |

**The easy way: run `python app.py` and use the Setup tab**, which fills all of this for you, step by step.

Already used an older version with your details typed into `config/*.py`? Copy your old `config` folder somewhere, update the project, then run:

```powershell
python setup/migrate_config.py "C:\path	o\old\config"
```

### 5. Add Your Resume

Put your resume in `user_data/resumes/` and set `default_resume_path` (section `questions`) to its path, Eg: `"user_data/resumes/resume.pdf"`.

---

## ▶️ Run the Bot

```powershell
python runAiBot.py
```

Before running, close all Chrome windows, keep fewer than 10 tabs open, and make sure Chrome is updated.

---

## 🔀 Easy Apply and Normal Apply

Set `apply_mode` in `config/settings.py` (or leave it as `"ask"` to choose at startup):

| Mode | What it does |
|---|---|
| `"easy"` | LinkedIn Easy Apply only (the form opens inside LinkedIn). |
| `"normal"` | Only jobs where Apply opens the company's website. The bot fills **Greenhouse, Lever, Ashby, Google Forms** and **any other website with a plain application form** (it follows "Apply" links to find it). Websites that need a login or account (Workday, iCIMS, sign-up pages), closed forms and pages without a form are saved in the applied jobs excel for you to apply by hand. Choose which are filled with `normal_apply_sites`. |
| `"both"` | Easy Apply when LinkedIn shows it, Normal Apply otherwise. |

### Missing details popup

For every question, the bot looks for an answer in this order:

1. **Saved answers**: answers you gave earlier, in `config/saved_answers.json`
2. **Your config**: `config/personals.py` and `config/questions.py`
3. **AI**: only if `use_AI = True` in `config/secrets.py`
4. **Popup**: asks you. Click **Save for all jobs** to reuse the answer next time, or **This job only** for company-specific questions like "Why do you want to work at X?"

`config/saved_answers.json` is plain JSON. Edit an `"answer"` to change it, or delete an entry to be asked again. Saved answers win over the config, so you can also use this file to fix a question the bot answers wrong.

Settings: `ask_instead_of_guessing = False` brings back the old guessing behaviour. Popups are off when `run_in_background = True`.
A popup you don't answer within `popup_timeout_minutes` (default 5) is skipped by itself, so an unattended run isn't stuck on one question (`0` = wait for ever). The countdown stops as soon as you type or click in the popup.

**Write with AI**: for open questions ("Share the most impressive thing you have built"), type a few words in the popup (Eg: "RAG chatbot for my college, 500 students use it, FastAPI + Gemini") and click **Write with AI**. AI turns your notes into a full answer you can edit before saving. Needs `use_AI = True`. Set `review_ai_answers = True` to get this popup for every long AI answer, not only when AI couldn't answer by itself.

**Always keep `pause_before_submit = True` for your first runs** and check each form in the browser before it's submitted.

Each question is asked **at most once per application**. If you click **Skip** on a required question, or a page still isn't accepted after `max_fill_attempts` tries (default 3), the application is skipped and the bot moves on without waiting for you.

### Websites that need an account (sign up / sign in)

Put an email and a password in `config/portal_login.py` (git-ignored). When a job website asks you to sign in, the bot:

1. Signs in if it created an account there before (kept in `config/portal_accounts.json`, no passwords in it), otherwise clicks "Create account".
2. Fills the sign-up form: the password boxes get your portal password, everything else comes from your config / saved answers / AI (with your resume) / a popup.
3. Asks before creating the account (same "pause before submit" dialog).
4. Shows a popup for an emailed verification code, or asks you to click the emailed link.

Use a **new password you don't use anywhere else**: the bot types it into many websites. It only types it on `https` pages and never on "Sign in with Google / LinkedIn" pages (those jobs are saved for you instead).

### No repeat applications

The bot remembers every job in the applied and failed jobs excels and skips:
* the same LinkedIn job again,
* the same job reposted by the company under a new ID (same company + same title),
* a company you already applied to `max_applications_per_company` times (default 2) in the last `avoid_same_company_days` days
  (config/search.py, default 7, `0` turns the company limit off),
* jobs that failed or were skipped before (set `retry_failed_jobs = True` to try them again).

### Searching

Each search is **one position** from your `search_terms`. With `randomize_search_order = True` the positions are put in a new random order on
every run, so each run starts with a different position. A longer position that contains a shorter one is folded into it
("Python Developer Intern" is covered by "Python Developer").

All filters go straight into the LinkedIn search address (the same codes linkedin.com puts there when you pick filters by hand), so nothing
is clicked and nothing is typed into LinkedIn's search box:

| config/search.py | In the address |
|---|---|
| the position | `keywords=Data%20Analyst` |
| `search_location` | `location=India` (one place; a list like "Delhi, Noida, India, Bengaluru" becomes its country) |
| `easy_apply_only` / Easy Apply mode | `f_AL=true` |
| `date_posted` | `f_TPR=r86400` (24 hours), `r604800` (week), `r2592000` (month) |
| `experience_level` | `f_E=1,2` (1 Internship, 2 Entry level, 3 Associate, 4 Mid-Senior, 5 Director, 6 Executive) |
| `job_type` / `on_site` | `f_JT=F,I` / `f_WT=2` (1 On-site, 2 Remote, 3 Hybrid) |
| `sort_by` | `sortBy=DD` (Most recent) or `R` (Most relevant) |
| `under_10_applicants`, `in_your_network`, `fair_chance_employer` | `f_EA=true`, `f_JIYN=true`, `f_FCE=true` |
| next pages | `start=25`, `start=50`, ... |

The full address is printed in the log, so you can open it in your own browser to see exactly what the bot sees.
Filters that have no address code (`companies`, `industry`, `job_function`, `benefits`, `salary`...) are only set through LinkedIn's
"All filters" panel when you fill them in.

### Control window (Pause / Resume, Skip, Stop, Quit)

A small window opens in the bottom-right corner while the bot runs (`show_control_panel` in config/settings.py):

* **Pause / Resume**: the bot waits at the next safe point. Fill anything yourself in the browser, then click Resume and the bot continues from there.
* **Skip this job**: drops the current application (never submits it) and goes to the next job. The job is saved in the apply-by-hand list.
* **Stop after this job**: finishes the current job, then shows the summary.
* **Quit now** (click twice): stops right away and shows the summary.

### Jobs to apply by hand

Every job the bot couldn't finish (login needed, no form, a question it couldn't answer, or skipped by you) is saved in
`all excels/apply_by_hand.csv` and `all excels/apply_by_hand.html` (clickable links, newest first). The page opens at the end of a run
when new jobs were added (`open_apply_by_hand_page`). The links stay there after the browser closes.

### How a run works

For each position (one at a time, in a new random order every run):

1. **Search**: one LinkedIn address with the position and all your filters (see Searching above). Newest jobs first.
2. **Job list**: each job is decided from its card, without opening it: already applied or handled before, a repost, a company at its
   `max_applications_per_company` limit, a title with one of your `skip_title_words`, or no Easy Apply (in Easy Apply mode) -> skipped.
   After `stop_after_pages_without_new_jobs` pages with only old jobs, the bot goes to the next search.
3. **Open the job**: the bot waits until LinkedIn shows that job's details (not the previous job's), then checks the description first
   (experience required, `bad_words`, security clearance) and jobs that are no longer accepting applications.
4. **Apply**: the job's own Apply button decides: "Easy Apply" or "Apply" on the company website (the "Easy Apply" filter button above
   the job list is never touched). Easy Apply page by page (Next / Review / Submit), in LinkedIn's popup or on its separate apply page; the bot then
   goes back to the job list and continues with the next job. In Normal Apply / Both mode, jobs without Easy Apply go to the company's website.
   A form that can't be completed is tried `max_fill_attempts` times, then saved in `logs/easy_apply_forms/` and the bot moves on.
5. **Save** the result in the excels. Jobs it couldn't finish go to the apply-by-hand list.
6. **Wait** your delays (see Speed and delays), then the next job.

The summary at the end shows **applications per hour** (time paused from the control window left out) and where the time went.

### Speed and delays

All in `config/settings.py`, in the **SPEED AND DELAYS** section. Every delay is `(min, max)` in seconds: the bot waits a random time
between the two numbers. `(0, 0)` means no wait. Pause and Quit in the control window work during every wait; "Stop after this job"
ends the waits between jobs (the current application still finishes at the normal pace).

| Setting | Default | When |
|---|---|---|
| `delay_after_application` | `(60, 120)` | after each application is sent |
| `delay_after_skipped_job` | `(3, 8)` | after a job was opened and then skipped or failed |
| `delay_before_opening_job` | `(2, 5)` | before clicking the next job in the list |
| `delay_between_form_pages` | `(2, 5)` | before Next / Review on each Easy Apply page |
| `delay_before_submit` | `(3, 7)` | before Submit (Easy Apply and company websites) |
| `delay_between_result_pages` | `(5, 12)` | before the next page of search results |
| `delay_between_searches` | `(30, 90)` | before searching the next position |
| `break_every_applications` / `break_minutes` | `8` / `(10, 20)` | a longer break (minutes) every 8 applications, `0` = never |
| `max_applications_per_hour` | `12` | when reached, waits until the oldest application of the last hour is 1 hour old, `0` = no limit |
| `max_applications_per_day` | `50` | when reached, stops for today, `0` = no limit |

**If LinkedIn says "We noticed you're applying at a fast pace ... we've briefly paused Easy Apply"**, the bot stops Easy Apply at once:
in Easy Apply mode the run ends; in Both mode it carries on with company-website jobs only. The job is kept to try again next run and
the page is saved in `logs/easy_apply_forms/linkedin-stopped-easy-apply-*.html`. Wait a few hours, then use bigger delays and lower
limits. LinkedIn does not allow automation tools, and no delay setting removes the risk of a restriction: slower is safer.

### Google Gemini

In config/secrets.py set `use_AI = True`, `ai_provider = "gemini"` and paste your key in `gemini_api_key` (free key: https://aistudio.google.com/app/apikey).
The bot checks the key at startup. If Google retired the model in `gemini_model` ("This model ... is no longer available"), the bot asks
Google which models your key can use, switches to the best "flash" model and tells you its name in the log. Gemini then writes answers to new questions ("Why do you want this job?", "Tell us about yourself")
from your details and resume, naming the company and role. Set `review_ai_answers = True` to see and edit long answers in a popup first.

### AI answers

With `use_AI = True` (config/secrets.py) the AI answers unknown questions using your config details **and the text of your resume** (`default_resume_path`, PDF or DOCX).

---

## 📊 The Dashboard (start here)

```powershell
python apply_and_pray.py
```

Your browser opens `http://127.0.0.1:5000`. It runs only on your computer: nothing is online, and other websites can't reach it.

| Tab | What it does |
|---|---|
| **Setup** | 6 steps: your basics, LinkedIn login, AI assistant, application details, Gmail, networking. Each has a how-to guide and a check, and unlocks features as you finish it |
| **Run** | Start the bot in a mode you've unlocked (Easy Apply, Normal Apply, both, Feed jobs, Networking), then Pause, Skip a job, Stop after this job or Quit. Shows what it's doing live. Tick **Test run** to fill every form without pressing the final Submit (nothing is sent) |
| **Applications** | Everything applied to, jobs to apply by hand (with "Mark applied"), CSV export |
| **People** | Everyone the bot reaches out to: request sent → connected → messaged → replied (your turn) |
| **Review** | Connection requests, messages and emails waiting for your approval. Edit, then **Approve and send**, or Skip. Nothing is sent without you (unless you turn review off in Setup → Gmail) |

**Feed jobs** (Run → Feed jobs): many jobs are only posted as LinkedIn posts. The bot searches posts for your job titles + "hiring", fills the forms they link to (Normal Apply), writes an email with your resume for "send your CV to ..." posts, and saves "DM me / comment" posts for Networking. Your experience, bad words and title filters apply. Settings: `config/feed.py`.

**Connection requests** (Review → Find people to connect with, then Run → Connections): the bot drafts a request to each person who posted a job you applied to (and to people whose job posts said "DM me"), once per person. The most valuable ones get a short work note while your monthly note allowance lasts (free LinkedIn: about 5). You approve them in Review; the Connections run sends them within your daily / weekly limits and active hours, with random gaps, and stops at once if LinkedIn warns about the invitation limit. Settings: Setup → Networking, or `config/outreach.py`.

**Personal messages** (part of Run → Networking): each run first checks who accepted your requests, then writes a short personal message to each new connection (your pitch, the job that connects you, a clear ask) and ONE follow-up to anyone who hasn't replied after 6 days. You approve them in Review. Before a follow-up the bot opens the conversation: if they replied, it's cancelled and they show as **Replied: your turn** in the **People** tab. The bot never messages someone who replied.

Your history lives in `user_data/app.db` (SQLite). Your old CSV files are imported automatically the first time.

---

## 📦 Windows app and website (for publishing)

**Build the Windows app** (from the project folder, with the venv set up):

```powershell
powershell -ExecutionPolicy Bypass -File packaginguild.ps1
```

It makes `dist\ApplyAndPray\ApplyAndPray.exe` and `dist\ApplyAndPray-windows.zip` (upload the zip to GitHub Releases). With [Inno Setup 6](https://jrsoftware.org/isdl.php) installed it also makes `dist\ApplyAndPray-Setup.exe` (no admin rights needed). The app keeps each user's data in `%LOCALAPPDATA%\ApplyAndPray`, never inside the app folder, so updates keep it. The recipe is `packaging\ApplyAndPray.spec`; only the `config\*.py` defaults are bundled, never anyone's `.json` data.

Every part of the app starts through one entry point, `apply_and_pray.py` (the `.exe` is built from it): no argument = the dashboard; `bot`, `check-linkedin`, `check-ai`, `draft`, `control-panel` are used by the dashboard itself.

**Full publishing guide** (website hosting on GitHub Pages or Vercel, uploading the app to Releases): [docs/DEPLOY.md](docs/DEPLOY.md).

**Website**: `website/` is a static site (landing page + setup guides). On [Vercel](https://vercel.com): New Project → import the GitHub repo → set **Root Directory** to `website` → Framework preset **Other** → Deploy. The download buttons point to this repo's GitHub Releases page: change the two links in `website/index.html` if the repo moves.

---

## 🧯 Troubleshooting

### ChromeDriver Version Error

If you see `This version of ChromeDriver only supports Chrome version X`, update Chrome from `chrome://settings/help`, close Chrome, and run again.

This build also detects your installed Chrome version and asks `undetected-chromedriver` for a matching driver.

### Chrome Profile Permission Error

This build uses a safer Windows profile path:

```text
%LOCALAPPDATA%\ApplyAndPrayChromeProfile
```

No more fighting `C:\temp` like it owes you money.

---

## ⚠️ Disclaimer

This project is for educational and research purposes only. Automating LinkedIn is against LinkedIn's User Agreement and can get your account restricted. You are responsible for how you use it and for complying with LinkedIn's terms and applicable laws. The defaults keep activity slow and limited. Raising the limits raises the risk.

Everything runs on your own computer. Your details, passwords and API keys stay on it and are never sent anywhere except to the websites and AI provider you choose.

Use at your own risk.

---

## 👤 Maintainer & credits

**Saif Siddiqui** maintains this version: [github.com/saif-siddiqui06/Apply-and-Pray](https://github.com/saif-siddiqui06/Apply-and-Pray). Bugs and ideas: [open an issue](https://github.com/saif-siddiqui06/Apply-and-Pray/issues).

Apply & Pray builds on the open-source LinkedIn job applier by **Shubham** ([LinkedIn](https://www.linkedin.com/in/shubham-sunil-kumar-333547133/)) and its contributors. See [CREDITS.md](CREDITS.md) for everyone whose work is in it. Licensed under AGPL-3.0, like the original.

---

## ⭐ Support

If this project saved you from clicking **Easy Apply** 10,000 times, give it a ⭐.
