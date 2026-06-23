% ============================================================
% web_engine.pl
%
% Non-interactive Prolog engine for the web app.
% Instead of reading from stdin, it writes one line of
% structured output and halts. Python parses that line.
%
% Output formats:
%   DIAGNOSED\tDisease\tSymptom1,Symptom2\tCount\tThreshold
%   NEED_ANSWER\tQuestion text\tFact atom
%   NO_DIAGNOSIS
%
% Entry point (called from Python via a temp .pl file):
%   :- web_run([diabetes, hypertension, ...]).
% ============================================================

:- dynamic fact/1, asked/1.
:- use_module(library(lists)).


% --- Ask one question (web version) ---
% If fact is already known or already asked, continue silently.
% If unknown, write NEED_ANSWER and halt — Python handles the rest.

web_ask(Question, Fact) :-
    ( fact(Fact)  -> true
    ; asked(Fact) -> true
    ;
        format('NEED_ANSWER\t~w\t~w~n', [Question, Fact]),
        halt
    ).


% --- Ask all questions for one disease, count yes answers ---

web_ask_questions([], Count, _Threshold, Count).

web_ask_questions([_|_], Acc, Threshold, Acc) :-
    Acc >= Threshold, !.

web_ask_questions([Q|Rest], Acc, Threshold, FinalCount) :-
    split_string(Q, "|", "", [QuestionText, FactName]),
    atom_string(FactAtom, FactName),
    web_ask(QuestionText, FactAtom),
    ( fact(FactAtom) -> NewAcc is Acc + 1 ; NewAcc = Acc ),
    web_ask_questions(Rest, NewAcc, Threshold, FinalCount).


% --- Collect which facts the patient confirmed ---

collect_matched([], []).
collect_matched([Q|Rest], [FactAtom|Matched]) :-
    split_string(Q, "|", "", [_, FactName]),
    atom_string(FactAtom, FactName),
    fact(FactAtom), !,
    collect_matched(Rest, Matched).
collect_matched([_|Rest], Matched) :-
    collect_matched(Rest, Matched).


% --- The investigation loop ---

web_investigate([]) :-
    write('NO_DIAGNOSIS'), nl, halt.

web_investigate([Disease|Rest]) :-
    disease(Disease, Threshold, Questions),
    web_ask_questions(Questions, 0, Threshold, Count),
    ( Count >= Threshold ->
        collect_matched(Questions, Matched),
        atomic_list_concat(Matched, ',', MatchedStr),
        format('DIAGNOSED\t~w\t~w\t~w\t~w~n',
               [Disease, MatchedStr, Count, Threshold]),
        halt
    ;
        web_investigate(Rest)
    ).


% --- Entry point ---

web_run(DiseaseList) :-
    web_investigate(DiseaseList).
