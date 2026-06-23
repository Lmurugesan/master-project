#!/usr/bin/env python3
"""
Reads diseases.yaml and generates Prolog files into the generated/ folder.

Run this after editing diseases.yaml:
    python3 generate_prolog.py

The app also calls this automatically on startup.
"""

import yaml
import os


def generate(yaml_path=None, output_dir=None):
    base = os.path.dirname(os.path.abspath(__file__))
    yaml_path = yaml_path or os.path.join(base, 'diseases.yaml')
    output_dir = output_dir or os.path.join(base, 'generated')

    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    os.makedirs(output_dir, exist_ok=True)
    diseases = config['diseases']
    routing = config['symptom_routing']

    _write_diseases(diseases, output_dir)
    _write_facts(diseases, routing, output_dir)
    _write_rules(routing, output_dir)

    print(f'[generate_prolog] Wrote diseases.pl, facts.pl, rules.pl → {output_dir}/')


def _escape(text):
    # Escape single quotes inside Prolog single-quoted atoms
    return text.replace("'", "''")


def _write_diseases(diseases, output_dir):
    lines = ['% AUTO-GENERATED from diseases.yaml — do not edit directly\n']
    for name, d in diseases.items():
        lines.append(f'disease({name}, {d["threshold"]}, [')
        qs = d['questions']
        for i, q in enumerate(qs):
            comma = ',' if i < len(qs) - 1 else ''
            text = _escape(q['text'])
            lines.append(f"    '{text}|{q['fact']}'{comma}")
        lines.append(']).\n')
    with open(os.path.join(output_dir, 'diseases.pl'), 'w') as f:
        f.write('\n'.join(lines))


def _write_facts(diseases, routing, output_dir):
    # Recognized symptoms = everything in symptom_routing except 'other'
    symptoms = sorted(k for k in routing if k != 'other')
    lines = ['% AUTO-GENERATED from diseases.yaml — do not edit directly\n']
    for s in symptoms:
        lines.append(f'recognized_symptom({s}).')
    with open(os.path.join(output_dir, 'facts.pl'), 'w') as f:
        f.write('\n'.join(lines))


def _write_rules(routing, output_dir):
    lines = ['% AUTO-GENERATED from diseases.yaml — do not edit directly\n']
    for symptom, disease_list in routing.items():
        dl = ', '.join(disease_list)
        lines.append(f'symptom_diseases({symptom}, [{dl}]).')
    lines.append('')
    for symptom, disease_list in routing.items():
        if disease_list:
            lines.append(f'first_disease_to_check({symptom}, {disease_list[0]}).')
    with open(os.path.join(output_dir, 'rules.pl'), 'w') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    generate()
