# Component 4 - Human Capability Development Engine (HCDE)

Decides how much AI assistance a user gets for a task (Human First, Hint, Guided, Shared, Emergency),
explains why, lets the user override, and adapts as capability grows.

Hybrid design: an interpretable decision layer (task analysis + BKT + transparent rules + fading)
chooses the tier; an LLM generates the response at that tier.

| Folder | Contents |
| --- | --- |
| `app/api/` | FastAPI routers |
| `app/db/` | SQLAlchemy models, Alembic migrations |
| `decision/` | task_analyzer, bkt, scoring, fading, explain |
| `generation/` | `generate()` interface, tier prompts, compliance check |
| `sim/` | synthetic learners and fading plots |
| `training/` | dataset build, QLoRA, evaluation (after 17 Oct) |
| `ml/` | Phase 2 feature export + training (after pilot) |
| `docs/` | tier rubric, API contract |
| `tests/` | pytest |

Run: `uvicorn components.c4_hcde.app.main:app --reload` from the repo root
Folder names use underscores so they import as Python packages.
