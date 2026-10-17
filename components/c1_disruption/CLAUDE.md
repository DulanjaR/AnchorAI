# CLAUDE.md — Anchor AI · Component 1: Disruption Recovery Planner

> Project context file for Claude Code. Lives in `components/c1_disruption/` of the team repo; read it at the start of every C1 session.
> Owner: Sehan A.M.R (IT23202986), GitHub @Ravindu912 · SLIIT IT4010 Research Project · Group J26-IT-366
> Version 3.0 · 13 October 2026: ported from Node.js/Express to Python/FastAPI in the team repo (v2.1 of 12 Oct 2026 is the source; every locked decision in §3 is unchanged).
> Team repo: `D:\RESEARCH PROJECT\AnchorAI` → GitHub `DulanjaR/AnchorAI`, C1 branch `dev/ravindu`.
> Old project (read-only reference, never modify): `D:\RESEARCH PROJECT\anchor-ai-component1` → `ravindu912/anchor-ai-component1`.

---

## 0. Rules for Claude Code (read first, every session)

### 0.1 Team repo rules (new in v3.0)

1. **Work only inside `components/c1_disruption/`** on branch `dev/ravindu`.
2. **Never edit `shared/`, `orchestration/`, other components or root files** (`README.md`, `requirements.txt`, `pytest.ini`, `CODEOWNERS`, `docker-compose.yml`, `.gitignore`, `.env.example`) without asking the owner first. Changes to `shared/` also need team agreement (`CODEOWNERS`).
3. **Read and import from `shared/` freely**: `shared.config.settings`, `shared.auth.require_api_key` (the `X-API-Key` check on every route), `shared.schemas`. Never copy shared code into C1.
4. **Imports are absolute from the repo root** (`from components.c1_disruption.engine import fi`), because the root `pytest.ini` sets `pythonpath = .`. Every package folder has an `__init__.py`.
5. **Tests run from the repo root:** `pytest` (root `pytest.ini`) must pass before every commit, including the other components' tests.
6. **One commit per task or phase, pushed to `origin dev/ravindu`** as a backup. No force-push. Merges into `dev` / `main` are the team's process, not Claude's.
7. **The old Node project is read-only.** Read it for reference; never write to it, never run commands that change it.
8. **C1's own pinned dependencies** live in `components/c1_disruption/requirements.txt` (`==`). They must install on Google Colab's Python as well as locally (supported: Python 3.11–3.13). Adding a package = pin it, check it installs for those versions, note it in DECISIONS.md.
9. **Golden spec:** `tests/golden/` (frozen 13 Oct 2026 from the Node project) is the reference behaviour. Python must match it exactly; never edit an expected value there to make a test pass.

### 0.2 Component rules (from v2.1, paths updated)

1. **Start each session by reading this file and `docs/PROGRESS.md`.** Say in 3–5 lines what the current task is and what was last done before writing any code.
2. **Do not change any decision in Section 3** without asking the owner. If code seems to need a change, stop and explain why.
3. **Keep the MVD engine pure.** No database, HTTP or framework code in `engine/`. Pure functions with type hints in, plain dicts out (same camelCase keys as the golden JSON and `docs/API.md`). Fully unit-tested.
4. **Never call a database from business logic.** Storage goes through the repository interface in `app/data/`. The team database is **Supabase (PostgreSQL)** (owner, 17 Oct 2026): `app/data/sql_store.py` (one `c1_records` table; also a local SQLite file for the demo); tests use the in-memory store. Every store passes the same store contract tests.
5. **No auto-actions.** Never auto-start tasks, auto-cascade overruns, or generate an MVD without the user confirming the disruption. These are deliberate design decisions, not missing features.
6. **Synthetic data is for pipeline validation only.** Label every synthetic dataset and every result from it `SYNTHETIC`. Never present it as a research finding.
7. **Test-first with owner approval.** For engine work, write the golden scenarios and their expected outputs to a file **on disk**, then stop. The owner checks them by hand and approves before the engine code is written. Never change an approved expected output to make a test pass; report the mismatch instead.
8. **One task at a time** (Section 7). Finish, run all tests, then stop and report. Do not jump ahead.
9. **All tunable numbers live in `engine/config.py`** (engine) or the matching settings module under `ml/` (ML). No magic numbers elsewhere.
10. **Explain as you go.** The owner must defend every line in a viva. Comment the *why*, keep code readable, and summarise what you changed after each task.
11. **Never claim something is done unless it is on disk.** Before saying a file is updated, committed or pushed, check it (`git status`, `git log -1`, `git ls-remote origin dev/ravindu`). Report the actual commit hash and the folder you are working in.
12. **Log your work** in `docs/PROGRESS.md` at the end of every task (format in Section 8). Record decisions in `docs/DECISIONS.md`, newest first, dated.

