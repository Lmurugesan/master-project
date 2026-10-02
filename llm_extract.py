"""
Optional LLM-based symptom extraction.

The keyword lexicon in app.py is a closed, exact-substring matcher: it is
perfectly accurate on phrasing it was authored for, and fails on natural
paraphrases of the same complaint (see the paper's evaluation section).
This module lets a large language model do the same job — mapping a
patient's free-text opening statement to the same fixed vocabulary of
symptom atoms the Prolog rules already know about — without letting the
model invent a symptom outside that vocabulary or bypass the deterministic
reasoning engine in any way. The LLM only ever proposes candidate atoms
from a closed list; every downstream decision (routing, thresholds,
confirmation) is still made entirely by the unmodified Prolog engine.

Supported providers (set LLM_PROVIDER to one of these):
    anthropic   -> Claude, via ANTHROPIC_API_KEY   (default model: claude-3-5-haiku-latest)
    openai      -> GPT,    via OPENAI_API_KEY       (default model: gpt-4o-mini)
    deepseek    -> DeepSeek, via DEEPSEEK_API_KEY    (default model: deepseek-chat)
    none        -> disabled; always falls back to the keyword lexicon

If LLM_PROVIDER is unset, no key is present, the network call fails, or the
response can't be parsed, callers should fall back to the keyword lexicon —
this module never raises out to the caller; it returns None on any failure
so app.py can degrade gracefully rather than breaking the chat.

No third-party HTTP library is required; only the standard library is used,
so this file adds no new pip dependency to requirements.txt.
"""

import json
import os
import urllib.request
import urllib.error

PROVIDER = os.environ.get('LLM_PROVIDER', 'none').lower()
TIMEOUT_SECONDS = 8

PROMPT_TEMPLATE = """You are a clinical symptom-recognition assistant. Your ONLY \
job is to identify which of the following exact symptom codes are mentioned \
or clearly implied in the patient's statement. Do not diagnose. Do not invent \
a code that isn't in this list. If the patient explicitly denies a symptom \
("I do NOT have a cough"), do not include it.

Symptom codes and what they mean:
  fatigue              - unusual tiredness, exhaustion, weakness, low energy
  headache              - head pain, migraine
  elevated_bp          - known/reported high blood pressure
  elevated_glucose     - known/reported high blood sugar or glucose
  polyuria              - urinating much more than usual
  polydipsia            - excessive/unusual thirst
  pale_skin             - skin looking unusually pale
  dizziness             - dizziness, lightheadedness
  dysuria                - pain or burning during urination
  urinary_frequency    - needing to urinate much more often than usual
  cough                  - a cough of any kind
  shortness_of_breath  - breathlessness, difficulty breathing
  fever                  - fever, high temperature
  night_sweats          - heavy sweating at night
  weight_loss            - unexplained/unintentional weight loss
  nausea                 - nausea, feeling sick, queasiness
  chest_pain             - chest pain or discomfort
  persistent_cough      - a cough lasting more than about three weeks
  chronic_cough          - a recurring cough, worse at night
  wheezing                - wheezing or a whistling sound when breathing

Patient statement: "{text}"

Respond with ONLY a JSON array of matching symptom codes from the list \
above, nothing else. Example: ["fatigue", "dizziness"]. If none match, \
respond with []."""

VALID_CODES = {
    'fatigue', 'headache', 'elevated_bp', 'elevated_glucose', 'polyuria',
    'polydipsia', 'pale_skin', 'dizziness', 'dysuria', 'urinary_frequency',
    'cough', 'shortness_of_breath', 'fever', 'night_sweats', 'weight_loss',
    'nausea', 'chest_pain', 'persistent_cough', 'chronic_cough', 'wheezing',
}


