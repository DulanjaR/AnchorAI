# C1 · Disruption Recovery Planner (Resilience)

Owner: **@Ravindu912** (Sehan A.M.R, IT23202986) · see `CODEOWNERS`

When a disruption (power cut, transport delay, connectivity failure, urgent work,
family obligation, health issue) breaks a student's planned day, C1 builds a
**Minimum Viable Day (MVD)**: the smallest realistic plan that still protects critical
deadlines and protected time, with a plain-language explanation for every task.
Keep-tagged tasks go to C3, Delegate-tagged tasks to C4.

The core idea is **Environmental Feasibility (EF)**: the kind of disruption decides
which task types can physically run during it. Rules and decisions: [CLAUDE.md](CLAUDE.md),
[docs/DECISIONS.md](docs/DECISIONS.md). API contract: [docs/API.md](docs/API.md).

## Status

Being ported from the original Node.js project (`ravindu912/anchor-ai-component1`) to
Python/FastAPI to match the team stack and `shared/` modules. The approved behaviour is
frozen in [tests/golden/](tests/golden/) and the Python code must match it exactly.
Progress: [docs/PROGRESS.md](docs/PROGRESS.md).

## Layout

| Folder | What |
|---|---|
| `app/` | The one C1 FastAPI service: `main.py`, `api/` (routers), `services/`, `data/` (repository + in-memory store) |
| `engine/` | Pure MVD engine (Fi, classification, placement, explanations); no I/O |
| `ml/drift/`, `ml/bandit/` | ML Model 1 (drift predictor) and ML Model 2 (contextual bandit) |
| `sim/` | Simulated users and synthetic data (always labelled SYNTHETIC) |
| `notebooks/` | Google Colab notebooks (experiments only) |
| `docs/` | API contract, decision log, progress log, plans, checkpoint and pre-test documents |
| `tests/` | pytest suites; `tests/golden/` is the frozen spec |

## Python versions

**Supported: Python 3.11, 3.12 and 3.13.** Developed on 3.13.3. The pinned
`requirements.txt` resolves to wheels for Linux x86_64 (Google Colab) on 3.10–3.13 and
for Windows on 3.13 (checked 13 Oct 2026). Colab's runtime Python changes over time:
the notebooks print it in their first cell.

## Setup and run (from the repo root)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS/Colab: source .venv/bin/activate
pip install -r requirements.txt -r components/c1_disruption/requirements.txt
cp .env.example .env               # API_KEY for shared.auth
uvicorn components.c1_disruption.app.main:app --reload
pytest                             # whole repo (root pytest.ini)
pytest components/c1_disruption    # C1 only
```

ML Model 1 in the API: train and download `c1_drift_model.joblib` (+ `.joblib.json`) with
`notebooks/01_model1_drift.ipynb`, put both in one folder and set
`C1_DRIFT_MODEL_PATH=<path to the .joblib>` in `.env`. Without it (or if the file is missing) the API
plans with drift 1.0. Model files are never committed (`components/c1_disruption/.gitignore`).

## PP1 demo (web page)

```bash
python -m components.c1_disruption.demo.web_demo     # opens http://127.0.0.1:8000
```

A small page in front of the real C1 API. First setup: free hours, **Sync calendar** (a calendar
file (.ics) exported from Google/Outlook/Apple, or a sample calendar → protected time) and tasks (name, start, end,
deadline, priority). The day calendar updates live; **⚡ Record a disruption** opens the report, then the
Minimum Viable Day (timeline + every tag explained) to accept or reject; accepting updates the calendar. **Load sample day** fills
a ready-made day; `http://127.0.0.1:8000/?auto` loads it and builds the MVD in one go (`?auto=accept` also accepts it). Data is in
memory and is gone when the server stops. A terminal version: `python -m components.c1_disruption.demo.pp1_demo`.

Database: open team decision (PostgreSQL vs Firestore). Until then C1 uses an
in-memory store behind a repository interface, so no database is needed to run it.
