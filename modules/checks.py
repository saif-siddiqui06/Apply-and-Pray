'''
Setup checks, each run as its own process by the dashboard (apply_and_pray.py check-linkedin / check-ai), so they always
use the settings just saved. Each returns {"ok": true/false, "detail": "..."}.

* linkedin() - opens the bot's own Chrome window on LinkedIn and waits (up to 5 minutes) until you're logged in.
* ai()       - sends one tiny request to the AI provider you set up.
'''

import time


LOGGED_OUT_WORDS = ("/login", "/authwall", "/uas/", "/checkpoint", "/signup", "linkedin.com/home", "/start/")


def logged_in(driver) -> bool:
    url = driver.current_url.lower()
    if "linkedin.com" not in url or any(word in url for word in LOGGED_OUT_WORDS): return False
    # LinkedIn's class names are scrambled now (Eg: "l4jlag"): look at what doesn't change, the links of the top menu and their labels
    if driver.find_elements("css selector", "input#username, input[name='session_key']"): return False
    return bool(driver.find_elements("css selector", "a[href*='/messaging/'], a[href*='/mynetwork/'], [aria-label^='Messaging'], [aria-label^='My Network'], "
                                                     "#global-nav, header.global-nav, .global-nav__me"))


def linkedin() -> dict:
    try:
        from modules.open_chrome import driver   # Starts the bot's Chrome with its own profile, like a normal run
    except BaseException as e:
        return {"ok": False, "detail": f"Chrome didn't start: {str(e).splitlines()[0][:200] if str(e) else type(e).__name__}. Close other bot windows and try again."}
    if driver is None: return {"ok": False, "detail": "Chrome didn't start. Close other bot windows and try again."}
    try:
        driver.get("https://www.linkedin.com/feed/")
        end = time.time() + 300
        while time.time() < end:
            try:
                if logged_in(driver):
                    time.sleep(2)
                    return {"ok": True, "detail": "Logged in to LinkedIn."}
            except Exception: pass
            time.sleep(2)
        return {"ok": False, "detail": "Not logged in after 5 minutes. Click Open LinkedIn and log in in the window that opens."}
    except BaseException as e:
        return {"ok": False, "detail": "The LinkedIn window was closed before the login finished." if "window" in str(e).lower() or "session" in str(e).lower() else str(e)[:200]}
    finally:
        try: driver.quit()
        except Exception: pass


def _first_line(error) -> str:
    text = str(error.get("error") if isinstance(error, dict) else error) or type(error).__name__
    return text.splitlines()[0][:250]


def check_gemini() -> dict:
    from modules.ai.geminiConnections import GeminiClient, gemini_completion, gemini_create_client, _settings, _model_gone
    key, model = _settings()
    if not key: return {"ok": False, "detail": "Paste your Gemini API key first."}
    answer = gemini_completion(GeminiClient(key, model), "Reply with the single word OK.", max_tokens=256, temperature=0)
    if not isinstance(answer, dict): return {"ok": True, "detail": f"Gemini works (model {model})."}
    if _model_gone(answer):   # Google retired this model: find one this key can use, and keep it
        client = gemini_create_client()
        if client:
            from modules.user_settings import save_section
            save_section("secrets", {"gemini_model": client.model})
            return {"ok": True, "detail": f"Gemini works. {model} isn't available any more, switched to {client.model}."}
    message = _first_line(answer)
    if answer.get("status") in (400, 401, 403) or "api key" in message.lower(): message = "Google refused the key. Copy it again from aistudio.google.com/app/apikey. (" + message + ")"
    if answer.get("status") == 429: message = "The key works, but its free limit is used up for today. It will work again tomorrow. (" + message + ")"
    return {"ok": answer.get("status") == 429, "detail": message}


def check_openai_compatible() -> dict:
    from openai import OpenAI
    from config.secrets import llm_api_url, llm_api_key, llm_model, ai_provider
    base_url = llm_api_url.rstrip("/") if ai_provider == "deepseek" else llm_api_url
    try:
        client = OpenAI(base_url=base_url, api_key=llm_api_key or "not-needed", timeout=40, max_retries=1)
        reply = client.chat.completions.create(model=llm_model, messages=[{"role": "user", "content": "Reply with the single word OK."}], max_tokens=20)
        return {"ok": True, "detail": f"{ai_provider.title()} works (model {llm_model}): “{(reply.choices[0].message.content or '').strip()[:40]}”."}
    except Exception as e:
        message = _first_line(e)
        if "401" in message or "invalid" in message.lower() and "key" in message.lower(): message = "The key was refused. Copy it again. (" + message + ")"
        elif "404" in message or "model" in message.lower(): message = f"The model “{llm_model}” wasn't found. Check its name. (" + message + ")"
        elif "connect" in message.lower(): message = f"Couldn't reach {base_url}. Is the address right, and is the program running? (" + message + ")"
        return {"ok": False, "detail": message}


def ai() -> dict:
    result = _ai_main()
    try:
        from modules.ai import fallback
        if fallback.configured():
            backup = fallback.check()
            result = {"ok": result["ok"] or backup["ok"], "detail": result["detail"] + " Backup AI: " + backup["detail"]}
    except Exception as e:
        result["detail"] += f" Backup AI: {str(e)[:120]}"
    return result


