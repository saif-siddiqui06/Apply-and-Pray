'''
Reads and fills application forms on any website.

`read_fields()` runs JavaScript in the page to list every visible field with its label, type, options and whether it's required,
and tags each element with a `data-aap` attribute so `fill_field()` can find it again.
'''

import os
import re
from time import sleep

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from modules.answer_store import match_option


_READ_FIELDS_JS = r'''
const MARK = 'data-aap';
const clean = t => (t || '').replace(/\s+/g, ' ').trim();
const textOf = el => el ? clean(el.innerText || el.textContent) : '';
const byIds = ids => clean((ids || '').split(/\s+/).map(id => textOf(document.getElementById(id))).join(' '));
const stripMarks = t => clean((t || '').replace(/✱/g, ' ').replace(/[*]+\s*$/, '').replace(/\(required\)\s*$/i, ''));

function visible(el) {
  if (!el) return false;
  const style = getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

// Label of a single input: <label for>, aria-labelledby, aria-label, wrapping <label>, nearby label, placeholder
function labelFor(el) {
  if (el.labels && el.labels.length) { const t = textOf(el.labels[0]); if (t) return t; }
  const lb = el.getAttribute('aria-labelledby'); if (lb) { const t = byIds(lb); if (t) return t; }
  const al = el.getAttribute('aria-label'); if (al) return clean(al);
  const wrap = el.closest('label'); if (wrap) { const t = textOf(wrap); if (t) return t; }
  // Walk up only through this field's own wrappers: once an ancestor also holds another field, its labels belong to that field
  let p = el.parentElement;
  for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
    const controls = [...p.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(c => c !== el && c.type !== 'radio' && c.type !== 'checkbox');
    if (controls.length) break;
    const l = p.querySelector('label, legend, .application-label, [class*="label"], [class*="Label"], [class*="queText"], [class*="question"]');
    if (l && !l.contains(el) && !l.querySelector('input, select, textarea') && !(l.htmlFor && l.htmlFor !== el.id)) { const t = textOf(l); if (t) return t; }
  }
  return clean(el.getAttribute('placeholder') || '');
}

// Text of one option in a radio / checkbox group
function optionText(el) {
  if (el.labels && el.labels.length) { const t = textOf(el.labels[0]); if (t) return t; }
  const al = el.getAttribute('aria-label'); if (al) return clean(al);
  const wrap = el.closest('label'); if (wrap) { const t = textOf(wrap); if (t) return t; }
  const next = el.nextElementSibling; if (next) { const t = textOf(next); if (t) return t; }
  // LinkedIn 2026: <div role=radio aria-label="question"><input><label></label></div><p>Yes</p> - the option is the text of its own box
  const box = el.closest('[role=radio]') || (el.parentElement && el.parentElement.parentElement);
  if (box) { const t = textOf(box); if (t) return t; }
  return clean(el.value);
}

// Question text of a radio / checkbox / button group: <legend>, role=group label, or the nearest label that isn't an option
function groupLabel(container, members) {
  // LinkedIn 2026: each option is <div role=radio aria-label="the question">, the question also stands just before the group
  for (const m of members) {
    const r = m.getAttribute('role') === 'radio' ? m : m.closest('[role=radio]');
    const al = r && r.getAttribute('aria-label');
    if (al && !members.some(o => clean(o.value || '') === clean(al))) return clean(al);
  }
  const holder = container.closest('fieldset, [role=radiogroup]');
  if (holder && !holder.querySelector('legend')) {
    const before = holder.previousElementSibling;
    if (before && !before.querySelector('input, select, textarea')) { const t = textOf(before); if (t && t.length < 300) return t; }
  }
  const fs = container.closest('fieldset');
  if (fs) {
    const lg = fs.querySelector('legend'); if (lg && textOf(lg)) return textOf(lg);
    const lb = fs.getAttribute('aria-labelledby'); if (lb && byIds(lb)) return byIds(lb);
  }
  const g = container.closest('[role=radiogroup], [role=group]');
  if (g) {
    const lb = g.getAttribute('aria-labelledby'); if (lb && byIds(lb)) return byIds(lb);
    const al = g.getAttribute('aria-label'); if (al) return clean(al);
  }
  let p = container.parentElement;
  for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
    const candidates = p.querySelectorAll('.application-label, legend, label, [class*="question"], [class*="label"], [class*="Label"], h3, h4');
    for (const l of candidates) {
      if (l.querySelector('input, select, textarea, button')) continue;
      if (members.some(m => l.contains(m) || (m.labels && [...m.labels].includes(l)))) continue;
      const t = textOf(l); if (t) return t;
    }
  }
  return '';
}

function isRequired(el, label) {
  if (el.required || el.getAttribute('aria-required') === 'true') return true;
  const holder = el.closest('fieldset, [role=radiogroup]');   // LinkedIn 2026: "Question*" stands just before the group
  if (holder && holder.previousElementSibling && /[*✱]\s*$/.test(textOf(holder.previousElementSibling))) return true;
  const item = el.closest('[role=listitem]');   // Google Forms marks required questions with a "Required question" star
  if (item && item.querySelector('[aria-label="Required question"]')) return true;
  if (/\*\s*$/.test(label || '') || /✱/.test(label || '') || /\(required\)/i.test(label || '')) return true;
  const box = el.closest('.application-question, [class*="field"], [class*="Field"], fieldset');
  return !!(box && /required/i.test(box.className || ''));
}

// Pick the form with the most fields, else the whole page. A given root (arguments[0]) limits the search to that element.
let root = arguments[0] || document;
if (!arguments[0]) {
  let best = 0;
  for (const form of document.querySelectorAll('form')) {
    const count = form.querySelectorAll('input:not([type=hidden]), select, textarea').length;
    if (count > best) { best = count; root = form; }
  }
  if (best < 2) root = document;
}
// Mark the application form so Submit / Next buttons are looked up inside it first (not a header search box)
document.querySelectorAll('[data-aap-form]').forEach(e => e.removeAttribute('data-aap-form'));
if (root !== document) root.setAttribute('data-aap-form', '1');

document.querySelectorAll('[' + MARK + ']').forEach(e => e.removeAttribute(MARK));
const fields = [];
const seenGroups = new Set();
let n = 0;

for (const el of root.querySelectorAll('input, select, textarea')) {
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || (tag === 'input' ? 'text' : tag)).toLowerCase();
  const isCombobox = el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list' || el.getAttribute('aria-haspopup') === 'listbox';
  if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type) || el.disabled) continue;
  if (type === 'search' && !isCombobox) continue;   // Site search boxes, but keep Ant Design dropdowns (<input type=search role=combobox>)

  if (type === 'radio' || type === 'checkbox') {
    const group = el.name ? [...root.querySelectorAll('input[type="' + type + '"][name="' + CSS.escape(el.name) + '"]')] : [el];
    const key = type + ':' + (el.name || n);
    if (seenGroups.has(key)) continue;
    seenGroups.add(key);
    if (!group.some(g => visible(g) || (g.labels && g.labels[0] && visible(g.labels[0])) || visible(g.parentElement))) continue;
    if (type === 'radio' && group.length > 1) {
      // A resume picker (LinkedIn Easy Apply: one radio per uploaded file "resume.pdf  10/20/2026"): not a question. Keep the chosen file, else the newest (first)
      let box = group[0].parentElement;
      while (box && !group.every(g => box.contains(g))) box = box.parentElement;
      const boxText = box ? (box.innerText || '') : '';
      if ((boxText.match(/\.(pdf|docx?)\b/gi) || []).length >= Math.min(group.length, 2) && /resume|\bcv\b|upload/i.test(boxText + ' ' + ((box && box.parentElement && box.parentElement.innerText) || '').slice(0, 400))) {
        if (!group.some(g => g.checked)) { try { group[0].click(); } catch (e) {} }
        continue;
      }
    }
    const id = String(n++);
    if (type === 'checkbox' && group.length === 1) {
      if (el.parentElement && [...el.parentElement.children].some(c => c.tagName === 'BUTTON' && /^(yes|no)$/i.test(textOf(c)))) continue;
      const label = labelFor(el);
      el.setAttribute(MARK, id);
      fields.push({aap: id, kind: 'checkbox', label: stripMarks(label), required: isRequired(el, label), options: [], value: el.checked ? 'checked' : '', name: el.name || '', id: el.id || '', autocomplete: ''});
      continue;
    }
    const options = group.map(optionText);
    group.forEach((g, i) => g.setAttribute(MARK, id + '-' + i));
    const label = groupLabel(el, group) || labelFor(el);
    const checked = group.filter(g => g.checked).map(optionText);
    fields.push({aap: id, kind: type === 'radio' ? 'radio' : 'checkbox_group', label: stripMarks(label), required: group.some(g => isRequired(g, label)), options, value: checked.join(', '), name: el.name || '', id: el.id || '', autocomplete: ''});
    continue;
  }

  if (type !== 'file' && !visible(el)) continue;
  if (type !== 'file' && el.getAttribute('aria-hidden') === 'true' && el.tabIndex === -1) continue;
  const id = String(n++);
  el.setAttribute(MARK, id);
  const label = labelFor(el);
  let kind = tag === 'textarea' ? 'textarea' : tag === 'select' ? 'select' : type;
  let value = el.value || '';
  let options = [];
  if (tag === 'select') {
    options = [...el.options].filter(o => o.value !== '' && !/^(select|choose|--|please select)/i.test(clean(o.text))).map(o => clean(o.text));
    value = el.value ? clean(el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '') : '';
    if (options.length && !options.includes(value)) value = '';
  } else if (isCombobox) {
    kind = 'combobox';
    const box = el.closest('[class*="control"], [class*="Control"], .ant-select') || (el.parentElement && el.parentElement.parentElement);
    const shown = box && box.querySelector('[class*="single-value"], [class*="singleValue"], [class*="multi-value"], [class*="multiValue"], .ant-select-selection-item');
    if (shown) value = textOf(shown);
  } else if (type === 'file') {
    value = el.files && el.files.length ? el.files[0].name : '';
    const box = el.closest('[class*="field"], [class*="Field"], .application-question, fieldset') || el.parentElement;
    if (!value && box && /\.(pdf|docx?|txt|rtf)\b/i.test(textOf(box))) value = 'uploaded';
  }
  fields.push({aap: id, kind, label: stripMarks(label), required: isRequired(el, label), options, value, name: el.name || el.getAttribute('formcontrolname') || '', id: el.id || '', autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(), placeholder: el.getAttribute('placeholder') || ''});
}

// Yes / No questions made of buttons instead of radio inputs (Ashby)
for (const box of root.querySelectorAll('div, span')) {
  const buttons = [...box.children].filter(c => c.tagName === 'BUTTON');
  if (buttons.length < 2 || buttons.length > 4 || !buttons.every(b => /^(yes|no)$/i.test(textOf(b)))) continue;
  if (!buttons.some(visible)) continue;
  const id = String(n++);
  buttons.forEach((b, i) => b.setAttribute(MARK, id + '-' + i));
  const pressed = buttons.filter(b => b.getAttribute('aria-pressed') === 'true' || /(active|selected|checked)/i.test(b.className || ''));
  const label = groupLabel(box, buttons);
  const input = box.parentElement && box.parentElement.querySelector('input');
  fields.push({aap: id, kind: 'button_choice', label: stripMarks(label), required: true, options: buttons.map(textOf), value: pressed.map(textOf).join(', '), name: '', id: '', autocomplete: ''});
}

// Widgets built from <div role=...> instead of real inputs (Google Forms)
const ariaLabel = el => { const lb = el.getAttribute('aria-labelledby'); return (lb && byIds(lb)) || clean(el.getAttribute('aria-label') || ''); };
const ariaOption = o => clean(o.getAttribute('data-value') || o.getAttribute('data-answer-value') || o.getAttribute('aria-label') || textOf(o));
const ariaRequired = (el, label) => el.getAttribute('aria-required') === 'true' || /\*/.test(label || '')
  || !!(el.closest('[role=listitem]') && el.closest('[role=listitem]').querySelector('[aria-label="Required question"]'));

// Dropdowns: <div role=listbox> with <div role=option data-value>. Skips the popup lists of searchable dropdowns (they have an owner).
for (const lb of root.querySelectorAll('[role=listbox]')) {
  if (lb.tagName === 'SELECT' || lb.hasAttribute(MARK) || !visible(lb)) continue;
  if (lb.id && document.querySelector('[aria-controls="' + CSS.escape(lb.id) + '"], [aria-owns="' + CSS.escape(lb.id) + '"]')) continue;
  const label = ariaLabel(lb) || groupLabel(lb, [lb]);
  if (!label) continue;
  const opts = [...lb.querySelectorAll('[role=option]')];
  const options = [...new Set(opts.map(ariaOption).filter(t => t && !/^(choose|select)$/i.test(t)))];
  if (!options.length) continue;
  const selected = opts.find(o => o.getAttribute('aria-selected') === 'true' && ariaOption(o) && !/^(choose|select)$/i.test(ariaOption(o)));
  const id = String(n++);
  lb.setAttribute(MARK, id);
  fields.push({aap: id, kind: 'aria_listbox', label: stripMarks(label), required: ariaRequired(lb, label), options, value: selected ? ariaOption(selected) : '', name: '', id: lb.id || '', autocomplete: ''});
}

// Radio groups: <div role=radiogroup> with <div role=radio>
for (const group of root.querySelectorAll('[role=radiogroup]')) {
  const radios = [...group.querySelectorAll('[role=radio]')].filter(r => r.tagName !== 'INPUT');
  if (!radios.length || !radios.some(visible)) continue;
  if (group.querySelector('input[type=radio]')) continue;   // Real radio inputs inside: read (or deliberately skipped, Eg: a resume picker) above
  const id = String(n++);
  radios.forEach((r, i) => r.setAttribute(MARK, id + '-' + i));
  const label = ariaLabel(group) || groupLabel(group, radios);
  const checked = radios.filter(r => r.getAttribute('aria-checked') === 'true').map(ariaOption);
  fields.push({aap: id, kind: 'aria_radio', label: stripMarks(label), required: ariaRequired(group, label), options: radios.map(ariaOption), value: checked.join(', '), name: '', id: '', autocomplete: ''});
}

// Checkboxes: <div role=checkbox>, grouped by the list they're in
const ariaGroups = new Map();
for (const box of root.querySelectorAll('[role=checkbox]')) {
  if (box.tagName === 'INPUT' || !visible(box)) continue;
  const container = box.closest('[role=list], [role=group]') || box.parentElement;
  if (!ariaGroups.has(container)) ariaGroups.set(container, []);
  ariaGroups.get(container).push(box);
}
for (const [container, boxes] of ariaGroups) {
  const id = String(n++);
  const label = ariaLabel(container) || groupLabel(container, boxes) || (boxes.length === 1 ? ariaOption(boxes[0]) : '');
  const checked = boxes.filter(b => b.getAttribute('aria-checked') === 'true').map(ariaOption);
  if (boxes.length === 1) {
    boxes[0].setAttribute(MARK, id);
    fields.push({aap: id, kind: 'checkbox', label: stripMarks(ariaOption(boxes[0]) || label), required: ariaRequired(container, label), options: [], value: checked.length ? 'checked' : '', name: '', id: '', autocomplete: ''});
    continue;
  }
  boxes.forEach((b, i) => b.setAttribute(MARK, id + '-' + i));
  fields.push({aap: id, kind: 'aria_checkbox_group', label: stripMarks(label), required: ariaRequired(container, label), options: boxes.map(ariaOption), value: checked.join(', '), name: '', id: '', autocomplete: ''});
}
return fields;
'''


