'''
Moves your details from old-style config files (values typed into config/*.py) into user_data/.

Usage, from the project folder:
    python setup/migrate_config.py <folder with your old config/*.py files>

* Values that differ from the defaults go to user_data/settings.json.
* Passwords and API keys go to Windows Credential Manager (or user_data/secrets.json without a keyring).
* saved_answers.json, portal_accounts.json and your resume are copied into user_data/.
Run it once. Running it again only overwrites the same values.
'''

import os
import sys
import json
import runpy
import shutil

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

from modules.user_settings import save_section, set_secret, user_path, SECRET_NAMES
from modules.runtime import bundle_path

SECTIONS = ["personals", "secrets", "questions", "search", "settings", "portal_login"]
PLACEHOLDERS = {"", "example_password", "username@example.com", "not-needed"}


def plain_values(namespace: dict) -> dict:
    return {name: (list(value) if isinstance(value, tuple) else value) for name, value in namespace.items()
            if not name.startswith("_") and isinstance(value, (str, int, float, bool, list, tuple, dict))}


def defaults(section: str) -> dict:
    os.environ["APPLY_AND_PRAY_DEFAULTS_ONLY"] = "1"
    try: return plain_values(runpy.run_path(bundle_path("config", section + ".py")))
    finally: os.environ.pop("APPLY_AND_PRAY_DEFAULTS_ONLY", None)


def copy_into_user_data(source: str, *target: str) -> str | None:
    if not source or not os.path.isfile(source): return None
    destination = user_path(*target)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.abspath(source) != os.path.abspath(destination): shutil.copy2(source, destination)
    return os.path.relpath(destination, PROJECT_DIR).replace("\\", "/")


def find_file(path: str, old_folder: str) -> str | None:
    '''Old paths were relative to the project, its parent folder, or the config folder.'''
    for candidate in (path, os.path.join(PROJECT_DIR, path), os.path.join(os.path.dirname(PROJECT_DIR), path), os.path.join(old_folder, os.path.basename(path))):
        if candidate and os.path.isfile(candidate): return candidate
    return None


def main(old_folder: str) -> None:
    os.environ["APPLY_AND_PRAY_DEFAULTS_ONLY"] = "1"   # The old files may already end with the settings loader
    for section in SECTIONS:
        old_file = os.path.join(old_folder, section + ".py")
        if not os.path.isfile(old_file):
            print(f"- {section}: no old file, skipped")
            continue
        old = plain_values(runpy.run_path(old_file))
        new_defaults = defaults(section)
        values, secrets = {}, 0
        for name, value in old.items():
            if name not in new_defaults: continue   # Setting no longer exists
            if name in SECRET_NAMES.get(section, []):
                if str(value).strip() not in PLACEHOLDERS:
                    set_secret(name, str(value).strip())
                    secrets += 1
                continue
            if value != new_defaults[name]: values[name] = value

        # Files that used to live in config/ or elsewhere
        if section == "settings": values.pop("saved_answers_file", None)   # Now always user_data/saved_answers.json
        if section == "questions" and "default_resume_path" in values:
            source = find_file(values["default_resume_path"], old_folder)
            moved = copy_into_user_data(source, "resumes", os.path.basename(source)) if source else None
            if moved: values["default_resume_path"] = moved
            else: print(f"  ! resume {values['default_resume_path']} not found, kept the path as it was")

        os.environ.pop("APPLY_AND_PRAY_DEFAULTS_ONLY", None)
        save_section(section, values)
        os.environ["APPLY_AND_PRAY_DEFAULTS_ONLY"] = "1"
        print(f"- {section}: {len(values)} value(s) saved" + (f", {secrets} password/key(s) put in the keyring" if secrets else ""))

    for name in ("saved_answers.json", "portal_accounts.json"):
        if copy_into_user_data(os.path.join(old_folder, name), name): print(f"- copied {name} into user_data/")
    print("\nDone. Your details are in user_data/ (git ignores it). The config/*.py files now only hold defaults.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print(__doc__)
        sys.exit(1)
    main(os.path.abspath(sys.argv[1]))
