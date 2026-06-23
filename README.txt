============================================================
  Medical Diagnosis Expert System
  Multi-file Prolog Structure — README
============================================================

HOW TO RUN
----------
1. Open SWI-Prolog
2. Navigate to this folder
3. Type:   ?- [main].
4. Type:   ?- start.


HOW TO RUN A QUICK TEST (no manual answering)
---------------------------------------------
?- run_test(diabetes).
?- run_test(hypertension).
?- run_test(anemia).
?- run_test(uti).
?- run_test(asthma).
?- run_test(tuberculosis).
?- run_test(no_match).
?- run_test(cough_chain).     <- proves smart chaining works


ANSWERING QUESTIONS
-------------------
Always end your answer with a period:
    yes.
    no.
    dont_know.


FILE STRUCTURE AND PURPOSE
--------------------------

facts.pl
    All recognized symptoms the patient can mention.
    To add a new symptom: add one recognized_symptom line here.

diseases.pl
    All disease definitions — name, threshold, questions.
    To add a new disease: add one disease(...) block here.

rules.pl
    Two things:
    - first_disease_to_check: maps a symptom to the first disease to investigate
    - related_diseases: after a disease fails, what related diseases come next
    Adding a new disease: add it to related_diseases so the chain knows where it fits.

engine.pl
    The core logic. Handles:
    - Asking questions (with skip-if-known logic)
    - Counting yes answers
    - Early stopping when threshold is reached
    - The investigate loop with smart related-disease chaining

dialogue.pl
    Every word the doctor says.
    Change the tone or wording here without touching any logic.

tests.pl
    Pre-loaded test scenarios.
    Add new test cases here for any new diseases you add.

main.pl
    Loads all files. Defines start/0.
    This is the only file you need to load.


HOW TO ADD A NEW DISEASE (example: adding Pneumonia)
-----------------------------------------------------
1. In diseases.pl — add:
    disease(pneumonia, 2, [
        'Do you have a high fever with chills?|fever_chills',
        'Do you have a productive cough with colored mucus?|productive_cough',
        'Is your breathing painful or difficult?|painful_breathing'
    ]).

2. In rules.pl — add it to related_diseases chains:
    Update related_diseases(asthma, [..., pneumonia]).
    Update related_diseases(tuberculosis, [..., pneumonia]).
    Add: related_diseases(pneumonia, [tuberculosis, asthma, anemia]).

3. In rules.pl — add entry symptom if needed:
    first_disease_to_check(painful_breathing, pneumonia).

4. In dialogue.pl — add intro and not_confirmed messages:
    introduce_disease(pneumonia) :- ...
    disease_not_confirmed(pneumonia) :- ...

5. In tests.pl — add a test case:
    load_test(pneumonia) :- ...

That is it. Nothing in engine.pl or main.pl needs to change.


WHAT CHANGED FROM THE SINGLE-FILE VERSION
------------------------------------------
1. MODULAR FILES
   The original code was one long file. Now each concern lives separately.
   Adding a new disease takes 5 targeted edits across the right files.
   No hunting through one long file.

2. SMART DISEASE CHAINING
   Old behavior: cough -> asthma fails -> UTI asked next (no connection at all).
   New behavior: cough -> asthma fails -> tuberculosis asked next (medically related).
   The related_diseases table in rules.pl controls this. Medically related
   diseases are always investigated before unrelated ones.

3. CONFIDENCE-AWARE DIAGNOSIS
   The doctor now says different things depending on how many symptoms matched.
   If Count > Threshold: "Based on the strong match across multiple symptoms..."
   If Count == Threshold: "Based on the symptoms you have described..."
   This makes the output feel more like a real clinical assessment.
============================================================