### 0.3 Sync with the planning chat (permanent, 14 Oct 2026)

The owner plans in a separate chat that reads the repo, so GitHub must always show the real state.

1. **Commit and push to `origin dev/ravindu` before reporting anything to the owner.** Unfinished work may be pushed as a commit whose message starts with `wip:`. **Never end a report with unpushed changes.**
2. **Keep `docs/STATUS.md` (one page) updated in the same commit as every change**, with these sections: Last commit (hash + date) · Done · In progress · Waiting on owner (decisions/questions) · PROPOSED items not yet approved · Next step · Test count from root pytest. (A commit cannot contain its own hash, so "Last commit" names the commit before it; the report gives the new hash.)
3. **Every report to the owner ends with:** the commit hash, the output of `git ls-remote origin dev/ravindu`, and the test count from root `pytest`.
4. **Commits are the owner's (15 Oct 2026):** author and committer = the owner's git identity (Ravindu, `ravindu912`). **No `Co-Authored-By` lines or any other attribution trailer** in commit messages, and no "Generated with" lines in pull-request texts.
4. **Decisions the owner pastes from the planning chat** are recorded in `docs/DECISIONS.md` with "Source: planning chat, <date>".

---

## 1. What Component 1 does

When a disruption (power outage, transport delay, connectivity failure, family obligation, health issue) ruins a working student's planned day, Component 1 builds a **Minimum Viable Day (MVD)**: the smallest realistic plan that still protects critical deadlines and personal boundaries, with a **plain-language explanation for every task decision**. It personalises over time from user feedback.

Target users: Sri Lankan university students, many of them **working students** balancing coursework with part-time jobs.

Anchor AI has 4 components (team repo `components/`). Component 1 is the entry point:
- Component 1 → **Component 3** (`c3_checkpointing`, Cognitive Checkpointing): receives **Keep**-tagged tasks
- Component 1 → **Component 4** (`c4_hcde`, Human Capability Development Engine): receives **Delegate**-tagged tasks
- Component 2 (`c2_capacity`, Human Capacity Manager) shares the same task list
- All components use the team's Python/FastAPI stack and the `shared/` modules; `orchestration/` routes between them. The shared database is Supabase (PostgreSQL), 17 Oct 2026.

The core research contribution is **Environmental Feasibility (EF)**: the type of disruption decides which task types are physically possible. No existing scheduling tool does this.

---

## 2. Technology stack

| Layer | Technology |
|---|---|
| Frontend (after PP1) | Flutter (Android, iOS, web) |
| Backend (C1) | Python 3.11–3.13 + FastAPI, Pydantic v2, pytest (one service: MVD API + ML endpoints) |
| Shared modules | `shared.config` (settings from `.env`), `shared.auth` (`X-API-Key`), `shared.schemas` |
| Database | **Supabase (PostgreSQL)** (17 Oct 2026); C1 stores records in one `c1_records` table through its repository interface (`SqlStore`); in-memory store for tests |
| ML Model 1 | scikit-learn **RandomForestRegressor** (Task 4) |
| ML Model 2 | Vowpal Wabbit contextual bandit (Task 5) |
| Experiments | Google Colab notebooks (`notebooks/`) calling code in `ml/` and `sim/` |
| Detection (Flutter) | flutter_local_notifications, connectivity_plus, sensors_plus, WidgetsBindingObserver |
| Calendar sync | Google Calendar API, Microsoft Graph API |

