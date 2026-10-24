'''
Google Gemini, called through its REST API with `requests` (the old `google.generativeai` package is no longer supported by Google).

Set in config/secrets.py:
    use_AI = True
    ai_provider = "gemini"
    gemini_api_key = "your key from https://aistudio.google.com/app/apikey"
    gemini_model = "gemini-3.8-flash"   (if Google retires a model, the bot switches to one your key can use)
(`llm_api_key` / `llm_model` are used if `gemini_api_key` / `gemini_model` are empty.)
'''

import re
import time
from time import sleep
from typing import Literal

import requests

from config import secrets
from modules.helpers import print_lg, critical_error_log, convert_to_json
from modules.ai.prompts import extract_skills_prompt

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.8-flash"
# Models that can't write form answers (speech, images, embeddings...), never picked when switching models
_NOT_FOR_TEXT = ("embedding", "tts", "image", "live", "audio", "aqa", "robotics", "computer-use", "native", "veo", "imagen", "learnlm")


class GeminiClient:
    def __init__(self, api_key: str, model: str, backup_keys: list[str] | None = None):
        self.api_key = api_key
        self.model = model
        self.first_model = model
        self.backup_keys = list(backup_keys or [])   # Used one after the other when this key's daily free quota is used up
        self.send_thinking_config = True   # Turned off if this model rejects it
        self.quota_until = 0.0             # Daily free quota used up on every model: no requests before this time
        self.fallbacks: list[str] | None = None   # Other models your key can use, tried when a model's daily quota runs out


def _backup_keys() -> list[str]:
    '''Extra Gemini keys (`gemini_backup_keys`, separated by commas / spaces / new lines), Eg: from other Google accounts.'''
    keys = re.split(r'[\s,;]+', (getattr(secrets, "gemini_backup_keys", "") or "").strip())
    main = _settings()[0]
    return [key for key in dict.fromkeys(keys) if key and key != main]


def _switch_key(client: GeminiClient) -> bool:
    '''This key's daily free quota is used up on every model: moves `client` to the next backup key. False when none is left.'''
    if not client.backup_keys: return False
    client.api_key = client.backup_keys.pop(0)
    client.model, client.fallbacks, client.send_thinking_config = client.first_model, None, True
    print_lg(f"Gemini's free quota is used up on this key, switching to a backup key ({len(client.backup_keys)} more left).")
    return True


def _settings() -> tuple[str, str]:
    key = (getattr(secrets, "gemini_api_key", "") or "").strip() or (secrets.llm_api_key or "").strip()
    model = (getattr(secrets, "gemini_model", "") or "").strip()
    if not model: model = secrets.llm_model if "gemini" in (secrets.llm_model or "").lower() else DEFAULT_MODEL
    return key, model.replace("models/", "")


def _thinking_config(model: str) -> dict | None:
    '''Short form answers don't need "thinking": faster, cheaper, and the answer isn't cut off by `maxOutputTokens`.'''
    if "2.5-flash" in model: return {"thinkingBudget": 0}
    if re.search(r'gemini-([3-9]|\d{2})', model): return {"thinkingLevel": "low"}
    return None


