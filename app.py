"""
Medical Diagnosis Chat — Flask + Prolog (no API key needed)

Symptom extraction:  keyword rules (rule-based NLP)
Diagnosis decision:  SWI-Prolog production rules
Doctor responses:    templated strings

Run:
    python3 app.py
Then open http://localhost:8080
"""

import os
import json
import tempfile
import subprocess
import re

import yaml
from flask import Flask, request, jsonify, send_from_directory

from llm_extract import llm_extract_symptoms, llm_clarify, PROVIDER as LLM_PROVIDER
import doctor_intake

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))
YAML_PATH = os.path.join(BASE, 'diseases.yaml')

import generate_prolog
generate_prolog.generate()

CONFIG = ALL_DISEASES = SYMPTOM_ROUTING = SEVERITY = CATEGORY = None


def reload_config():
    """
    (Re)load diseases.yaml into the module-level globals every route reads
    from. Called at startup, and again right after a doctor confirms a new
    rule into the knowledge base — so a freshly-added disease is live
    immediately, with no server restart needed.
    """
    global CONFIG, ALL_DISEASES, SYMPTOM_ROUTING, SEVERITY, CATEGORY
    with open(YAML_PATH) as f:
        CONFIG = yaml.safe_load(f)

    ALL_DISEASES   = list(CONFIG['diseases'].keys())
    SYMPTOM_ROUTING = CONFIG['symptom_routing']

    # Per-fact clinical severity (1-5). Used only to rank and label reasons
    # when explaining a result — the confirmation threshold itself stays a
    # plain fact count (or a primary-symptom short-circuit), decided
    # entirely in Prolog.
    SEVERITY = {}
    for _ddata in CONFIG['diseases'].values():
        for _q in _ddata['questions']:
            SEVERITY[_q['fact']] = _q.get('severity', 3)

    # Broad category each disease belongs to — drives the first stage of
    # the reasoning chain (category, then specific disease within it), not
    # just a flat list of unrelated diseases. See diseases.yaml's
    # 'categories' block.
    CATEGORY = CONFIG.get('categories', {})


reload_config()

app = Flask(__name__, static_folder='static')


# ---------------------------------------------------------------------------
# Keyword-based symptom extraction  (no API needed)
# ---------------------------------------------------------------------------

SYMPTOM_KEYWORDS = {
    'fatigue':               ['tired', 'fatigue', 'exhausted', 'weak', 'weakness', 'lethargic', 'no energy'],
    'headache':              ['headache', 'head ache', 'head pain', 'migraine', 'head hurts'],
    'elevated_bp':           ['high blood pressure', 'high bp', 'elevated bp', 'hypertension', 'blood pressure high'],
    'elevated_glucose':      ['high blood sugar', 'high glucose', 'elevated glucose', 'blood sugar', 'sugar level'],
    'polyuria':              ['urinating a lot', 'pee a lot', 'urinate often', 'frequent urination', 'urinating more'],
    'polydipsia':            ['very thirsty', 'always thirsty', 'excessive thirst', 'drinking a lot of water'],
    'pale_skin':             ['pale', 'pale skin', 'pallor', 'skin looks pale', 'look pale'],
    'dizziness':             ['dizzy', 'dizziness', 'lightheaded', 'light headed', 'spinning'],
    'dysuria':               ['burning when i urinate', 'burning urination', 'pain urinating', 'painful urination',
                              'burning pee', 'stinging urination'],
    'urinary_frequency':     ['urinate frequently', 'frequent urination', 'bathroom often', 'pee often', 'need to urinate'],
    'cough':                 ['cough', 'coughing'],
    'shortness_of_breath':   ['short of breath', 'shortness of breath', 'breathless', 'hard to breathe',
                              'difficulty breathing', 'out of breath'],
    'fever':                 ['fever', 'high temperature', 'high temp', 'temperature', 'running a fever'],
    'night_sweats':          ['night sweats', 'sweating at night', 'sweat at night', 'wake up sweating'],
    'weight_loss':           ['lost weight', 'weight loss', 'losing weight', 'dropped weight'],
    'nausea':                ['nausea', 'nauseous', 'feel sick', 'queasy', 'want to vomit'],
    'chest_pain':            ['chest pain', 'chest hurts', 'chest ache', 'pain in chest'],
    'persistent_cough':      ['cough for weeks', 'weeks of coughing', 'long cough', 'cough that wont go away'],
    'chronic_cough':         ['cough at night', 'cough worse at night', 'night cough', 'recurring cough'],
    'wheezing':              ['wheeze', 'wheezing', 'whistling breath', 'whistling sound breathing'],
}