---

## 3. Locked decisions

### 3.1 Task Flexibility Index (Fi)

```
Fi = (Deadline Proximity × Priority Score) / (Duration × Environmental Feasibility)
```

- **Low Fi = urgent, keep. High Fi = flexible, safe to reduce or move.**
- Encodings:
  - Priority Score: **High = 1, Medium = 2, Low = 3** (high priority → low Fi)
  - Deadline Proximity: **calendar days until deadline**, floored at **0.5** ("due today", and overdue)
  - Duration: **hours**, after drift correction (`estimate × drift_score`; drift = 1.0 until ML Model 1 is trained)
- **EF definition (Q1, 6 Oct 2026, formula text unchanged):** EF is the feasibility of the task type **under the conditions of the time slot it would run in**.
  - Inside the disruption window: EF = `config.ENV_FEASIBILITY[disruption_type][task_type]`.
  - Outside the window: normal conditions, **EF = 1.0** (`OUTSIDE_WINDOW_EF`).
  - Tasks with EF < 0.3 cannot run inside the window (gate, 3.3), so their Fi always uses EF = 1.0.
- **Fi computed once (Q5, 6 Oct 2026):** Fi is a planning estimate, computed **once, before placement**, from the EF of the *intended* slot: EF < 0.3 → 1.0; EF ≥ 0.3 and the window is still ahead in today's plan → the disruption EF; window already over → 1.0. It is not recomputed if the task ends up outside the window. This breaks the Fi → order → slot → EF loop.
- EF therefore does two jobs: the **gate** (hard constraint: blocked tasks never go into the window) and the **weighting** inside the window (feasible tasks such as paper reading, EF 1.2, get a lower Fi and are pulled into the window).
- A `None` (JSON `null`) EF value is an open research decision. If the engine needs one, **raise a clear error naming the disruption type and task type**. Never invent a value. The check runs for every task, even one whose Fi would use 1.0.

### 3.2 Classification — tag by outcome

Tags describe **what actually happens to the task today** (Q2):

| Tag | Meaning |
|---|---|
| **Keep** | Placed in full today (0% compression) |
| **Reduce** | Placed today, compressed by **up to 50%** (variable ratio, only as much as the time budget needs) |
| **Move** | Not placed today; deferred to tomorrow |
| **Delegate** | Flagged delegable by the user **and not placed** (Q3; a delegable task that fits is just placed) |
| **Protect** | A user-defined protected block (sleep, meals, prayer, work shift). Never touched. |

Candidate groups (used for ordering, not final tags):
- **A. Keep candidates:** Fi < 0.5 and High priority.
- **B. Early Reduce candidates:** Fi < 0.5 but not High priority.
- **C. Reduce candidates:** Fi in [0.5, 2.0].
- **D. Move candidates:** Fi > 2.0 (never placed today).

A Reduce candidate that fits with 0% compression is tagged **Keep**, reason code `FITS_FULLY`.

### 3.3 MVD generation algorithm (time-slot placement)

The engine assigns each placed task a **start and end time**. It does not just compare total hours.

Inputs: plan date, time the replan starts (`planFrom`), work start/end, protected blocks, disruption (type, start, end), task list.

1. **Protect** all protected blocks. Free time = work hours from `planFrom` on, minus protected blocks, as a list of intervals. **No placed task may overlap a protected block (PTVR must be 0%).** Blocks crossing midnight (sleep 22:00–06:00) are split in two.
2. **Disruption kinds (Task 2a, 12 Oct 2026; `DISRUPTION_KINDS` in `engine/config.py`):**
   - **environment** (`power_outage`, `transport_delay`, `connectivity_failure`): conditions change. The window is part of free time, but only tasks with EF ≥ 0.3 may be placed inside it (steps 3 and 6 below).
   - **unavailable** (`urgent_work`, `family_obligation`, `health_issue`): the student's time is taken. The window is **removed from free time like a protected block**: nothing is placed in it, there is **no EF lookup** (so no null-EF error), no gate and no window-first, and every task's Fi uses EF = 1.0. Laptop work is fine outside the window (golden S15, S16).

   **A window that crosses midnight is clipped at the end of the plan day** (decided 6 Oct 2026): a power cut 20:00–02:00 is 20:00–24:00 for today's plan (the window-to-interval helper in `engine/time.py`; golden S14).
