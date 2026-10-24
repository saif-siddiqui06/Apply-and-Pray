'''
"Missing detail" popup, shown when the bot doesn't know how to answer an application question.
'''

import time
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

SAVE_ALL = "save"
THIS_JOB = "once"


def ask_user(
    question: str,
    question_type: str = "text",
    options: list[str] | None = None,
    company: str = "",
    job_title: str = "",
    suggestion: str = "",
    note: str = "",
    allow_save: bool = True,
    timeout_seconds: float = 0,
    ai_writer: Callable[[str], str] | None = None,
    _test_action=None,
) -> tuple[str, bool] | None:
    '''
    Shows a popup asking the user to answer `question`.
    * `question_type`: "text" (one line), "textarea" (multi-line) or anything with `options` (pick one).
    * `allow_save`: If False, only "Continue" is shown (Eg: for one-time verification codes).
    * `timeout_seconds`: The popup closes by itself if it isn't answered in that time (raises `TimeoutError`), 0 = waits for ever.
      The countdown stops as soon as you type or click in the popup.
    * `ai_writer(notes) -> answer`: Shows a "Write with AI" button: you type a few words, AI writes the full answer (raises if it can't).
    * Returns `(answer, save_for_all_jobs)`, or `None` if the user skipped the question.
    * `_test_action`: Used by tests to fill and press a button automatically, `(answer, "save" | "once" | "skip")`.
    '''
    result: dict = {"value": None}
    options = [option for option in (options or []) if option and option.strip()]

    root = tk.Tk()
    root.title("Missing detail - Apply and Pray")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    heading = "The bot needs your answer to continue"
    if job_title or company: heading += f"\n{job_title}{' @ ' if job_title and company else ''}{company}"
    ttk.Label(frame, text=heading, font=("Segoe UI", 10, "bold"), wraplength=520, justify="left").pack(anchor="w")
    ttk.Label(frame, text=question.strip(), font=("Segoe UI", 11), wraplength=520, justify="left").pack(anchor="w", pady=(12, 8))

    # Answer input
    choice = tk.StringVar(value=suggestion if suggestion in options else "")
    text_widget = None
    entry_var = tk.StringVar(value=suggestion if not options else "")
    if options and len(options) <= 8:
        for option in options:
            ttk.Radiobutton(frame, text=option, value=option, variable=choice).pack(anchor="w", pady=1)
    elif options:
        ttk.Combobox(frame, values=options, textvariable=choice, state="readonly", width=60).pack(anchor="w")
    elif question_type == "textarea":
        text_widget = tk.Text(frame, width=66, height=7, wrap="word", font=("Segoe UI", 10))
        text_widget.insert("1.0", suggestion)
        text_widget.pack(anchor="w")
        text_widget.focus_set()
    else:
        entry = ttk.Entry(frame, textvariable=entry_var, width=66)
        entry.pack(anchor="w")
        entry.focus_set()

    # Hints
    mentions_company = bool(company) and company.lower() in question.lower()
    hints = []
    if note: hints.append(note)
    if allow_save and mentions_company: hints.append(f'This question mentions {company}, so "This job only" is probably right.')
    if allow_save: hints.append('"Save for all jobs" reuses this answer automatically next time.')
    if hints: ttk.Label(frame, text="\n".join(hints), foreground="#555555", wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
    error_label = ttk.Label(frame, text="", foreground="#b00020")
    error_label.pack(anchor="w")

    # "Write with AI": a few words from you (Eg: "RAG chatbot for my college, 500 students use it") -> the full answer, which you can edit
    ai_status = None
    if ai_writer and not options:
        ai_row = ttk.Frame(frame)
        ai_row.pack(fill="x", pady=(6, 0))
        ai_button = ttk.Button(ai_row, text="Write with AI")
        ai_button.pack(side="left")
        ai_status = ttk.Label(ai_row, text="Type a few words about your answer, then click Write with AI.", foreground="#555555", wraplength=400, justify="left")
        ai_status.pack(side="left", padx=8)
        writing = {"thread": None, "answer": None, "error": None}

        def show_answer(text: str) -> None:
            if text_widget is not None:
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", text)
            else: entry_var.set(text)

        def wait_for_ai() -> None:
            if writing["thread"].is_alive():
                root.after(200, wait_for_ai)
                return
            ai_button.state(["!disabled"])
            if writing["answer"]:
                show_answer(writing["answer"])
                ai_status.config(text="Written by AI from your notes. Edit it if needed, then save. Click again for another version.", foreground="#1b5e20")
            else:
                ai_status.config(text=f"AI couldn't write it: {writing['error'] or 'no answer'}", foreground="#b00020")

        def write_with_ai() -> None:
            notes = current_answer()
            if not notes:
                ai_status.config(text="Type a few words about your answer first (what you did, numbers, tools).", foreground="#b00020")
                return
            writing.update(answer=None, error=None)
            def work():
                try: writing["answer"] = (ai_writer(notes) or "").strip()
                except Exception as e: writing["error"] = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
            writing["thread"] = threading.Thread(target=work, daemon=True)
            writing["thread"].start()
            ai_button.state(["disabled"])
            ai_status.config(text="Writing...", foreground="#555555")
            root.after(200, wait_for_ai)

        ai_button.config(command=write_with_ai)
    countdown_label = ttk.Label(frame, text="", foreground="#555555")
    if timeout_seconds > 0: countdown_label.pack(anchor="w")

    def current_answer() -> str:
        if options: return choice.get().strip()
        if text_widget is not None: return text_widget.get("1.0", "end").strip()
        return entry_var.get().strip()

    def finish(action: str) -> None:
        if action == "skip":
            result["value"] = None
            root.destroy()
            return
        answer = current_answer()
        if not answer:
            error_label.config(text="Please enter an answer, or click Skip.")
            return
        result["value"] = (answer, action == SAVE_ALL)
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(12, 0))
    if allow_save:
        save_button = ttk.Button(buttons, text="Save for all jobs", command=lambda: finish(SAVE_ALL))
        once_button = ttk.Button(buttons, text="This job only", command=lambda: finish(THIS_JOB))
        save_button.pack(side="left")
        once_button.pack(side="left", padx=8)
        default_button = once_button if mentions_company else save_button
    else:
        default_button = ttk.Button(buttons, text="Continue", command=lambda: finish(THIS_JOB))
        default_button.pack(side="left")
    ttk.Button(buttons, text="Skip", command=lambda: finish("skip")).pack(side="right")
    default_button.focus_set() if options else None
    if question_type != "textarea": root.bind("<Return>", lambda event: default_button.invoke())
    root.protocol("WM_DELETE_WINDOW", lambda: finish("skip"))

    # Center on screen and grab focus, the browser window is usually in front
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    root.lift()
    root.focus_force()

    # Nobody there (Eg: the bot runs overnight): skip the question so the run goes on with the next job.
    # Once you type or click in the popup, it waits for you.
    if timeout_seconds > 0:
        deadline = time.time() + timeout_seconds
        touched = {"yes": False}
        def stop_countdown(event=None):
            if not touched["yes"]:
                touched["yes"] = True
                countdown_label.config(text="")
        root.bind("<Key>", stop_countdown, add="+")
        root.bind("<Button>", stop_countdown, add="+")
        def tick():
            if touched["yes"]: return
            left = deadline - time.time()
            if left <= 0:
                result["timed_out"] = True
                finish("skip")
                return
            countdown_label.config(text=f"No answer: skipped automatically in {int(left // 60)}:{int(left % 60):02d}")
            root.after(1000, tick)
        tick()

    if _test_action:
        test_answer, test_button = _test_action
        def run_test():
            if test_answer is not None:
                if options: choice.set(test_answer)
                elif text_widget is not None: text_widget.delete("1.0", "end"); text_widget.insert("1.0", test_answer)
                else: entry_var.set(test_answer)
            finish({"save": SAVE_ALL, "once": THIS_JOB}.get(test_button, "skip"))
        root.after(300, run_test)

    root.mainloop()
    if result.get("timed_out"): raise TimeoutError("No answer in the popup")
    return result["value"]
