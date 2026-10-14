# C2 - StudentLife preliminary experiment (results and limitations)

**Status: PRELIMINARY. Pipeline practice only. Not validation of C2.**
Notebooks: `notebooks/01` to `05` (StudentLife only; never merged with SWELL-KW).
Large files (model, CSV tables, figures) are in the group Google Drive folder `AnchorAI_c2_outputs`, not in Git.

## What was done
1. **01 inspection** - listed files/columns/participants of the C2-relevant StudentLife sources only (phone lock, dark, charging, activity, app usage, EMA stress/sleep, PSS/PSQI/PANAS surveys). Everything else was excluded on purpose (GPS, audio, calls, SMS, calendar/deadlines (C1 overlap), clinical scales).
2. **02 daily features** - participant-by-day table (49 participants, 3,150 days). A sleep proxy from dark+locked intervals was built and **rejected**: Spearman 0.098 vs reported sleep (785 days).
3. **03 model table** - one row per EMA stress answer, using phone data only from the **24 h before** the answer (no leakage), plus personal-baseline deviation features (`dev_*`). 1,159 answers, 47 participants, 18 features. Participant-grouped split (37 train / 10 test).
4. **04 models** - Logistic Regression and Random Forest vs a majority baseline.
5. **05 robustness** - 4 feature sets x 5 grouped-CV layouts x 5 folds, with a shuffled-label control.

## Target used (a StudentLife stress label, NOT a C2 capacity label)
`y_stressed = 1` for EMA stress answers 2-3 ("Definitely stressed", "Stressed out"); `0` for 4-5 ("Feeling good", "Feeling great"); answer 1 ("A little stressed") excluded as ambiguous. Class balance 597 / 562.

## Key numbers
| Check | Result |
|---|---|
| Step 4, grouped CV (5 folds), Random Forest | F1 0.625, ROC-AUC 0.628 |
| Step 4, grouped CV, Logistic Regression | F1 0.559, ROC-AUC 0.564 |
| Step 4, fixed 10-person test split | about chance (RF AUC 0.487, LR 0.417) |
| Shuffled-label control | AUC about 0.50 (no leakage) |
| Step 5, A all 18 features, RF | AUC 0.629 +/- 0.054 (clearly above chance) |
| Step 5, B without coverage features, RF | AUC 0.557 (NOT clearly above chance) |
| Step 5, C raw features only, RF | AUC 0.523 (no) |
| Step 5, D personal-baseline `dev_*` only, RF | AUC 0.591 +/- 0.057 (above the control, but marginal) |

"Clearly above chance" rule (fixed before looking): mean AUC > shuffled mean + 2 x shuffled std.

## What this means (honest reading)
- Phone-only features give a **weak** stress signal at best (AUC about 0.55-0.63). It is **unstable**: it changes with which people are held out.
- The best-looking result (set A) depends partly on **coverage** features (`act_n`, app counts), which describe how much data was collected, not behaviour. Without them the signal mostly disappears.
- The most interesting result: features that compare a person with **their own earlier baseline** (`dev_*`) hold more signal than raw features. This weakly supports the C2 design idea of personal baselines, but it is **not proof**.
- Caution: `dev_*` features may also pick up a **time trend** across the term (people change over weeks). A control with a "days since first answer" feature is still to be done.
- A model file (`c2_prelim_studentlife_model.joblib`, Random Forest on all features) exists on Drive as a **prototype only**. Because it uses coverage features, it should not be reused without retraining.

## Limitations (must be stated in the report)
- Public data, university students at one US college, not working students. Target = stress, not capacity or readiness.
- Self-reported EMA answers are the only labels. Sleep is only a proxy. No steps, heart rate or reaction-time data exist in StudentLife.
- Small data: 47 people, very uneven answers per person (2 to 121). Small test set (10 people, 151 rows).
- The 1-5 stress codes are not one ordered scale; the binary mapping above is a documented choice.
- Time zone assumed `America/New_York`; activity codes 0-3 are not yet interpreted (check the StudentLife paper).

## Next steps
1. Optional control: time-trend feature check for `dev_*`.
2. SWELL-KW as a **separate** experiment (data still to be downloaded; see `data/swell_kw/README.md`).
3. The decisive part for C2: collect **own working-student data** (Part B behavioural task, context signals, self-reported capacity and task outcomes) and define/validate the final High / Moderate / Low / At Risk labels there.
4. Backend/DB and phone sensing (Health Connect, UsageStats) are later work and not needed for this milestone.