def _ai_main() -> dict:
    try:
        from config.secrets import ai_provider, use_AI
        if not use_AI: return {"ok": False, "detail": "AI is turned off."}
        return check_gemini() if ai_provider == "gemini" else check_openai_compatible()
    except BaseException as e:
        return {"ok": False, "detail": _first_line(e)}


def linkedin_pages() -> dict:
    '''
    "Check LinkedIn" in the dashboard: opens the bot's Chrome and reads each kind of page the bot uses, without clicking anything that
    sends or changes something. Tells which part of the bot would break after a LinkedIn layout change.
    Returns {"ok", "detail", "parts": [{"name", "ok", "detail"}]}.
    '''
    import re
    from urllib.parse import quote
    parts = []
    def part(name, ok, detail): parts.append({"name": name, "ok": bool(ok), "detail": detail})
    try:
        from modules.open_chrome import driver
    except BaseException as e:
        return {"ok": False, "detail": f"Chrome didn't start: {str(e).splitlines()[0][:150] if str(e) else type(e).__name__}", "parts": []}
    try:
        from config.search import search_terms, search_location
        from modules.smart_search import plan_searches, location_for_search
        term = (plan_searches(search_terms, False) or ["Software Engineer"])[0]
        place = location_for_search(search_location) or "India"

        driver.get("https://www.linkedin.com/feed/"); time.sleep(5)
        if not logged_in(driver):
            part("LinkedIn login", False, "Not logged in: use Setup -> LinkedIn login first.")
            return {"ok": False, "detail": "Not logged in to LinkedIn.", "parts": parts}
        part("LinkedIn login", True, "Logged in.")

        # Job search -> a job's page
        driver.get("https://www.linkedin.com/jobs/search-results/?keywords=" + quote(f"{term} jobs in {place}") + "&f_AL=true&f_TPR=r604800"); time.sleep(8)
        ids = driver.execute_script("""return [...document.querySelectorAll('li[data-occludable-job-id], [role=button][componentkey^="job-card-component-ref-"]')]
            .map(c => c.getAttribute('data-occludable-job-id') || (c.getAttribute('componentkey') || '').replace('job-card-component-ref-', '')).filter(Boolean)""") or []
        part("Job search (Easy Apply, Normal Apply)", len(ids) > 0, f"{len(ids)} job cards read for \"{term}\"." if ids else "No job cards could be read: the job search layout changed.")
        if ids:
            driver.get(f"https://www.linkedin.com/jobs/view/{ids[0]}/"); time.sleep(7)
            text = driver.execute_script("return (document.querySelector('main') || document.body).innerText") or ""
            has_desc = bool(driver.find_elements("css selector", ".jobs-box__html-content")) or bool(re.search(r'about the job', text, re.I))
            apply = [b for b in driver.find_elements("xpath", "//*[(self::button or self::a) and (contains(@aria-label,'Easy Apply') or contains(@aria-label,'Apply') or normalize-space()='Apply' or normalize-space()='Easy Apply')]") if b.is_displayed()]
            part("Job page: description", has_desc, "The job description is readable." if has_desc else "No job description found: experience / bad-word checks would fail.")
            part("Job page: Apply button", bool(apply), "The Apply button is found." if apply else "No Apply button found: applications would fail.")

        # Feed posts
        from modules.feed_jobs import _READ_POSTS_JS
        driver.get("https://www.linkedin.com/search/results/content/?keywords=" + quote(f"{term} hiring") + "&datePosted=%22past-week%22&sortBy=%22date_posted%22"); time.sleep(7)
        posts = driver.execute_script(_READ_POSTS_JS) or []
        part("Feed posts (Feed jobs)", len(posts) > 0, f"{len(posts)} posts read." if posts else "No posts could be read: the post search layout changed.")

        # People search and a profile
        from modules.people_search import _RESULTS_JS
        driver.get("https://www.linkedin.com/search/results/people/?keywords=" + quote(f"recruiter {place}")); time.sleep(6)
        people = driver.execute_script(_RESULTS_JS) or []
        part("People search (Networking)", len(people) > 0, f"{len(people)} people read." if people else "No people could be read: the people search layout changed.")
        if people:
            from modules.connections import _TOP_CARD_JS, _TOP, Connector
            driver.get(people[0]["profile_url"]); time.sleep(6)
            card = driver.execute_script(_TOP_CARD_JS) or {}
            connector = Connector(driver)
            actions = connector._visible(f"{_TOP}//*[(self::button or self::a)][normalize-space(.)='Connect' or normalize-space(.)='Message' or normalize-space(.)='More' or normalize-space(.)='Follow' or contains(@aria-label,'to connect')]")
            ok = bool(card.get("name")) and actions is not None
            part("Profile page (requests, messages)", ok, f"Name and buttons found on {card.get('name') or 'the profile'}." if ok else "The profile's name or buttons weren't found: requests / messages would fail.")
    except BaseException as e:
        part("Check", False, f"Stopped: {str(e).splitlines()[0][:160] if str(e) else type(e).__name__}")
    finally:
        try: driver.quit()
        except Exception: pass
    broken = [p["name"] for p in parts if not p["ok"]]
    return {"ok": not broken, "detail": "Everything the bot needs on LinkedIn works." if not broken else "Not working: " + ", ".join(broken), "parts": parts}
