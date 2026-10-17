# Model 1 on CESAW — REAL (CESAW, professional developers)

External validation of Model 1 on real estimation errors. Limitation: these are professional software developers, not students, and CESAW has no priority or task type (every task is `Digital`, `Medium`). Data: CESAW (SEI/CMU), not committed (licence not stated).

- Tasks in the file: 61817; kept 60284 from 247 developers.
- Dropped: plan ≤ 0: 692; actual ≤ 0: 0; no readable start time: 841.
- Real log(actual ÷ estimate): mean -0.206, median -0.060, sd 1.069.
- Model: quantile forest, 50 trees (production default 200), point = q50 (median). **Earned-trust gate:** a developer's estimates are corrected only if, on their 20 most recent training tasks, the model beat B0 by 5% (at least 5 tasks); otherwise drift 1.0 (their own estimate).
- Warm evaluation: seeded sample of 40 developers with ≥ 20 working days, one origin per 30 of their days. Cold start covers every developer: 10 seeded groups of developers, each held out in turn (none of a developer's own tasks in training).

## Summary: does the gate close the gap to B0?

| Part | Model before gate (mean, no gate) | Model with gate + median | B0 drift = 1.0 | Gate open (model corrects) |
|---|---|---|---|---|
| Cold start MAE minutes | 80.20 | 75.04 | 75.04 | 0.0% of predictions |
| Warm MAE minutes | 82.00 | 75.88 | 76.57 | 27.2% of predictions |

**The gate fell back to B0 for most predictions:** on the warm evaluation it let the model correct only 27.2% of predictions (18 of 40 developers at least once; 22 never). That is a valid finding: on these real, noisy estimates the model rarely proved it beats the developer's own estimate, and the gate kept the plan at the estimate instead of making it worse.

In cold start the gate is always closed (a developer with no history has proven nothing), so the model equals B0 there by design.

Where the gate was open (warm, 3624 predictions): model 66.98 min vs B0 69.53 min on the same tasks.

## Cold start — developers held out in groups (n = 0) (with gate + median)

| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n | gate open (predictions) | developers: gate open / closed |
|---|---|---|---|---|---|---|
| model | 75.04 | 0.760 | 0.740 | 60284 | 0.0% | 0 open / 247 closed |
| B0 drift = 1.0 | 75.04 | 0.760 | – | 60284 | no gate | no gate |
| B1 global mean | 75.41 | 0.769 | – | 60284 | no gate | no gate |
| B2 per-student mean | 75.41 | 0.769 | – | 60284 | no gate | no gate |
| B3 shrinkage only | 75.41 | 0.769 | – | 60284 | no gate | no gate |

Developers open / closed = the gate's state at each developer's last evaluation point (cold start: their only point). Baselines have no gate.


## Warm — rolling-origin (sampled developers) (with gate + median)

| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n | gate open (predictions) | developers: gate open / closed |
|---|---|---|---|---|---|---|
| model | 75.88 | 0.767 | 0.733 | 13322 | 27.2% | 11 open / 29 closed |
| B0 drift = 1.0 | 76.57 | 0.776 | – | 13322 | no gate | no gate |
| B1 global mean | 77.65 | 0.787 | – | 13322 | no gate | no gate |
| B2 per-student mean | 84.48 | 0.821 | – | 13322 | no gate | no gate |
| B3 shrinkage only | 78.85 | 0.790 | – | 13322 | no gate | no gate |

Developers open / closed = the gate's state at each developer's last evaluation point (cold start: their only point). Baselines have no gate.


## Learning curve (warm, model with gate + median)

| Developer's records seen | MAE minutes | n |
|---|---|---|
| 0–0 | – | 0 |
| 1–4 | 105.93 | 1973 |
| 5–9 | 74.49 | 113 |
| 10–19 | 31.95 | 198 |
| 20–39 | 33.10 | 44 |
| 40+ | 71.46 | 10994 |

## Before gate (run of 15 Oct 2026: mean point, no gate)


External validation of Model 1 on real estimation errors. Limitation: these are professional software developers, not students, and CESAW has no priority or task type (every task is `Digital`, `Medium`). Data: CESAW (SEI/CMU), not committed (licence not stated).

- Tasks in the file: 61817; kept 60284 from 247 developers.
- Dropped: plan ≤ 0: 692; actual ≤ 0: 0; no readable start time: 841.
- Real log(actual ÷ estimate): mean -0.206, median -0.060, sd 1.069.
- Model: quantile forest, 50 trees (production default 200). Warm evaluation: seeded sample of 40 developers with ≥ 20 working days, one origin per 30 of their days. Cold start covers every developer: 10 seeded groups of developers, each held out in turn (none of a developer's own tasks in training).

### Cold start — developers held out in groups (n = 0)

| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n |
|---|---|---|---|---|
| model | 80.20 | 0.792 | 0.738 | 60284 |
| B0 drift = 1.0 | 75.04 | 0.760 | – | 60284 |
| B1 global mean | 75.41 | 0.769 | – | 60284 |
| B2 per-student mean | 75.41 | 0.769 | – | 60284 |
| B3 shrinkage only | 75.41 | 0.769 | – | 60284 |

### Warm — rolling-origin (sampled developers)

| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n |
|---|---|---|---|---|
| model | 82.00 | 0.790 | 0.728 | 13322 |
| B0 drift = 1.0 | 76.57 | 0.776 | – | 13322 |
| B1 global mean | 77.65 | 0.787 | – | 13322 |
| B2 per-student mean | 84.48 | 0.821 | – | 13322 |
| B3 shrinkage only | 78.85 | 0.790 | – | 13322 |

### Learning curve (warm, model)

| Developer's records seen | MAE minutes | n |
|---|---|---|
| 0–0 | – | 0 |
| 1–4 | 111.21 | 1973 |
| 5–9 | 77.30 | 113 |
| 10–19 | 34.61 | 198 |
| 20–39 | 37.07 | 44 |
| 40+ | 77.83 | 10994 |
