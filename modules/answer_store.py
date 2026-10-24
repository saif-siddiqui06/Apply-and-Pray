'''
Saved answers for application questions.

Answers you type in the "missing detail" popup are saved in a JSON file (`saved_answers_file` in config/settings.py)
and reused automatically the next time the same question shows up, on LinkedIn Easy Apply or on company websites.
'''

import os
import re
import json
from datetime import datetime

from modules.helpers import print_lg


# Words that don't change what a question is asking. Units (days, months, years) and topics (python, java) are NOT here on purpose.
_FILLER_WORDS = {
    "a", "an", "the", "of", "to", "for", "in", "on", "at", "by", "with", "and", "or", "as", "from", "about",
    "is", "are", "was", "were", "be", "been", "do", "does", "did", "have", "has", "had",
    "what", "which", "please", "kindly", "enter", "specify", "provide", "mention", "select", "choose", "tell",
    "us", "you", "your", "yours", "i", "my", "me", "this", "that", "it", "if", "any",
    "required", "optional", "answer", "question",
}

DECLINE_PHRASES = ["decline", "prefer not", "not wish", "don't wish", "do not wish", "not want", "don't want", "not to say", "not to answer", "rather not", "not disclose"]


def normalize_question(text: str) -> str:
    '''Lowercases the question and strips punctuation, required markers and extra spaces.'''
    text = (text or "").lower()
    text = re.sub(r'\(\s*(required|optional)\s*\)', ' ', text)
    text = re.sub(r'[^a-z0-9+#]+', ' ', text)   # Keeps "c++" and "c#"
    return " ".join(text.split())


def question_keywords(normalized: str) -> frozenset:
    '''Words that carry the meaning of the question, with simple plurals removed ("years" -> "year").'''
    words = set()
    for word in normalized.split():
        if word in _FILLER_WORDS: continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"): word = word[:-1]
        words.add(word)
    return frozenset(words)


def _clean_option(text: str) -> str:
    return " ".join(re.sub(r'[^a-z0-9+#]+', ' ', (text or "").lower()).split())


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r'\d[\d,]*\.?\d*', text)]


def _option_contains_number(option: str, value: float) -> bool:
    '''True if an option like "1-3 years", "5+ years", "Less than 2" or "More than 10" covers `value`.'''
    low = option.lower()
    nums = _numbers(low)
    if not nums: return False
    if len(nums) >= 2 and re.search(r'\d\s*(-|–|to)\s*\d', low): return nums[0] <= value <= nums[1]
    if "+" in low or "more than" in low or "above" in low or "over" in low or "at least" in low: return value >= nums[0]
    if "less than" in low or "under" in low or "below" in low or "fewer" in low: return value < nums[0]
    return len(nums) == 1 and nums[0] == value


def match_option(answer: str | None, options: list[str] | None) -> str | None:
    '''
    Finds the option that means the same as `answer`.
    * Returns the option text exactly as shown on the form, or `None` if no option is a safe match.
    '''
    if answer is None or not options: return None
    answer_clean = _clean_option(str(answer))
    if not answer_clean: return None
    choices = [(option, _clean_option(option)) for option in options if option and _clean_option(option)]

    # 1. Same text
    for option, clean in choices:
        if clean == answer_clean: return option

    # 2. "Decline" matches any "Prefer not to say" style option
    if answer_clean.startswith("decline") or any(phrase in str(answer).lower() for phrase in DECLINE_PHRASES):
        for option, clean in choices:
            if any(phrase in option.lower() for phrase in DECLINE_PHRASES): return option
        return None

    # 3. Yes / No match options that start with that word ("Yes, I am authorized"), never "None of the above"
    if answer_clean in ("yes", "no"):
        for option, clean in choices:
            if clean.split()[0] == answer_clean: return option
        return None

    # 4. A number matches the range that contains it ("2" -> "1-3 years")
    if re.fullmatch(r'\d+(\.\d+)?', answer_clean.replace(" ", "")):
        value = float(answer_clean.replace(" ", ""))
        in_range = [option for option, _ in choices if _option_contains_number(option, value)]
        if len(in_range) == 1: return in_range[0]

    # 5. Whole-word containment in either direction, only if exactly one option matches
    contained = [option for option, clean in choices
                 if re.search(r'\b' + re.escape(answer_clean) + r'\b', clean) or re.search(r'\b' + re.escape(clean) + r'\b', answer_clean)]
    if len(contained) == 1: return contained[0]
    return None



class AnswerStore:
    '''
    Reads and writes saved answers. The file is re-read whenever it changes on disk, so edits you make by hand apply immediately.
    '''
    def __init__(self, path: str):
        self.path = path
        self._answers: dict[str, dict] = {}
        self._mtime = None
        self._broken = False
        self._load()


    def _load(self) -> None:
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            self._answers, self._mtime, self._broken = {}, None, False
            return
        if mtime == self._mtime: return
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            self._answers = data.get("answers", {}) if isinstance(data, dict) else {}
            self._mtime = mtime
            self._broken = False
        except Exception as e:
            # Don't overwrite a file the user broke while editing, they'd lose all saved answers
            self._broken = True
            self._mtime = mtime
            print_lg(f'Saved answers file "{self.path}" has a mistake and could not be read, fix it or delete it. New answers will not be saved until then!', e)


    def find(self, question: str, options: list[str] | None = None) -> str | None:
        '''
        Returns the saved answer for `question`, or `None`.
        * Matches the exact question first, then questions with the same keywords in a different order or wording.
        * If `options` are given, returns the matching option text, or `None` if the saved answer isn't one of them.
        '''
        self._load()
        key = normalize_question(question)
        if not key: return None
        entry = self._answers.get(key)
        if entry is None:
            keywords = question_keywords(key)
            if keywords:
                for saved_key, saved_entry in self._answers.items():
                    if question_keywords(saved_key) == keywords:
                        entry = saved_entry
                        break
        if entry is None: return None
        answer = entry.get("answer")
        if answer is None or str(answer).strip() == "": return None
        if options: return match_option(str(answer), options)
        return str(answer)


    def save(self, question: str, answer: str, question_type: str = "text", options: list[str] | None = None) -> bool:
        '''Saves `answer` for `question` and returns `True` if it was written to the file.'''
        self._load()
        if self._broken:
            print_lg(f'Not saving answer for "{question}" because "{self.path}" could not be read.')
            return False
        key = normalize_question(question)
        if not key or answer is None or str(answer).strip() == "": return False
        self._answers[key] = {
            "question": question.strip(),
            "answer": str(answer),
            "type": question_type,
            "options": list(options) if options else [],
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            folder = os.path.dirname(self.path)
            if folder: os.makedirs(folder, exist_ok=True)
            temp_path = self.path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump({"version": 1, "answers": self._answers}, file, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.path)
            self._mtime = os.path.getmtime(self.path)
            print_lg(f'Saved answer for "{question.strip()}" in "{self.path}"')
            return True
        except Exception as e:
            print_lg(f'Failed to save answer in "{self.path}"!', e)
            return False
