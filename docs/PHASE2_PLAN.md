# Phase 2 plan: Networking, Feed Jobs and a publishable product

Status: **APPROVED (24 Oct 2026).** Decisions:
- **Hosting:** A. Local app on the user's PC + a free static website on Vercel (landing page, download, guides).
- **Git history:** stop tracking private files and ship clean defaults. History is not rewritten (no force-push). The owner changes the LinkedIn password and AI key that were pushed earlier.
- **Build order:** M0 cleanup → M1 dashboard + setup → M2 Feed jobs → M3 Connections → M4 DMs → M5 installer + website.
- **Database:** SQLite (`user_data/app.db`). Old CSVs imported once, CSV / Excel export kept.
- **Default limits:** Safe. 15 invites/day, 80/week, 20 DMs/day, 20 emails/day, 9:00–21:00, random gaps.

**M0 design:** the `config/*.py` files stay in git, but only with blank defaults and their explanations. Each user's own values live in `user_data/settings.json`, which is never in git, and the dashboard edits that file in M1. Passwords and keys live in Windows Credential Manager (`keyring`), with `user_data/secrets.json` as a fallback. At the end of each config file, the user's values are loaded over the defaults, so `from config.personals import first_name` keeps working everywhere.

What you told me:
- **Review mode:** the bot drafts and you approve ("basic OK mode"). An automatic mode can be added later.
- **Premium:** you don't have LinkedIn Premium, but every user's setup is different, so limits are worked out per user.
- **Gmail:** you have an app password, so email applications are in scope.
- **Messages:** connection requests and messages carry a short work-related note (role, skill, ask), whenever the limits allow one.
- **Release:** it will be published, and users go through a website, step-by-step setup, and features unlock as they add details.

---

## 0. The big decision: where does the bot run?

| | **A. Local app + website (recommended)** | B. Fully hosted website |
|---|---|---|
| Where Chrome runs | On the user's own PC, with their own LinkedIn login | On your servers, cloud browsers |
| LinkedIn ban risk | Low: their own home IP and their own browser | **Very high**: data-centre IPs and many accounts from one place get flagged fast |
| Users' passwords / API keys | Stay on their PC | You store everyone's LinkedIn, Gmail and API keys, which is a big security and legal burden |
| Your cost | Almost zero (static website) | Servers + browsers per user, every month |
| License (AGPL-3.0, see LICENSE) | Fine: source is public | AGPL makes you publish all server-side changes too |

**Recommended (A):**
- **The website** is the landing page: what it does, download, setup guides, FAQ.
- **The app** is what users install. It opens a **local dashboard in their browser** (`http://localhost:5000`, built on the Flask `app.py` that already exists). Setup, unlocking features, starting runs, the review queue and trackers all live there.
- Later, it can be packaged as a single `.exe` installer (PyInstaller) so users don't need to install Python.

> Decision needed: A or B?

---

## 1. Must fix before publishing (security and privacy)

Checked in the repo today:
1. **`config/secrets.py` and `config/personals.py` are tracked by git**, even though `.gitignore` lists them. Git ignores `.gitignore` for files it already tracks. Your next commit and push would upload your real passwords and API key to GitHub.
2. **`config/__pycache__/secrets.cpython-*.pyc` and `personals.*.pyc` are committed.** These compiled files contain the values that were in the config files when they were compiled.
3. a personal resume PDF in `modules/resumes/` is sitting in the project (untracked right now, but one `git add .` away).
4. Fix:
   - Move *all* user data into one ignored folder, `user_data/`, holding the profile, keys, resume, database and logs.
   - Ship clean templates only.
   - Remove the tracked files from git.
   - **Change any password or key that was ever pushed** (LinkedIn, Gemini), because GitHub history keeps them.
5. Add a clear disclaimer: automation is against LinkedIn's User Agreement and users run it at their own risk. Default to safe limits.

---

## 2. Setup and feature unlocking (the onboarding flow)

The dashboard shows each feature as 🔒 / ✅ along with "what's still needed". Every step has a short how-to guide, input checks and a **Test** button, so users know it works before they run anything.

