# sim — synthetic simulation (everything here is **SYNTHETIC**)

Pipeline validation only, never a research finding (CLAUDE.md rule 6). Layers
(docs/METHODOLOGY.md §7):

| Layer | What | Code |
|---|---|---|
| **A** planned tasks | the owner's persona task lists (`personas.csv`, `tasks.csv`) | `personas.py` |
| **B** actual durations | planted drift per persona × noise (seeded) | `generate.py` |
| **C** disruptions | random confirmed disruptions (seeded), with their overlap on planned tasks | `generate.py` |
| **D** MVDs + decisions | engine runs (raw vs corrected durations), simulated Accept / Edit / Reject | `events.py` |

`experiment.py` runs all layers for every persona × seed (default seeds 11, 22, 33, 44, 55) and
returns the Model 1 evaluation (leave-one-student-out, rolling-origin, baselines B0–B3) and the
event metrics, every table labelled SYNTHETIC. Two extra cases: a **null persona** (no drift) and a
**misspecified generator** (drift also depends on a hidden daily factor the model cannot see).

## Input format (fill these in; `examples/` has a tiny example)

### `personas.csv` — one row per persona

| Column | Required | Meaning |
|---|---|---|
| `personaId` | yes | e.g. `P01` |
| `label` | yes | short description, e.g. "working student, evening shifts" |
| `workStart`, `workEnd` | yes | `HH:MM` |
| `protectedBlocks` | no | `label start-end` items separated by `;`, e.g. `Lunch 12:30-13:30; Sleep 22:00-06:00` |
| `driftDigital`, `driftAnalog`, `driftMeeting`, `driftFixed` | no | planted drift multiplier per task type (actual ÷ estimate), default 1.0 |
| `eveningFactor` | no | extra multiplier for tasks starting 18:00 or later, default 1.0 |
| `weekendFactor` | no | extra multiplier on Saturday/Sunday, default 1.0 |
| `noiseSd` | no | noise sd on the log scale, default 0.10 |
| `preferredStrategy` | no | hidden strategy the simulated student prefers (`default`, `compress_25`, `no_compress`), default `default` |

### `tasks.csv` — one row per planned task (layer A)

| Column | Required | Meaning |
|---|---|---|
| `personaId` | yes | must exist in `personas.csv` |
| `day` | yes | 1, 2, 3, … (day 1 = `sim/settings.py` `START_DATE`, a Monday) |
| `taskId` | yes | unique within the persona |
| `title` | yes | |
| `type` | yes | `Digital` / `Analog` / `Meeting` / `Fixed` |
| `priority` | yes | `High` / `Medium` / `Low` |
| `estimatedMinutes` | yes | the student's own estimate |
| `deadlineInDays` | yes | 0 = due that day, 1 = next day, … |
| `deadlineTime` | no | `HH:MM`, default `23:59` |
| `plannedStart`, `plannedEnd` | no | the original plan slot `HH:MM` (both or neither) |
| `delegable` | no | `true` / `false`, default `false` |

The loader checks every row and names the file, line and column of any problem.
