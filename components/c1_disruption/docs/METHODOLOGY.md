# Component 1 methodology (revised 14 October 2026)

Disruption Recovery Planner · Anchor AI (J26-IT-366) · owner @Ravindu912

Written from the owner's methodology brief of 14 Oct 2026. Items marked **PROPOSED**
are definitions Claude Code filled in where the brief left a detail open; they are
configurable, documented in `DECISIONS.md`, and wait for the owner's confirmation.
Everything produced from synthetic data is labelled **SYNTHETIC** and is not a
research finding (CLAUDE.md rule 6).

## 1. What does not change

The MVD engine's rules stay exactly as approved: Fi, the candidate groups, tags by
outcome, reason codes, the hard feasibility gate, window-first placement, the two
disruption kinds, midnight clipping, deadline risk, explanations (CLAUDE.md §3.1–3.3).
The frozen golden spec (`tests/golden/`: S1–S16 and 57 API cases) must keep passing
exactly. **Every new engine parameter defaults to the old behaviour.**

What changes is the ML layer, the logging and the evaluation.

## 2. Engine extensions (defaults = approved behaviour)

| Extension | Default | Status |
|---|---|---|
| Per-task duration as point + optional low/high (`estimatedHoursLow/High`, from Model 1). Fi uses the point. | low = high = point | built (14 Oct) |
| Strategy config `compressRatio` (maximum shortening) | 0.5 (`MAX_COMPRESSION`) | built (14 Oct) |
| Strategy config `deferOrder`, `recoveryTiming` | current behaviour | **definitions pending** |
| Keep time-budget check uses `high` when given | high = point | **definition pending** |
| Overload check for normal days + early deadline warning (separate function, not in the MVD path) | — | PROPOSED scope, §2.1 |
| Plan diff: tags that differ between two plans of the same input | — | built (14 Oct) |
| D-MOVE carry-over of moved tasks | off | **PROPOSED, not implemented** until approved |

### 2.1 Overload check (PROPOSED scope)

For one plan day without a disruption: **available minutes** = work hours from
`planFrom`, minus protected blocks; **planned minutes** = sum of the tasks' corrected
point durations (also reported with `high`). **Slack ratio** = (available − planned) ÷
available; overloaded when planned > available. **Early deadline warning**: tasks due
today are taken in deadline order (earliest first); a task is flagged when the free
time before its deadline (within work hours) is less than the corrected minutes of it
and every earlier-deadline task. Only deadlines on the plan day are checked.

## 3. Model 1 — Timeline Drift Predictor (main ML contribution)

**Question:** how long will this task really take this student?

- **Target:** `y = log(actual ÷ estimated)` (log drift). Regression, not classification.
  0 = on time; +0.405 = 50% over; symmetric for over- and under-runs.
- **Features:** task type, estimated minutes, start hour, day of week (weekend flag),
  priority score.
- **Pooled model:** one Random Forest over all students' records.
- **Per-student shrinkage:** `ŷ = f(x) + w · r̄_s`, with `r̄_s` the student's mean
  residual `y − f(x)` on their own past records and `w = n_s ÷ (n_s + k)`. **k is chosen by
  cross-validation** over a fixed grid. Day-1 students (n = 0) get the pooled `f(x)`.
- **Range:** quantiles q10 and q90 (configurable) of the log drift, from a quantile
  regression forest or equivalent; shifted by the same shrinkage term.
- **Correction used by the engine:** point = `estimate × exp(ŷ)`, low/high from the
  quantiles.
- **Baselines (in code):** B0 drift = 1.0 · B1 global mean log ratio · B2 per-student
  mean log ratio (global when n = 0) · B3 shrinkage only (B1 + `w · r̄_s`, no forest).
- **Evaluation:**
  - *Leave-one-student-out* (cold start): train on all other students, predict the held-out one with n = 0.
  - *Rolling-origin* (warm): for each student, predict day d from days < d (all other students fully available).
  - Measures: MAE in minutes, MAE of the log ratio, interval coverage (share of actuals inside q10–q90; nominal 80%), learning curve (MAE against n).
  - No tuning on test data: k is chosen by cross-validation inside the training fold only.
- **Exclusion rule (9 Oct 2026):** time lost to a confirmed disruption is not task time.
- **Fallback:** model unavailable or untrained → drift = 1.0; the engine keeps working.

## 4. Model 2 — Strategy Personalizer (lightweight)

**Question:** which way of building the MVD will this student accept?

- **Actions** = concrete strategy configs (compress ratio × defer order × recovery
  timing). A **distinctness check** generates MVDs for every action on synthetic
  scenarios and reports, for each pair, how often the plans differ (plan diff); pairs that
  never differ are merged or dropped. Until defer order and recovery timing are defined,
  actions differ in compress ratio only.
- **Policy:** pooled LinUCB with a shared component plus a per-student component
  (one ridge model on `[shared features, student-specific copy]`, so a new student starts
  from the shared part).
