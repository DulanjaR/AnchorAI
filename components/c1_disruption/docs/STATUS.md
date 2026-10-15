# C1 status

One page, updated in every commit (CLAUDE.md §0.3). Details: `PROGRESS.md` (log), `DECISIONS.md` (decisions), `METHODOLOGY.md` (method).

## Last commit
`a9989cd` · 2026-10-15 · "wip: C1 Model 1 on REAL CESAW data - loader, evaluation, notebook 04 (run not finished)" (this update is in the commit after it).

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

## In progress
- **Model 1 on REAL data (CESAW):** code, tests, notebook 04, METHODOLOGY §9 and `C1_CESAW_PATH` done (wip commit). The full run (leave-one-developer-out over 247 developers + warm sample, 50 trees) did not finish in 11 h (a worker crashed) and was stopped; no result table yet. Waiting on owner: a faster evaluation design (see PROPOSED).

## Waiting on owner
- **Team decisions (open):** database (PostgreSQL vs Firestore); base path for orchestration; `/health` requires `X-API-Key`?
- Open research decision: the `None` EF values (Meeting/Fixed under power cut and transport delay, all of connectivity failure). Connectivity events are skipped and counted.
- D-MOVE: approved, implement after PP1 (golden S17+ first).

## PROPOSED items not yet approved
- **Explanation bug found while building the demo (not fixed, golden behaviour):** a never-placed low-urgency (group D) Digital task on a power-cut day gets reason `BLOCKED_BY_DISRUPTION` and the text "there is not enough free time outside it, even at half length", even when there is free time. The reason order checks "blocked" before "low urgency". Proposal after PP1: check group D first (needs a golden update).
- CESAW evaluation design: cold start as grouped 10-fold by developer (every developer still unseen when predicted) instead of 247 single-developer folds; warm on the seeded 40-developer sample; progress logging.
- CESAW mapping: priority `Medium` for every task (CESAW has none); tasks without a readable start time (843) dropped and counted.
- deferOrder "deadline" keeps the groups and orders within them; recoveryTiming "latest" keeps window-first.
- Model 2 simulation: count a shown plan as "preferred" when it equals the preferred strategy's plan (today the label decides; on persona days the compression actions rarely change the plan).
- OVERRUN_RISK message wording; "end of window" read as the end of the free stretch the task starts in.
- Disruption-profile interpretations (DECISIONS.md 2026-10-14 "Layer C = per-persona disruption profile"): weekly count rule, "evening bus" = bus block from 15:00, P08 evening = 18:00–22:00, missing times = any time, missing durations = 30–240 min, P04 Saturday row, 5-minute steps, several disruptions per day planned independently.

## Next step
Decide the CESAW design and run it; PP1 demo (Task 6, PP1 = 19 Oct 2026); D-MOVE after PP1 (golden S17+ first).

## Test count
Root `pytest`: **614 passed** (C1 613 + C4 1), 15 Oct 2026.