3. **Gate:** a task with EF < 0.3 for this disruption may only be placed **outside** the window (before or after it). It becomes Move only if it does not fit there.
4. Compute Fi for each task once (3.1, Q5).
5. **Order (Q4):**
   1. Group A, then B, then C. Group D is not placed.
   2. Within each group: Fi ascending.
   3. Fi tie: earliest absolute deadline first. Deadline tie: shortest duration first.
6. **Place** tasks one by one in that order, each as **one contiguous slot** (never split across a protected block or two gaps):
   - **Window-first (Q6, revised 6 Oct 2026):** while the window is active, a task with EF ≥ 0.3 is first placed **inside the window**, starting at **max(gap start, window start)**, if it fits wholly inside gap ∩ window. Only if it does not fit inside the window: a gap that overlaps the window and holds the whole task, starting at the **gap start**. This keeps normal-condition time free for tasks that need it (golden S12, S13).
   - Otherwise (and always for gated tasks): the earliest feasible gap that holds the full task.
7. **Over budget:** if no gap holds the full task, compress it into the **largest** feasible gap (least compression; ties → earliest), as long as compression ≤ 50%. Because tasks go in order, the **last** Keep candidate in the order is the one reduced first. Reduce candidates are compressed only as much as needed.
8. **Not placed:** delegable → **Delegate**; otherwise → **Move**.
9. **Deadline risk warning (revised 6 Oct 2026):** `deadlineRisk: true` when a task is tagged **Move** and it is **due today or tomorrow** (`DEADLINE_RISK_DAYS`), **or** urgent (Fi < 0.5). Delegate tasks do not get the warning. The system makes trade-offs visible; it cannot create time.
10. **Explanation:** every task gets one reason code and one plain-language sentence generated from it. The codes are exactly those of the reason function in `engine/classify.py`, first match wins:
    - Placed: `REDUCE_BUDGET` (compressed) → `OUTSIDE_DISRUPTION_WINDOW` (gated task placed outside the window) → `KEEP_URGENT` (group A) / `FITS_FULLY` (groups B, C)
    - Not placed: `DELEGABLE` → `BLOCKED_BY_DISRUPTION` (gated, no room outside the window) → `LOW_URGENCY` (Fi > 2) → `TIME_TAKEN_BY_DISRUPTION` (kind unavailable: the time went to the disruption) → `BUDGET_EXCEEDED`
    - Protected blocks: `PROTECTED_BLOCK` (set in `engine/mvd.py`)
    Each code has one template in `engine/explain.py`; a new code needs a template there and a line here. The template texts are frozen in the golden JSON (`tests/golden/`).
    `LOW_URGENCY` + free time left today (`freeMinutesLeft > 0` after placement) → the explanation adds: "You have free time today, so you can start it early if you like." The task is still Move; starting early is the student's choice (no auto-actions).
11. **Three-way comparison:** original plan / user's manual replan (if provided) / MVD.
12. The user must **Accept / Edit / Reject** before the MVD is finalised.
13. Finalised tags are written to shared task data for Components 3 and 4.

A second disruption on the same day (tentative): the current MVD becomes the new baseline and the engine runs again on what remains (store `parentMvdId`).

### 3.4 Disruption detection (three passive signals, no GPS)

1. **App inactivity (primary trigger):** no Start Task tap at +15 and +30 min after scheduled start. Schedule both notifications at "Confirm Schedule"; cancel them on Start Task.
2. **Network connectivity drop:** connectivity_plus (supporting signal; power/connectivity disruptions).
3. **Sustained device motion:** sensors_plus accelerometer (supporting signal; transport disruptions). Log only derived "sustained motion period" start/end events, never raw sensor data.

