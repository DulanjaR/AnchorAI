# Task 4 plan — ML Model 1 (Timeline Drift Predictor) on SYNTHETIC data

> **SUPERSEDED 14 Oct 2026** by the Model 1 redesign (`docs/METHODOLOGY.md` §3, DECISIONS.md 2026-10-14). Kept for the record.
>
> **DRAFT.** Copied unchanged from the old project (`anchor-ai-component1/docs/TASK4_PLAN.md`,
> 12 Oct 2026) during the port to the team repo. The body below is **not** up to date.
> Changes approved by the owner after it was written, which the next version of this
> plan must include:
>
> 1. **Third baseline:** per-student average drift (each student's own mean drift from
>    the training weeks), next to Baseline A (drift = 1.0) and Baseline B (one shared
>    average drift).
> 2. **No test-week leakage**, with a test that proves it: nothing from week 4 (including
>    the user-level feature and the baselines) may be computed from test-week records.
> 3. **Layered persona approach** for the synthetic data: layer A planned tasks, B actual
>    durations, C disruptions, D MVDs. The personas come from the owner's persona document,
>    not from the S01–S10 table in section 3.
> 4. **Google Colab notebooks** for the experiments (`notebooks/`, first cell clones the
>    `dev/ravindu` branch and installs C1's requirements).
>
> Paths: `ml-service/app/drift/` → `components/c1_disruption/ml/drift/`, served by the one
> C1 FastAPI app (`app/main.py`); `ml-service/data/` → `ml/data/`. Pins live in
> `components/c1_disruption/requirements.txt`.

> PLAN for owner approval, 12 Oct 2026. No code is written until it is approved.
> Everything produced in Task 4 is **SYNTHETIC**: it shows the pipeline works,
> it is **not** a research finding (CLAUDE.md rule 6).

## 1. Pin dependencies

`ml-service/requirements.txt` gets exact versions (`==`). New packages, at the
current releases (checked with `pip index versions` today):

| Package | Version | Why |
|---|---|---|
| scikit-learn | 1.9.1 | RandomForestRegressor |
| pandas | 3.0.6 | tables for the synthetic logs |
| numpy | 2.5.4 | random numbers, maths |
| joblib | 1.6.0 | save / load the trained model (already a scikit-learn dependency; pinned explicitly) |

Already installed, pinned at what the venv has now: fastapi 0.142.2, uvicorn 0.54.0,
httpx 0.28.1, pytest 9.1.1, pydantic 2.13.5. After installing, I run `pip freeze`
and pin the full list (including indirect packages) in `requirements.lock.txt`,
so the results can be reproduced exactly. Python 3.13.3.

## 2. Starting values: `ml-service/data/pretest_priors.json`

```json
{
  "status": "PROVISIONAL",
  "source": "Defaults, NOT survey data. Replace when the final pre-test CSV arrives (CLAUDE.md §3.8).",
  "starting_drift": { "Digital": 1.0, "Analog": 1.0, "Meeting": 1.0, "Fixed": 1.0 },
  "strategy_ranking": null,
  "max_compression": 0.5,
  "synthetic": {
    "tasks_per_day_mean": 4,
    "task_type_mix": { "Digital": 0.40, "Analog": 0.35, "Meeting": 0.15, "Fixed": 0.10 },
    "disruption_overlap_rate": 0.15
  }
}
```

- `starting_drift` = **1.0 for every type**: the CLAUDE.md §3.6 fallback, not an invented value.
  The `/drift` fallback returns this number, so once the survey arrives (C1 Q4–Q5) the
  fallback becomes the survey's value without a code change.
- `strategy_ranking` stays `null` until Task 5. `max_compression` mirrors config.js (0.5)
  and is not read by the engine. EF values are **not** put here: they stay in config.js
  and only change by owner decision.
- `synthetic` = the generator's knobs that the survey can later set (C1 Q2–Q3). Today
  they are my defaults.

## 3. SYNTHETIC generator

`ml-service/app/drift/synthetic.py`, fixed seed, every row has `dataset = "SYNTHETIC"`.

- **10 students (S01–S10) × 28 days (4 weeks, Mon 7 Sep – Sun 4 Oct 2026)**, 3, 4 or 5
  tasks a day (probabilities 0.25 / 0.50 / 0.25, so about 4 a day, about 1,120 tasks in all).
- Each task gets: type (mix above), priority (High/Medium/Low, equal shares), planned
  minutes (Digital 30–240, Analog 30–180, Meeting 30–90, Fixed 60–180, in 15-min steps),
  and a start time between 08:00 and 22:00.
- **True actual minutes = planned × planted drift × noise.** Noise is multiplicative
  log-normal with σ = 0.10 (about ±10%).
- **Disruption overlap:** 15% of tasks overlap a confirmed disruption (15–90 minutes,
  random kind/type). The **recorded** start-to-done span then includes that time:
  recorded = true actual + overlap. This is what the app would really log.
- **Cleaning (CLAUDE.md §3.6):** before training, `clean actual = recorded − overlap`.
  A record is **dropped** if the overlap is more than 50% of the recorded span, or if
  less than 10 minutes would remain (not reliable). Both numbers go in a config file,
  not in the code.

### Planted drift patterns (the hidden truth)

Periods: **morning** = start before 12:00, **afternoon** = 12:00–17:59, **evening** = 18:00 or later.
**Weekend** = Saturday or Sunday.

**For everyone:**

| ID | Pattern |
|---|---|
| G1 | **Meeting** drift = 1.00 (meetings end on time) |
| G2 | **Fixed** drift = 1.00 (lectures and shifts have a set length) |
| G3 | **Digital tasks planned at 180 min or more** run a further **×1.10** (bigger coding tasks are underestimated more) |
| G4 | **Priority has NO effect** (a negative control: the model should not invent one) |

**Per student** (applies to Digital and Analog; the time-of-day and weekend factors multiply the base):

| Student | Digital base | Analog base | Time-of-day / weekend habit |
|---|---|---|---|
| S01 | 1.40 | 1.00 | evening ×1.20 (both types) |
| S02 | 1.10 | 1.30 | morning ×0.85 for Analog (reads best in the morning) |
| S03 | 0.85 | 0.90 | none (over-estimates everything) |
| S04 | 1.60 | 1.20 | weekend ×1.15 (both types) |
| S05 | 1.00 | 1.00 | none (accurate: control student) |
| S06 | 1.25 | 1.50 | evening ×1.25 (both types) |
| S07 | 1.30 | 0.95 | afternoon ×1.10 (both types) |
| S08 | 0.95 | 1.40 | morning ×0.90 (both types) |
| S09 | 1.50 | 1.10 | evening ×1.30 for Digital only |
| S10 | 1.20 | 1.20 | weekend ×0.90 (both types) |

Example: S09, Digital, 200 min planned, Tuesday 19:00 → 1.50 × 1.30 × 1.10 (G3) = 2.145 before noise.

## 4. Model

`ml-service/app/drift/model.py`

- **RandomForestRegressor**, target = **drift = clean actual ÷ planned**.
- Features (CLAUDE.md §3.6): task type (one-hot), planned minutes, start hour, day of week,
  priority score, **plus one user-level feature**: the student's own average drift for that
  task type in the training weeks, shrunk towards the overall average for that type
  (`(n·user_mean + k·type_mean) / (n + k)`, k = 5). This is the "shared model with user-level
  features" from §3.6. A brand-new user simply gets the type average.
- Fixed settings, **no tuning on the test week**: 300 trees, min 5 samples per leaf,
  `random_state = seed`.
- Predicted minutes = planned × predicted drift.

## 5. Experiment

`ml-service/app/drift/experiment.py`

- **Train on weeks 1–3, test on week 4** (time-based split, as in real use).
- **MAE in minutes** on the week-4 tasks (clean actual), for three methods:
  1. **Baseline A, drift = 1.0** (trust the plan)
  2. **Baseline B, average drift** (one number: mean drift of the training weeks)
  3. **RandomForest**
- **5 seeds** (11, 22, 33, 44, 55): each seed makes a new synthetic dataset and a new forest.
  Report **mean ± standard deviation** (and min–max) of the MAE per method, and the RF's
  improvement over each baseline.
- **Extra (cheap, supports the §3.6 rule):** the same RF trained on the *uncleaned* records
  (disruption time left in), so the report shows what the exclusion rule saves.
- Output: `ml-service/reports/drift_experiment_SYNTHETIC.md` and `.json`, every table titled
  SYNTHETIC. The datasets themselves are regenerated from the seeds; only seed 11's CSV is
  committed as an example (`ml-service/data/synthetic_drift_SYNTHETIC_seed11.csv`, about 1,100 rows).

## 6. Does the model recover the planted habits?

For each seed, after training:

1. **Grid check:** for every student × {Digital, Analog} × {morning, afternoon, evening} ×
   {weekday, weekend}, at a fixed planned length (90 min, so G3 is off), compare the model's
   predicted drift with the planted drift (noise-free). **Pass if** mean absolute difference
   ≤ 0.08 **and** Spearman rank correlation ≥ 0.90.
2. **Direction checks** (each must hold): S04 Digital > S03 Digital; S01 evening > S01
   morning; S09 Digital evening > S09 Digital morning but S09 Analog evening ≈ morning
   (within 0.05); S02 Analog morning < S02 Analog afternoon; S10 weekend < S10 weekday;
   Digital planned 200 min > the same task planned 90 min (G3); Meeting and Fixed within
   0.05 of 1.00 (G1, G2).
3. **Negative control:** changing only the priority moves the prediction by less than 0.03 (G4).

These pass thresholds are fixed **now, before any run**. If a check fails, I report it
as failed and explain why; I do not change the thresholds or tune on week 4.

## 7. FastAPI `/drift` endpoint

`POST /drift`, in batches because the backend asks for a whole day of tasks at once:

```json
{ "tasks": [ { "userId": "u1", "taskType": "Digital", "plannedMinutes": 120,
               "start": "19:00", "date": "2026-10-13", "priority": "High" } ] }
```
→
```json
{ "results": [ { "drift": 1.42, "correctedMinutes": 170, "source": "model",
                 "recordsForType": 412 } ],
  "dataset": "SYNTHETIC" }
```

- **Fallback:** if the training data has **fewer than 30 records for that task type**, the
  answer is `drift = starting_drift` from `pretest_priors.json` (1.0 today) with
  `source: "fallback"`. Also used if no trained model file exists. The 30 is a setting, not
  a magic number.
- Unknown user → user feature = the type average (no error).
- Bad input (unknown task type, minutes ≤ 0, bad time) → `422` from FastAPI's validation.
- The trained model is saved as `ml-service/models/drift_model.joblib` (git-ignored; made by
  `python -m app.drift.train`), with a small metadata JSON (records per type, seed, dataset =
  SYNTHETIC, training date) that **is** committed.
- **Out of scope for Task 4:** the Node backend calling `/drift` (that is wiring for later;
  the engine keeps drift = 1.0 until then).

## 8. Tests (pytest)

- Generator: same seed → same data; about 4 tasks a day; every row SYNTHETIC; about 15%
  overlap; the cleaning rule subtracts / drops exactly as specified.
- Model: on seed 11 the RF beats both baselines; the recovery checks of section 6 pass.
- Endpoint: model answer for a well-covered type; fallback for a type with < 30 records
  (tested with a tiny training set); fallback when no model file exists; 422 on bad input;
  `dataset: "SYNTHETIC"` in every answer.
- Priors file loads and says PROVISIONAL.
- The backend's 248 Jest tests are not touched.

## 9. Files

```
ml-service/
├── requirements.txt          pinned (==)
├── requirements.lock.txt     full pip freeze
├── app/
│   ├── main.py               + POST /drift
│   └── drift/
│       ├── settings.py       all tunable numbers (30-record threshold, k = 5, cleaning limits, RF settings)
│       ├── planted.py        the planted patterns of section 3 (hidden truth, used only by the generator and the recovery check)
│       ├── synthetic.py      generator + cleaning rule
│       ├── features.py       feature table (incl. the user-level feature)
│       ├── model.py          train / load / predict with fallback
│       ├── train.py          python -m app.drift.train  → models/drift_model.joblib
│       └── experiment.py     5-seed experiment + recovery checks → reports/
├── data/  pretest_priors.json, synthetic_drift_SYNTHETIC_seed11.csv
├── models/ drift_model.meta.json (model file itself git-ignored)
├── reports/ drift_experiment_SYNTHETIC.md / .json
└── tests/  test_synthetic.py, test_model.py, test_drift_api.py
```

Docs after the work: CLAUDE.md §3.6 (features, threshold source), §7 Task 4 tick;
DECISIONS.md; PROGRESS.md.

## 10. Questions for the owner

1. **User-level feature** = the student's shrunk average drift per task type (section 4). OK,
   or would you rather use a plain student ID (simpler, but it cannot handle new users)?
2. **The 30-record threshold counts records per task type in the shared training data**
   (all users together), as the shared-model approach in §3.6 suggests. OK, or per user?
3. **Cleaning:** drop a record when the overlap is more than 50% of its span, or less than
   10 minutes would remain. OK?
4. **Pass thresholds** in section 6 (≤ 0.08 drift difference, Spearman ≥ 0.90). OK?
