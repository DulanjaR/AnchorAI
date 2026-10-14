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

## Data

`data/` holds the owner's SYNTHETIC persona set (made in the planning chat from PERSONAS.md):
`SYNTHETIC_personas.csv` (10 personas, with a free-text `specialHabits` column),
`SYNTHETIC_habits.csv` (the special habits as explicit fields), `SYNTHETIC_tasks_planned.csv`
(589 tasks, 30 days), `SYNTHETIC_schedule.csv` (every block of every day). `examples/` is a tiny
set for tests.

## Input format (`examples/` has a tiny example)

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

### `habits.csv` — special habits (optional; explicit fields, one row per persona that has any)

| Column | Meaning |
|---|---|
| `personaId` | must exist in `personas.csv` |
| `lateFactor`, `lateFrom` | × drift for tasks starting at or after `lateFrom` (both or neither) |
| `afterNightShiftFactor` | × drift for the first study task (earliest planned start) on a day after a night shift; a night-shift day = the schedule has an `office` block from 00:00 (needs a schedule) |
| `titleDrift` | `title prefix=drift` items separated by `;`: a task whose title starts with the prefix uses this drift **instead of** its type drift |
| `longTaskFactor`, `longTaskMinutes` | × drift for Digital tasks estimated at `longTaskMinutes` or more (both or neither) |

### `schedule.csv` — one row per block of a persona's day (optional)

| Column | Meaning |
|---|---|
| `personaId`, `day`, `date` | `date` must match `day` (day 1 = `START_DATE`) |
| `kind` | `sleep`, `routine`, `bus` (travel), `office`, `campus`, `family`, `tutor`, `fixed` (e.g. a quiz), `study_window` |
| `label` | shown in explanations of protected time |
| `start`, `end` | `HH:MM`; `end` may be `24:00`; a block crossing midnight is two rows on two days |

`study_window` (the data's name) means **free time for tasks of any kind**, not only study. With a
schedule, each day's engine input is built from it: **workHours** = first window start to last
window end; **protectedBlocks** = every other block inside that span plus the gaps between windows.
A window wins only over **travel** (`bus`) blocks (tasks on the bus or train); every other kind (quiz,
meals, work, campus, family, tutoring) stays protected even inside a window. Without a schedule the
persona's own `workStart`–`workEnd` and `protectedBlocks` are used.

**Disruptions** (layer C) can start at any time of the day, even in protected time: they happen
naturally and the student has no control over them. A disruption only **affects** the day when its
window overlaps the planned slot of at least one task; only then is an MVD made. The others are
counted as `no_effect`; events the engine cannot plan (a None EF value) as `cannot_plan`.

The loaders check every row and name the file, line and column of any problem.