After +30 min the app goes silent. On return: "What happened?" → completed / disruption / still working. On disruption the user confirms **type, time lost, severity** (type pre-suggested from signals). Passive signals are best-effort context collected while the app process is alive; they never trigger an MVD on their own.

**One-tap disruption recording (decided 9 Oct 2026; app phase, after PP1):**
- **Quick-reply buttons on the +15-minute notification:** Started / Power cut / Delayed / Something urgent came up.
- **Start and end times estimated from signals:** connectivity lost and restored, sustained motion start and end, the first missed Start tap.
- **Calendar:** a new calendar event that overlaps planned tasks is detected as `urgent_work`.
- **On return:** a pre-filled "Looks like X from HH:MM to HH:MM, right?" plus "Is it still happening, until when?". Planning uses the **remaining** window (from now to the confirmed end).
- **The user always confirms** (rule 5). Fallback when signals give nothing: the window runs from the first missed Start tap until the user returns, and the user corrects it.

**Disruption times are recorded (decided 9 Oct 2026)** for four uses: planning (the remaining window); cleaning ML Model 1 training data (§3.6); ML Model 2 context (§3.7); research statistics and per-event metrics (§3.8).

### 3.5 Task completion detection (hybrid)

- **Primary:** Start Task + Mark Done → exact timestamps → actual duration.
- **Backup:** end-of-day review at the user's configured work-end time (not a fixed clock time): Done / Partial (25/50/75%) / Not Done.
- Overruns are captured as data, never cascaded.

### 3.6 ML Model 1 — Timeline Drift Predictor (redesigned 14 Oct 2026; main ML contribution)

Full method: `docs/METHODOLOGY.md` §3. Replaces the earlier RandomForest-on-ratio plan (`docs/TASK4_PLAN.md`, superseded).

- **Regressor, not a classifier.** Target = **log(actual ÷ estimated)** (log drift: overruns and underruns are symmetric; 0 = on time).
- **Pooled Random Forest** across all students + **per-student shrinkage**: the student's mean residual is added with weight `w = n / (n + k)`, n = the student's completed records, **k chosen by cross-validation**. A day-1 student (n = 0) gets the pooled estimate.
- **Quantile output**: a range (default q10–q90) as well as the point, from a quantile regression forest or equivalent (library chosen by what installs cleanly; recorded in DECISIONS.md).
- Features: task type, estimated duration, time of day, day of week, priority (+ the shrinkage term).
- MVD uses `corrected = estimate × exp(predicted log drift)`; the range feeds the engine's `estimatedHoursLow/High`.
- **Baselines in code:** B0 drift = 1.0; B1 global mean ratio; B2 per-student mean ratio (global when n = 0); B3 shrinkage only, no forest.
- **Evaluation:** leave-one-student-out (cold start), rolling-origin (warm), MAE in minutes, MAE of the log ratio, interval coverage, learning curve against n.
- **Graceful fallback:** model unavailable or untrained → drift = 1.0; the engine keeps working.
- **Exclusion rule (decided 9 Oct 2026):** training data must not count time lost to a disruption as task time. For a completed task whose start–done span overlaps a **confirmed** disruption, subtract the overlap from the actual duration, or drop the record if that is not reliable.
- **Starting drift per task type** comes from the pre-test (C1 Q4–Q5, §3.8) and is PROVISIONAL; the model itself is trained on pilot data, not on the survey.

### 3.7 ML Model 2 — Strategy Personalizer (redesigned 14 Oct 2026; lightweight)

Full method: `docs/METHODOLOGY.md` §4. Replaces the Vowpal Wabbit plan.

- **Actions are concrete strategy configs** for the engine (`engine/strategy.py`): compress ratio × defer order × recovery timing. A **distinctness check** on synthetic scenarios reports how often each pair of actions gives different MVDs; actions that never differ are merged or dropped.
- **Pooled LinUCB** with a shared component + a per-student component.
- Context: disruption kind, severity, time-of-day bucket, share of digital tasks, slack ratio, weekday/weekend, student history.
- Reward: Accept = 1, Reject = 0, Edit = 1 − (tags changed ÷ total tags) (**PROPOSED**, owner to confirm).
- Baselines: fixed order, per-student most-accepted counter, random.
- **Policy modes** (config): `fixed_order` (pilot week 1, **default**), `bandit`, `randomised` (per event, randomly show the bandit or the fixed ranking, and log which).
- Output: a ranked strategy list; the top one shapes the MVD. The user still Accepts / Edits / Rejects (rule 5).
- **Starting ranking per disruption kind** may come from the pre-test (C1 Q8–Q9, §3.8), PROVISIONAL. Honest limitation: ~3–5 disruptions per pilot user, so no full convergence.

