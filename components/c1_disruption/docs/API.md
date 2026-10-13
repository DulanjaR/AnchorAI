# Component 1 API

> Approved by the owner 8 Oct 2026 (all four questions in §6 answered with the defaults).
> Ported 13 Oct 2026 from Node.js/Express to **Python/FastAPI** (`components/c1_disruption/app/`)
> with the same endpoints and behaviour; differences are listed in §7.

FastAPI app around the MVD engine. All storage goes through the repository interface
(`app/data/repository.py`), in-memory for now; the real database (PostgreSQL or
Firestore, open team decision) is plugged in later without changing the routes.

## 1. Ground rules

- **Base path** `/api` (one setting: `C1_API_PREFIX` in `app/settings.py`; the base path
  for orchestration is an open question). JSON in, JSON out. Times are `HH:MM`, dates `YYYY-MM-DD`,
  deadlines `YYYY-MM-DDTHH:MM`, all in Sri Lanka time (Asia/Colombo).
- **Team API key:** header `X-API-Key` on **every** request, `/health` included, checked by
  `shared.auth.require_api_key` (value: `API_KEY` in `.env`, `shared.config`). Wrong or
  missing → `401 INVALID_API_KEY`. Checked before anything else.
- **Who is calling:** header `X-User-Id: <id>` on every `/api` request. This is a
  stand-in until real user auth is set up (team decision).
- **Disruption types** come from `DISRUPTION_KINDS` in the engine config: environment (`power_outage`, `transport_delay`, `connectivity_failure`) and unavailable (`urgent_work`, `family_obligation`, `health_issue`). For an unavailable type the window is taken time: nothing is placed in it (Task 2a). The generated MVD includes `disruption.kind`.
- **No auto-actions** (CLAUDE.md rule 5): an MVD is generated only for a disruption
  the user has **confirmed**; nothing starts, cascades or finalises by itself.
