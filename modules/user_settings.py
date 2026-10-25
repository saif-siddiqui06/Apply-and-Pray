'''
Your own settings, kept outside the code so the project can be shared and updated without your details.

* `config/*.py` hold the DEFAULTS and the explanation of every setting. They are in git, so never put your details there.
* `user_data/settings.json` holds YOUR values (name, phone, search terms...), one section per config file. Git ignores `user_data/`.
* Passwords and API keys are kept in Windows Credential Manager (macOS Keychain / Linux Secret Service) through `keyring`,
  or in `user_data/secrets.json` when no keyring is available.

Each config file ends with `apply_user_settings(globals(), "<section>")`, which puts your values over the defaults,
so `from config.personals import first_name` keeps working everywhere.
'''

import os
import json

from modules.runtime import PROJECT_DIR, APP_HOME
USER_DATA_DIR = os.environ.get("APPLY_AND_PRAY_DATA_DIR") or os.path.join(APP_HOME, "user_data")   # Override: Eg: a test profile
SETTINGS_FILE = os.path.join(USER_DATA_DIR, "settings.json")
SECRETS_FILE = os.path.join(USER_DATA_DIR, "secrets.json")     # Only used when keyring isn't available
KEYRING_SERVICE = "Apply-and-Pray"

# Settings that are passwords / keys: never written to settings.json
SECRET_NAMES = {
    "secrets": ["password", "llm_api_key", "gemini_api_key", "gemini_backup_keys", "fallback_api_key"],
    "portal_login": ["portal_password"],
    "gmail": ["gmail_app_password"],
}


def user_path(*parts: str) -> str:
    '''A path inside `user_data/`, Eg: user_path("resumes", "resume.pdf").'''
    return os.path.join(USER_DATA_DIR, *parts)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as file: return json.load(file)
    except FileNotFoundError: return {}
    except Exception as e:
        print(f"Couldn't read {path} ({e}), using the defaults.")
        return {}


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as file: json.dump(data, file, indent=2, ensure_ascii=False)
    os.replace(temp, path)   # Never leaves a half-written file


#< Secrets
def _keyring():
    try:
        import keyring
        from keyring.backends.fail import Keyring as NoKeyring
        return None if isinstance(keyring.get_keyring(), NoKeyring) else keyring
    except Exception:
        return None


def get_secret(name: str) -> str:
    store = _keyring()
    if store is not None:
        try:
            value = store.get_password(KEYRING_SERVICE, name)
            if value is not None: return value
        except Exception: pass
    return str(_read_json(SECRETS_FILE).get(name, ""))


def set_secret(name: str, value: str) -> None:
    '''Saves a password / key. An empty value deletes it.'''
    store = _keyring()
    if store is not None:
        try:
            if value: store.set_password(KEYRING_SERVICE, name, value)
            else:
                try: store.delete_password(KEYRING_SERVICE, name)
                except Exception: pass
            return
        except Exception: pass
    secrets = _read_json(SECRETS_FILE)
    if value: secrets[name] = value
    else: secrets.pop(name, None)
    _write_json(SECRETS_FILE, secrets)
#>


def load_section(section: str) -> dict:
    return dict(_read_json(SETTINGS_FILE).get(section, {}))


def save_section(section: str, values: dict) -> None:
    '''Saves your values for one config section (merged with what's there). Secrets go to the keyring, never to settings.json.'''
    settings = _read_json(SETTINGS_FILE)
    current = settings.get(section, {})
    for name, value in values.items():
        if name in SECRET_NAMES.get(section, []): set_secret(name, str(value or ""))
        else: current[name] = value
    settings[section] = current
    _write_json(SETTINGS_FILE, settings)


def apply_user_settings(module_globals: dict, section: str) -> None:
    '''Puts your values over the defaults of a config file. Only names the config file defines are used (a typo can't add a setting).'''
    if os.environ.get("APPLY_AND_PRAY_DEFAULTS_ONLY") == "1": return   # Reading the plain defaults (Eg: setup/migrate_config.py)
    for name, value in load_section(section).items():
        if name.startswith("_") or name not in module_globals: continue
        default = module_globals[name]
        if isinstance(default, tuple) and isinstance(value, list): value = tuple(value)   # JSON has no tuples, Eg: delays (1, 2)
        module_globals[name] = value
    for name in SECRET_NAMES.get(section, []):
        if name in module_globals:
            secret = get_secret(name)
            if secret: module_globals[name] = secret
