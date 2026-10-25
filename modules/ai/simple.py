'''
One plain function to get text from the AI you set up (Gemini, OpenAI, DeepSeek or a local model), for writing
invitation notes and messages outside the bot's main run (Eg: from the dashboard). Returns None when AI is off or fails,
so the caller can fall back to a template.
'''

from modules.helpers import print_lg

_client = None
_client_ready = False


def _setup():
    global _client, _client_ready
    if _client_ready: return _client
    _client_ready = True
    try:
        from config.secrets import use_AI, ai_provider, llm_api_url, llm_api_key, llm_model
        if not use_AI: return None
        if ai_provider == "gemini":
            from modules.ai.geminiConnections import gemini_create_client
            _client = ("gemini", gemini_create_client())
        else:
            from openai import OpenAI
            base_url = llm_api_url.rstrip("/") if ai_provider == "deepseek" else llm_api_url
            _client = ("openai", OpenAI(base_url=base_url, api_key=llm_api_key or "not-needed", timeout=60, max_retries=1), llm_model)
        if _client[1] is None: _client = None
    except Exception as e:
        print_lg("AI isn't available for writing messages:", str(e)[:150])
        _client = None
    return _client


def write(prompt: str, max_tokens: int = 400) -> str | None:
    text = _write_main(prompt, max_tokens)
    if text: return text
    from modules.ai import fallback   # Gemini quota used up / AI not set: the backup AI (Groq / OpenRouter)
    return fallback.complete(prompt, max_tokens) if fallback.configured() else None


def _write_main(prompt: str, max_tokens: int = 400) -> str | None:
    client = _setup()
    if client is None: return None
    try:
        if client[0] == "gemini":
            from modules.ai.geminiConnections import gemini_completion
            answer = gemini_completion(client[1], prompt, max_tokens=max_tokens, temperature=0.6)
            if isinstance(answer, dict):
                print_lg("AI couldn't write it:", str(answer.get("error"))[:150])
                return None
            return str(answer).strip() or None
        reply = client[1].chat.completions.create(model=client[2], messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.6)
        return (reply.choices[0].message.content or "").strip() or None
    except Exception as e:
        print_lg("AI couldn't write it:", str(e)[:150])
        return None
