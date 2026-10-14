# C2 - SWELL-KW preliminary experiment (results and limitations)

**Status: PRELIMINARY. Pipeline practice only. Not validation of C2.**
Notebooks: `notebooks/06_swell_inspection`, `07_swell_model_table_and_models`, `08_swell_confound_controls`. SWELL-KW is used on its own and never merged with StudentLife.
Source: SWELL Knowledge Work Dataset, DOI 10.17026/DANS-X55-69ZP (DANS), licence CC-BY-NC-SA-4.0. Cite Koldijk et al., ICMI 2014.
Derived tables, figures and CSVs are in the group Drive folder `AnchorAI_c2_outputs`, not in Git.

## Data used
Only C2-relevant files: A (computer interaction per minute: mouse/keyboard/app switching), D (heart rate, HRV `RMSSD`, skin conductance `SCL`), plus the overview, questionnaire and behavioural-feature files for inspection. Face and Kinect posture were not used (not available from a phone).
Data-quality findings: HR and RMSSD use `999` for "no valid value" (52.5% of minutes, converted to missing); 7 truncated timestamps in file D; 2 cells with `#VALUE!` in `SnMouseDistance`; participants PP8 and PP11 have almost no valid HR.

## Design facts discovered (important)
- 25 people, 3 blocks each. Every block starts with a short `R` period (meaning not confirmed).
- **Neutral (N) is always Block 1.** Time pressure (T) and email interruptions (I) are in Blocks 2 and 3, counterbalanced across people (13 did I then T, 12 did T then I).
- Self-report ratings (stress, NASA-TLX, mental effort) exist only once per block, i.e. 75 labelled blocks in total.

## Target used (a work-condition label, NOT a C2 capacity label)
`y_pressure = 1` for T or I, `0` for N (R excluded).

## Results
| Experiment | Result |
|---|---|
| Step 7, N vs T/I, all features, Random Forest, grouped CV | AUC 0.864 (looked strong) |
| **E1: `Blok` alone or minutes-since-start alone** | **AUC 1.000** |
| E2: T vs I only (order counterbalanced), `Blok`-only control | AUC 0.356 (below chance: balanced-design artifact) |
| E2: T vs I, all features (RF) | AUC 0.578, not clearly above chance |
| E2: T vs I, computer features without app-switching | AUC 0.508 (chance) |
| E2: T vs I, physiology only | AUC 0.43 to 0.49 (chance) |
| E2: T vs I, personal-baseline `dev_` only (RF) | AUC 0.608, marginal and inconclusive |
| E4: N vs T, no app-switching features (RF) | AUC 0.876, but the order-only control is 1.000 |

## Honest conclusion
The strong N-vs-pressure scores in step 7 are explained by the study design: neutral is always the first block, so session order alone separates it perfectly. They cannot be read as stress or capacity detection. The only order-free comparison (T vs I) shows no reliable difference from phone/PC/physiology features (the single marginal result is `dev_` at AUC about 0.6). Interruptions are visible mainly as app switching, which restates the experimental manipulation.

## Limitations (must be in the report)
- 25 people, 75 labelled blocks, one lab study; not working students; labels are experimental conditions, not capacity.
- N cannot be compared fairly with T/I in this dataset because of the fixed block order.
- HR is unusable for about half of the minutes; participant coverage is uneven.

## Possible next test (not done)
The `R` period occurs at the start of every block. If it is confirmed as a rest period (check the ICMI 2014 paper), deviations from each block's own `R` baseline would remove the order drift and give a fairer test of the personal-baseline idea.