| Step | Details asked | How-to guide inside the app | Test button | Unlocks |
|---|---|---|---|---|
| **1. Basics** | Name, phone, email, city / state / country, resume (PDF upload), job titles to search, location, experience level | – | Reads the resume and shows what it found | **Easy Apply** |
| **2. LinkedIn login** | Nothing stored. User logs in once in the bot's own Chrome window, and the session is kept in a local Chrome profile | Explains why we don't store the password | "Check login" opens LinkedIn and confirms it's logged in | Needed for everything on LinkedIn |
| **3. AI** | Provider (Gemini free / OpenAI / DeepSeek), API key | Step-by-step with links: how to create a Gemini key in Google AI Studio, free limits, what it costs | Sends one tiny request and shows the model and status | AI answers, cover notes, **personalised messages** |
| **4. Application details** | Years of experience, current / expected salary, notice period, work authorisation, LinkedIn / portfolio links, an email + password for job-site accounts (Greenhouse, etc.) | Why a separate portal password is safer | – | **Normal Apply** |
| **5. Gmail** | Gmail address + 16-character app password | Turn on 2-Step Verification → Google Account → Security → App passwords → copy the code (with screenshots) | Sends a test email to yourself | **Feed jobs: apply by email** |
| **6. Networking** | Premium yes / no, your pitch in 2–3 lines, college (for alumni search), message tone, daily limits (safe defaults pre-filled) | What LinkedIn allows on free vs Premium, why limits matter | Shows the limits it will use | **Connection requests + DMs** |

Storage:
- The profile goes in `user_data/profile.json`.
- Secrets (API key, Gmail app password, portal password) go in the **Windows Credential Manager via `keyring`**, not in plain text files. A fallback file is used on systems without keyring.

---

## 3. Feature A: Connection requests with a work note

**Who to connect with**, in order of value. Users switch each source on or off:
1. **The hiring person on jobs you applied to.** The bot already records them: 118 of your 477 applied jobs have a hirer link.
2. **Recruiters / talent acquisition at companies you applied to** (LinkedIn people search: "recruiter" + company).
3. **Engineers in the same field at those companies**, alumni of your college first (for referrals).

**Flow, for each person:**
1. Skip them if they're already contacted, already connected or pending, or the company is blacklisted.
2. Open their profile and read their name, headline and current company.
3. Decide on the note:
   - **Notes left this month > 0** (the free plan allows only a few, Premium many more): the AI writes a note under 200 characters. It mentions the role you applied for and one matching skill, plus a polite ask.
   - **No notes left:** send the request without a note. The personal message goes into the DM after they accept (Feature B).
   - Notes are used on the **most valuable people first** (source 1 before 3).
4. Review mode: the request and note wait in the **Review Queue**, and nothing is sent until you approve it.
5. Send it, then save the person to the outreach tracker.

**Limits (defaults, editable):**
- 15 requests a day, at most 80 a week.
- A random 40–120 s gap between requests.
- Only between 9:00 and 21:00.
- Stops immediately if LinkedIn shows a warning ("you've reached the weekly invitation limit", security check).

---

## 4. Feature B: Personal DMs, follow-up, stop on reply

DMs can only go to 1st-degree connections on a free account, so the flow is **connect → accepted → DM**:
1. At the start of every run, the bot checks which pending requests were **accepted**.
2. For each newly accepted person, the AI writes a short DM (3–5 lines) from:
   - your pitch
   - their headline
   - the job you applied for and its link
   - one or two skills from your resume that match it
   - a clear ask (a referral, forwarding your profile, or a 10-minute chat)
3. The DM goes to the Review Queue, then you approve and the bot sends it.
4. **One follow-up** if there's no reply after 6 days (also reviewed). After that, stop for good.
5. **If they reply, the bot never messages them again.** The tracker marks them "Replied, your turn" and the dashboard highlights it.
6. Premium users with InMail credits can optionally message people who aren't connected (off by default).

**When AI isn't available** (quota or no key): ready-made templates with blanks ({first_name}, {company}, {role}, {skill}). You can edit the templates in the dashboard.

---

## 5. Feature C: Jobs from the LinkedIn feed

