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
    local       -> a locally hosted model served by Ollama (http://localhost:11434),
                   no API key required (default model: llama3.2:1b)
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
  increased_hunger      - hungrier than usual, even after eating
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
    'polydipsia', 'increased_hunger', 'pale_skin', 'dizziness', 'dysuria',
    'urinary_frequency', 'cough', 'shortness_of_breath', 'fever',
    'night_sweats', 'weight_loss', 'nausea', 'chest_pain', 'persistent_cough',
    'chronic_cough', 'wheezing',
}
# This must stay in sync with SYMPTOM_KEYWORDS' key set in app.py — both
# are the same free-text recognition vocabulary, just two different ways
# of populating it (deterministic keywords vs. the LLM). Facts that only
# ever get confirmed via an explicit yes/no follow-up question (e.g.
# chest_tightness, high_hba1c) are deliberately excluded from both.


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


def _call_local(prompt):
    # Ollama's /api/generate is a local HTTP endpoint — no API key, no
    # network egress. Requires `ollama serve` running and the model pulled
    # (e.g. `ollama pull llama3.2:1b`); if Ollama isn't reachable, this
    # raises URLError like any other provider and the caller degrades to
    # the keyword lexicon exactly as it would for a failed API call.
    model = os.environ.get('LLM_MODEL', 'llama3.2:1b')
    host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    data = _post_json(
        f'{host}/api/generate',
        {},
        {'model': model, 'prompt': prompt, 'stream': False},
    )
    return data['response']


_PROVIDERS = {
    'anthropic': _call_anthropic,
    'openai': _call_openai,
    'deepseek': _call_deepseek,
    'local': _call_local,
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

A genuine clarifying question explicitly asks what a medical term means or \
why it's being asked — for example "what is HbA1c" or "why does that matter". \
Only in that case, answer clearly and briefly in plain, reassuring language a \
patient would understand — 2 to 4 sentences. Do not diagnose them or suggest \
what their answer should be. The original question will automatically be \
shown again right after your reply, so do NOT repeat or rephrase the \
question yourself — just answer what they asked, and stop.

In every other case — including a typo, a vague or partial attempt to \
answer (e.g. "past few weeks", "kind of", "maybe"), gibberish, or anything \
off-topic — this is NOT a clarifying question, even if it's unclear what \
the patient meant. Do not try to interpret it, explain any words in it, or \
guess what they meant. In every one of these cases, respond with exactly \
the following and nothing else: NOT_A_QUESTION

Examples:
  Question was "Do you have a cough?" Patient wrote "past few weeks" ->
  NOT_A_QUESTION (this is a vague attempt to answer, not a question)
  Patient wrote "what does that mean" -> genuine clarifying question, answer it
  Patient wrote "asdkfj" -> NOT_A_QUESTION

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
        # Case-insensitive and tolerant of minor punctuation the model
        # might add — smaller/local models don't always reproduce an exact
        # literal like "NOT_A_QUESTION" verbatim (e.g. "Not_a_question."),
        # and treating a near-miss as a real clarification would show the
        # patient garbage instead of falling back cleanly.
        if not raw or raw.upper().lstrip('.').startswith('NOT_A_QUESTION'):
            return None
        # Despite the prompt instructing it not to, some models (especially
        # smaller/local ones) still restate the original question at the
        # end of their reply. Since the caller always appends
        # pending_question itself right after this return value, an
        # unstripped restatement would show the patient the same question
        # twice in a row. Strip an exact trailing repeat defensively,
        # rather than relying on every model to follow the instruction.
        pq = (pending_question or '').strip().rstrip('?').strip().lower()
        if pq:
            raw_stripped = raw.rstrip()
            tail = raw_stripped.rstrip('"').rstrip().rstrip('?').strip().lower()
            if tail.endswith(pq):
                cut = len(tail) - len(pq)
                raw_stripped = raw_stripped[:cut].rstrip(' "\n')
                raw = raw_stripped.rstrip('.,:;-—').strip() or raw
        return raw
    except (urllib.error.URLError, KeyError, IndexError, TimeoutError, ValueError):
        return None
