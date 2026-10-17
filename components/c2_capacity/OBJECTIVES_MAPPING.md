# C2 objectives mapping (for Progress Presentation 1)

Honest status of each submitted objective against the work done so far. Status: Done, Partial, Planned.

## Main objective
Personalized capacity manager that compares readiness with planned workload and personal baseline, gives an explainable recommendation, and leaves the final decision to the user.

| Element | Status | Where |
|---|---|---|
| Readiness vs planned workload | Done (prototype) | `demo/` task requirement (Light 35, Standard 55, Demanding 70) and mismatch rule |
| Personal baseline | Done (prototype) | z-score against the person's own mean and spread, never a population norm |
| Explainable | Done | Top drivers with share of strain, "How this estimate was made" |
| User decides | Done | Accept, Edit, Reject, stored in Decisions |
| Evaluated with real users | Planned | See evaluation plan below |

## Specific objectives

| # | Objective | Status | Evidence now | Remaining |
|---|---|---|---|---|
| 1 | Identify factors (energy, focus, motivation, stress, fatigue, recovery, sleep, workload, interruptions) | Partial | Factor table below; demo covers sleep, activity, break proxy, night phone use, interruptions (app switches), optional heart rate, focus check, optional energy/motivation/stress check-in, task difficulty | Literature support for each row (citations) |
| 2 | Personalized model, High / Moderate / Low / At Risk | Partial | Baseline-deviation engine with transparent weights and 4 bands, plus capacity-vs-task mismatch rule | Weights and cut-offs are provisional. Calibrate and validate on working-student data |
| 3 | Behavioural and physiological support, no diagnosis | Mostly done | StudentLife and SWELL-KW explored (weak, honest results); no medical claims in the interface | Own data to confirm which signals help |
| 4 | Explainable recommendation, Accept / Edit / Reject | Done (prototype) | `demo/` Today tab | Persist to a backend, real sensing on Android |
| 5 | Accuracy, precision, recall, F1, confusion matrix; SUS and NASA-TLX | Partial | Metric pipeline run on public data (proxy labels, not capacity). SUS and NASA-TLX forms built (Evaluation tab) | Capacity metrics need own labelled data. Run SUS and NASA-TLX in the study |
| 6 | Compare with standard productivity approach, acceptance and feedback | Planned | Decision records and evaluation forms exist | Run the study |

## Factor table (Objective 1)

| Factor | Latent or direct | Proxy used by C2 | Source |
|---|---|---|---|
| Sleep | Direct | Sleep duration vs own usual | Health Connect sleep sessions |
| Recovery | Latent | Sleep, resting heart rate, break gaps | Health Connect, steps |
| Fatigue | Latent | Reaction-time slowing, variability, drift in the focus check | In-app focus check |
| Focus | Latent | Misses, premature responses, accuracy, variability | In-app focus check |
| Energy | Latent | Activity level, sleep and recovery signals | Health Connect |
| Motivation | Latent | No reliable sensor. Not estimated directly. Inferred only through the task and engagement records of the other components | Other components |
| Stress | Latent | Resting heart rate and heart rate variability against own usual, phone use at night | Health Connect, usage access |
| Interruptions | Direct (proxy) | App switches per hour (counts only, no content) | UsageStatsManager |
| Workload demand | Direct | Task and difficulty received from C1 | C1 |

Latent states are never read directly from a phone; they are estimated from signals and shown with a confidence level.

## Note on design versus proposal
The proposal names self-reported readiness factors. The prototype estimates them from sensed signals and a short behavioural check, and does not ask the student to fill in ratings; the pilot study uses a self-rating only as the research label. This follows the proposal wording that behavioural and physiological data support the estimate, and it avoids relying on repeated questionnaires.

## Evaluation plan (Objectives 5 and 6)
- Participants: working university students, ethics approval and informed consent before any data is collected.
- Design: within-subject. Each participant uses Anchor Capacity and a standard productivity routine (for example a to-do list with a timer) in counterbalanced order, over several weeks to build baselines.
- Labels for model validation: perceived capacity rating, task outcome, behavioural performance in the focus check, collected repeatedly per person. Splits grouped by participant.
- Model metrics: accuracy, precision, recall, F1, confusion matrix (not accuracy alone), against a Logistic Regression baseline and Random Forest.
- User measures: SUS, NASA-TLX, recommendation responses (accept, edit, reject), perceived usefulness, feedback.
- Limits to state: small sample, short period, provisional thresholds until calibrated.