### 3.8 Evaluation and logging (revised 14 Oct 2026)

Metrics (`metrics/`, definitions in `docs/METHODOLOGY.md` §5): CTRR (planned and realised), PTVR (must be 0%; property test on every generated plan), feasibility and realised feasibility (raw vs corrected durations, same event), plan completion rate, decision-change rate (`engine/diff.py`), acceptance, edits per MVD, time-to-decision, tight-slack flag (threshold fixed in config before analysis); after D-MOVE: carry-over placement rate, post-move deadline misses. Also from the original plan: MVD Acceptance Rate trend, Explanation Acceptance Rate, Comparative Realism Rating (vs no-change and manual replan), SUS ≥ 70. Pilot: 10–20 SLIIT students, 2–3 weeks; **week 1 = fixed-order baseline**.

Logged per MVD: ranking shown, policy mode, model on/off, strategy config, tags, Accept/Edit/Reject, structured edit diff, time-to-decision, manual replan first. Logged per task: estimated, corrected (point/low/high), actual, completion status.

Synthetic simulation (`sim/`, always **SYNTHETIC**): 10 personas × 5 seeds, plus a null persona (no drift) and a misspecified generator (drift depends on features the model does not see). Persona task lists come from the owner.

**Pre-test (decided 10 Oct 2026):** Component 1 has 10 questions (C1 Q1–Q10) in the team survey `docs/Pre_test_PartA_C1_C2_C3.docx` (**DRAFT**, DECISIONS.md 2026-10-12). The answers set the **starting values** only:

| Answers | Set |
|---|---|
| C1 Q2–Q3 (how often, which disruption) | synthetic-data parameters (disruption frequency and type mix) |
| C1 Q4–Q5 (planned vs actual time, coding and reading) | ML Model 1 starting drift per task type |
| C1 Q6–Q7 (what still works in a power cut / internet failure) | EF values in `engine/config.py` |
| C1 Q8–Q9 (strategy in a power cut / urgent work) | ML Model 2 starting strategy ranking per disruption kind |
| C1 Q10 (how much a task can be shortened) | `MAX_COMPRESSION` |

Starting values go in `ml/data/pretest_priors.json`, marked **PROVISIONAL** until the survey CSV arrives. The models are trained on pilot data, not on the survey. Changing a config value from the survey is still an owner decision (rule 2).

---

## 4. Engine config

File: `engine/config.py` (Phase 3 of the port). Values are initial heuristics, tuned in the pilot; identical to the Node `config.js`.

```python
PRIORITY_SCORE = {"High": 1, "Medium": 2, "Low": 3}
FEASIBILITY_GATE = 0.3      # EF below this = cannot be placed inside the window; may be placed outside it
OUTSIDE_WINDOW_EF = 1.0     # EF outside the disruption window (normal conditions)
DEADLINE_MIN_DAYS = 0.5
DEADLINE_RISK_DAYS = 1      # moved + due within this many days → deadline risk
KEEP_THRESHOLD = 0.5
REDUCE_RANGE = (0.5, 2.0)
MAX_COMPRESSION = 0.5       # up to 50%
TASK_TYPES = ("Digital", "Analog", "Meeting", "Fixed")
DISRUPTION_KINDS = {        # Task 2a
    "power_outage": "environment", "transport_delay": "environment", "connectivity_failure": "environment",
    "urgent_work": "unavailable", "family_obligation": "unavailable", "health_issue": "unavailable",
}
ENV_FEASIBILITY = {         # environment kinds only
    "power_outage":         {"Digital": 0.1,  "Analog": 1.2,  "Meeting": None, "Fixed": None},
    "transport_delay":      {"Digital": 0.7,  "Analog": 1.2,  "Meeting": None, "Fixed": None},
    "connectivity_failure": {"Digital": None, "Analog": None, "Meeting": None, "Fixed": None},
}
```