YES_WORDS = ['yes', 'yeah', 'yep', 'yup', 'correct', 'right', 'sure', 'absolutely',
             'definitely', 'i do', 'i have', 'that is right', "that's right", 'indeed',
             'true', 'exactly', 'positive', 'affirmative', 'of course']

# Hedged answers — hint at "yes" but are not an unconditional one. Classified
# as 'unsure' (see detect_yes_no), never silently upgraded to a full "yes":
# "sometimes" thirsty is not the same claim as "thirsty most of the time",
# and "sometimes" isn't even a coherent answer to a yes/no history question
# like "have you ever been told you have high blood pressure?".
PARTIAL_YES = ['sometimes', 'a bit', 'little', 'kind of', 'sort of', 'slightly',
               'occasionally', 'at times', 'now and then', 'mild', 'mildly',
               'somewhat', 'i think so', 'maybe yes', 'probably']

NO_WORDS = ['no', 'nope', 'nah', 'not really', "don't", 'dont', 'never', 'negative',
            'i do not', "i don't", 'i have not', "i haven't", 'false', 'incorrect',
            'not at all', 'absolutely not']

# These mean "I don't know" — should NOT count as no
UNSURE_PATTERNS = ['not sure', "don't know", 'dont know', 'no test', 'not tested',
                   "haven't tested", 'not taken', 'unknown', 'no idea', 'unsure',
                   'not checked', 'never checked', 'no result', 'yet to']


def extract_symptoms(text):
    """Return list of symptom atoms found in free text via keyword matching."""
    tl = text.lower()
    found = []
    for fact, keywords in SYMPTOM_KEYWORDS.items():
        for kw in keywords:
            if kw in tl:
                found.append(fact)
                break
    return found


def extract_symptoms_smart(text):
    """
    Prefer LLM-based extraction (paraphrase-robust, see llm_extract.py) when
    LLM_PROVIDER is configured; fall back to the keyword lexicon whenever the
    LLM is disabled, unreachable, or returns nothing usable. The fallback
    means the app always runs, with or without an API key configured.
    """
    if LLM_PROVIDER != 'none':
        result = llm_extract_symptoms(text)
        if result is not None:
            return result
    return extract_symptoms(text)


def detect_yes_no(text):
    """
    Return 'yes', 'no', 'unsure', or 'unrecognized'.
    Priority: unsure-patterns first, then partial-yes, then yes/no keywords.
    'no test taken yet' → unsure (not no)
    'sometimes' / 'a little' → unsure, NOT yes. A hedge like "sometimes" is
    not the same claim as the question it answers ("...most of the time?",
    "have you ever been told...?", "are you currently on...?") and should
    never silently count as full confirmation — doing so overstates what
    the patient actually said and can produce a screening result built on
    answers the patient never gave.
    Anything that doesn't match any known pattern → 'unrecognized', so the
    caller can re-ask instead of silently treating gibberish as an answer.
    """
    tl = text.lower().strip()

    # Explicit "I don't know / not tested" → unsure, never count as no
    if any(p in tl for p in UNSURE_PATTERNS):
        return 'unsure'

    # Hedged / partial answers → unsure, never an unconditional yes
    if any(w in tl for w in PARTIAL_YES):
        return 'unsure'

    if any(w in tl for w in YES_WORDS):
        return 'yes'
    if any(w in tl for w in NO_WORDS):
        return 'no'
    return 'unrecognized'


def disease_order_for(confirmed_facts):
    # Pick the symptom with the most specific (shortest) routing list.
    # Only investigate diseases that are medically related to what the patient said.
    # Never append unrelated diseases — a headache patient should never be asked about UTI.
    best_route = None
    best_len   = 999
    for fact in confirmed_facts:
        if fact in SYMPTOM_ROUTING:
            route = SYMPTOM_ROUTING[fact]
            if len(route) < best_len:
                best_len   = len(route)
                best_route = route
    return best_route if best_route else ALL_DISEASES


