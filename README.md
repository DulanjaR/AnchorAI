# Anchor AI (J26-IT-366)

Middleware AI system that adaptively regulates AI assistance to preserve human capability,
structured around the Human Capability Preservation (HCP) framework.

| Folder | Component | HCP dimension |
| --- | --- | --- |
| `components/c1_disruption/` | Disruption Recovery Planner | Resilience |
| `components/c2_capacity/` | Human Capacity Manager | Capacity |
| `components/c3_checkpointing/` | Cognitive Checkpointing Module | Continuity |
| `components/c4_hcde/` | Human Capability Development Engine | Autonomy + Competence |
| `shared/` | Common schema, auth, DB, config used by all components | - |
| `orchestration/` | Integration layer that routes between components | - |

## Branching

- `main` - stable, merged from `dev` at milestones (progress reviews, pre-test launch).
- `dev` - integration branch. Everyone merges here often.
- Feature branches - short-lived, off `dev`, named `c<N>/<what>` (e.g. `c4/bkt-module`).

Each member works only inside their own `components/c<N>_*/` folder, so merges rarely conflict.
Changes to `shared/` need agreement from the team (see `CODEOWNERS`).

## Local setup

```bash
cp .env.example .env
docker compose up -d db          # PostgreSQL
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn components.c4_hcde.app.main:app --reload   # example: run HCDE
```
