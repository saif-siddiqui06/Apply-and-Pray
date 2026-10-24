'''
Saves a password or API key in Windows Credential Manager (or user_data/secrets.json without a keyring).

Usage, from the project folder:
    python setup/set_secret.py gemini_api_key
    python setup/set_secret.py --list

The value is typed hidden, it never shows on screen or in any file in the project.
'''

import os
import sys
import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.user_settings import set_secret, get_secret, SECRET_NAMES

NAMES = [name for names in SECRET_NAMES.values() for name in names]

if len(sys.argv) != 2 or sys.argv[1] not in NAMES + ["--list"]:
    print(__doc__ + "\nNames: " + ", ".join(NAMES))
    sys.exit(1)
if sys.argv[1] == "--list":
    for name in NAMES: print(f"{name:20} {'set' if get_secret(name) else '-'}")
    sys.exit(0)
value = getpass.getpass(f"{sys.argv[1]} (Enter to delete): ").strip()
set_secret(sys.argv[1], value)
print("Saved." if value else "Deleted.")
