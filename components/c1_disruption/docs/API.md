# Component 1 API (Task 3)

> Approved by the owner 8 Oct 2026 (all four questions in §6 answered with the defaults). Implemented in `backend/src/`.

Node.js + Express 5 API around the MVD engine. All storage goes through the data-access
layer (`backend/src/data/`), in-memory for now; Firestore is plugged in later without
changing the routes.

## 1. Ground rules

- **Base path** `/api`. JSON in, JSON out. Times are `HH:MM`, dates `YYYY-MM-DD`,
  deadlines `YYYY-MM-DDTHH:MM`, all in Sri Lanka time (Asia/Colombo).
- **Who is calling:** header `X-User-Id: <id>` on every `/api` request. This is a
  stand-in until Firebase Auth is set up; it will be replaced by a Firebase ID token.
- **Disruption types** come from `DISRUPTION_KINDS` in the engine config: environment (`power_outage`, `transport_delay`, `connectivity_failure`) and unavailable (`urgent_work`, `family_obligation`, `health_issue`). For an unavailable type the window is taken time: nothing is placed in it (Task 2a). The generated MVD includes `disruption.kind`.
- **No auto-actions** (CLAUDE.md rule 5): an MVD is generated only for a disruption
  the user has **confirmed**; nothing starts, cascades or finalises by itself.
- **Errors:** `{ "error": { "code", "message" } }` with
  `400` invalid input (unknown fields are refused too, so typos are caught) · `401` no `X-User-Id` · `404` not found (or another user's data) · `409` wrong state
  (e.g. deciding an MVD twice) · `422` the engine cannot plan (e.g. a `null` EF value;
  the message names the disruption and task type).
- **Clock:** "now" is injected (`createApp({ store, clock })`), so tests are repeatable.

## 2. Data (one record type per future Firestore collection)

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
backend/src/
├── app.js            createApp({ store, clock }): wires routes, JSON errors
├── api/              one router per area: settings, protectedBlocks, tasks, disruptions, mvds, reviews
│   ├── auth.js       X-User-Id stand-in (Firebase Auth later)
│   ├── errors.js     ApiError + the one error handler
│   └── validate.js   small hand-written input checks (no new dependency)
├── services/
│   ├── mvdService.js builds the engine input from stored data, applies decisions
│   ├── clock.js      "now" in Asia/Colombo; fixed clock for tests
│   └── owned.js      load a record and check it belongs to the caller (else 404)
└── data/
    ├── repository.md the interface every store must implement (async methods)
    └── memoryStore.js in-memory implementation (firestoreStore.js later)
```

Routes stay thin; the engine stays pure; `services/` is the only place that combines
stored data with the engine.

## 5. Tests (Jest + supertest)

- Store contract tests (re-run later against `firestoreStore.js` / the emulator)
- Route tests per area: valid input, invalid input (400), other user's data (404), wrong state (409)
- **End-to-end flow:** set work hours and protected blocks → create tasks → report a power cut →
  generate → accept → tasks carry `mvdTag` → PTVR = 0 on the finalised plan
- Edit and reject flows; second disruption sets `parentMvdId`; null EF → 422
- **Every golden scenario (S1–S14) replayed through the HTTP API** must give the same tags, slots and reasons as the engine tests (`tests/api/goldenFlow.test.js`)

## 6. Owner decisions (8 Oct 2026)

1. Disruption window = `start` + `timeLostMinutes` (the user confirms "time lost", CLAUDE.md §3.4).
2. An edit that overlaps a protected block is refused with `400` (PTVR must stay 0).
3. `X-User-Id` header as a stand-in for Firebase Auth until a teammate sets it up.
4. `severity` is stored for the bandit (Task 5) but does not change the MVD in Task 3.
