% ============================================================
% tests.pl
% Pre-loaded test cases. Use these to test without
% answering questions manually.
%
% HOW TO RUN A TEST:
%   ?- run_test(diabetes).
%   ?- run_test(hypertension).
%   ?- run_test(anemia).
%   ?- run_test(uti).
%   ?- run_test(asthma).
%   ?- run_test(tuberculosis).
%   ?- run_test(no_match).
%   ?- run_test(cough_chain).   <- shows smart chaining: asthma fails, TB asked next
% ============================================================


run_test(Name) :-
    reset_system,
    load_test(Name),
    nl,
    format('=== Running test: ~w ===~n', [Name]),
    symptom_diseases(other, AllowedDiseases),
    first_disease_to_check(other, StartDisease),
    build_ordered_list(StartDisease, AllowedDiseases, OrderedList),
    investigate(OrderedList).


% --- Test: Diabetes confirmed ---
load_test(diabetes) :-
    assertz(fact(elevated_glucose)),
    assertz(fact(polyuria)),
    assertz(fact(polydipsia)),
    assertz(asked(elevated_glucose)),
    assertz(asked(high_hba1c)),
    assertz(asked(polyuria)),
    assertz(asked(polydipsia)),
    assertz(asked(fatigue)),
    write('Loaded: diabetes — elevated_glucose + polyuria + polydipsia'), nl.


% --- Test: Hypertension confirmed ---
load_test(hypertension) :-
    assertz(fact(elevated_bp)),
    assertz(fact(hypertension_headache)),
    assertz(asked(history_of_hypertension)),
    assertz(asked(on_bp_medication)),
    assertz(asked(elevated_bp)),
    assertz(asked(hypertension_headache)),
    write('Loaded: hypertension — elevated_bp + headache'), nl.


% --- Test: Anemia confirmed ---
load_test(anemia) :-
    assertz(fact(fatigue)),
    assertz(fact(pale_skin)),
    assertz(asked(fatigue)),
    assertz(asked(pale_skin)),
    assertz(asked(dizziness)),
    write('Loaded: anemia — fatigue + pale_skin'), nl.


% --- Test: UTI confirmed ---
load_test(uti) :-
    assertz(fact(dysuria)),
    assertz(fact(urinary_frequency)),
    assertz(asked(dysuria)),
    assertz(asked(urinary_frequency)),
    assertz(asked(urinary_urgency)),
    assertz(asked(suprapubic_pain)),
    write('Loaded: uti — dysuria + urinary_frequency'), nl.


% --- Test: Asthma confirmed ---
load_test(asthma) :-
    assertz(fact(chronic_cough)),
    assertz(fact(wheezing)),
    assertz(asked(chronic_cough)),
    assertz(asked(chest_tightness)),
    assertz(asked(wheezing)),
    assertz(asked(exercise_triggered)),
    write('Loaded: asthma — chronic_cough + wheezing'), nl.


% --- Test: Tuberculosis confirmed ---
load_test(tuberculosis) :-
    assertz(fact(persistent_cough)),
    assertz(fact(night_sweats)),
    assertz(asked(persistent_cough)),
    assertz(asked(coughing_blood)),
    assertz(asked(night_sweats)),
    assertz(asked(unexplained_weight_loss)),
    assertz(asked(tb_exposure)),
    write('Loaded: tuberculosis — persistent_cough + night_sweats'), nl.


% --- Test: Nothing confirmed ---
load_test(no_match) :-
    assertz(asked(elevated_glucose)),
    assertz(asked(high_hba1c)),
    assertz(asked(polyuria)),
    assertz(asked(polydipsia)),
    assertz(asked(fatigue)),
    assertz(asked(history_of_hypertension)),
    assertz(asked(on_bp_medication)),
    assertz(asked(elevated_bp)),
    assertz(asked(hypertension_headache)),
    assertz(asked(pale_skin)),
    assertz(asked(dizziness)),
    assertz(asked(dysuria)),
    assertz(asked(urinary_frequency)),
    assertz(asked(urinary_urgency)),
    assertz(asked(suprapubic_pain)),
    assertz(asked(chronic_cough)),
    assertz(asked(chest_tightness)),
    assertz(asked(wheezing)),
    assertz(asked(exercise_triggered)),
    assertz(asked(persistent_cough)),
    assertz(asked(coughing_blood)),
    assertz(asked(night_sweats)),
    assertz(asked(unexplained_weight_loss)),
    assertz(asked(tb_exposure)),
    write('Loaded: no_match — all answers no'), nl.


% --- Test: Smart chaining — cough given, asthma fails, TB asked next ---
% This proves the fix: cough -> asthma checked -> not confirmed -> TB asked.
% UTI is NOT asked next. That would make no medical sense.
load_test(cough_chain) :-
    % All asthma questions answered no
    assertz(asked(chronic_cough)),
    assertz(asked(chest_tightness)),
    assertz(asked(wheezing)),
    assertz(asked(exercise_triggered)),
    % TB will now be asked because it is related to asthma in rules.pl
    write('Loaded: cough_chain — asthma fails, tuberculosis should be next'), nl.