Many jobs, especially in India, are only posted as feed posts.
1. Search posts with your job titles plus hiring words, e.g. `hiring python fresher`, from the past week, using LinkedIn's post search.
2. For each new post, read its text, author and links. Your existing filters apply: **experience, bad words, blacklisted companies.**
3. The AI (or keyword rules without AI) puts the post into one of these:

| Post says | Bot does |
|---|---|
| Google Form / careers link | Opens it with the **Normal Apply** you already have |
| "Send your CV to hr@…" | **Emails your resume from Gmail** with a short cover note tailored to the post (subject: "Application: {role}, {your name}"). Goes through the Review Queue in review mode |
| "DM me" / "comment interested" | Adds the author to Feature A (connection + note). **No auto-commenting**: identical "Interested" comments look like spam to recruiters |
| Senior / irrelevant / spam | Skip, with the reason saved |

Email limits: at most 20 emails a day, never the same address twice for the same role, and every email is saved to the tracker.

---

## 6. Shared pieces (built once, used by all features)

- **Limits manager:** one place that counts daily and weekly actions per type (invites, DMs, emails, applications) and adds random gaps. Every feature asks it "may I?" before acting.
- **Review Queue (dashboard page):** cards with the person or post, the draft text, and **Approve / Edit / Skip / Approve all**. The bot sends approved items on its next pass.
- **Database:** switch from many CSV files to one SQLite file (`user_data/app.db`), with tables for jobs, people, messages, feed posts, emails and limits. That makes "never contact twice" and the trackers reliable. **CSV / Excel export** stays available. Your current history CSVs are imported once.
- **AI module:** one function for all providers, with automatic fallback (model → next model → templates), so a quota limit doesn't stop the run. This is the problem you hit on 20 Oct.
- **Same control window** (Pause / Skip / Stop) and the same logs for every mode.

---

## 7. Dashboard pages

1. **Setup**: the 6 steps, lock status, test buttons.
2. **Run**: pick modes (Easy Apply / Normal Apply / Feed jobs / Connections / DMs) and start / stop. Live status and today's counts against the limits.
3. **Review Queue**: drafts waiting for approval.
4. **Outreach tracker**: everyone contacted, with status (Requested → Accepted → DM sent → Follow-up → Replied).
5. **Applications**: Easy, Normal, feed and email applications, plus the apply-by-hand list.
6. **Settings**: limits, message templates, tone, blacklists.

---

## 8. Build order (each milestone is reviewed before the next)

| # | Milestone | You can test it by |
|---|---|---|
| ✅ **M0** | Publishing cleanup: `user_data/` folder, secrets out of git and into keyring, clean templates, disclaimer | A fresh clone contains no personal data; the bot still runs with your data |
| ✅ **M1** | Dashboard + setup steps 1–6 with guides, test buttons and feature locks; SQLite + import of old CSVs | New-user walkthrough from empty to "Easy Apply unlocked" |
| ✅ **M2** | Feed jobs: post search, classify, Normal Apply for links, Gmail apply with Review Queue | A run collects posts, applies to form links, and drafts emails you approve |
| ✅ **M3** | Connection requests to hirers of applied jobs, note logic, limits, tracker | 10 requests drafted → approved → sent, all shown in the tracker |
| ✅ **M4** | Acceptance check → personalised DMs → follow-up → stop on reply | Accepted people get a reviewed DM, and replies stop the sequence |
| ✅ **M5** | Recruiter + alumni search sources; Windows installer (.exe); website landing page + guides | Install on a clean PC from the website |

Why this order: M0 must come first because of the secrets. Feed jobs (M2) are real applications at the lowest account risk. Networking (M3–M4) needs the limits manager and Review Queue built first.

---

## 9. Questions for you

1. **Hosting:** A (local app + website, recommended) or B (hosted)?
2. **Website:** what's the link, and what's it built with? (Landing page only, or do you expect login and accounts on it?)
3. **Database:** OK to move from CSV files to SQLite, with export kept?
4. **Default limits:** are 15 invites/day, 80/week and 20 emails/day OK for you?
5. **Message language and tone:** English, professional and short? Anything you always want included (e.g. portfolio link)?
6. **Build order:** OK, or do you want connections (M3) before feed jobs (M2)?