_NAME_WORDS = {"fname": "first name", "firstname": "first name", "lname": "last name", "lastname": "last name", "mname": "middle name",
               "fullname": "full name", "mobile": "mobile number", "phone": "phone number", "tel": "phone number", "dob": "date of birth",
               "zip": "zip code", "zipcode": "zip code", "pincode": "pin code", "exp": "experience", "loc": "location", "emailid": "email"}
_NAME_NOISE = {"application", "applicant", "candidate", "input", "field", "fields", "form", "txt", "text", "answer", "value", "data",
               "standard", "question", "id", "ctl", "ctl00", "main", "the", "your"}


def readable_name(identifier: str) -> str:
    '''A label made from a field's name / id: "application_fname" -> "first name", "standardFields.locationPreference.answer" -> "location preference".'''
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', identifier or "")
    words = [word.lower() for word in re.split(r'[^A-Za-z0-9]+', spaced) if word]
    return " ".join(_NAME_WORDS.get(word, word) for word in words if word not in _NAME_NOISE and not word.isdigit() and len(word) > 1)


def _looks_like_identifier(label: str) -> bool:
    return bool(label) and " " not in label and bool(re.search(r'[_.]|[a-z][A-Z]', label))


def read_fields(driver: WebDriver, root: WebElement | None = None) -> list[dict]:
    '''Returns every visible field of the application form on the current page (only inside `root` if given).'''
    fields = driver.execute_script(_READ_FIELDS_JS, root) or []
    for field in fields:   # No visible label (only name="application_fname"): such fields were skipped, so required fields stayed empty
        label = field.get("label") or ""
        if (not label and not field.get("placeholder")) or label.lower() in ("text", "input", "field") or _looks_like_identifier(label):
            readable = readable_name(label if _looks_like_identifier(label) else (field.get("name") or field.get("id") or ""))
            if readable: field["label"] = readable
    return fields


