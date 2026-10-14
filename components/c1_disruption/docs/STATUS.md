# C1 status

One page, updated in every commit (CLAUDE.md §0.3). Details: `PROGRESS.md` (log), `DECISIONS.md` (decisions), `METHODOLOGY.md` (method).

## Last commit
`1c35891` · 2026-10-14 · "docs: sync rule and STATUS.md" (this update is in the commit after it).

## Done
- **Port to the team repo** (13 Oct): golden spec frozen as JSON (S1–S16, 57 API cases), Python engine and FastAPI app match it exactly; shared `X-API-Key`, `/api` prefix as one setting, repository + in-memory store.
- **Methodology update** (14 Oct), all with defaults = approved behaviour:
  - Engine: duration range (low/high, Fi on the point), strategy `compressRatio`, plan diff, overload check for normal days.
  - Logging per MVD and per task; metrics module.
  - Model 1: pooled quantile forest on log drift + per-student shrinkage (k by CV), q10–q90, baselines B0–B3, cold/warm evaluation, drift-1.0 fallback.
  - Model 2: 3 strategy actions (distinctness checked), pooled LinUCB, 3 baselines, policy modes (default `fixed_order`).
  - Simulation layers A–D (planted / null / misspecified, 5 seeds, SYNTHETIC); 3 Colab notebooks.
- **Colab → API for Model 1** (14 Oct): notebook 01 trains on all records and downloads `c1_drift_model.joblib` + `.joblib.json`; the API loads it from `C1_DRIFT_MODEL_PATH` (empty / missing / bad file → drift 1.0). Model files are git-ignored inside C1. Checked end to end with a real server.

## In progress
- Nothing running. Tasks 4–5 (Models 1–2): code done; SYNTHETIC results wait for the persona task lists.

## Waiting on owner
- **Persona task lists** P01–P10 (`personas.csv`, `tasks.csv`, format in `sim/README.md`).
- **Definitions:** use of the high duration in the Keep check; values of `deferOrder` and `recoveryTiming`; D-MOVE rules; contents of D-SOURCE and D-HCP.
- **Team decisions:** database (PostgreSQL vs Firestore); base path for orchestration; `/health` requires `X-API-Key` (team rule) — OK for health checks?
- Open research decision: the `None` EF values (Meeting/Fixed under power cut and transport delay, all of connectivity failure). The simulation skips and counts events that hit them.

## PROPOSED items not yet approved
- Metric definitions (METHODOLOGY.md §5), incl. critical task = High priority and due today/tomorrow; completed = `done`.
- `TIGHT_SLACK_THRESHOLD` = 0.10.
- Model 2 reward: Accept 1 · Reject 0 · Edit 1 − tags changed ÷ total tags.
- Model 2 action catalogue: `default` (≤ 50%), `compress_25`, `no_compress`.
- Overload check scope (one day; deadline warning for tasks due that day).
- Explanation wording for compress ratios other than 0.5.
- Exclusion-rule limits (drop if overlap > 50% of the span or < 10 min left).
- Simulation rules: disruption rate 0.3 per day, completion rule (true minutes ≤ planned minutes), accept 0.85 / 0.3, weekly retraining.
- Calibrating Model 1's range if it stays conservative (95% coverage vs nominal 80% on the test fixture).
- D-MOVE carry-over (not implemented until approved).

## Next step
Owner sends the persona task lists → run `notebooks/03_simulation_report.ipynb` → report the SYNTHETIC results.

## Test count
Root `pytest`: **513 passed** (C1 512 + C4 1), 14 Oct 2026.
