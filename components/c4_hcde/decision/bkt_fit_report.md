# BKT fit report (simulated attempt log)

10800 attempts by 300 students on 9 skills (3 domains x 3 difficulty levels); 20% of students held out. Fitted with pyBKT, seed 7.

## Prediction on held-out students

| Model | AUC | RMSE |
| --- | --- | --- |
| assistance-aware BKT | 0.7427 | 0.4264 |
| standard BKT | 0.6243 | 0.4531 |

## Fitted parameters per assistance tier (true value in brackets)

| Tier | Guess | Slip | Learn |
| --- | --- | --- | --- |
| PROBE | 0.106 (0.15) | 0.22 (0.2) | 0.013 |
| HUMAN_FIRST | 0.174 (0.2) | 0.103 (0.1) | 0.174 |
| HINT | 0.513 (0.45) | 0.126 (0.1) | 0.163 |
| GUIDED | 0.63 (0.6) | 0.132 (0.1) | 0.017 |
| SHARED | 0.834 (0.8) | 0.103 (0.1) | 0.001 |
| EMERGENCY | 0.943 (0.97) | 0.018 (0.02) | 0.01 |

| Difficulty | Prior (true) |
| --- | --- |
| easy | 0.402 (0.45) |
| medium | 0.234 (0.3) |
| hard | 0.157 (0.15) |

Mean absolute error of the recovered guess parameters: 0.037.