**`None` values are open research decisions for the owner.** Do not invent values.

---

## 5. Folder structure (`components/c1_disruption/`)

```
components/c1_disruption/
├── CLAUDE.md, README.md
├── requirements.txt     C1's pinned dependencies (==), Colab-compatible
├── app/                 the one C1 FastAPI service
│   ├── main.py          app factory, /health, mounts the /api routers (prefix = one setting) and the ML routes
│   ├── api/             routers (settings, protected blocks, tasks, disruptions, mvds, reviews), errors, auth (X-User-Id stand-in + shared X-API-Key)
│   ├── services/        mvd service (stored data ↔ engine, decisions), clock, ownership checks
│   └── data/            repository interface + in-memory store (real DB store after the team decision)
├── engine/              pure Python: config, time, fi, classify, explain, mvd, strategy, diff, overload (no I/O, no framework)
├── ml/
│   ├── drift/           ML Model 1: data, model (quantile forest + shrinkage), baselines, evaluation, corrector (MVD hook)
│   └── bandit/          ML Model 2: actions (+ distinctness), context, linucb, policies (BanditChooser, baselines)
├── metrics/             evaluation metrics (CTRR, PTVR, feasibility, completion, decision change, …)
├── sim/                 SYNTHETIC simulation: personas.py (layer A loader), generate.py (B, C), events.py (D), experiment.py; examples/ (tiny test set)
├── notebooks/           Google Colab notebooks (experiments only; first cell clones dev/ravindu + installs requirements)
├── docs/                METHODOLOGY.md, API.md, DECISIONS.md, PROGRESS.md, TASK4_PLAN.md (superseded), Component1_Checkpoint_v3.docx, Pre_test_PartA_C1_C2_C3.docx (DRAFT)
└── tests/
    ├── golden/          frozen spec: scenarios/S01–S16.json, api_cases.json, README.md, tools/ (Node checker)
    ├── engine/          unit tests, invariants (PTVR = 0 and other hard rules), 500-day seeded stress test
    ├── api/             route tests from api_cases.json + golden flows over HTTP
    ├── data/            store contract tests (run against every store)
    ├── metrics/         metric definitions on golden scenarios
    ├── ml/              Model 1 / Model 2 (SYNTHETIC fixtures)
    └── sim/             simulation layers A–D
```

Data records (repository collections): `users`, `tasks`, `protectedBlocks`, `disruptions`, `mvds` (tags, slots, reason codes, explanations, `parentMvdId`), `feedback` (accept/edit/reject + edit content), `signals` (passive signal events), `completions`.

---

## 6. Open questions (owner decides; do not guess)

1. EF values for the `None` entries (waiting for pre-test results: C1 Q6–Q7). Note: the survey asks about power cuts and internet failure only, so it gives no evidence for `transport_delay` or the `Fixed` task type. Since Task 2a only the environment kinds need EF: `connectivity_failure` (all task types) and Meeting/Fixed under `power_outage` and `transport_delay`. `family_obligation`, `health_issue` and `urgent_work` need none.
2. On-device MVD generation during outages (future work; engine stays portable pure functions so it can be ported to Dart).
3. Threshold tuning (0.5, 0.5–2.0, 0.3) during the pilot.
4. Whether Component 3 should also checkpoint Reduce tasks (owner to ask Member 3).
5. **Gate: "after" or "outside"?** The C:\ v2 draft said gated tasks may only go *after* the window. The approved rule and scenario S9 allow *before or after*. This file uses "before or after".
6. ~~Database (team decision): PostgreSQL vs Firestore.~~ **Answered 17 Oct 2026: Supabase (PostgreSQL).**
7. **Base path for orchestration:** C1 serves `/api/...` as in `docs/API.md`; the prefix is one setting, so it can become e.g. `/c1/api` when `orchestration/` is designed. (Added 13 Oct 2026.)
8. **Engine details pending (14 Oct 2026):** how the high duration is used in the Keep check; the values of `defer_order` and `recovery_timing`; the scope of the overload check. Built with defaults = old behaviour; see DECISIONS.md PROPOSED entries.
9. **D-MOVE carry-over** rules: PROPOSED, not implemented until approved.

