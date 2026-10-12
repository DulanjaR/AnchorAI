# C3 – Cognitive Checkpointing (Task Continuity)

C3 helps working IT students resume their work after an interruption. The student
saves a short checkpoint (goal, completed work, current point, next step, resources),
and C3 predicts how hard it will be to resume (Low / Medium / High) and produces a
restart summary. C3 only summarises the student's own progress; it never generates
task content (that is C4).

## Folder layout

- `CLAUDE.md` – project rules and scope for Claude Code in this component.
- `.gitignore` – keeps datasets, model weights and large files out of git.
- `notebooks/` – Google Colab notebooks (classifier and Qwen fine-tuning).
- `data/raw/hirsch/` – Hirsch et al. dataset and codebook (local only, git-ignored).
- `data/generated/` – synthetic checkpoint -> restart summary pairs (`.jsonl`).
- `models/` – trained models such as `c3_difficulty_model.pkl` (git-ignored).
- `outputs/` – charts and evaluation results.
- `parser/` – read-only parsers that pre-fill checkpoint fields from text files.
- `app/` – the C3 application code.
- `tests/` – automated tests.