def gemini_completion(client: GeminiClient, prompt: str, is_json: bool = False, max_tokens: int = 600, temperature: float = 0.4) -> dict | str:
    '''Sends `prompt` to Gemini. Returns the text (or parsed JSON), or {"error": ..., "status": HTTP status}.'''
    if not client: return {"error": "Gemini client is not available"}
    if time.time() < client.quota_until:
        return {"error": f"Gemini's free quota is used up, AI is off for another {(client.quota_until - time.time()) / 60:.0f} min", "status": 429}
    rate_limited, failures, busy = False, 0, 0
    for attempt in range(8):
        config = {"temperature": temperature, "maxOutputTokens": max_tokens}
        thinking = _thinking_config(client.model) if client.send_thinking_config else None
        if thinking: config["thinkingConfig"] = thinking
        if is_json: config["responseMimeType"] = "application/json"
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
        try:
            response = requests.post(API_URL.format(model=client.model), params={"key": client.api_key}, json=body, timeout=40)
            data = response.json()
            if response.status_code == 429:
                wait = _retry_seconds(response, data)
                if wait > 90:   # The daily quota, not the per-minute limit: waiting doesn't help, another model has its own quota
                    if _switch_model(client) or _switch_key(client): continue
                    client.quota_until = time.time() + wait
                    print_lg(f"Gemini's daily free quota is used up on every model, AI is off for {wait / 3600:.1f} hours. Questions it would answer are asked in a popup or left for you.")
                    return {"error": data.get("error", {}).get("message", "Gemini quota exceeded").splitlines()[0], "status": 429}
                if not rate_limited:   # Per-minute limit: wait and try once more
                    rate_limited = True
                    print_lg(f"Gemini rate limit reached, waiting {wait}s...")
                    sleep(wait + 1)
                    continue
            if response.status_code in (500, 502, 503, 504) and busy < 2:   # "The model is overloaded": usually fine a few seconds later
                busy += 1
                print_lg(f"Gemini is busy (HTTP {response.status_code}), trying again in {3 * busy}s...")
                sleep(3 * busy)
                continue
            if response.status_code != 200:
                message = data.get("error", {}).get("message", f"HTTP {response.status_code}")
                if response.status_code == 400 and thinking and "thinking" in message.lower():   # This model has no "thinking" setting
                    client.send_thinking_config = False
                    continue
                if client.fallbacks is not None and _model_gone({"error": message, "status": response.status_code}) and _switch_model(client): continue
                return {"error": message, "status": response.status_code}
            candidates = data.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
            reason = str(candidates[0].get("finishReason") if candidates else data.get("promptFeedback"))
            if reason == "MAX_TOKENS":   # Cut off (often after "thinking"): give it more room once, never use half an answer
                if max_tokens < 4096:
                    max_tokens = 4096
                    continue
                return {"error": "Gemini's answer was cut off"}
            if not text:
                return {"error": f"Empty answer from Gemini ({reason})"}
            if is_json:
                text = re.sub(r'^```(json)?|```$', '', text.strip()).strip()
                return convert_to_json(text)
            return text
        except Exception as e:
            failures += 1
            if failures >= 2: return {"error": str(e)}
            sleep(2)
    return {"error": "Gemini didn't answer"}


def _retry_seconds(response, data: dict) -> int:
    '''How long Google asks to wait after a rate limit: the Retry-After header, or "retryDelay" in the error details.'''
    try:
        if response.headers.get("Retry-After"): return int(float(response.headers["Retry-After"]))
        for detail in data.get("error", {}).get("details", []):
            if "retryDelay" in detail: return int(float(str(detail["retryDelay"]).rstrip("s")))
    except (TypeError, ValueError): pass
    return 8


def _switch_model(client: GeminiClient) -> bool:
    '''Google counts the daily free quota per model: moves `client` to the next model your key can use. False when none is left.'''
    if client.fallbacks is None: client.fallbacks = _replacement_models(client, "")[:3]
    if not client.fallbacks: return False
    old, client.model = client.model, client.fallbacks.pop(0)
    client.send_thinking_config = True
    print_lg(f"Gemini model {old} can't answer any more today (daily free quota), switching to {client.model}.")
    return True


def _model_gone(error: dict) -> bool:
    '''True if the error says the model itself can't be used (retired, renamed, not for this key), not the key or the quota.'''
    message = str(error.get("error", "")).lower()
    return error.get("status") == 404 or any(text in message for text in ("no longer available", "not found", "is not supported", "deprecated", "update your code to use"))


def _version(name: str) -> float:
    found = re.search(r'gemini-(\d+(?:\.\d+)?)', name)
    return float(found.group(1)) if found else 0.0


def _replacement_models(client: GeminiClient, error_message: str) -> list[str]:
    '''
    Models to try instead of a retired one: the one Google's error message names first, then the models your key can use
    (stable before preview, "flash" before "pro" because it's faster with a bigger free quota, newest version first).
    '''
    suggested = [name for name in re.findall(r'models/(gemini-[\w.\-]*\w)', error_message) if name != client.model]
    available = []
    try:
        response = requests.get(MODELS_URL, params={"key": client.api_key, "pageSize": 1000}, timeout=20)
        for model in response.json().get("models", []):
            name = model.get("name", "").replace("models/", "")
            if name.startswith("gemini") and "generateContent" in model.get("supportedGenerationMethods", []) \
                    and not any(word in name for word in _NOT_FOR_TEXT) and name != client.model:
                available.append(name)
    except Exception as e:
        print_lg("Couldn't get the list of Gemini models:", e)
    def rank(name: str) -> tuple:
        unstable = any(word in name for word in ("preview", "exp"))
        return (unstable, "flash" not in name, "lite" in name, -_version(name), len(name))
    return list(dict.fromkeys(suggested + sorted(available, key=rank)))


