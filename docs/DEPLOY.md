# Publishing Apply & Pray

How to put the website online, publish the Windows app, and keep both up to date. Everything here is free.

The website (`website/`) is a plain static site: two HTML pages and one stylesheet, no build step. Its **Download** buttons point to this repo's GitHub Releases page, so the two go together:

| What | Where it lives | Who updates it |
|---|---|---|
| Website | GitHub Pages (or Vercel) | Automatic on every push to `main` |
| Windows app | GitHub Releases (`ApplyAndPray-windows.zip`) | You, once per version (step 3) |
| Code | This repo | You, via commits / pull requests |

---

## 1. Website on GitHub Pages (recommended: already set up)

The workflow `.github/workflows/pages.yml` publishes `website/` whenever `main` changes. Turn it on once:

1. Open the repo on GitHub → **Settings** → **Pages** (left menu).
2. Under **Build and deployment**, set **Source** to **GitHub Actions**. Nothing else to choose.
3. Go to the **Actions** tab → **Website** (left) → **Run workflow** → **Run workflow** (green button). Wait about 1 minute for the green tick.
4. Your site is live at **`https://<your-github-username>.github.io/Apply-and-Pray/`**. For this repo: `https://saif-siddiqui06.github.io/Apply-and-Pray/`.
   The address is also shown in Settings → Pages, and on the finished workflow run.

From then on, every push to `main` that changes `website/` republishes it by itself.

**Your own domain (optional)**: Settings → Pages → **Custom domain** → type it (Eg: `applyandpray.in`) → Save, then at your domain seller add a `CNAME` record pointing `www` to `<your-github-username>.github.io`. Tick **Enforce HTTPS** once it's offered (can take an hour).

---

## 2. Website on Vercel (alternative)

Use this instead of (or as well as) GitHub Pages if you prefer Vercel.

1. Sign in at [vercel.com](https://vercel.com) with your GitHub account.
2. **Add New…** → **Project** → find **Apply-and-Pray** → **Import**. (First time: allow Vercel to see the repo.)
3. On the setup screen:
   - **Framework Preset**: **Other**
   - **Root Directory**: click **Edit** → choose **`website`** → Continue
   - **Build Command** / **Output Directory**: leave empty
4. Click **Deploy**. After ~30 seconds you get an address like `apply-and-pray.vercel.app`.
5. Every push to `main` redeploys; pull requests get their own preview address.

`website/vercel.json` already sets clean addresses (`/guides` instead of `/guides.html`) and safe headers. Custom domain: Project → **Settings** → **Domains** → add it and follow Vercel's DNS instructions.

> PythonAnywhere also works but isn't needed: it's for Python web apps, and this site is static. The dashboard itself never goes online: it runs on each user's own PC.

---

## 3. Publish the Windows app (makes the Download button work)

1. On your PC, in the project folder, build it:
   ```powershell
   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
   ```
   This makes `dist\ApplyAndPray-windows.zip` (and `dist\ApplyAndPray-Setup.exe` if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed). The zip is checked to contain only the program: never `user_data\`, logs or your settings.
2. On GitHub: repo → **Releases** (right side) → **Draft a new release**.
3. **Choose a tag** → type a version, Eg: `v2.0.0` → **Create new tag**. Title: `Apply & Pray 2.0.0`.
4. Describe what's new (a few lines), then drag **`ApplyAndPray-windows.zip`** (and `ApplyAndPray-Setup.exe`, if you built it) into the box at the bottom.
5. Click **Publish release**.

The website's buttons go to `/releases/latest`, so they always offer the newest version. If the repo is ever renamed or moved, update the three GitHub links in `website/index.html` (`download-link`, `source-link`, `footer-code`).

**New version later**: change `AppVersion` in `packaging/installer.iss`, rebuild, and publish a new release with a higher tag (`v2.0.1`, `v2.1.0`...).

---

## 4. Before each release: check it on your own account

LinkedIn changes its pages often (in October 2026 it scrambled its class names and moved job search to a new page). Before publishing:

1. Run `python apply_and_pray.py`, finish Setup, and do a short run of each mode you changed.
2. If a page can't be read, the bot saves a copy in `logs\easy_apply_forms\`: fix the reader against it, then release.

## 5. Things to know

- **"Windows protected your PC"**: the app isn't code-signed, so Windows warns on first start (users click *More info → Run anyway*; the website's guide explains it). A code-signing certificate removes the warning, but costs money every year.
- **License**: AGPL-3.0. The code must stay open; anyone who changes and shares it must share their changes too.
- **Never commit** `user_data/`, `logs/`, `all excels/`, `dist/` or `build/`: `.gitignore` already excludes them.
