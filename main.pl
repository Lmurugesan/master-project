% ============================================================
% main.pl
% Load this file in SWI-Prolog. It pulls in everything else.
%
% HOW TO RUN:
%   ?- [main].
%   ?- start.
%
% HOW TO TEST:
%   ?- run_test(diabetes).
%   ?- run_test(cough_chain).
% ============================================================

:- dynamic fact/1, asked/1.

:- use_module(library(lists)).

:- consult(facts).
:- consult(diseases).
:- consult(rules).
:- consult(engine).
:- consult(dialogue).
:- consult(tests).


% ============================================================
% start/0
%
% Flow:
%   1. Reset all memory from any previous session
%   2. Greet the patient
%   3. Ask what is bothering them — exactly once, no retry
%   4. Look up which diseases could explain that symptom
%   5. Put the most relevant disease first in the list
%   6. Hand off to investigate/1 which only checks that list
% ============================================================

start :-
    reset_system,
    nl,
    write('  ============================================='), nl,
    write('        Medical Diagnosis Assistant           '), nl,
    write('  ============================================='), nl,
    nl,
    write('  Doctor : Hello! I am glad you came in today.'), nl,
    write('           Before I ask you anything specific,'), nl,
    write('           can you tell me what has been bothering'), nl,
    write('           you the most lately?'), nl,
    nl,
    write('  You can say one of the following, then press Enter:'), nl,
    write('    fatigue       polyuria      polydipsia    cough'), nl,
    write('    headache      dysuria       dizziness     fever'), nl,
    write('    elevated_bp   pale_skin     night_sweats  nausea'), nl,
    write('    weight_loss   elevated_glucose             other'), nl,
    nl,
    write('  (Type your answer with a period at the end. Example:  fatigue.)'), nl,
    nl,
    write('  Patient: '),
    read(Input),
    nl,
    handle_opening(Input).


% --- Handle what the patient says at the start ---

handle_opening(Input) :-
    ( recognized_symptom(Input) ->
        MainSymptom = Input,
        format('  Doctor : I see — ~w. That can be caused by a few', [MainSymptom]), nl,
        write('           different things. Let me ask you some more'), nl,
        write('           focused questions to figure out what is going on.'), nl
    ;
        MainSymptom = other,
        write('  Doctor : No problem at all. I will ask you some'), nl,
        write('           general questions and we will work through it together.'), nl
    ),
    nl,
    write('  Doctor : I will ask you yes or no questions. Take your time.'), nl,
    write('           If you are honestly not sure, just say dont_know.'), nl,
    write('           End every answer with a period — yes.  no.  dont_know.'), nl,
    nl,
    % Get only the diseases that could explain this symptom
    symptom_diseases(MainSymptom, AllowedDiseases),
    % Put the most relevant one first
    first_disease_to_check(MainSymptom, StartDisease),
    build_ordered_list(StartDisease, AllowedDiseases, OrderedList),
    % Investigate only within the medically relevant set
    investigate(OrderedList).
