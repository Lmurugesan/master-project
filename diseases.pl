% ============================================================
% diseases.pl
% Every disease the system can diagnose.
%
% Format:
%   disease( Name, Threshold, [ 'Question text|fact_name', ... ] )
%
% Threshold = how many yes answers needed to confirm.
% The | separates question text from the fact atom name.
%
% To add a new disease:
%   1. Add a disease(...) block here.
%   2. Add its related diseases in rules.pl.
%   3. Done. No other file needs to change.
% ============================================================


disease(diabetes, 3, [
    'Have you been told your blood sugar or glucose is high?|elevated_glucose',
    'Have you had a blood test showing high HbA1c?|high_hba1c',
    'Are you urinating much more often than usual?|polyuria',
    'Are you feeling extremely thirsty most of the time?|polydipsia',
    'Are you feeling unusually tired or fatigued?|fatigue'
]).

disease(hypertension, 2, [
    'Have you ever been told you have high blood pressure?|history_of_hypertension',
    'Are you currently on any blood pressure medication?|on_bp_medication',
    'Have you had high blood pressure readings recently?|elevated_bp',
    'Do you get frequent headaches, especially in the morning?|hypertension_headache'
]).

disease(anemia, 2, [
    'Do you feel unusually weak or tired most of the time?|fatigue',
    'Has anyone noticed your skin looks pale lately?|pale_skin',
    'Do you feel dizzy or lightheaded when you stand up?|dizziness'
]).

disease(uti, 2, [
    'Do you feel pain or burning when you urinate?|dysuria',
    'Do you need to urinate much more often than usual?|urinary_frequency',
    'Do you get sudden, hard-to-control urges to urinate?|urinary_urgency',
    'Do you feel pressure or pain in your lower abdomen?|suprapubic_pain'
]).

disease(asthma, 2, [
    'Do you have a recurring cough that gets worse at night?|chronic_cough',
    'Do you feel tightness or pressure in your chest?|chest_tightness',
    'Do you wheeze or hear a whistling sound when you breathe?|wheezing',
    'Does cold air or exercise make your breathing worse?|exercise_triggered'
]).

disease(tuberculosis, 2, [
    'Have you had a cough lasting more than three weeks?|persistent_cough',
    'Do you cough up blood or blood-stained mucus?|coughing_blood',
    'Do you sweat heavily at night even when it is not hot?|night_sweats',
    'Have you lost weight recently without trying?|unexplained_weight_loss',
    'Have you been in close contact with anyone who had TB?|tb_exposure'
]).