def _element(driver: WebDriver, aap: str) -> WebElement:
    return driver.find_element(By.CSS_SELECTOR, f'[data-aap="{aap}"]')


def _click(driver: WebDriver, element: WebElement) -> None:
    '''Clicks an element, falling back to its label or a JavaScript click when a styled wrapper covers it.'''
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', element)
    try:
        element.click()
        return
    except Exception:
        pass
    element_id = element.get_attribute("id")
    if element_id:
        labels = driver.find_elements(By.CSS_SELECTOR, f'label[for="{element_id}"]')
        if labels:
            try:
                labels[0].click()
                return
            except Exception:
                pass
    driver.execute_script("arguments[0].click();", element)


_SET_VALUE_JS = r'''
const el = arguments[0], value = arguments[1];
const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;   // React / Vue only notice values set through the native setter
el.focus();
setter.call(el, value);
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
el.dispatchEvent(new Event('blur', {bubbles: true}));
return el.value;
'''


def focus_browser(driver: WebDriver) -> None:
    '''Brings the browser tab to the front. Popups take the focus away, and some websites then ignore what the bot types.'''
    try: driver.execute_cdp_cmd("Page.bringToFront", {})
    except Exception: pass
    try: driver.switch_to.window(driver.current_window_handle)
    except Exception: pass