def gemini_create_client() -> GeminiClient | None:
    '''
    Checks the key and model with a tiny request. If Google retired the model, switches to one your key can use.
    Returns a client, or None (the bot then runs without AI).
    '''
    key, model = _settings()
    if not key or "YOUR_API_KEY" in key or key.startswith("sk-"):
        print_lg("Gemini API key is missing: put it in `gemini_api_key` in config/secrets.py (get one at https://aistudio.google.com/app/apikey). Continuing without AI.")
        return None
    client = GeminiClient(key, model, _backup_keys())
    print_lg(f"Checking Gemini ({model})" + (f", with {len(client.backup_keys)} backup key(s)" if client.backup_keys else "") + "...")
    answer = gemini_completion(client, "Reply with the single word OK.", max_tokens=256, temperature=0)
    if isinstance(answer, dict) and _model_gone(answer):
        print_lg(f"Gemini model {model} can't be used: {str(answer.get('error'))[:200]}")
        for other in _replacement_models(client, str(answer.get("error", "")))[:4]:
            print_lg(f"Trying Gemini model {other}...")
            candidate = GeminiClient(key, other)
            answer = gemini_completion(candidate, "Reply with the single word OK.", max_tokens=256, temperature=0)
            if not isinstance(answer, dict):
                client = candidate
                print_lg(f'Using Gemini model {other}. Put gemini_model = "{other}" in config/secrets.py to skip this check next time.')
                break
    if isinstance(answer, dict):
        print_lg(f"Gemini is not working: {answer.get('error')}. Check `gemini_api_key` and `gemini_model` in config/secrets.py. Continuing without AI.")
        return None
    print_lg(f"---- Gemini connected, model: {client.model} ----")
    return client


def gemini_extract_skills(client: GeminiClient, job_description: str) -> dict | list | None:
    try:
        prompt = extract_skills_prompt.format(job_description) + "\n\nImportant: Respond with only the JSON object, without any markdown formatting or other text."
        return gemini_completion(client, prompt, is_json=True, max_tokens=800)
    except Exception as e:
        critical_error_log("Error occurred while extracting skills with Gemini!", e)
        return {"error": str(e)}


_ANSWER_PROMPT = """You are filling in a job application form as the candidate described below. Answer the question the way this candidate would.

Rules:
- Use only facts from the candidate information. Never invent degrees, employers, numbers or skills that aren't there.
- Numbers (years, salary, notice period): reply with only the number.
- Yes / No questions: reply with only "Yes" or "No".
- Short questions (a name, a city, a title): reply with a few words.
- Open questions ("Why do you want this job?", "Tell us about yourself", "Why should we hire you?"): write {length} in the first person,
  specific to this job and company, mentioning 1-2 relevant skills or projects from the candidate information. Sound natural, not like a template.
- Never use placeholders like [Company] or "XYZ", never repeat the question, no markdown, no quotes.

CANDIDATE INFORMATION:
{profile}

{job}QUESTION: {question}
"""


def gemini_answer_question(
    client: GeminiClient,
    question: str, options: list[str] | None = None,
    question_type: Literal['text', 'textarea', 'single_select', 'multiple_select'] = 'text',
    job_description: str = None, about_company: str = None, user_information_all: str = None
) -> str | dict:
    '''Answers one form question. Returns the answer text, or {"error": ...}.'''
    try:
        print_lg(f'Asking Gemini: "{question}"')
        job = ""
        if about_company: job += f"COMPANY: {about_company}\n"
        if job_description and job_description != "Unknown": job += f"JOB DESCRIPTION:\n{job_description[:3500]}\n\n"
        length = "3 to 5 sentences (under 700 characters)" if question_type == "textarea" else "1 to 2 sentences"
        prompt = _ANSWER_PROMPT.format(length=length, profile=(user_information_all or "")[:9000], job=job, question=question.strip())
        if options and question_type in ("single_select", "multiple_select"):
            prompt += "\nOPTIONS:\n" + "\n".join(f"- {option}" for option in options)
            prompt += "\nReply with exactly one option, copied exactly as written." if question_type == "single_select" else "\nReply with the matching options separated by commas, copied exactly."
        answer = gemini_completion(client, prompt, max_tokens=700 if question_type == "textarea" else 120)
        if isinstance(answer, str):
            answer = answer.strip().strip('"').strip()
        return answer
    except Exception as e:
        critical_error_log("Error occurred while answering question with Gemini!", e)
        return {"error": str(e)}
