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
    try:
        from config.secrets import ai_provider, use_AI
        if not use_AI: return {"ok": False, "detail": "AI is turned off."}
        return check_gemini() if ai_provider == "gemini" else check_openai_compatible()
    except BaseException as e:
        return {"ok": False, "detail": _first_line(e)}
