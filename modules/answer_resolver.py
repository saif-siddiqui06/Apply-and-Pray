'''
Decides the answer for an application question. Order:
1. Saved answers (answers you gave in earlier popups)
2. Your profile (config files), passed in by the caller
3. AI, if `use_AI = True`
4. Popup asking you, the answer is saved if you click "Save for all jobs"
'''

from typing import Callable

from modules.helpers import print_lg
from modules.answer_store import AnswerStore, match_option, normalize_question
from modules.popup import ask_user


class AnswerResolver:
    def __init__(self, store: AnswerStore, ai_answer: Callable | None = None, popups_enabled: bool = True):
        '''
        * `ai_answer(question, question_type, options, job_description) -> str | None`, or `None` if AI is off.
        * `popups_enabled`: False when running in background, unknown questions are then left unanswered.
        '''
        self.store = store
        self.ai_answer = ai_answer
        self.popups_enabled = popups_enabled
        self.review_ai_answers = False      # True: long AI answers are shown in the popup to edit before use
        self.popup_timeout_minutes = 0      # Popups not answered in this time are skipped, 0 = wait for ever
        # `ai_writer(question, notes, question_type, company, job_title, job_description) -> str`: the popup's "Write with AI" button
        self.ai_writer: Callable | None = None
        self._job_description: str | None = None   # Of the current question, for "Write with AI"
        self.on_popup_closed: Callable | None = None   # Called after every popup, Eg: to give the browser window its focus back
        self.last_source = None     # "saved", "profile", "ai", "user" or None, for logging
        self._job_answers: dict[str, str | None] = {}   # Popup / AI results for the current application, `None` = you skipped it
        self._away = False


    def start_job(self) -> None:
        '''Call before each application. Within one application every question is asked at most once, even if the form is re-read.'''
        self._job_answers = {}
        self._away = False      # A popup of this application went unanswered (`popup_timeout_minutes`): don't wait on the others


    def skipped_this_job(self) -> list[str]:
        '''Questions you skipped in the current application.'''
        return [question for question, answer in self._job_answers.items() if answer is None]


    def find_saved(self, question: str, options: list[str] | None = None) -> str | None:
        answer = self.store.find(question, options)
        if answer is not None:
            self.last_source = "saved"
            print_lg(f'Using saved answer for "{question}": "{answer}"')
        return answer


    def ask_ai(self, question: str, question_type: str = "text", options: list[str] | None = None, job_description: str | None = None,
               company: str = "", job_title: str = "") -> str | None:
        if not self.ai_answer: return None
        try:
            try: answer = self.ai_answer(question, question_type, options, job_description, company=company, job_title=job_title)
            except TypeError: answer = self.ai_answer(question, question_type, options, job_description)   # Older 4-argument AI functions
        except Exception as e:
            print_lg("Failed to get AI answer!", e)
            return None
        if not isinstance(answer, str) or not answer.strip(): return None
        answer = answer.strip()
        if options:
            answer = match_option(answer, options)
            if answer is None: return None
        self.last_source = "ai"
        print_lg(f'AI answered "{question}": "{answer}"')
        return answer


    def ask_user(self, question: str, question_type: str = "text", options: list[str] | None = None,
                 company: str = "", job_title: str = "", suggestion: str = "", note: str = "", allow_save: bool = True) -> str | None:
        '''Shows the popup (once per question per application) and saves the answer if the user chose "Save for all jobs".'''
        if not self.popups_enabled: return None
        if not (question or "").strip() or question.strip().lower() == "unknown": return None   # Never ask a blank question
        key = normalize_question(question)
        if allow_save and key in self._job_answers:
            answer = self._job_answers[key]
            if answer is not None and options: answer = match_option(answer, options)
            if answer is not None: self.last_source = "user"
            return answer
        if allow_save and self._away:
            print_lg(f'Not asking for "{question}": an earlier popup of this application went unanswered')
            self._job_answers[key] = None
            return None
        print_lg(f'Asking you for: "{question}"')
        writer = None
        if self.ai_writer and allow_save and not options and question_type in ("text", "textarea"):   # Not for verification codes
            job_description = self._job_description
            def writer(notes: str) -> str:
                answer = self.ai_writer(question, notes, question_type, company, job_title, job_description)
                print_lg(f'AI wrote an answer for "{question}" from your notes')
                return answer
        timed_out = False
        try: result = ask_user(question, question_type, options, company, job_title, suggestion, note, allow_save,
                               timeout_seconds=self.popup_timeout_minutes * 60, ai_writer=writer)
        except TimeoutError: result, timed_out = None, True
        if timed_out: self._away = True
        if self.on_popup_closed:
            try: self.on_popup_closed()
            except Exception: pass
        if result is None:
            print_lg(f'No answer in {self.popup_timeout_minutes:g} min (popup_timeout_minutes), skipped: "{question}"' if timed_out else f'You skipped: "{question}"')
            if allow_save: self._job_answers[key] = None
            return None
        answer, save_for_all = result
        if save_for_all: self.store.save(question, answer, question_type, options)
        if allow_save: self._job_answers[key] = answer
        self.last_source = "user"
        return answer


    def resolve_unknown(self, question: str, question_type: str = "text", options: list[str] | None = None, *,
                        company: str = "", job_title: str = "", job_description: str | None = None, allow_popup: bool = True,
                        allow_review: bool | None = None) -> str | None:
        '''
        For questions the profile couldn't answer: AI first, then the popup. Each is tried once per question per application.
        `allow_review` (default: `allow_popup`): whether long AI answers may be shown for editing (`review_ai_answers`).
        '''
        if allow_review is None: allow_review = allow_popup
        self.last_source = None
        self._job_description = job_description
        ai_key = "ai:" + normalize_question(question)
        if ai_key not in self._job_answers:
            self._job_answers[ai_key] = self.ask_ai(question, question_type, options, job_description, company, job_title) if self.ai_answer else None
            if self._job_answers[ai_key] is None: self._job_answers[ai_key] = ""   # "" = AI had no answer, not "you skipped"
        answer = self._job_answers[ai_key]
        if answer:
            if options: answer = match_option(answer, options)
            if answer is not None:
                # Optional: let you read / edit long AI-written answers before they go into the form
                if self.review_ai_answers and question_type == "textarea" and allow_review and self.popups_enabled:
                    return self.ask_user(question, question_type, options, company, job_title, suggestion=answer,
                                         note="Written by AI from your details and resume. Edit it if needed.")
                self.last_source = "ai"
                return answer
        if allow_popup: return self.ask_user(question, question_type, options, company, job_title)
        return None


    def resolve(self, question: str, question_type: str = "text", options: list[str] | None = None, *,
                profile_answer: str | None = None, required: bool = True, popup: bool = True,
                company: str = "", job_title: str = "", job_description: str | None = None) -> str | None:
        '''
        Full lookup: saved answers, then `profile_answer`, then AI, then popup (only for required questions).
        * `popup=False`: stops before the popup, so the caller can try a default answer first (it calls `ask_user` itself after).
        * Returns the answer (matching option text if `options` are given), or `None` if unanswered.
        '''
        self.last_source = None
        answer = self.find_saved(question, options)
        if answer is not None: return answer
        if profile_answer is not None and str(profile_answer).strip() != "":
            answer = match_option(str(profile_answer), options) if options else str(profile_answer)
            if answer is not None:
                self.last_source = "profile"
                return answer
        return self.resolve_unknown(question, question_type, options, company=company, job_title=job_title,
                                    job_description=job_description, allow_popup=required and popup, allow_review=required)