# ---------------------------------------------------------------------------
# Prolog bridge
# ---------------------------------------------------------------------------

# Prolog wants forward slashes in quoted paths even on Windows;
# BASE comes from os.path and would otherwise contain backslashes there.
BASE_POSIX = BASE.replace(os.sep, '/')

PROLOG_LOADER = f"""
:- dynamic fact/1, asked/1.
:- use_module(library(lists)).
:- consult('{BASE_POSIX}/generated/facts.pl').
:- consult('{BASE_POSIX}/generated/diseases.pl').
:- consult('{BASE_POSIX}/generated/rules.pl').
:- consult('{BASE_POSIX}/web_engine.pl').
"""


def run_prolog(facts, asked, disease_order):
    fact_lines  = ''.join(f':- assertz(fact({f})).\n'  for f in facts)
    asked_lines = ''.join(f':- assertz(asked({a})).\n' for a in asked)
    dl = '[' + ', '.join(disease_order) + ']'

    script = (PROLOG_LOADER + fact_lines + asked_lines
              + f':- web_run({dl}).\n:- halt.\n')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pl',
                                     delete=False, dir=tempfile.gettempdir()) as tf:
        tf.write(script)
        tf_path = tf.name

    try:
        result = subprocess.run(
            ['swipl', '-q', '-s', tf_path],
            capture_output=True, text=True, timeout=15
        )
        line = result.stdout.splitlines()[0].strip() if result.stdout.strip() else ''
    except subprocess.TimeoutExpired:
        return {'type': 'error', 'detail': 'Prolog timed out'}
    finally:
        os.unlink(tf_path)

    if not line:
        return {'type': 'error', 'detail': result.stderr[:300]}

    parts = line.split('\t')
    tag   = parts[0]

    if tag == 'DIAGNOSED' and len(parts) >= 5:
        matched = [m for m in parts[2].split(',') if m]
        # Rank matched facts by clinical severity (most important first) —
        # this drives both the reasons list below and the "why" panel.
        matched_ranked = sorted(matched, key=lambda f: -SEVERITY.get(f, 3))
        # 'primary' = one hallmark symptom alone was enough to confirm;
        # 'threshold' = the plain fact-count reached the disease's
        # threshold instead. Defaults to 'threshold' for older Prolog
        # output that doesn't carry the field.
        reason = parts[5] if len(parts) >= 6 else 'threshold'
        return {'type': 'diagnosed', 'disease': parts[1],
                'matched': matched_ranked, 'count': int(parts[3]), 'threshold': int(parts[4]),
                'severities': {f: SEVERITY.get(f, 3) for f in matched},
                'reason': reason}
    if tag == 'NEED_ANSWER' and len(parts) >= 3:
        return {'type': 'need_answer', 'question': parts[1], 'fact': parts[2]}
    if tag == 'NO_DIAGNOSIS':
        return {'type': 'no_diagnosis'}

    return {'type': 'error', 'detail': line}


# ---------------------------------------------------------------------------
# Templated doctor responses  (no API needed)
# ---------------------------------------------------------------------------

WELCOME = (
    "Hello! I'm glad you came in today. I'm here to help figure out "
    "what might be going on with your health.\n\n"
    "Can you tell me what has been bothering you the most lately? "
    "Feel free to describe your symptoms in your own words."
)

# Stage-one message: announced once, the first time investigation enters a
# given category, before any disease-specific question in it. This is what
# makes the chain visible as "category, then disease" rather than a flat
# list — e.g. a cough is first framed as a respiratory-system question,
# and only then narrowed to asthma vs. tuberculosis specifically.
CATEGORY_INTRO = {
    'metabolic':      "Based on what you've described, let's start by looking into possible metabolic causes.",
    'cardiovascular': "Let's start by looking into your cardiovascular system.",
    'hematologic':    "Let's start by checking for signs related to your blood count.",
    'urinary':        "Let's start by looking into your urinary system.",
    'respiratory':    "Let's start by looking into your respiratory system.",
}

