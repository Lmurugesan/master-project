% ============================================================
% web_engine.pl
%
% Non-interactive Prolog engine for the web app.
% Instead of reading from stdin, it writes one line of
% structured output and halts. Python parses that line.
%
% Output formats:
%   DIAGNOSED\tDisease\tSymptom1,Symptom2\tCount\tThreshold\tReason
%     Reason is 'primary' (one hallmark symptom was enough on its own —
%     see diseases.yaml's 'primary: true') or 'threshold' (the plain
%     fact-count reached the disease's threshold instead).
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


% --- Parse one encoded question string: "text|fact" or "text|fact|primary" ---

split_question(Q, QuestionText, FactAtom, IsPrimary) :-
    split_string(Q, "|", "", Parts),
    ( Parts = [QT, FN, "primary"] -> IsPrimary = true
    ; Parts = [QT, FN]            -> IsPrimary = false
    ),
    QuestionText = QT,
    atom_string(FactAtom, FN).


% --- Ask all questions for one disease, count yes answers.
% Stops early either when a single hallmark ("primary") fact is confirmed,
% or once the plain count reaches Threshold — whichever happens first.
% FinalReason is bound to 'primary' or 'threshold' accordingly. ---

web_ask_questions([], Count, _Threshold, Count, threshold).

web_ask_questions([_|_], Acc, Threshold, Acc, threshold) :-
    Acc >= Threshold, !.

web_ask_questions([Q|Rest], Acc, Threshold, FinalCount, FinalReason) :-
    split_question(Q, QuestionText, FactAtom, IsPrimary),
    web_ask(QuestionText, FactAtom),
    ( fact(FactAtom) ->
        ( IsPrimary == true ->
            % A hallmark symptom on its own is enough — stop here rather
            % than asking the rest of this disease's questions.
            FinalCount  is Acc + 1,
            FinalReason = primary
        ;
            NewAcc is Acc + 1,
            web_ask_questions(Rest, NewAcc, Threshold, FinalCount, FinalReason)
        )
    ;
        web_ask_questions(Rest, Acc, Threshold, FinalCount, FinalReason)
    ).


% --- Collect which facts the patient confirmed ---

collect_matched([], []).
collect_matched([Q|Rest], [FactAtom|Matched]) :-
    split_question(Q, _, FactAtom, _),
    fact(FactAtom), !,
    collect_matched(Rest, Matched).
collect_matched([_|Rest], Matched) :-
    collect_matched(Rest, Matched).


% --- The investigation loop ---

web_investigate([]) :-
    write('NO_DIAGNOSIS'), nl, halt.

web_investigate([Disease|Rest]) :-
    disease(Disease, Threshold, Questions),
    web_ask_questions(Questions, 0, Threshold, Count, Reason),
    ( (Reason == primary ; Count >= Threshold) ->
        collect_matched(Questions, Matched),
        atomic_list_concat(Matched, ',', MatchedStr),
        format('DIAGNOSED\t~w\t~w\t~w\t~w\t~w~n',
               [Disease, MatchedStr, Count, Threshold, Reason]),
        halt
    ;
        web_investigate(Rest)
    ).


% --- Entry point ---

web_run(DiseaseList) :-
    web_investigate(DiseaseList).
