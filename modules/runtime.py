'''
Where things are, whether the app runs from source (python app.py) or as the Windows app (ApplyAndPray.exe, built with PyInstaller).

* BUNDLE_DIR - the program's own files: templates, static, config defaults. Read-only inside the Windows app.
* APP_HOME   - where your data goes (user_data/, logs/, all excels/). The working folder of every part of the app.
               From source: the project folder. Windows app: %LOCALAPPDATA%\\ApplyAndPray (writable, survives updates).
* command()  - how to start one part of the app as its own process (the bot, a setup check, the control window...).
               From source it runs apply_and_pray.py, in the Windows app the .exe itself, with the same sub-commands.
'''

import os
import sys

FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE_DIR = getattr(sys, "_MEIPASS", PROJECT_DIR) if FROZEN else PROJECT_DIR

if os.environ.get("APPLY_AND_PRAY_HOME"):
    APP_HOME = os.environ["APPLY_AND_PRAY_HOME"]
elif FROZEN:
    APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ApplyAndPray")
else:
    APP_HOME = PROJECT_DIR


def bundle_path(*parts: str) -> str:
    return os.path.join(BUNDLE_DIR, *parts)


def home_path(*parts: str) -> str:
    return os.path.join(APP_HOME, *parts)


def command(*arguments: str) -> list[str]:
    '''The command line that runs `apply_and_pray <arguments>` as a new process.'''
    if FROZEN: return [sys.executable, *arguments]
    return [sys.executable, os.path.join(PROJECT_DIR, "apply_and_pray.py"), *arguments]


def enter_home() -> None:
    '''Makes APP_HOME the working folder (the bot's paths like "logs/" and "all excels/" are relative to it).'''
    os.makedirs(APP_HOME, exist_ok=True)
    os.chdir(APP_HOME)
    if PROJECT_DIR not in sys.path: sys.path.insert(0, PROJECT_DIR)