def _digits(text: str) -> str:
    return re.sub(r'\D', '', text or "")


def _value_matches(value: str, text: str) -> bool:
    '''True if the box shows what was typed (allowing for phone masks like "+91 (917) 071-8677").'''
    value, text = (value or "").strip(), (text or "").strip()
    if not text: return True
    if value == text or text.lower()[:30] in value.lower(): return True
    digits = _digits(text)
    return len(digits) >= 6 and digits[-6:] in _digits(value)


def _type(element: WebElement, text: str, verify: bool = True) -> bool:
    '''
    Types `text` like a person, then checks it stuck. If the website ignored the keys, sets the value directly. Returns True if it stuck.
    `verify=False` for search boxes of dropdowns, where the typed text disappears once an option is picked.
    '''
    element.send_keys(Keys.CONTROL, "a")
    element.send_keys(Keys.DELETE)
    element.send_keys(text)
    if not verify: return True
    try:
        if _value_matches(element.get_attribute("value"), text): return True
        element.parent.execute_script(_SET_VALUE_JS, element, text)
        return _value_matches(element.get_attribute("value"), text)
    except Exception:
        return False


def _visible_options(driver: WebDriver) -> list[WebElement]:
    options = []
    # Ant Design draws visible options without role=option (its role=option copies are hidden, for screen readers)
    for option in driver.find_elements(By.CSS_SELECTOR, '[role="option"], .ant-select-item-option'):
        try:
            if option.is_displayed() and option.text.strip(): options.append(option)
        except Exception: pass
    return options