- **Errors:** `{ "error": { "code", "message" } }` with
  `400` invalid input (unknown fields are refused too, so typos are caught; malformed JSON → `INVALID_JSON`) · `401` no or wrong `X-API-Key` (`INVALID_API_KEY`) or no `X-User-Id` (`NO_USER`) · `404` not found (or another user's data) · `409` wrong state
  (e.g. deciding an MVD twice) · `422` the engine cannot plan (e.g. a `null` EF value;
  the message names the disruption and task type).
- **Clock:** "now" is injected (`create_app(store=..., clock=...)`), so tests are repeatable.

## 2. Data (one record type per repository collection)

| Collection | Main fields |
|---|---|
| `users` | `id`, `workStart`, `workEnd` |
| `protectedBlocks` | `id`, `userId`, `label`, `start`, `end` (may cross midnight, e.g. sleep 22:00–06:00) |
| `tasks` | `id`, `userId`, `title`, `type` (Digital/Analog/Meeting/Fixed), `priority` (High/Medium/Low), `estimatedHours`, `deadline`, `delegable`, `plannedDate`, `plannedStart`, `plannedEnd` (the original plan), `status` (planned/in_progress/done/partial/not_done), `startedAt`, `doneAt`, `mvdTag`, `mvdStart`, `mvdEnd`, `mvdId` |
| `disruptions` | `id`, `userId`, `date`, `type`, `start`, `timeLostMinutes`, `end` (derived), `severity` (1–3), `confirmed: true`, `suggestedType`, `reportedAt` |
| `mvds` | `id`, `userId`, `disruptionId`, `parentMvdId`, `date`, `planFrom`, `status` (proposed/superseded/accepted/edited/rejected), `input` (the exact engine input, so any MVD can be re-run), engine output (tasks with tag, slot, reason, explanation, deadline risk; protected blocks; warnings; `freeMinutesLeft`), `comparison`, `finalPlan` |
| `feedback` | `id`, `userId`, `mvdId`, `action` (accept/edit/reject), `edits` (what the user changed), `reason`, `at` |
| `completions` | `id`, `userId`, `taskId`, `date`, `source` (buttons/review), `outcome` (done/partial/not_done), `partialPct` (25/50/75), `actualMinutes` |
| `signals` | reserved for passive-signal events from Flutter (not used in Task 3) |

## 3. Endpoints

### Settings and protected blocks
| Method | Path | Does |
|---|---|---|
| GET / PUT | `/api/me/settings` | Read / set work hours `{ workStart, workEnd }` |
| GET / POST | `/api/protected-blocks` | List / create a protected block |
| PATCH / DELETE | `/api/protected-blocks/:id` | Change / delete one |

### Tasks (CRUD + completion buttons, CLAUDE.md §3.5)
| Method | Path | Does |
|---|---|---|
| GET | `/api/tasks?date=YYYY-MM-DD` | List tasks (optionally for one planned date) |
| POST | `/api/tasks` | Create a task |
| GET / PATCH / DELETE | `/api/tasks/:id` | Read / change / delete one |
| POST | `/api/tasks/:id/start` | **Start Task** button: records `startedAt` |
| POST | `/api/tasks/:id/done` | **Mark Done** button: records `doneAt` and a completion with `actualMinutes` (overruns are stored, never cascaded) |

### Disruption and MVD (CLAUDE.md §3.3 steps 11–13)
| Method | Path | Does |
|---|---|---|
| POST | `/api/disruptions` | User-confirmed report: `{ date, type, start, timeLostMinutes (1–1439), severity (1–3), suggestedType?, confirmed: true }`. Without `confirmed: true` → `400 NOT_CONFIRMED`. The window is `start` → `start + timeLostMinutes` (the engine clips it at midnight). |
| GET | `/api/disruptions/:id` | Read one |
| POST | `/api/disruptions/:id/mvd` | **Generate** a proposed MVD. Body (optional): `{ planFrom?, manualReplan? }`; `planFrom` defaults to now. Input to the engine: the user's work hours, protected blocks, and that day's tasks that are not done. Returns the MVD **and** the three-way comparison: original plan / manual replan (if sent) / MVD. If an accepted/edited MVD already exists for that day, it is stored as `parentMvdId` (second disruption, tentative): the engine then replans only that MVD's Keep/Reduce tasks that are not done, and the comparison's "original" is that MVD's final plan. `planFrom` defaults to now on the day itself, otherwise to work start. A newer proposal for the same disruption marks an undecided older one `superseded`. No work hours → `409 NO_SETTINGS`; engine error (e.g. null EF) → `422`. |
| GET | `/api/mvds/:id` | Read one |
| POST | `/api/mvds/:id/accept` | Finalise as proposed. Writes `mvdTag`, `mvdStart`, `mvdEnd`, `mvdId` onto each task (for Components 3 and 4). Feedback `accept`. |
| POST | `/api/mvds/:id/edit` | Finalise with the user's changes: `{ changes: [{ taskId, tag?, start?, end? }] }`. The changed plan is written to the tasks; the changes are stored in feedback as `{ taskId, before, after }` (`edit`, the richest signal for the bandit). Overlapping a protected block → `400 PROTECTED_BLOCK_OVERLAP`, nothing written. Move/Delegate clear the slot. |
| POST | `/api/mvds/:id/reject` | `{ reason? }`. Nothing is written to the tasks. Feedback `reject`. |

An MVD can be decided **once** (accept, edit or reject); a second decision returns `409`.

### End-of-day review (backup completion detection, CLAUDE.md §3.5)
| Method | Path | Does |
|---|---|---|
| GET | `/api/reviews/:date` | Tasks of that day without a completion yet |
| POST | `/api/reviews/:date` | `{ items: [{ taskId, outcome: done/partial/not_done, partialPct? }] }` → completions (`source: review`), task status updated. `partialPct` (25/50/75) only with `partial`. All items are checked before anything is written. |

### For Components 3 and 4
`GET /api/tasks?date=...` returns `mvdTag` on every task: Component 3 reads **Keep**, Component 4 reads **Delegate**.

## 4. Code layout

```
components/c1_disruption/app/
├── main.py           create_app(store, clock): /health, mounts the routers under the prefix, error handlers
├── settings.py       C1Settings: api_prefix (env C1_API_PREFIX)
├── api/              one router per area: settings, protected_blocks, tasks, disruptions, mvds, reviews
│   ├── deps.py       require_user (X-User-Id stand-in), get_deps (store + clock)
│   ├── errors.py     ApiError + the error handlers (C1 app only)
│   ├── models.py     Pydantic request models, one per request body
│   └── validation.py field types with the Node API's rules and messages
├── services/
│   ├── mvd_service.py builds the engine input from stored data, applies decisions
│   ├── clock.py      "now" in Asia/Colombo (UTC+05:30); FixedClock for tests
│   └── owned.py      load a record and check it belongs to the caller (else 404)
└── data/
    ├── repository.py the interface every store implements (Protocol)
    └── memory_store.py in-memory implementation (a database store after the team decision)
```

Routes stay thin; the engine stays pure; `services/` is the only place that combines
stored data with the engine.

## 5. Tests (pytest, run from the repo root)

- Store contract tests (`tests/data/`), re-run later against the database store
- **All 57 frozen API cases** (`tests/golden/api_cases.json`, from the Node route tests):
  valid input, invalid input (400), other user's data (404), wrong state (409), edit and
  reject flows, second disruption sets `parentMvdId`, null EF → 422
- **Every golden scenario (S1–S16) replayed through the HTTP API** must give exactly the
  golden plan, every field (`tests/api/test_golden_flow.py`); accepted plans keep PTVR = 0
- API key on every route, the prefix setting, error shapes (`tests/api/test_auth_and_errors.py`)

## 6. Owner decisions (8 Oct 2026)

1. Disruption window = `start` + `timeLostMinutes` (the user confirms "time lost", CLAUDE.md §3.4).
2. An edit that overlaps a protected block is refused with `400` (PTVR must stay 0).
3. `X-User-Id` header as a stand-in for Firebase Auth until a teammate sets it up.
4. `severity` is stored for the bandit (Task 5) but does not change the MVD in Task 3.

## 7. Differences from the Node API (port, 13 Oct 2026)

1. **`X-API-Key` on every route** (team rule), including `/health`, which needed nothing in Node.
2. **Dates must exist:** `2026-02-30` is refused (`400`); Node rolled it over to 2 March
   (DECISIONS.md 2026-10-13).
3. **Which error is reported first** when a request has several problems: Pydantic checks
   the whole body before the route runs, so e.g. an invalid `manualReplan` gives `400`
   even when work hours are not set (Node: `409 NO_SETTINGS` first). Status codes for a
   request with one problem are unchanged.
4. **Only engine errors are `422`:** an unexpected error is `500 INTERNAL`; Node turned
   any error inside the engine call into `422`.
5. **Numbers** are returned as Python stores them: a whole number sent as `2` comes back
   as `2`; values the engine computes as floats (e.g. `efUsed`, `compressionPct`) may print
   as `1.0` / `50.0` where Node printed `1` / `50`. Same numeric value; explanation texts are
   identical (golden spec).
