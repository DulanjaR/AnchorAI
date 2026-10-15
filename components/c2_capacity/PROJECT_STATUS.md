# C2 Human Capacity Preservation Manager: project status (handoff note)

Last updated: 2026-10-15. Branch `dev/hirunya`. Work only inside `components/c2_capacity/`.

## Design principle
Sensing-first, not self-report-driven. Inputs: sleep, activity, break proxies, screen/app use, optional heart rate, plus a short behavioural focus check (reaction time, variability, misses, premature responses, accuracy, drift). Task difficulty is the only task context. Everything is compared with the person's own baseline. No medical claims. AI recommends, the user accepts, edits or rejects.

## Done
- StudentLife pipeline: notebooks 01 to 05 (inspect, daily features, model table, models, robustness). Result: weak, unstable stress signal (AUC about 0.55 to 0.63).
- SWELL-KW pipeline: notebooks 06 to 08 (inspect, models, confound controls). Result: AUC 0.86 is a design artifact (neutral is always Block 1; block order alone gives AUC 1.0). Order-balanced T vs I test is near chance.
- Results and limitations: `outputs/studentlife_preliminary_results.md`, `outputs/swell_preliminary_results.md`.
- Demo front end: `demo/index.html` (single file, open in a browser). Simulated context signals, real focus check, baseline-deviation engine, tide-gauge result, accept/edit/reject. Thresholds are provisional.

## Not done (next)
1. Commit and push the `demo/` folder and this file (not yet committed at the time of writing).
2. Milestone report and slides (English). Viva script.
3. Own working-student data collection design: counterbalanced order, repeated measures per person, label definition (perceived capacity, task outcome, behavioural performance), ethics and consent.
4. Optional: SWELL `R` baseline test (check what `R` means in the ICMI 2014 paper); StudentLife time-trend control.
5. Later: Android sensing through Health Connect (Google Fit APIs are being retired) and UsageStatsManager; backend and database.

## Rules to keep
- StudentLife and SWELL-KW are never merged. Public data is for pipeline and feature exploration, not validation.
- No invented labels or synthetic data mixed into real rows. The demo's simulated persona data is labelled as simulated.
- Participant id is never a feature. Participant-grouped splits only.
- Raw data and model files stay out of Git (see `.gitignore`).