_SUGGESTION_SELECTORS = '[role="option"], .dropdown-location, .pac-item, [class*="suggestion"] li, [class*="autocomplete"] li, [class*="Suggestion"]'


def _visible_suggestions(driver: WebDriver) -> list[WebElement]:
    found = []
    for element in driver.find_elements(By.CSS_SELECTOR, _SUGGESTION_SELECTORS):
        try:
            if element.is_displayed() and element.text.strip(): found.append(element)
        except Exception: pass
    return found


def _type_location(driver: WebDriver, element: WebElement, answer: str) -> None:
    '''Location fields (Lever) clear what you type unless a suggestion is picked: types the city and picks the best suggestion.'''
    city = answer.split(",")[0].strip()
    country = answer.split(",")[-1].strip().lower() if "," in answer else ""
    _type(element, city, verify=False)
    sleep(2)
    suggestions = _visible_suggestions(driver)
    if not suggestions:
        _type(element, answer)
        return
    texts = [suggestion.text.strip().lower() for suggestion in suggestions]
    starts = [i for i, text in enumerate(texts) if text.startswith(city.lower())]
    in_country = [i for i in starts if country and (country in texts[i] or re.search(r'\b' + re.escape(country[:3]) + r'\b', texts[i]))]
    index = (in_country or starts or [0])[0]
    suggestions[index].click()


