"""
Doctor-side knowledge acquisition — the real backend for the "Rule Intake"
interface (previously a prototype only).

This is a guided, deterministic conversation (no LLM/API key required, same
philosophy as the patient-side keyword lexicon): a doctor describes a new
condition one step at a time, the draft is shown back to them for review,
and only on explicit confirmation is it written into diseases.yaml and the
Prolog rules regenerated — nothing reaches the live knowledge base
automatically. This mirrors exactly what the prototype depicted.

Session shape (passed back and forth with the client, same pattern as the
patient chat in app.py):
    {
        'stage':        one of STAGES below,
        'name':         disease name (slug), e.g. 'migraine'
        'category':     broad category string
        'threshold':    int
        'symptoms':     [{'fact':, 'text':, 'severity':, 'primary':}, ...]
        'cur_fact':     fact slug currently being defined (mid-symptom)
        'cur_text':     question text currently being defined
        'cur_severity': severity currently being defined
    }
"""

import re
import os

import yaml

import generate_prolog

STAGES = ('name', 'symptom_text', 'symptom_fact', 'symptom_severity',
          'symptom_primary', 'symptom_more', 'threshold', 'category', 'review', 'done')


def slugify(text):
    s = text.strip().lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')


def new_session():
    return {
        'stage': 'name',
        'name': None,
        'category': None,
        'threshold': None,
        'symptoms': [],
        'cur_fact': None,
        'cur_text': None,
        'cur_severity': None,
    }


def start_message():
    return (
        "Rule Intake — let's add a new condition to the knowledge base.\n\n"
        "What condition would you like to add? (e.g. \"Migraine\")"
    )


def step(session, message):
    """
    Advance the guided intake by one turn. Returns (reply_text, session,
    draft_or_None). draft is only non-None once the stage reaches 'review'
    — that's the point a doctor can confirm or discard it.
    """
    stage = session['stage']
    msg = message.strip()

    if stage == 'name':
        session['name'] = slugify(msg)
        session['stage'] = 'symptom_text'
        return (
            f"Got it — **{msg.strip().title()}**.\n\n"
            "Now let's capture the symptoms that would confirm it. "
            "Describe the first confirming question, as you'd ask the patient "
            "(e.g. \"Do you have a throbbing, one-sided headache?\")",
            session, None
        )

    if stage == 'symptom_text':
        session['cur_text'] = msg
        session['stage'] = 'symptom_fact'
        suggested = slugify(msg.split('?')[0])[:40] or 'symptom'
        session['cur_fact'] = suggested
        return (
            f"What should this symptom be called internally? "
            f"(a short code, e.g. \"{suggested}\" — press enter to use that, "
            f"or type your own)",
            session, None
        )

    if stage == 'symptom_fact':
        if msg:
            session['cur_fact'] = slugify(msg)
        session['stage'] = 'symptom_severity'
        return (
            "On a scale of 1 (mild/nonspecific) to 5 (severe/hallmark), "
            "how clinically significant is this symptom on its own?",
            session, None
        )

    if stage == 'symptom_severity':
        try:
            sev = max(1, min(5, int(re.sub(r'[^0-9]', '', msg) or '3')))
        except ValueError:
            sev = 3
        session['cur_severity'] = sev
        session['stage'] = 'symptom_primary'
        return (
            f"Severity {sev}/5 noted.\n\n"
            "Is this a *hallmark* symptom — specific enough that confirming "
            "it alone should be enough to confirm the condition, without "
            "needing the other symptoms too? (yes/no)",
            session, None
        )

    if stage == 'symptom_primary':
        is_primary = msg.lower().startswith(('y', 'yes'))
        session['symptoms'].append({
            'fact': session['cur_fact'],
            'text': session['cur_text'],
            'severity': session['cur_severity'],
            'primary': is_primary,
        })
        session['cur_fact'] = None
        session['cur_text'] = None
        session['cur_severity'] = None
        session['stage'] = 'symptom_more'
        return (
            "Added. Describe another confirming question, or type \"done\" "
            "if that's all of them.",
            session, None
        )

    if stage == 'symptom_more':
        if msg.lower() in ('done', 'no', 'no more', 'that\'s all', 'finished'):
            session['stage'] = 'threshold'
            n = len(session['symptoms'])
            return (
                f"{n} symptom{'s' if n != 1 else ''} captured.\n\n"
                "How many of these (not counting any hallmark symptom, which "
                "confirms on its own) should be required together to confirm "
                "this condition? (a number, e.g. 2)",
                session, None
            )
        session['cur_text'] = msg
        session['stage'] = 'symptom_fact'
        suggested = slugify(msg.split('?')[0])[:40] or 'symptom'
        session['cur_fact'] = suggested
        return (
            f"What should this symptom be called internally? "
            f"(a short code, e.g. \"{suggested}\" — press enter to use that, "
            f"or type your own)",
            session, None
        )

    if stage == 'threshold':
        try:
            n = int(re.sub(r'[^0-9]', '', msg) or '2')
        except ValueError:
            n = 2
        session['threshold'] = max(1, n)
        session['stage'] = 'category'
        return (
            "Last question — what broad category does this condition belong "
            "to? (e.g. \"respiratory\", \"metabolic\", \"neurological\")",
            session, None
        )

    if stage == 'category':
        session['category'] = slugify(msg) or 'other'
        session['stage'] = 'review'
        draft = build_draft(session)
        return (
            "Here's the draft — review it below and confirm to add it to "
            "the knowledge base, or discard it.",
            session, draft
        )

    if stage == 'review':
        # Shouldn't normally receive free text here — the client should
        # call the confirm/discard endpoints instead — but handle it
        # gracefully if it does.
        return (
            "Please use Confirm or Discard on the draft above.",
            session, build_draft(session)
        )

    return ("This intake is finished.", session, None)


