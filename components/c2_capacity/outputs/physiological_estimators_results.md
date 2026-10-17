# C2 physiological state estimators (CATSA and WESAD), preliminary results

**Status: PRELIMINARY, public lab data. These estimate single latent states (mental effort, stress), not the capacity label.**
Notebooks: `notebooks/10_wesad_stress_hrv.ipynb`, `notebooks/11_catsa_cognitive_load.ipynb`. Each data set is used on its own and never merged. Windows are 60 seconds with a 30 second step. People are never split between train and test. Shuffled-label controls are in the CSV files in `outputs/pilot_runs/`.

## Results (people held out, 5-fold participant-grouped CV, 10 layouts)
| Data set | Target | Features | Model | AUC | Balanced acc | F1 |
|---|---|---|---|---|---|---|
| WESAD (15 people) | stress vs non-stress | HR/HRV raw | LR | 0.96 | 0.89 | 0.78 |
| WESAD | stress vs non-stress | HR/HRV person-normalised | RF | 0.93 | 0.85 | 0.74 |
| WESAD | baseline vs stress only | HR/HRV person-normalised | RF | 0.92 | 0.84 | 0.79 |
| WESAD | stress vs non-stress | + EDA and temperature (lab ceiling) | RF | 0.99 | 0.93 | 0.89 |
| CATSA (50 people) | task vs baseline | HR/HRV raw | LR | 0.66 | 0.62 | 0.72 |
| CATSA | task vs baseline | HR/HRV person-normalised | LR | 0.74 | 0.68 | 0.79 |
| CATSA | task vs baseline | + EDA and temperature (lab ceiling) | RF | 0.89 | 0.79 | 0.90 |

Majority baseline: AUC 0.50, balanced accuracy 0.50 (accuracy alone is misleading because one class is 78 to 80% of rows).

## What the data show
- WESAD: heart rate rises about 14 bpm under stress (73.6 to 87.4 bpm); meditation 71.0, amusement 74.0. Stress is strong and clear, so raw heart signals work from day one and a personal baseline adds nothing.
- CATSA: the effect of a mental task is small (about +3 bpm). A personal baseline helps here (AUC 0.66 to 0.74).
- Wrist HRV (RMSSD) rose under stress and under tasks in both data sets, the opposite of the textbook direction. Likely cause: movement noise in wrist photoplethysmography. Heart rate is the reliable marker; HRV direction should not be interpreted.

## New-user (cold start) curve for the CATSA model, 50 people
| History available | AUC | Balanced acc |
|---|---|---|
| 0 (population average) | 0.64 | 0.58 |
| 3 windows | 0.68 | 0.64 |
| 10 windows (about 5 minutes) | 0.73 | 0.67 |
| 25 windows (full baseline) | 0.74 | 0.68 |

## Limits (state them)
Lab tasks, wrist Empatica E4, small groups (15 and 50 people), CATSA condition order not documented, windows overlap, person-normalisation uses each person's own windows, no everyday life. Outputs are a physiological stress load and a mental-effort estimate, not a diagnosis. The capacity band (High, Moderate, Low, At Risk) still has no public ground truth and remains a provisional rule engine.

## Real working life: nurses on shift (notebook 12), preliminary
Data: 15 nurses, about 1,350 hours of real shifts, wrist Empatica E4, stress level (0, 1, 2) reported by the nurse on a phone survey after an event (CC0, Zenodo 5514277). Survey times line up with the sensor clock as US Central time (322 of 358 events have sensor data). 2,093 one-minute windows from 217 events. Nurses held out in every test; shuffled-label controls in `outputs/pilot_runs/nurses_stress_results.csv`.

| Test | Features | AUC | Balanced acc | F1 |
|---|---|---|---|---|
| High stress (2) vs no stress (0) | heart rate + movement (raw) | 0.55 | 0.53 | 0.68 to 0.79 |
| same | heart rate vs the nurse's own usual + movement | 0.55 | 0.52 to 0.54 | 0.68 to 0.78 |
| same | + heart-rate variability | 0.56 | 0.54 | 0.68 to 0.79 |
| same | + EDA and temperature | 0.49 | 0.47 to 0.49 | 0.67 to 0.78 |
| Stress episodes (1 or 2) vs ordinary working minutes | heart rate + movement | 0.53 to 0.56 | 0.52 to 0.55 | n/a |

Average heart rate was 87.7 bpm in no-stress events, 86.1 in level 1 and 86.1 in level 2: no difference. **In real working life, wrist heart rate and movement did not separate self-reported stress from no stress (AUC about 0.55, barely above the shuffled control at about 0.49).** This contrasts with the lab (WESAD AUC 0.96). Possible reasons, not proven: noisy after-the-fact self-reports, events flagged by the study itself, physically active hospital work, chronic rather than acute stress. Conclusion: heart rate alone is not enough for everyday stress detection; C2 needs several signals, a personal baseline and an objective behavioural measure, and its capacity layer must be validated on its own working-student data.
