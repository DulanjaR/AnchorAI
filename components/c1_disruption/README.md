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

The main screen is a **7-day week calendar**; everything else opens as a popup. **Load sample week**
fills a student's week (routine: bus = commute, campus mornings; lunch and dinner protected; tasks
today and on later days; an effort task). The **simulated clock** (+5 / +15 / +30 min or set a time)
drives reminders (5 min before, adjustable) and the start prompt ("Time to start" → Started / Power
cut / Delayed / Something urgent came up; one more prompt at +15; silent at +30 and "What happened?"
when you return; "Delayed on the way?" first if the task is at Home and *sustained motion* is ticked).
Nothing starts by itself. A disruption → today's MVD (accept / reject) → the **rest of the week**
proposal from the rearranger (moved tasks and effort sessions on their new day, each with its reason;
options A–E for a task that does not fit; accept / edit times / reject). Task form: location
(pre-filled from the routine) and effort-task fields; Setup: free hours, routine, protected time,
calendar sync (.ics). Quick start: `?auto=prompt`, `?auto=mvd`, `?auto=rearrange`, `?auto=options`,
`?auto=week`. Data is in memory and is gone when the server stops. A terminal version:
`python -m components.c1_disruption.demo.pp1_demo`.

## Using the demo for real (5-day self-trial) and Supabase

```bash
python -m components.c1_disruption.demo.web_demo                 # data in a local file (kept between runs)
python -m components.c1_disruption.demo.web_demo --db supabase   # data in the team's Supabase database
```

- **Your data is kept.** By default it is stored in `anchor_c1_demo.sqlite3` in your home folder, so
  closing the server or the PC loses nothing. The bar under the header shows where the data is.
- **Supabase:** in the Supabase dashboard, *Connect* → *Session pooler* → copy the URI and put it in the
  repo's `.env` (never commit it): `DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
  Start with `--db supabase`. C1 creates its table `c1_records` itself (row-level security on, so
  Supabase's public API cannot read it).
- **Each day:** keep the page open (the clock is LIVE; tap *Allow notifications* to get reminders when
  the tab is in the background). Add the day's tasks, tap *Started* / *Mark done* (that is what gives
  Model 1 real durations), record disruptions when they happen, decide the plans (Model 2's data), and
  use **🌙 End of day** for tasks you did not mark (with the minutes they really took, if you know).
- **Export my data** downloads everything (JSON) and the Model 1 records (CSV). Notebook 01 can train on
  them (dataset `PILOT`: your own data, one person — for checking the system, not a study result).
- The pretend clock (+5 / +15 / +30, *Go*) is only for trying the prompts; it is marked PRETEND, and
  *Back to real time* returns to live. *Try the sample week* uses a separate sample student.

Database: the team database is Supabase (PostgreSQL), 17 Oct 2026; C1's `SqlStore` (`app/data/sql_store.py`)
keeps its records in one table. Tests use the in-memory store.

