'''
Small always-on-top control window for the bot: Pause / Resume, Skip this job, Stop after this job, Quit now.

It runs as its own program (started by the bot), so it stays clickable even while the bot is busy or a popup is open.
It talks to the bot through two small files:
* state file  (written here): {"paused": bool, "skip": int, "stop": bool, "quit": bool}
* status file (written by the bot): one line of text about what the bot is doing
Usage: python control_panel.py <state_file> <status_file>
'''

import os
import sys
import json
import tkinter as tk
from tkinter import ttk


def main(state_path: str, status_path: str) -> None:
    state = {"paused": False, "skip": 0, "stop": False, "quit": False}

    def save() -> None:
        try:
            with open(state_path + ".tmp", "w", encoding="utf-8") as file: json.dump(state, file)
            os.replace(state_path + ".tmp", state_path)
        except Exception: pass

    save()
    root = tk.Tk()
    root.title("Apply and Pray - Control")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=10)
    frame.pack(fill="both", expand=True)

    # Fixed heights, so the buttons never move when the text changes (you shouldn't have to chase the Resume button)
    status = tk.StringVar(value="Starting...")
    tk.Label(frame, textvariable=status, wraplength=330, justify="left", anchor="nw", height=2, width=46, fg="#333333").pack(anchor="w", pady=(0, 4))
    hint = tk.StringVar(value="")
    tk.Label(frame, textvariable=hint, wraplength=330, justify="left", anchor="nw", height=3, width=46, fg="#b05a00").pack(anchor="w", pady=(0, 4))

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    pause_text = tk.StringVar(value="Pause")

    def toggle_pause() -> None:
        state["paused"] = not state["paused"]
        pause_text.set("Resume" if state["paused"] else "Pause")
        hint.set("Paused: you can fill the form yourself in the browser. Click Resume to let the bot continue." if state["paused"] else "")
        save()

    def skip_job() -> None:
        state["skip"] += 1
        state["paused"] = False
        pause_text.set("Pause")
        hint.set("Skipping the current job...")
        save()

    def stop_after_job() -> None:
        state["stop"] = True
        state["paused"] = False
        pause_text.set("Pause")
        hint.set("The bot will stop after the current job and show the summary.")
        save()

    confirm_quit = {"armed": False}
    def quit_now() -> None:
        if not confirm_quit["armed"]:
            confirm_quit["armed"] = True
            quit_button.config(text="Click again to quit")
            root.after(4000, lambda: (confirm_quit.update(armed=False), quit_button.config(text="Quit now")))
            return
        state["quit"] = True
        state["paused"] = False
        hint.set("Quitting...")
        save()

    ttk.Button(buttons, textvariable=pause_text, command=toggle_pause, width=10).grid(row=0, column=0, padx=2, pady=2)
    ttk.Button(buttons, text="Skip this job", command=skip_job, width=14).grid(row=0, column=1, padx=2, pady=2)
    ttk.Button(buttons, text="Stop after this job", command=stop_after_job, width=17).grid(row=1, column=0, columnspan=2, sticky="we", padx=2, pady=2)
    quit_button = ttk.Button(buttons, text="Quit now", command=quit_now, width=14)
    quit_button.grid(row=2, column=0, columnspan=2, sticky="we", padx=2, pady=2)

    def refresh() -> None:
        try:
            with open(status_path, "r", encoding="utf-8") as file: text = file.read().strip()
            if text == "__exit__":
                root.destroy()
                return
            if text: status.set(text[:300])
        except Exception: pass
        root.after(700, refresh)

    root.protocol("WM_DELETE_WINDOW", root.iconify)   # Closing only minimises it, the bot keeps running
    root.update_idletasks()
    root.geometry(f"+{root.winfo_screenwidth() - root.winfo_width() - 30}+{root.winfo_screenheight() - root.winfo_height() - 90}")
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