def _open_combobox(driver: WebDriver, element: WebElement) -> None:
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', element)
    control = driver.execute_script("return arguments[0].closest('[class*=\"control\"], [class*=\"Control\"], .ant-select-selector')", element)
    try:
        (control or element).click()
    except Exception:
        driver.execute_script("arguments[0].focus();", element)
        element.send_keys(Keys.ARROW_DOWN)
    sleep(1)
    if not _visible_options(driver):
        try:
            driver.execute_script("arguments[0].focus();", element)
            element.send_keys(Keys.ARROW_DOWN)
            sleep(1)
        except Exception: pass


def _is_checked(element: WebElement) -> bool:
    '''Works for real checkboxes and for <div role=checkbox> (Google Forms), which `is_selected()` always reports as unchecked.'''
    try:
        return element.is_selected() or element.get_attribute("aria-checked") == "true"
    except Exception:
        return False


def _pick_aria_listbox(driver: WebDriver, element: WebElement, answer: str) -> bool:
    '''Google Forms dropdown: click it, then click the option in the list that pops up.'''
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', element)
    element.click()
    sleep(1)
    for option in reversed(_visible_options(driver)):   # The popup copy of the options is rendered last
        value = option.get_attribute("data-value") or option.text.strip()
        if value == answer or option.text.strip() == answer:
            option.click()
            sleep(0.8)
            return True
    element.send_keys(Keys.ESCAPE)
    return False


def read_combobox_options(driver: WebDriver, field: dict, limit: int = 60) -> list[str]:
    '''Opens a searchable dropdown and returns its options (empty for dropdowns that only show options after typing).'''
    try:
        element = _element(driver, field["aap"])
        _open_combobox(driver, element)
        options = [option.text.strip() for option in _visible_options(driver)[:limit]]
        element.send_keys(Keys.ESCAPE)
        return options
    except Exception:
        return []


