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

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))

import generate_prolog
generate_prolog.generate()

with open(os.path.join(BASE, 'diseases.yaml')) as f:
    CONFIG = yaml.safe_load(f)

ALL_DISEASES   = list(CONFIG['diseases'].keys())
SYMPTOM_ROUTING = CONFIG['symptom_routing']

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
NO_WORDS  = ['no', 'nope', 'nah', 'not really', "don't", 'dont', 'never', 'negative',
             'i do not', 'i don\'t', 'i have not', "i haven't", 'false', 'incorrect']


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


def detect_yes_no(text):
    """Return 'yes', 'no', or 'unsure'."""
    tl = text.lower().strip()
    if any(w in tl for w in YES_WORDS):
        return 'yes'
    if any(w in tl for w in NO_WORDS):
        return 'no'
    return 'unsure'


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

PROLOG_LOADER = f"""
:- dynamic fact/1, asked/1.
:- use_module(library(lists)).
:- consult('{BASE}/generated/facts.pl').
:- consult('{BASE}/generated/diseases.pl').
:- consult('{BASE}/generated/rules.pl').
:- consult('{BASE}/web_engine.pl').
"""


def run_prolog(facts, asked, disease_order):
    fact_lines  = ''.join(f':- assertz(fact({f})).\n'  for f in facts)
    asked_lines = ''.join(f':- assertz(asked({a})).\n' for a in asked)
    dl = '[' + ', '.join(disease_order) + ']'

    script = (PROLOG_LOADER + fact_lines + asked_lines
              + f':- web_run({dl}).\n:- halt.\n')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pl',
                                     delete=False, dir='/tmp') as tf:
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
        return {'type': 'diagnosed', 'disease': parts[1],
                'matched': matched, 'count': int(parts[3]), 'threshold': int(parts[4])}
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
                    parts.append(DISEASE_INTRO.get(dname, ''))
                    session['last_intro']  = dname
                    session['last_ruled']  = None
                break

        parts.append(question)
        return '\n\n'.join(p for p in parts if p)

    if rtype == 'diagnosed':
        disease  = prolog_result['disease']
        matched  = prolog_result['matched']
        count    = prolog_result['count']
        thresh   = prolog_result['threshold']
        strength = "strongly" if count > thresh else "clearly"
        syms     = ', '.join(m.replace('_', ' ') for m in matched)
        return (
            f"Thank you for your patience with all those questions.\n\n"
            f"Based on the symptoms you have described, this {strength} points to "
            f"**{disease.upper()}**.\n\n"
            f"The key symptoms that led me to this conclusion are: {syms}.\n\n"
            f"⚠️ This is not a confirmed diagnosis. Please follow up with a specialist "
            f"and run proper lab tests. They will give you a definitive answer."
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
        'order_set':    False,
        'last_intro':   None,
        'last_ruled':   None,
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

    # --- Handle answer to the current pending question ---
    if pending_fact:
        answer = detect_yes_no(user_message)
        if answer == 'yes' and pending_fact not in facts:
            facts.append(pending_fact)
        if pending_fact not in asked:
            asked.append(pending_fact)
        session['pending_fact'] = None

    # --- Also extract any freely mentioned symptoms ---
    for sym in extract_symptoms(user_message):
        if sym not in facts:
            facts.append(sym)
        if sym not in asked:
            asked.append(sym)

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

if __name__ == '__main__':
    print('\nStarting Medical Diagnosis Chat at http://localhost:8080\n')
    app.run(debug=False, port=8080)