DISEASE_INTRO = {
    'diabetes':     "I see. Let me ask you a few questions about your blood sugar levels and some related symptoms.",
    'hypertension': "Let me check a few things related to your blood pressure.",
    'anemia':       "Alright. I'd like to ask some questions about possible signs of low blood count.",
    'uti':          "Okay. I would like to ask you about your urinary symptoms.",
    'asthma':       "Given what you've mentioned, let me check whether this could be related to your airways.",
    'tuberculosis': "I want to rule out one more thing that can cause persistent respiratory symptoms.",
}

RULED_OUT = {
    'diabetes':     "Your answers don't strongly suggest diabetes. Let me check something else.",
    'hypertension': "This doesn't point clearly to high blood pressure. Let me look at another possibility.",
    'anemia':       "The picture doesn't clearly suggest anemia.",
    'uti':          "This doesn't look like a urinary tract infection.",
    'asthma':       "Asthma seems less likely based on your answers. Let me check one more related condition.",
    'tuberculosis': "Your answers don't strongly point to tuberculosis. Please do get a chest X-ray to be safe.",
}

# Confident, disease-specific reason for each confirmed fact — used to explain
# a diagnosis in direct clinical terms rather than restating the raw fact name.
FACT_REASON = {
    # diabetes
    'elevated_glucose':        "Your blood glucose has been confirmed high, the direct marker of diabetes.",
    'high_hba1c':               "A blood test has confirmed high HbA1c, showing sustained high blood sugar.",
    'polyuria':                  "You are urinating far more than normal — a direct result of excess glucose in the urine.",
    'polydipsia':                "You are experiencing extreme thirst — the body's direct response to fluid loss from polyuria.",
    'fatigue':                   "You are experiencing persistent fatigue, caused by cells not getting the glucose they need.",
    # hypertension
    'history_of_hypertension':  "You have already been diagnosed with high blood pressure in the past.",
    'on_bp_medication':          "You are currently on blood pressure medication, confirming an existing hypertension diagnosis.",
    'elevated_bp':               "Your blood pressure readings have been confirmed high.",
    'hypertension_headache':    "You have frequent morning headaches, a direct symptom of elevated blood pressure overnight.",
    # anemia
    'pale_skin':                 "Your skin has been noticeably pale, a direct sign of reduced red blood cell count.",
    'dizziness':                 "You feel dizzy on standing, caused by reduced oxygen delivery from low red blood cells.",
    # uti
    'dysuria':                   "You have pain or burning during urination, the hallmark symptom of a urinary tract infection.",
    'urinary_frequency':        "You need to urinate far more often than usual, consistent with bladder irritation from infection.",
    'urinary_urgency':          "You get sudden, hard-to-control urges to urinate, a direct sign of bladder inflammation.",
    'suprapubic_pain':          "You feel pressure or pain in your lower abdomen, directly over the bladder.",
    # asthma
    'chronic_cough':             "You have a recurring cough that worsens at night, a hallmark pattern of asthma.",
    'chest_tightness':           "You feel tightness or pressure in your chest from narrowed airways.",
    'wheezing':                  "You wheeze when you breathe, caused by air moving through constricted airways.",
    'exercise_triggered':        "Cold air or exercise makes your breathing worse, a direct trigger for asthmatic airways.",
    # tuberculosis
    'persistent_cough':          "You have had a cough lasting more than three weeks, the defining symptom of tuberculosis.",
    'coughing_blood':            "You are coughing up blood or blood-stained mucus, a direct sign of lung tissue damage.",
    'night_sweats':               "You have heavy night sweats, a hallmark systemic sign of active tuberculosis infection.",
    'unexplained_weight_loss':  "You have lost weight without trying, consistent with the body fighting a chronic infection.",
    'tb_exposure':                "You have had close contact with someone who had TB, a confirmed exposure route.",
}