def build_draft(session):
    return {
        'name': session['name'],
        'category': session['category'],
        'threshold': session['threshold'],
        'symptoms': session['symptoms'],
    }


# ---------------------------------------------------------------------------
# Committing a confirmed draft into diseases.yaml
# ---------------------------------------------------------------------------

def _disease_block_text(draft):
    name = draft['name']
    lines = [f"  {name}:",
             f"    threshold: {draft['threshold']}",
             f"    entry_symptoms: [{', '.join(s['fact'] for s in draft['symptoms'])}]",
             f"    questions:"]
    for s in draft['symptoms']:
        text = s['text'].replace('"', '\\"')
        lines.append(f"      - fact: {s['fact']}")
        lines.append(f"        text: \"{text}\"")
        lines.append(f"        severity: {s['severity']}")
        if s['primary']:
            lines.append(f"        primary: true")
    lines.append(f"    related: []")
    return '\n'.join(lines) + '\n'


def commit_draft(draft, yaml_path):
    """
    Insert the confirmed draft's disease block, routing entries, and
    category into diseases.yaml via targeted text insertion — never a
    full re-dump — so hand-written comments and formatting in the rest of
    the file are preserved exactly. Then regenerates the Prolog files.
    Raises ValueError if a disease with this name already exists.
    """
    with open(yaml_path) as f:
        text = f.read()
        f.seek(0)
        config = yaml.safe_load(text)

    name = draft['name']
    if name in config.get('diseases', {}):
        raise ValueError(f'A disease named "{name}" already exists.')

    # 1. Insert the new disease block just before the symptom_routing
    #    section comment, right after the last existing disease.
    marker = '\n\n# Maps each opening symptom'
    idx = text.index(marker)
    block = '\n' + _disease_block_text(draft)
    text = text[:idx] + block + text[idx:]

    # 2. Add/extend symptom_routing entries for each fact this disease uses.
    for s in draft['symptoms']:
        fact = s['fact']
        pattern = re.compile(rf'^(  {re.escape(fact)}:\s*\[)([^\]]*)(\])', re.MULTILINE)
        m = pattern.search(text)
        if m:
            existing = [d.strip() for d in m.group(2).split(',') if d.strip()]
            if name not in existing:
                existing.append(name)
            new_list = ', '.join(existing)
            text = text[:m.start()] + f"{m.group(1)}{new_list}{m.group(3)}" + text[m.end():]
        else:
            # Brand-new symptom fact — add a routing line right before
            # the catch-all 'other:' line.
            other_pat = re.compile(r'^(  other:\s*\[)', re.MULTILINE)
            om = other_pat.search(text)
            new_line = f"  {fact}:{' ' * max(1, 20 - len(fact) - 3)}[{name}]\n"
            text = text[:om.start()] + new_line + text[om.start():]

    # 3. Add this disease to the categories: block.
    cat_pat = re.compile(r'^(categories:\n)', re.MULTILINE)
    cm = cat_pat.search(text)
    cat_line = f"  {name}:{' ' * max(1, 15 - len(name) - 1)}{draft['category']}\n"
    text = text[:cm.end()] + cat_line + text[cm.end():]

    # Validate before writing — never leave diseases.yaml in a broken state.
    yaml.safe_load(text)

    with open(yaml_path, 'w') as f:
        f.write(text)

    base = os.path.dirname(os.path.abspath(yaml_path))
    generate_prolog.generate(yaml_path=yaml_path, output_dir=os.path.join(base, 'generated'))

    with open(yaml_path) as f:
        return yaml.safe_load(f)
