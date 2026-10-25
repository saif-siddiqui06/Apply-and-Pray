'''
A second, free AI used automatically when your main AI can't answer (Eg: Gemini's free daily quota is used up on every key).

Groq and OpenRouter both have free plans and an OpenAI-compatible API:
* Groq        - fast, free key at https://console.groq.com/keys
* OpenRouter  - many models, the ones ending in ":free" cost nothing, key at https://openrouter.ai/keys
Set it in the dashboard (Setup -> AI assistant -> Backup AI). If the model you chose is retired, a free one the key can use is picked.
'''

import re

from modules.helpers import print_lg

PROVIDERS = {
    "groq": {"url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile", "pick": re.compile(r'llama|gpt-oss|qwen|gemma|mixtral', re.I)},
    "openrouter": {"url": "https://openrouter.ai/api/v1", "model": "meta-llama/llama-3.3-70b-instruct:free", "pick": re.compile(r':free$', re.I)},
}
_state = {"client": None, "model": None, "ready": False, "off": False}


def configured() -> bool:
    from config import secrets
    return (getattr(secrets, "fallback_ai", "") or "") in PROVIDERS and bool((getattr(secrets, "fallback_api_key", "") or "").strip())


def _client():
    if _state["ready"]: return _state["client"]
    _state["ready"] = True
    if not configured(): return None
    from openai import OpenAI
    from config import secrets
    provider = PROVIDERS[secrets.fallback_ai]
    _state["client"] = OpenAI(base_url=provider["url"], api_key=secrets.fallback_api_key.strip(), timeout=45, max_retries=1)
    _state["model"] = (getattr(secrets, "fallback_model", "") or "").strip() or provider["model"]
    return _state["client"]


def _another_model() -> str | None:
    '''The model is retired / unknown: a free one this key can use.'''
    from config import secrets
    try:
        names = [model.id for model in _client().models.list().data]
        wanted = PROVIDERS[secrets.fallback_ai]["pick"]
        good = [name for name in names if wanted.search(name) and not re.search(r'guard|whisper|tts|embed|vision-preview', name, re.I)]
        return sorted(good, key=lambda name: ("70b" not in name and "versatile" not in name, len(name)))[0] if good else None
    except Exception:
        return None


def complete(prompt: str, max_tokens: int = 500) -> str | None:
    '''Text from the backup AI, or None (not set up, or it failed too).'''
    client = _client()
    if client is None or _state["off"]: return None
    for attempt in range(2):
        try:
            reply = client.chat.completions.create(model=_state["model"], messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.4)
            text = (reply.choices[0].message.content or "").strip()
            return text or None
        except Exception as e:
            message = str(e)
            if attempt == 0 and re.search(r'model.*(not found|decommissioned|does not exist|not exist|unavailable)|404', message, re.I):
                replacement = _another_model()
                if replacement and replacement != _state["model"]:
                    print_lg(f"Backup AI: model {_state['model']} isn't available, using {replacement}.")
                    _state["model"] = replacement
                    continue
            if re.search(r'401|invalid api key|unauthorized', message, re.I): _state["off"] = True   # Wrong key: stop trying this run
            print_lg("Backup AI couldn't answer:", message.splitlines()[0][:160])
            return None
    return None


def answer_question(question: str, question_type: str = "text", options: list[str] | None = None, job_description: str | None = None,
                    about_job: str | None = None, information: str = "") -> str | None:
    '''The same kind of answer the main AI gives, from the backup AI.'''
    from modules.ai.geminiConnections import _ANSWER_PROMPT
    job = (f"COMPANY: {about_job}\n" if about_job else "") + (f"JOB DESCRIPTION:\n{job_description[:3500]}\n\n" if job_description and job_description != "Unknown" else "")
    length = "3 to 5 sentences (under 700 characters)" if question_type == "textarea" else "1 to 2 sentences"
    prompt = _ANSWER_PROMPT.format(length=length, profile=(information or "")[:9000], job=job, question=question.strip())
    if options:
        prompt += "\nOPTIONS:\n" + "\n".join(f"- {option}" for option in options) + "\nReply with exactly one option, copied exactly as written."
    print_lg(f'Asking the backup AI: "{question[:120]}"')
    answer = complete(prompt, max_tokens=700 if question_type == "textarea" else 120)
    return answer.strip().strip('"').strip() if answer else None


def check() -> dict:
    '''Setup check for the backup AI.'''
    if not configured(): return {"ok": False, "detail": "Choose a backup AI and paste its key."}
    answer = complete("Reply with the single word OK.", max_tokens=10)
    if answer: return {"ok": True, "detail": f"Backup AI works (model {_state['model']})."}
    return {"ok": False, "detail": "The backup AI didn't answer: check its key (and that the account is active)."}
