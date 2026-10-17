# C1 status

One page, updated in every commit (CLAUDE.md §0.3). Details: `PROGRESS.md` (log), `DECISIONS.md` (decisions), `METHODOLOGY.md` (method).

## Last commit
`8c4473b` · 2026-10-16 · "C1 sim: SYNTHETIC rerun with the earned-trust gate; earlier run kept as 'Before gate'" (this update is in the commit after it).

## Done
- **Port to the team repo** (13 Oct): golden spec frozen as JSON (S1–S16, 57 API cases), Python engine and FastAPI app match it exactly; shared `X-API-Key`, `/api` prefix as one setting, repository + in-memory store.
- **Methodology update** (14 Oct), defaults = approved behaviour: engine duration range, strategy `compressRatio`, plan diff, overload check; logging; metrics; Model 1 (pooled quantile forest + shrinkage, B0–B3, cold/warm evaluation, fallback); Model 2 (actions, pooled LinUCB, baselines, policy modes); simulation layers A–D; 3 Colab notebooks; Colab → API model file (`C1_DRIFT_MODEL_PATH`).
- **SYNTHETIC persona data** (14 Oct): `sim/data/` personas, habits, tasks (589), schedules (300 days); engine input from the free-time windows; tasks can be anything; disruptions at any time, MVD only when one overlaps a task.
- **Step 1+2 of the 14 Oct planning decisions:** layer C = per-persona disruption profile (`SYNTHETIC_disruption_profile.csv`) with top-up to 10 effective disruptions per persona; approved replanning scope (done tasks left out, in-progress tasks replanned for their remaining minutes); P09 long tasks from 120 min; all planning-chat decisions recorded in DECISIONS.md.
- **Step 3/4:** full SYNTHETIC run (5 seeds × planted / null / misspecified) → `sim/results/c1_simulation_SYNTHETIC.md`; Model 1 warm coverage 0.72–0.75 (inside 70–90%) → no calibration.
- **Step 5:** `OVERRUN_RISK` warning for Keep tasks whose high estimate would cross the next fixed block or the end of the free time (planning still uses the point).
- **Step 6:** strategy `deferOrder` (`fi` | `deadline`) and `recoveryTiming` (`earliest` | `latest`); 5-action catalogue (default, compress_25, no_compress, deadline_first, evening_first); distinctness check passed (no pair never differs).
- **Rerun with the 5-action catalogue:** Model 1 unchanged; Model 2 mean acceptance (SYNTHETIC, assumed 0.85/0.3): most accepted 0.742, bandit 0.680, fixed 0.609, random 0.537.
- **Task 6 (part 1): PP1 demo script** `demo/pp1_demo.py`: one power-cut day end to end through the API (in-process, or `--url` for a running server): plan → confirmed disruption → MVD with all four tags and their explanations → accept → tags for C3/C4 → feedback logged. Tested (`tests/test_demo.py`).
- **Task 6 (part 2): PP1 web demo** `demo/web_demo.py` + `demo/web/index.html`: a small page in front of the real API (add tasks, protected time, report a disruption, MVD timeline with original vs new slots, every tag explained, accept/reject, hand-off to C3/C4). `python -m components.c1_disruption.demo.web_demo`. Tested (`tests/test_web_demo.py`); checked in a headless browser.
- **Task 6 (part 3): web demo reworked after owner feedback (15 Oct):** first setup (free hours, **Sync calendar** = import a calendar file (.ics) or a sample calendar → protected time; tasks with name, start, end, deadline, priority, or "no set time") next to a live day calendar; a visible **⚡ Record a disruption** button on the calendar opens the report, then the MVD review; accepting puts the new plan on the calendar with the disruption marked.
- **Model 1 on REAL data (CESAW, professional developers):** `docs/results/c1_model1_cesaw.md`. 60,284 tasks from 247 developers (dropped: plan ≤ 0 692, no readable start 841). **Finding: Model 1 does not beat "trust the plan" on CESAW.** Cold MAE 80.2 min vs B0 75.0; warm 82.0 vs B0 76.6 (B3 78.9). Range coverage 0.74 / 0.73 (inside 70–90%). Real estimates are very noisy (sd of log ratio 1.07, median −0.06).
- **Model 1: median point + earned-trust gate** (planning chat, 16 Oct): point = forest q50; the model corrects a student only after beating B0 on their recent tasks, else drift 1.0 (API `correctionSource: "gate"`). Model file format 2. Tests added (gate opens/closes, evidence uses earlier days only, margin, minimum records, gate off = old behaviour, mean = old point).
- **Gate values approved** (lookback 20, minimum 5, margin 5%). **Notebook 01** saves the format-2 model (with the gate) and prints each persona's gate: ready to retrain in Colab. **PP1 demo script** runs as SYNTHETIC persona P01 with Model 1 on: P01's gate is open (model 6.2 min vs own estimate 14.0 min on 20 recent tasks), and the planner uses P01's corrected durations.
- **SYNTHETIC rerun with the gate** (`sim/results/c1_simulation_SYNTHETIC.md`, earlier run kept as "Before gate"; 5 seeds × 3 variants). Warm MAE min, model with gate vs before vs B0: planted 8.87 vs 7.25 vs 12.19 (gate open for 8.8 of 10 personas, closed 1.2); null 4.20 vs 4.36 vs 4.18 (open 1.6 / closed 8.4: the model now no longer adds error where there is no drift); misspecified 17.01 vs 16.73 vs 17.90 (open 5.6 / closed 4.4). Cold start = B0 by design (planted 12.25 vs 8.50 before). The gate costs accuracy where the drift is real (cold start, early weeks) and protects where there is nothing to learn. Planned completion rate (corrected plans), planted 0.38 (before 0.42); null: identical to raw plans.
- **CESAW rerun with the gate + median** (`docs/results/c1_model1_cesaw.md`, earlier run kept as "Before gate"; REAL, professional developers). Cold: model = B0 by design, 75.04 min (before 80.20); gate closed for all 247 developers. Warm: model 75.88 min vs B0 76.57 (before 82.00): the gap to B0 is closed and the model is now slightly better than every baseline. The gate fell back to B0 for most predictions: open for 27.2% (11 of 40 developers open at their last point, 29 closed; 18 open at least once). Where open: model 66.98 vs B0 69.53 min on the same tasks. Not separable from this run: how much comes from the median vs the gate (no median-only run).

