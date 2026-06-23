% ============================================================
% engine.pl
%
% The reasoning core. Three jobs:
%   1. Ask questions without repeating
%   2. Count yes answers, stop early when threshold is reached
%   3. Walk through the allowed disease list, stop when confirmed
%
% The allowed disease list comes from symptom_diseases in rules.pl.
% The engine never goes outside that list. No unrelated diseases.
% ============================================================


% --- Clear everything before a new patient ---

reset_system :-
    retractall(fact(_)),
    retractall(asked(_)).


% --- Ask one question ---
% Skip if the fact is already known (patient said it at the start)
% Skip if this exact question was already asked this session
% dont_know is neutral — counts as nothing, stored as nothing

ask_question(Question, Fact) :-
    ( fact(Fact)  -> true
    ; asked(Fact) -> true
    ;
        format('~n  Doctor : ~w~n  Patient: ', [Question]),
        read(Response),
        ( Response == yes       -> assertz(fact(Fact))
        ; Response == dont_know -> true
        ; true
        ),
        assertz(asked(Fact))
    ).


% --- Ask all questions for one disease, count yes answers ---
%
% Clause 1: No questions left. Return whatever count we have.
%
% Clause 2: Yes count already hit the threshold. Stop right here.
%           The cut ! prevents falling to clause 3.
%           No more questions for this disease.
%
% Clause 3: Normal case. Ask the next question.
%           If yes, increment counter. Then move to next question.

ask_disease_questions([], Count, _Threshold, Count).

ask_disease_questions([_|_], Acc, Threshold, Acc) :-
    Acc >= Threshold, !.

ask_disease_questions([Q|Rest], Acc, Threshold, FinalCount) :-
    split_string(Q, "|", "", [QuestionText, FactName]),
    atom_string(FactAtom, FactName),
    ask_question(QuestionText, FactAtom),
    ( fact(FactAtom) -> NewAcc is Acc + 1 ; NewAcc = Acc ),
    ask_disease_questions(Rest, NewAcc, Threshold, FinalCount).


% --- Collect which symptom names the patient confirmed ---
% Used in print_diagnosis to show the patient the reasoning.

collect_matched_facts([], []).

collect_matched_facts([Q|Rest], [FactAtom|Matched]) :-
    split_string(Q, "|", "", [_, FactName]),
    atom_string(FactAtom, FactName),
    fact(FactAtom), !,
    collect_matched_facts(Rest, Matched).

collect_matched_facts([_|Rest], Matched) :-
    collect_matched_facts(Rest, Matched).


% --- The investigation loop ---
%
% Takes the list of allowed diseases for this patient's symptom.
% Tries them one at a time in order.
%
% When confirmed  -> print diagnosis and stop. Done.
% When not confirmed -> move to next disease in the list.
% When list is empty -> no diagnosis found. Close gracefully.
%
% The key fix: this list only contains medically related diseases.
% It comes from symptom_diseases in rules.pl.
% Headache patients will never be asked about urination.

investigate([]) :-
    dialogue:no_diagnosis_found.

investigate([Disease|Rest]) :-
    disease(Disease, Threshold, Questions),
    dialogue:introduce_disease(Disease),
    ask_disease_questions(Questions, 0, Threshold, Count),
    ( Count >= Threshold ->
        dialogue:print_diagnosis(Disease, Questions, Count, Threshold)
    ;
        dialogue:disease_not_confirmed(Disease),
        investigate(Rest)
    ).


% --- Build the investigation list in the right order ---
% Puts the most likely disease first, then the rest of the allowed list.

build_ordered_list(StartDisease, AllAllowed, OrderedList) :-
    delete(AllAllowed, StartDisease, Rest),
    OrderedList = [StartDisease | Rest].
