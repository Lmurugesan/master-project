============================================================
  Medical Diagnosis Expert System
  Prolog + Flask — README
============================================================

This repository has two ways to run the system:

  A. WEB APP (recommended) — a chat UI in your browser, served by
     Flask, reasoning done by SWI-Prolog under the hood.
  B. CONSOLE APP — a plain-text conversation directly inside
     SWI-Prolog, useful for quick testing without a browser.

Both work the same way on macOS, Linux, and Windows. Windows-specific
notes are called out below wherever a step differs.


------------------------------------------------------------
1. REQUIREMENTS
------------------------------------------------------------
  - Python 3.9+
  - SWI-Prolog (provides the `swipl` command)
  - pip packages in requirements.txt (Flask, PyYAML)

macOS:
    brew install swi-prolog
    (Python 3 is usually already installed; otherwise brew install python)

Linux (Debian/Ubuntu):
    sudo apt install swi-prolog python3 python3-pip

Windows:
    1. Install Python from https://www.python.org/downloads/
       - IMPORTANT: check "Add python.exe to PATH" in the installer.
    2. Install SWI-Prolog from https://www.swi-prolog.org/download/stable
       - The Windows installer adds `swipl` to your PATH automatically
         (default option). If you skip that option, add the SWI-Prolog
         `bin` folder (e.g. C:\Program Files\swipl\bin) to your PATH
         manually via System Properties -> Environment Variables.
    3. Open a fresh Command Prompt or PowerShell window (PATH changes
       only apply to new terminal windows) and verify both are on PATH:
           py --version
           swipl --version


------------------------------------------------------------
2. SETUP (all platforms)
------------------------------------------------------------
From the project folder:

macOS / Linux:
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

Windows (Command Prompt or PowerShell):
    py -m venv venv
    venv\Scripts\activate
    py -m pip install -r requirements.txt

(The virtual environment is optional but recommended so the two
 packages don't get installed globally.)


------------------------------------------------------------
3. RUNNING THE WEB APP
------------------------------------------------------------
macOS / Linux:
    python3 app.py

Windows:
    py app.py

Then open http://localhost:8080 in your browser. The app regenerates
the Prolog knowledge base from diseases.yaml automatically on every
startup — no manual build step needed on any platform.

To stop the server: Ctrl+C in the terminal it's running in.


------------------------------------------------------------
4. RUNNING THE CONSOLE APP
------------------------------------------------------------
1. Open SWI-Prolog:
     macOS/Linux:  swipl
     Windows:      swipl   (or double-click swipl-win from the Start menu)
2. Navigate to this folder if you didn't launch swipl from inside it:
     ?- cd('C:/path/to/MasterProject').      (Windows: use forward slashes)
     ?- cd('/path/to/MasterProject').        (macOS/Linux)
3. Load and start:
     ?- [main].
     ?- start.


HOW TO RUN A QUICK TEST (no manual answering)
----------------------------------------------
?- [main].
?- run_test(diabetes).
?- run_test(hypertension).
?- run_test(anemia).
?- run_test(uti).
?- run_test(asthma).
?- run_test(tuberculosis).
?- run_test(no_match).
?- run_test(cough_chain).     <- proves the routing table stays on-topic


ANSWERING QUESTIONS (console app only)
----------------------------------------
Always end your answer with a period:
    yes.
    no.
    dont_know.

(The web app accepts natural free text instead — no periods needed.)


------------------------------------------------------------
5. FILE STRUCTURE AND PURPOSE
------------------------------------------------------------

Console reference implementation (repository root):
  facts.pl          All recognized opening-symptom atoms.
  diseases.pl       Disease definitions — name, threshold, questions.
  rules.pl          symptom_diseases/2 (which diseases an opening
                     symptom could explain) and first_disease_to_check/2
                     (which of those to ask about first).
  engine.pl         Core reasoning: ask questions, count yes answers,
                     stop early at threshold, investigate the routed list.
  dialogue.pl       Every word the doctor says in the console app.
  tests.pl          Pre-loaded test scenarios (see Section 4 above).
  main.pl           Loads all of the above; defines start/0.

Web deployment:
  diseases.yaml         Declarative source: thresholds, entry symptoms,
                         questions, and symptom routing — edit this file
                         to add or change a disease for the web app.
  generate_prolog.py    Compiles diseases.yaml into generated/*.pl.
  generated/             Auto-generated Prolog files (rebuilt on every
                         app.py startup — do not edit by hand).
  web_engine.pl         Non-interactive version of the reasoning engine,
                         used by the Flask app over HTTP.
  app.py                Flask routes, free-text symptom extraction,
                         yes/no answer classification, and the templated
                         doctor dialogue for the web UI.
  static/index.html     The browser chat interface.

NOTE: the console app's knowledge base (facts.pl / diseases.pl /
rules.pl at the repo root) is currently maintained separately from
diseases.yaml and is not auto-regenerated from it. If you add a
disease for the web app, add it to the console files too if you want
both front ends to stay in sync.


------------------------------------------------------------
6. HOW TO ADD A NEW DISEASE
------------------------------------------------------------
Web app (recommended — one file):
  1. Add a block under `diseases:` in diseases.yaml with a threshold,
     entry_symptoms, and questions.
  2. Add the disease name to the relevant symptom_routing lines.
  3. Restart app.py — it regenerates generated/*.pl automatically.

Console app (example: adding Pneumonia):
  1. In diseases.pl, add:
       disease(pneumonia, 2, [
           'Do you have a high fever with chills?|fever_chills',
           'Do you have a productive cough with colored mucus?|productive_cough',
           'Is your breathing painful or difficult?|painful_breathing'
       ]).
  2. In rules.pl, add it to the relevant symptom_diseases/2 lists and
     add a first_disease_to_check/2 line for its key symptom.
  3. In dialogue.pl, add introduce_disease(pneumonia) and
     disease_not_confirmed(pneumonia) clauses.
  4. In tests.pl, add a load_test(pneumonia) clause.

Nothing in engine.pl, web_engine.pl, or app.py's reasoning logic needs
to change either way — only data files.


------------------------------------------------------------
7. TROUBLESHOOTING
------------------------------------------------------------
"swipl is not recognized" (Windows):
    SWI-Prolog's bin folder isn't on PATH. Reinstall and check the
    "add to PATH" option, or add it manually, then open a NEW terminal
    window (existing windows won't see the PATH update).

"python is not recognized" (Windows):
    Use `py` instead of `python`, or reinstall Python with "Add
    python.exe to PATH" checked.

Port 8080 already in use:
    Another process is using it. Stop it, or edit the port number in
    the last line of app.py (app.run(..., port=8080)).
============================================================
