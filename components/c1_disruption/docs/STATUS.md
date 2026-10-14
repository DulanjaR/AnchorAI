# C1 status

One page, updated in every commit (CLAUDE.md §0.3). Details: `PROGRESS.md` (log), `DECISIONS.md` (decisions), `METHODOLOGY.md` (method).

## Last commit
`59ab967` · 2026-10-14 · "C1 sim: full SYNTHETIC run (5 seeds x 3 variants); Model 1 coverage inside 70-90%, no calibration" (this update is in the commit after it).

## Done
- **Port to the team repo** (13 Oct): golden spec frozen as JSON (S1–S16, 57 API cases), Python engine and FastAPI app match it exactly; shared `X-API-Key`, `/api` prefix as one setting, repository + in-memory store.
- **Methodology update** (14 Oct), defaults = approved behaviour: engine duration range, strategy `compressRatio`, plan diff, overload check; logging; metrics; Model 1 (pooled quantile forest + shrinkage, B0–B3, cold/warm evaluation, fallback); Model 2 (actions, pooled LinUCB, baselines, policy modes); simulation layers A–D; 3 Colab notebooks; Colab → API model file (`C1_DRIFT_MODEL_PATH`).
- **SYNTHETIC persona data** (14 Oct): `sim/data/` personas, habits, tasks (589), schedules (300 days); engine input from the free-time windows; tasks can be anything; disruptions at any time, MVD only when one overlaps a task.
- **Step 1+2 of the 14 Oct planning decisions:** layer C = per-persona disruption profile (`SYNTHETIC_disruption_profile.csv`) with top-up to 10 effective disruptions per persona; approved replanning scope (done tasks left out, in-progress tasks replanned for their remaining minutes); P09 long tasks from 120 min; all planning-chat decisions recorded in DECISIONS.md.
- **Step 3/4:** full SYNTHETIC run (5 seeds × planted / null / misspecified) → `sim/results/c1_simulation_SYNTHETIC.md`; Model 1 warm coverage 0.72–0.75 (inside 70–90%) → no calibration.
- **Step 5:** `OVERRUN_RISK` warning for Keep tasks whose high estimate would cross the next fixed block or the end of the free time (planning still uses the point).

## In progress
- Step 6 (`deferOrder`, `recoveryTiming`, 5-action catalogue, distinctness).

## Waiting on owner
- **Team decisions (open):** database (PostgreSQL vs Firestore); base path for orchestration; `/health` requires `X-API-Key`?
- Open research decision: the `None` EF values (Meeting/Fixed under power cut and transport delay, all of connectivity failure). Connectivity events are skipped and counted.
- D-MOVE: approved, implement after PP1 (golden S17+ first).

## PROPOSED items not yet approved
- OVERRUN_RISK message wording; "end of window" read as the end of the free stretch the task starts in.
- Disruption-profile interpretations (DECISIONS.md 2026-10-14 "Layer C = per-persona disruption profile"): weekly count rule, "evening bus" = bus block from 15:00, P08 evening = 18:00–22:00, missing times = any time, missing durations = 30–240 min, P04 Saturday row, 5-minute steps, several disruptions per day planned independently.

## Next step
Step 6, then rerun the SYNTHETIC simulation with the 5-action catalogue.

## Test count
Root `pytest`: **587 passed** (C1 586 + C4 1), 14 Oct 2026.