def _post_json(url, headers, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={**headers, 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())


def _extract_json_array(text):
    start = text.find('[')
    end = text.rfind(']')
    if start == -1 or end == -1 or end < start:
        return None
    try:
        codes = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(codes, list):
        return None
    return [c for c in codes if isinstance(c, str) and c in VALID_CODES]


def _call_anthropic(prompt):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        return None
    model = os.environ.get('LLM_MODEL', 'claude-3-5-haiku-latest')
    data = _post_json(
        'https://api.anthropic.com/v1/messages',
        {'x-api-key': key, 'anthropic-version': '2023-06-01'},
        {'model': model, 'max_tokens': 200,
         'messages': [{'role': 'user', 'content': prompt}]},
    )
    return data['content'][0]['text']


def _call_openai(prompt):
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return None
    model = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
    data = _post_json(
        'https://api.openai.com/v1/chat/completions',
        {'Authorization': f'Bearer {key}'},
        {'model': model, 'max_tokens': 200,
         'messages': [{'role': 'user', 'content': prompt}]},
    )
    return data['choices'][0]['message']['content']


def _call_deepseek(prompt):
    # DeepSeek's Chat Completions API is OpenAI-compatible.
    # https://api-docs.deepseek.com/
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        return None
    model = os.environ.get('LLM_MODEL', 'deepseek-chat')
    data = _post_json(
        'https://api.deepseek.com/chat/completions',
        {'Authorization': f'Bearer {key}'},
        {'model': model, 'max_tokens': 200,
         'messages': [{'role': 'user', 'content': prompt}]},
    )
    return data['choices'][0]['message']['content']


_PROVIDERS = {
    'anthropic': _call_anthropic,
    'openai': _call_openai,
    'deepseek': _call_deepseek,
}


def llm_extract_symptoms(text):
    """
    Return a list of symptom codes the configured LLM provider recognizes
    in `text`, or None if extraction is disabled/unavailable/failed —
    callers should fall back to the keyword lexicon on None.
    """
    call = _PROVIDERS.get(PROVIDER)
    if call is None:
        return None
    try:
        raw = call(PROMPT_TEMPLATE.format(text=text.replace('"', "'")))
        if raw is None:
            return None
        return _extract_json_array(raw)
    except (urllib.error.URLError, KeyError, IndexError, TimeoutError, ValueError):
        return None


CLARIFY_PROMPT_TEMPLATE = """You are a medical screening assistant. A patient \
was just asked this yes/no screening question:

"{question}"

Instead of answering yes or no, they wrote:

"{message}"

If this is a genuine question asking what a term means, or why the question \
is being asked, answer it clearly and briefly in plain, reassuring language a \
patient would understand — 2 to 4 sentences. Do not diagnose them or suggest \
what their answer should be. End your reply by naturally leading back into \
the original question so the patient knows to answer it.

If the patient's message is NOT a genuine clarifying question — for example, \
if it is gibberish, off-topic, or an unrecognized attempt to answer — respond \
with exactly: NOT_A_QUESTION

Respond with ONLY your reply text, or exactly NOT_A_QUESTION."""


def llm_clarify(message, pending_question):
    """
    If `message` looks like a genuine clarifying question about
    `pending_question` (e.g. "what is HbA1c"), return a short plain-language
    answer from the configured LLM provider that leads back into the
    original question. Returns None if disabled, not applicable, or the call
    fails for any reason — callers should fall back to the generic
    "I didn't quite catch that" re-prompt on None, exactly as they already
    do for llm_extract_symptoms.
    """
    call = _PROVIDERS.get(PROVIDER)
    if call is None:
        return None
    try:
        prompt = CLARIFY_PROMPT_TEMPLATE.format(
            question=pending_question or '',
            message=message.replace('"', "'"),
        )
        raw = call(prompt)
        if raw is None:
            return None
        raw = raw.strip()
        if not raw or raw.startswith('NOT_A_QUESTION'):
            return None
        return raw
    except (urllib.error.URLError, KeyError, IndexError, TimeoutError, ValueError):
        return None