def doctor_response_for(prolog_result, session):
    rtype = prolog_result['type']

    if rtype == 'need_answer':
        question   = prolog_result['question']
        fact       = prolog_result['fact']
        last_ruled = session.get('last_ruled')
        last_intro = session.get('last_intro')

        parts = []

        # Work out which disease this question belongs to
        for dname, ddata in CONFIG['diseases'].items():
            q_facts = [q['fact'] for q in ddata['questions']]
            if fact in q_facts:
                if dname != last_intro:
                    if last_ruled:
                        parts.append(RULED_OUT.get(last_ruled, ''))
                    # Stage one: announce the category only the first time
                    # we enter it, before stage two's disease-specific intro.
                    category = CATEGORY.get(dname)
                    if category and category != session.get('last_category'):
                        parts.append(CATEGORY_INTRO.get(category, ''))
                        session['last_category'] = category
                    parts.append(DISEASE_INTRO.get(dname, ''))
                    session['last_intro']  = dname
                    session['last_ruled']  = None
                break

        parts.append(question)
        return '\n\n'.join(p for p in parts if p)

    if rtype == 'diagnosed':
        disease  = prolog_result['disease']
        matched  = prolog_result['matched']

        # Show the reasons behind this screening result — never call it a
        # "diagnosis" or say a disease was "confirmed": this is a screening
        # tool, not a diagnostic one. `matched` already arrives ranked most
        # clinically significant first (see run_prolog); show the top few,
        # each labeled with its severity so the ranking is visible, not
        # just implied by order.
        severities = prolog_result.get('severities', {})
        reasons = [
            (FACT_REASON.get(f, f"You reported: {f.replace('_', ' ')}."), severities.get(f, 3))
            for f in matched
        ][:4]
        reasons_block = '\n'.join(
            f"{i+1}. {r} *(severity {sev}/5)*" for i, (r, sev) in enumerate(reasons)
        )

        # A 'primary' result means one hallmark symptom was decisive on its
        # own — say so plainly, rather than implying a tally of facts was
        # what tipped it, which is what 'threshold' results actually are.
        if prolog_result.get('reason') == 'primary':
            lead = (
                f"Thank you for answering that.\n\n"
                f"One of your answers is a key finding on its own — that's "
                f"enough by itself to point to **{disease.upper()}**:"
            )
        else:
            lead = (
                f"Thank you for your patience with all those questions.\n\n"
                f"This screening points to **{disease.upper()}**. Here are the reasons:"
            )

        return (
            f"{lead}\n\n"
            f"{reasons_block}\n\n"
            f"⚠️ This result is based only on the symptoms you reported in this chat. "
            f"Please follow up with a specialist and run proper lab tests to confirm it clinically."
        )

    if rtype == 'no_diagnosis':
        return (
            "I have checked everything that your symptoms could reasonably point to, "
            "and I wasn't able to confirm a specific condition based on your answers today.\n\n"
            "That doesn't mean nothing is wrong — some conditions only show up in a physical "
            "exam or blood tests. Please book an appointment at a clinic soon."
        )

    return f"Something went wrong with the reasoning engine. ({prolog_result.get('detail', '')})"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/start', methods=['POST'])
def start():
    session = {
        'facts':        [],
        'asked':        [],
        'disease_order': ALL_DISEASES,
        'pending_fact': None,
        'pending_question': None,
        'order_set':    False,
        'last_intro':   None,
        'last_ruled':   None,
        'last_category': None,
        'done':         False,
    }
    return jsonify({'message': WELCOME, 'session': session})