def fill_field(driver: WebDriver, field: dict, answer: str) -> bool:
    '''
    Puts `answer` into `field`. Returns `True` if it worked.
    * For radio, select, checkbox groups and button choices, `answer` must be one of the field's options (use `match_option` first).
    * For single checkboxes, any answer ticks it.
    * For file fields, `answer` is the file path.
    '''
    kind = field["kind"]
    try:
        if kind in ("radio", "button_choice", "aria_radio"):
            index = field["options"].index(answer)
            _click(driver, _element(driver, f'{field["aap"]}-{index}'))
            return True

        if kind in ("checkbox_group", "aria_checkbox_group"):
            wanted = [part.strip() for part in str(answer).split(",") if part.strip()]
            picked = [match_option(part, field["options"]) for part in wanted]
            for option in filter(None, picked):
                element = _element(driver, f'{field["aap"]}-{field["options"].index(option)}')
                if not _is_checked(element): _click(driver, element)
            return any(picked)

        element = _element(driver, field["aap"])

        if kind == "checkbox":
            if not _is_checked(element): _click(driver, element)
            return True

        if kind == "aria_listbox":
            return _pick_aria_listbox(driver, element, answer)

        if kind == "select":
            Select(element).select_by_visible_text(answer)
            return True

        if kind == "file":
            driver.execute_script("arguments[0].style.display='block'; arguments[0].style.visibility='visible';", element)
            element.send_keys(os.path.abspath(answer))
            return True

        if kind == "combobox":
            _open_combobox(driver, element)
            _type(element, answer, verify=False)
            sleep(1.5)
            options = _visible_options(driver)
            texts = [option.text.strip() for option in options]
            choice = match_option(answer, texts)
            if choice is None and len(options) >= 1 and texts[0].lower().startswith(answer.lower()[:4]): choice = texts[0]   # Location search results
            if choice is None:   # The typed text filtered the right option out (Eg: "Acknowledge/Confirm"): clear it and pick from the full list
                element.send_keys(Keys.CONTROL, "a")
                element.send_keys(Keys.BACKSPACE)
                sleep(1)
                if not _visible_options(driver): _open_combobox(driver, element)
                options = _visible_options(driver)
                texts = [option.text.strip() for option in options]
                choice = match_option(answer, texts)
            if choice is None:
                element.send_keys(Keys.ESCAPE)
                return False
            options[texts.index(choice)].click()
            return True

        # Text, email, tel, url, number, date, textarea
        if kind == "text" and re.search(r'\b(location|city)\b', field.get("label", ""), re.I):
            _type_location(driver, element, answer)
            return True
        return _type(element, answer)
    except Exception:
        return False


def visible_errors(driver: WebDriver) -> list[str]:
    '''Validation error messages currently shown on the page.'''
    script = r'''
    const out = [];
    for (const el of document.querySelectorAll('[class*="error"], [class*="Error"], [role="alert"], [aria-live="assertive"]')) {
      const s = getComputedStyle(el); const r = el.getBoundingClientRect();
      const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
      if (t && t.length < 200 && s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0 && !out.includes(t)) out.push(t);
    }
    return out.slice(0, 10);
    '''
    try: return driver.execute_script(script) or []
    except Exception: return []


def captcha_visible(driver: WebDriver) -> bool:
    '''True if a CAPTCHA the user must solve is on screen (not invisible background CAPTCHAs).'''
    script = r'''
    for (const f of document.querySelectorAll('iframe')) {
      const src = f.src || ''; const r = f.getBoundingClientRect(); const s = getComputedStyle(f);
      if (s.display === 'none' || s.visibility === 'hidden' || r.width < 50 || r.height < 50) continue;
      if (/recaptcha\/(api2|enterprise)\/(anchor|bframe)/.test(src) && !/size=invisible/.test(src)) return true;
      if (/hcaptcha\.com/.test(src) && r.height > 60) return true;
      if (/challenges\.cloudflare\.com/.test(src)) return true;
    }
    return false;
    '''
    try: return bool(driver.execute_script(script))
    except Exception: return False