Resolved: slot choice (Q6 revision), reason-code names, deadline-risk rule, midnight-crossing disruptions (all 6 Oct 2026; see DECISIONS.md).

---

## 7. Implementation plan (PP1 ≈ mid-October 2026: backend complete)

| # | Task | Dates | Done when |
|---|---|---|---|
| 1 | Project skeleton | Oct 6 | Done (Node) |
| 2 | Fi + MVD engine with golden tests | Oct 6–8 | Done (Node) |
| 3 | API around the engine | Oct 9–10 | Done (Node) |
| 2a | Disruption kinds | Oct 12 | Done (Node) |
| P | **Port to the team repo (Python/FastAPI)** | Oct 13 | P1 golden spec frozen as JSON; P2 structure; P3 engine matches all golden JSON + invariants + 500-day stress test; P4 FastAPI app passes api_cases.json and golden flows over HTTP; P5 ML scaffolding + Colab notebooks; P6 root pytest green, docs updated, pushed |
| 4 | ML Model 1 (redesign 14 Oct) | after the port | Pooled RF on log drift + shrinkage + quantiles; B0–B3; LOSO + rolling-origin evaluation on SYNTHETIC personas; fallback drift 1.0 |
| 5 | ML Model 2 (redesign 14 Oct) | after Task 4 | Strategy actions + distinctness check; pooled LinUCB; baselines; policy modes; simulated acceptance |
| 6 | PP1 demo prep | Oct 15 | One disruption scenario end to end; tests and chart ready |

Golden scenarios use only `power_outage` and `transport_delay` with Digital and Analog tasks until the null EF values are filled, plus the "unavailable" kinds (S15, S16), which need no EF.

### Progress checklist

- [x] Tasks 1, 2, 3, 2a — Node project (`anchor-ai-component1`, last commit 2bfedfa): Jest 248/248
- [x] Port P1 — commit e96a567 (13 Oct 2026): golden spec S1–S16 + 57 API cases frozen as JSON, checked against Node
- [x] Port P2 — commit 15f4aff (13 Oct 2026): structure, CLAUDE.md, README, docs, pinned requirements
- [x] Port P3 — 13 Oct 2026: pure Python engine; all 16 golden scenarios match exactly; invariants + the same 500 seeded days as Node (hash-checked); pytest 225/225 from the repo root
- [x] Port P4 — 13 Oct 2026: FastAPI app (same endpoints as docs/API.md, shared X-API-Key, Pydantic models, repository + in-memory store); all 57 API cases and S1–S16 over HTTP pass
- [x] Methodology update (14 Oct 2026): engine extensions with defaults (strategy, duration range, plan diff, overload check), logging, metrics, Model 1, Model 2, simulation framework, Colab notebooks (replaces port P5); docs (P6). pytest 500/500 from the repo root
- [~] Task 4 — Model 1 code and evaluation done; waiting for the owner's persona task lists for the SYNTHETIC simulation results
- [~] Task 5 — Model 2 code done; same
- [ ] Task 6
- [ ] Pending owner definitions: high duration in the Keep check, defer order, recovery timing, D-MOVE rules, D-SOURCE / D-HCP entries

---

## 8. Progress log format (`docs/PROGRESS.md`)

Add one entry at the top after every task or work session:

```
## YYYY-MM-DD — Task N: <short title> — <done | in progress | blocked>
Commit: <hash or "not committed">
Files created: <paths>
Files changed: <paths, one line each on what changed>
Tests: <command> → <passed/failed counts>
Decisions applied: <links to DECISIONS.md entries>
Open questions for owner: <list or "none">
Next step: <one line>
```

The owner shares this file with their planning assistant, so it must be accurate and complete.
