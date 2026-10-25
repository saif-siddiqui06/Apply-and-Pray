'''
Apply & Pray: one entry point for every part of the app. The Windows app (ApplyAndPray.exe) is built from this file.

    python apply_and_pray.py                    the dashboard (opens in your browser)
    python apply_and_pray.py bot                the bot (the mode comes from APPLY_AND_PRAY_MODE, set by the dashboard)
    python apply_and_pray.py check-linkedin     setup check: LinkedIn login
    python apply_and_pray.py check-ai           setup check: AI key
    python apply_and_pray.py check-linkedin-pages   read-only check of every LinkedIn page the bot uses
    python apply_and_pray.py draft              prepare connection requests and messages
    python apply_and_pray.py control-panel <state file> <status file>

The dashboard starts the other parts itself, you only need the first line.
'''

import sys
import json
import runpy

from modules.runtime import enter_home


def main(arguments: list[str]) -> None:
    enter_home()   # Before anything reads config: the bot's paths ("logs/", "all excels/") are relative to the data folder
    task = arguments[0] if arguments else "dashboard"
    if task == "dashboard":
        import app
        app.main()
    elif task == "bot":
        runpy.run_module("runAiBot", run_name="__main__")
    elif task in ("check-linkedin", "check-ai", "check-linkedin-pages"):
        from modules import checks
        result = {"check-linkedin": checks.linkedin, "check-ai": checks.ai, "check-linkedin-pages": checks.linkedin_pages}[task]()
        print(json.dumps(result), flush=True)
    elif task == "draft":
        from modules.connections import draft_invites
        from modules.messages import draft_messages
        result = draft_invites()
        result["messages"] = draft_messages()
        print(json.dumps(result), flush=True)
    elif task == "control-panel" and len(arguments) == 3:
        from modules import control_panel
        control_panel.main(arguments[1], arguments[2])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # Needed by PyInstaller on Windows
    main(sys.argv[1:])
