% ============================================================
% dialogue.pl
% Every word the doctor says lives here.
% The engine calls these but never prints anything itself.
% To change the tone or wording, only edit this file.
% ============================================================

:- module(dialogue, [
    introduce_disease/1,
    disease_not_confirmed/1,
    print_diagnosis/4,
    no_diagnosis_found/0
]).


% --- Doctor introduces a new area of questioning ---

introduce_disease(diabetes) :-
    nl,
    write('  Doctor : I would like to ask you a few questions about'), nl,
    write('           your blood sugar levels and some related symptoms.'), nl.

introduce_disease(hypertension) :-
    nl,
    write('  Doctor : Let me check a few things related to your blood pressure.'), nl.

introduce_disease(anemia) :-
    nl,
    write('  Doctor : Headaches can sometimes be linked to low blood count.'), nl,
    write('           Let me ask you a few questions about that.'), nl.

introduce_disease(uti) :-
    nl,
    write('  Doctor : I would like to ask about your urinary symptoms.'), nl.

introduce_disease(asthma) :-
    nl,
    write('  Doctor : Given the cough you mentioned, I want to check'), nl,
    write('           whether this could be related to your airways.'), nl.

introduce_disease(tuberculosis) :-
    nl,
    write('  Doctor : Since asthma seems less likely, I want to check'), nl,
    write('           one more thing that can also cause a persistent cough.'), nl.


% --- Doctor explains why a disease was ruled out and what comes next ---

disease_not_confirmed(hypertension) :-
    nl,
    write('  Doctor : Your answers do not strongly point to high blood pressure.'), nl,
    write('           But headaches can also come from other causes.'), nl,
    write('           Let me check one more thing.'), nl.

disease_not_confirmed(anemia) :-
    nl,
    write('  Doctor : The symptoms do not clearly point to anemia either.'), nl.

disease_not_confirmed(diabetes) :-
    nl,
    write('  Doctor : The picture so far does not suggest diabetes.'), nl,
    write('           Let me look at something else.'), nl.

disease_not_confirmed(uti) :-
    nl,
    write('  Doctor : This does not look like a urinary tract infection.'), nl.

disease_not_confirmed(asthma) :-
    nl,
    write('  Doctor : Based on your answers, asthma seems less likely.'), nl,
    write('           But I want to rule out one more thing related to the lungs.'), nl.

disease_not_confirmed(tuberculosis) :-
    nl,
    write('  Doctor : The answers do not strongly point to tuberculosis.'), nl,
    write('           However, please do get a chest X-ray to be safe.'), nl.


% --- Doctor delivers the confirmed diagnosis ---
% Wording changes based on how strong the match was.

print_diagnosis(Disease, Questions, Count, Threshold) :-
    collect_matched_facts(Questions, MatchedFacts),
    confidence_message(Count, Threshold, ConfMsg),
    nl,
    write('  Doctor : Thank you for your patience with all those questions.'), nl,
    format('           ~w~n', [ConfMsg]),
    format('           this appears to be ~w.~n', [Disease]),
    nl,
    write('  Doctor : The symptoms that led me to this conclusion are:'), nl,
    print_symptom_list(MatchedFacts),
    nl,
    write('  Doctor : I want to be clear — this is not a confirmed diagnosis.'), nl,
    write('           Please follow up with a specialist and run proper lab tests.'), nl,
    write('           They will give you a definitive answer.'), nl.


% --- Confidence wording based on match strength ---

confidence_message(Count, Threshold, 'Based on the strong match across several symptoms,') :-
    Count > Threshold.

confidence_message(Count, Threshold, 'Based on the symptoms you have described,') :-
    Count =:= Threshold.

confidence_message(_, _, 'Based on what you have shared,').


% --- Print each matched symptom on its own line ---

print_symptom_list([]).
print_symptom_list([Symptom|Rest]) :-
    format('             - ~w~n', [Symptom]),
    print_symptom_list(Rest).


% --- When the entire relevant disease list is exhausted ---
% This is the graceful close. The doctor does not jump to
% unrelated diseases. They acknowledge they could not find it
% and advise seeing a specialist.

no_diagnosis_found :-
    nl,
    write('  Doctor : I have checked everything that your symptoms could'), nl,
    write('           reasonably point to, and I was not able to confirm'), nl,
    write('           a specific condition based on your answers today.'), nl,
    nl,
    write('  Doctor : That does not mean nothing is wrong. Some conditions'), nl,
    write('           only show up in a physical exam or blood tests.'), nl,
    write('           Please book an appointment at a clinic soon.'), nl,
    write('           They will be able to examine you properly.'), nl.