- **Context:** disruption kind, severity, time-of-day bucket, share of digital tasks,
  slack ratio, weekday/weekend, student history (past acceptance rate, number of past
  events).
- **Reward:** Accept = 1 · Reject = 0 · Edit = 1 − (tags changed ÷ total tags)
  (**PROPOSED**, owner to confirm).
- **Baselines:** fixed order · per-student most-accepted counter · random.
- **Policy modes:** `fixed_order` (default; pilot week 1) · `bandit` · `randomised` (per
  event, show the bandit or the fixed ranking at random, and log which).

## 5. Metrics (PROPOSED definitions; `metrics/`)

| Metric | Definition |
|---|---|
| **Critical task** | priority High **and** due today or tomorrow (`DEADLINE_RISK_DAYS`) |
| **CTRR planned** | critical tasks placed (Keep or Reduce) in the MVD ÷ critical tasks |
| **CTRR realised** | critical tasks completed (`done`) on the day ÷ critical tasks |
| **PTVR** | placed tasks overlapping a protected block ÷ placed tasks; must be 0 (checked on every generated plan) |
| **Feasibility** | placed tasks whose slot holds their required minutes (after the allowed compression) ÷ placed tasks, required = raw estimate or corrected point; reported raw vs corrected for the **same event** |
| **Realised feasibility** | placed tasks whose actual minutes ≤ slot minutes ÷ placed tasks with an actual |
| **Plan completion rate** | placed tasks completed (`done`) ÷ placed tasks |
| **Decision-change rate** | tags that differ between the model-off and model-on MVD of the same event ÷ tasks (plan diff) |
| **Acceptance** | accepted ÷ decided (also reported: accepted or edited ÷ decided) |
| **Edits per MVD** | tasks changed per edited MVD (and per decided MVD) |
| **Time-to-decision** | `decidedAt − createdAt`, seconds |
| **Tight slack** | slack ratio < `TIGHT_SLACK_THRESHOLD` (config, **0.10**, fixed before analysis) |
| Carry-over placement rate, post-move deadline misses | after D-MOVE is approved |

## 6. Logging

- **Per MVD:** ranking shown, policy mode, model on/off, strategy config used, tags,
  Accept / Edit / Reject, structured edit diff (which tags changed), time-to-decision,
  whether a manual replan was done first.
- **Per task:** estimated, corrected (point / low / high), actual, completion status.

All inside C1's own records (repository collections); no shared database change.

## 7. Synthetic simulation (SYNTHETIC only)

Layered: **A** planned tasks (persona task lists from the owner) → **B** actual
durations (persona drift) → **C** disruptions → **D** MVDs and simulated decisions.
10 personas (P01–P10) × 5 seeds, plus a **null persona** (no drift: actual = estimate
× noise) and a **misspecified generator** (drift depends on a feature the model does not
see), to show the model does not invent patterns and to show where it fails. Colab
notebooks stay thin: they call repo code and explain each step in plain English.

## 8. Evaluation design (D-EVAL)

- Primary outcome for Model 1: plan completion rate and realised feasibility, raw vs
  corrected, on the same events.
- **Week 1 of the pilot = fixed-order baseline** for Model 2; `randomised` mode after that.
- Decision-change rate shows how often the model changes what the student is told.
- Results are split by the tight-slack flag (threshold fixed before analysis).

## 9. External validation of Model 1: CESAW (REAL data)

- **What:** CESAW (SEI/CMU; ~60,000 tasks of professional developers with planned and actual minutes) is used as an **external validation of Model 1 on real estimation errors**. Source: <https://kilthub.cmu.edu/articles/CESAW_Project_Data_Fact_sheets/9922697>.
- **Data handling:** the licence is not stated, so the data is **never committed**. It is kept outside the repository and found through the setting `C1_CESAW_PATH`. `.gitignore` also blocks `CESAW_*.csv`.
- **Mapping** (`ml/drift/external/cesaw.py`): developer → student; plan minutes → estimate; actual minutes → actual (interrupt time already excluded); task type `Digital` (original phase kept as an extra column); start hour and weekday from the start timestamp; priority `Medium` (none in CESAW). Tasks with plan ≤ 0, actual ≤ 0 or no readable start time are dropped and counted in the result file.
- **Evaluation:** the same as §3 (leave-one-developer-out for cold start, rolling-origin for warm; model vs B0–B3; MAE in minutes, MAE of the log ratio, q10–q90 coverage). Because one fit on 60,000 tasks is slow, the model uses 50 trees, the warm evaluation covers a seeded sample of developers (≥ 20 working days) with one origin per 30 of their days, and folds run in parallel (`ml/drift/external/settings.py`).
- **Labelling:** results are labelled **REAL (CESAW, professional developers)**, never SYNTHETIC. Table: `docs/results/c1_model1_cesaw.md`; notebook: `notebooks/04_model1_cesaw.ipynb`.
- **Limitation:** professional developers, not students; no priority or task type; professionals' estimation errors may differ in size and pattern from students' own. The result supports "Model 1 works on real estimation errors", not "Model 1 is right for students".