@app.route('/chat', methods=['POST'])
def chat():
    body         = request.json
    user_message = body['message']
    session      = body['session']

    facts        = session['facts']
    asked        = session['asked']
    disease_order = session['disease_order']
    pending_fact  = session.get('pending_fact')
    pending_question = session.get('pending_question')

    # --- Handle answer to the current pending question ---
    if pending_fact:
        answer = detect_yes_no(user_message)

        if answer == 'unrecognized':
            # Don't record anything or advance. If the patient appears to be
            # asking a genuine clarifying question (e.g. "what is HbA1c"),
            # try answering it via the configured LLM before falling back to
            # the generic re-prompt — this never bypasses the pending
            # question, it only optionally explains it first.
            clarification = None
            if LLM_PROVIDER != 'none':
                clarification = llm_clarify(user_message, pending_question)

            if clarification:
                reply = f"{clarification}\n\n{pending_question or ''}".strip()
            else:
                reply = (
                    "Sorry, I didn't quite catch that. Could you answer with "
                    "a simple yes or no?\n\n" + (pending_question or '')
                ).strip()

            return jsonify({
                'message': reply,
                'session': session,
                'debug': {'facts': facts, 'asked': asked}
            })

        if answer == 'yes' and pending_fact not in facts:
            facts.append(pending_fact)
        if pending_fact not in asked:
            asked.append(pending_fact)
        session['pending_fact'] = None
        session['pending_question'] = None

    # --- Also extract any freely mentioned symptoms ---
    for sym in extract_symptoms_smart(user_message):
        if sym not in facts:
            facts.append(sym)
        if sym not in asked:
            asked.append(sym)

    # --- Safe abstention: nothing has been recognized and no question has
    # been asked yet. Do NOT silently default to checking every disease
    # starting with whichever happens to be first in the catalog (that
    # produces a confident but unsupported result — see the paper's
    # evaluation of this exact failure mode). Ask for a clearer symptom
    # description instead, and keep asking until one is recognized. ---
    if not facts and not asked:
        return jsonify({
            'message': (
                "I want to make sure I ask about the right thing — could you "
                "describe the main symptom that's bothering you? For example: "
                "fatigue, headache, cough, or frequent urination."
            ),
            'session': session,
            'debug': {'facts': facts, 'asked': asked}
        })

    # --- Set disease order once we know the first symptom ---
    if not session['order_set'] and facts:
        disease_order = disease_order_for(facts)
        session['disease_order'] = disease_order
        session['order_set'] = True

    # --- Run Prolog ---
    result = run_prolog(facts, asked, disease_order)

    # Track which disease was ruled out (for transition messages)
    if result['type'] == 'need_answer':
        fact = result['fact']
        for dname, ddata in CONFIG['diseases'].items():
            if fact in [q['fact'] for q in ddata['questions']]:
                if dname != session.get('last_intro'):
                    session['last_ruled'] = session.get('last_intro')
                break
        session['pending_fact'] = result['fact']
        session['pending_question'] = result['question']

    if result['type'] in ('diagnosed', 'no_diagnosis'):
        session['done'] = True

    session['facts'] = facts
    session['asked'] = asked

    response = doctor_response_for(result, session)

    return jsonify({
        'message': response,
        'session': session,
        'debug':   {'prolog': result, 'facts': facts, 'asked': asked}
    })


# ---------------------------------------------------------------------------
# Doctor-side knowledge acquisition ("Rule Intake") — the real backend
# behind the interface, previously a prototype only. See doctor_intake.py.
# ---------------------------------------------------------------------------

@app.route('/doctor')
def doctor_page():
    return send_from_directory('static', 'doctor.html')


@app.route('/doctor/start', methods=['POST'])
def doctor_start():
    session = doctor_intake.new_session()
    return jsonify({'message': doctor_intake.start_message(), 'session': session})


@app.route('/doctor/chat', methods=['POST'])
def doctor_chat():
    body = request.json
    user_message = body['message']
    session = body['session']

    reply, session, draft = doctor_intake.step(session, user_message)
    return jsonify({'message': reply, 'session': session, 'draft': draft})


@app.route('/doctor/confirm', methods=['POST'])
def doctor_confirm():
    body = request.json
    draft = body['draft']
    try:
        doctor_intake.commit_draft(draft, YAML_PATH)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Could not save: {e}'}), 500

    # Make the new disease live immediately, no restart needed.
    reload_config()

    return jsonify({
        'ok': True,
        'message': f"Added to the knowledge base — \"{draft['name']}\" is now "
                    f"part of live screening, effective immediately.",
        'diseases': ALL_DISEASES,
    })


@app.route('/doctor/discard', methods=['POST'])
def doctor_discard():
    # Nothing was ever written — discarding just means the client throws
    # the draft away and starts a new /doctor/start session.
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print('\nStarting Medical Diagnosis Chat at http://localhost:8080\n')
    print('Doctor knowledge-acquisition interface: http://localhost:8080/doctor\n')
    app.run(debug=False, port=8080)
