'''
Jobs the bot couldn't finish, saved so you can apply by hand later (the browser tabs are gone once the bot closes):
* all excels/apply_by_hand.csv   - one row per job
* all excels/apply_by_hand.html  - the same list as a page with clickable links, newest first
'''

import os
import csv
import html
from datetime import datetime

from modules.helpers import print_lg

FIELDS = ["Date", "Job Title", "Company", "Reason", "Apply Link", "LinkedIn Job", "Job ID"]


class PendingLinks:
    def __init__(self, folder: str = "all excels"):
        self.csv_path = os.path.join(folder, "apply_by_hand.csv")
        self.html_path = os.path.join(folder, "apply_by_hand.html")
        self.added_this_run = 0
        self._ids = {row.get("Job ID") for row in self._rows()}


    def _rows(self) -> list[dict]:
        try:
            with open(self.csv_path, "r", encoding="utf-8") as file: return list(csv.DictReader(file))
        except FileNotFoundError: return []
        except Exception as e:
            print_lg(f'Could not read "{self.csv_path}":', e)
            return []


    def add(self, job_id: str, title: str, company: str, reason: str, apply_link: str, linkedin_link: str) -> None:
        '''Saves one job (once per Job ID) and refreshes the html page.'''
        from modules.runtime import TEST_RUN
        if TEST_RUN or not job_id or job_id in self._ids: return   # Test run: nothing is recorded
        if not apply_link or apply_link in ("Easy Applied", "about:blank"): apply_link = linkedin_link
        try:
            os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
            new_file = not os.path.exists(self.csv_path)
            with open(self.csv_path, "a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=FIELDS)
                if new_file: writer.writeheader()
                writer.writerow({"Date": datetime.now().strftime("%Y-%m-%d %H:%M"), "Job Title": title, "Company": company,
                                 "Reason": (reason or "")[:300], "Apply Link": apply_link, "LinkedIn Job": linkedin_link, "Job ID": job_id})
            self._ids.add(job_id)
            self.added_this_run += 1
            self.write_html()
        except Exception as e:
            print_lg(f'Could not save "{title} | {company}" in "{self.csv_path}". Close the file if it is open in Excel.', e)
        try:   # The dashboard's database
            from modules import db
            db.record_apply_by_hand(job_id, title, company, (reason or "")[:300], apply_link, linkedin_link)
        except Exception as e:
            print_lg("Couldn't save the apply-by-hand link in the database:", e)


    def write_html(self) -> None:
        rows = list(reversed(self._rows()))
        cells = []
        for row in rows:
            link = html.escape(row.get("Apply Link") or "")
            linkedin = html.escape(row.get("LinkedIn Job") or "")
            cells.append(
                f'<tr><td>{html.escape(row.get("Date", ""))}</td><td><b>{html.escape(row.get("Job Title", ""))}</b><br>{html.escape(row.get("Company", ""))}</td>'
                f'<td>{html.escape(row.get("Reason", ""))}</td><td><a href="{link}" target="_blank">Apply</a>'
                + (f' &middot; <a href="{linkedin}" target="_blank">LinkedIn</a>' if linkedin and linkedin != link else "") + "</td></tr>")
        page = f'''<!doctype html><html><head><meta charset="utf-8"><title>Apply by hand ({len(rows)})</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}} table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}} th{{background:#f4f4f4}} a{{color:#0a66c2}}
tr:hover{{background:#fafafa}} .muted{{color:#666}}</style></head><body>
<h2>Jobs to apply by hand <span class="muted">({len(rows)})</span></h2>
<p class="muted">The bot couldn't finish these (login needed, no form found, a question it couldn't answer, or you skipped them). Newest first. Updated {datetime.now():%d %b %Y %H:%M}.</p>
<table><tr><th>Saved</th><th>Job</th><th>Why</th><th>Links</th></tr>
{"".join(cells)}
</table></body></html>'''
        try:
            with open(self.html_path, "w", encoding="utf-8") as file: file.write(page)
        except Exception as e:
            print_lg(f'Could not write "{self.html_path}":', e)


    def open_page(self) -> None:
        '''Opens the html page in your default browser (Windows).'''
        try:
            if os.path.exists(self.html_path) and hasattr(os, "startfile"): os.startfile(os.path.abspath(self.html_path))
        except Exception as e:
            print_lg("Could not open the apply-by-hand page:", e)
