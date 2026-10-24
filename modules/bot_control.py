'''
Lets the control window (modules/control_panel.py) pause, skip, stop or quit the bot.

The bot calls `control.checkpoint()` at safe points (before each job, each form page, each field):
* paused -> waits there until you click Resume (you can fill the form yourself meanwhile)
* skip   -> raises `SkipJob`, the current application is dropped and the bot moves to the next job
* quit   -> raises `QuitBot`, the bot stops right away and shows the summary
`control.stop_requested` becomes True after "Stop after this job", the job loop ends after the current job.

`SkipJob` and `QuitBot` extend BaseException on purpose, so the many `except Exception` blocks don't swallow them.
'''

import os
import sys
import json
import subprocess
from time import sleep, time

from modules.helpers import print_lg


class SkipJob(BaseException):
    '''You clicked "Skip this job".'''


class QuitBot(BaseException):
    '''You clicked "Quit now".'''


class BotControl:
    def __init__(self, folder: str = "logs"):
        os.makedirs(folder, exist_ok=True)
        self.state_path = os.path.abspath(os.path.join(folder, "control_state.json"))
        self.status_path = os.path.abspath(os.path.join(folder, "control_status.txt"))
        self._process = None
        self._skips_seen = 0
        self._state = {}
        self._last_read = 0.0
        self.quitting = False
        self.stop_requested = False
        self.paused_seconds = 0.0   # Time spent paused, left out of the speed in the summary
        for path in (self.state_path, self.status_path):
            try: os.remove(path)
            except OSError: pass


    def start_panel(self) -> None:
        '''Opens the control window. If it can't start, the bot just runs without it.'''
        from modules.runtime import command
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen(command("control-panel", self.state_path, self.status_path), creationflags=flags)
            print_lg("Control window opened: Pause / Resume, Skip this job, Stop after this job, Quit now.")
        except Exception as e:
            print_lg("Could not open the control window, continuing without it.", e)


    def close_panel(self) -> None:
        self.status("__exit__")
        if self._process is not None:
            try: self._process.wait(timeout=3)
            except Exception:
                try: self._process.terminate()
                except Exception: pass


    def status(self, text: str) -> None:
        '''One line shown in the control window.'''
        try:
            with open(self.status_path, "w", encoding="utf-8") as file: file.write(text)
        except Exception: pass


    def _read(self) -> dict:
        if time() - self._last_read < 0.25: return self._state
        self._last_read = time()
        try:
            with open(self.state_path, "r", encoding="utf-8") as file: self._state = json.load(file)
        except Exception: pass
        return self._state


    def checkpoint(self, allow_skip: bool = True) -> str | None:
        '''
        Call at safe points. Waits while paused. Raises `QuitBot` on quit, and `SkipJob` on skip if `allow_skip`
        (else returns "skip" so the caller can drop the job its own way). Returns None to carry on.
        '''
        paused_at = None
        try:
            while True:
                state = self._read()
                if state.get("quit"):
                    self.quitting = True
                    raise QuitBot()
                if state.get("stop") and not self.stop_requested:
                    self.stop_requested = True
                    print_lg("You clicked 'Stop after this job'.")
                if state.get("skip", 0) > self._skips_seen:
                    self._skips_seen = state["skip"]
                    print_lg("You clicked 'Skip this job'.")
                    if allow_skip: raise SkipJob()
                    return "skip"
                if not state.get("paused"): return None
                if paused_at is None:
                    paused_at = time()
                    print_lg("Paused from the control window. Waiting for Resume...")
                    self.status("Paused. Fill anything you want in the browser, then click Resume.")
                sleep(0.5)
        finally:
            if paused_at is not None: self.paused_seconds += time() - paused_at


    def clear_skip(self) -> None:
        '''Forget a "Skip" clicked while no job was running.'''
        self._skips_seen = self._read().get("skip", self._skips_seen)


    def wait(self, seconds: float, allow_skip: bool = False, return_on_stop: bool = True) -> None:
        '''
        Sleep that still reacts to Pause / Quit, to Skip with `allow_skip` (raises `SkipJob`), and ends early after
        "Stop after this job" when `return_on_stop` (waits inside an application keep their length, so the job finishes at the normal pace).
        '''
        end = time() + seconds
        while time() < end:
            self.checkpoint(allow_skip=allow_skip)
            if self.stop_requested and return_on_stop: return
            sleep(min(0.5, max(0.0, end - time())))