## In progress
- **Rearranger (17 Oct, owner-approved design):** golden R01–R08 written test-first (`tests/golden/rearrange/`, DRAFT) — **waiting for owner approval before any code.**
- **Task category feature (Model 1):** code and tests done on a side branch (merged after the reruns land); then the SYNTHETIC with/without-category comparison.

## Waiting on owner
- **Team decisions (open):** database (PostgreSQL vs Firestore); base path for orchestration; `/health` requires `X-API-Key`?
- Open research decision: the `None` EF values (Meeting/Fixed under power cut and transport delay, all of connectivity failure). Connectivity events are skipped and counted.
- D-MOVE: approved, implement after PP1 (golden S17+ first).

## PROPOSED items not yet approved
- Rearranger interpretations used to hand-work R01–R08 (`tests/golden/rearrange/README.md`, items 1–11), incl. option B = split with shortening-only room-making, option C not for High priority, splittable defaults, effort rounding to 5 min (extra to the earliest days), reason wording.
- Model 1 gate details not covered by the approval (DECISIONS.md 2026-10-16): error in minutes, out-of-fold forest in the evidence, band widened when closed.
- CESAW follow-ups (not done; each is a method change to decide before any rerun, no tuning on these results): (a) use the forest's median (q50) as the point instead of the mean: with skewed, noisy errors the mean pulls predictions down (B1 global mean is also worse than B0); (b) add the CESAW phase as a feature (it plays the role of task type); (c) report per-developer MAE as well as pooled.
- **Explanation bug found while building the demo (not fixed, golden behaviour):** a never-placed low-urgency (group D) Digital task on a power-cut day gets reason `BLOCKED_BY_DISRUPTION` and the text "there is not enough free time outside it, even at half length", even when there is free time. The reason order checks "blocked" before "low urgency". Proposal after PP1: check group D first (needs a golden update).
- deferOrder "deadline" keeps the groups and orders within them; recoveryTiming "latest" keeps window-first.
- Model 2 simulation: count a shown plan as "preferred" when it equals the preferred strategy's plan (today the label decides; on persona days the compression actions rarely change the plan).
- OVERRUN_RISK message wording; "end of window" read as the end of the free stretch the task starts in.
- Disruption-profile interpretations (DECISIONS.md 2026-10-14 "Layer C = per-persona disruption profile"): weekly count rule, "evening bus" = bus block from 15:00, P08 evening = 18:00–22:00, missing times = any time, missing durations = 30–240 min, P04 Saturday row, 5-minute steps, several disruptions per day planned independently.

## Planned after PP1 (not now)
- ~~D-MOVE carry-over~~ superseded on 17 Oct by the **rearranger** (see In progress).
- **Model 2 LLM-persona idea:** not used for results; at most an exploratory stress test later.

## Next step
PP1 charts and rehearsal (Task 6, PP1 = 19 Oct 2026); decide the CESAW follow-ups; D-MOVE after PP1 (golden S17+ first).

## Test count
Root `pytest`: **666 passed, 2 skipped** (C1 665 + C4 1; the 2 chart tests need matplotlib and pass in the notebook environment), 17 Oct 2026.
