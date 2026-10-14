# Human Capacity Manager (Capacity)

Owner: TBD. Keep all code for this component inside this folder; import common code from `shared/`.

## Workspace layout

- `data/` - dataset copies, `studentlife/` and `swell_kw/` kept separate
- `notebooks/` - Colab/Jupyter notebooks
- `models/` - saved models (later)
- `outputs/` - results, tables, plots
- `src/` - reusable Python code

Focus: estimating a working student's current readiness/capacity for mentally
demanding work (sleep, fatigue, focus, stress, recovery, activity, recent break,
behavioural attention indicators). StudentLife and SWELL-KW are never merged.

## Design principle: sensing-first, not self-report-driven

Inputs are primarily automatically collected or objectively measured signals
(sleep records, activity/steps, inactivity/break proxies, screen/app usage,
optional heart-rate trends) plus a short behavioural task (reaction time,
variability, misses, premature responses, accuracy, attention drift). Task
difficulty is the only task-context input. Energy, focus, stress, fatigue and
recovery are latent states **estimated** from these signals, never read
directly from the phone. Each user is compared with their own baseline. No
medical or diagnostic claims. AI recommends; the user accepts, edits or rejects.

## Status (preliminary)

StudentLife pipeline (notebooks 01-05) is done; results are weak and
preliminary, see `outputs/studentlife_preliminary_results.md`. SWELL-KW and our
own working-student data are still to do.
