# Progress log

Newest first. Format: see CLAUDE.md Section 8.
Working copy (since 13 Oct 2026): `D:\RESEARCH PROJECT\AnchorAI\components\c1_disruption` → GitHub `DulanjaR/AnchorAI`, branch `dev/ravindu`.
Entries before 13 Oct 2026 are from the Node project `D:\RESEARCH PROJECT\anchor-ai-component1` (`ravindu912/anchor-ai-component1`), now read-only.

## 2026-10-14 — Methodology update: engine extensions, logging, metrics, Model 1, Model 2, simulation, Colab — done (waiting for persona task lists)
Commits (dev/ravindu): 43f8ff5 engine strategy/range/diff · 453794e docs (METHODOLOGY.md, CLAUDE.md §3.6–3.8, DECISIONS) · 15de920 overload check · 1a0495c logging + ML hooks · 9cad504 metrics · 9f6f6a1 Model 1 · 577b841 Model 2 · next commit: simulation, notebooks, docs
Files created: engine/{strategy,diff,overload}.py; app/services/planning.py; metrics/{config,plan_metrics,records}.py; ml/drift/{settings,data,model,baselines,evaluation,corrector}.py; ml/bandit/{settings,actions,context,linucb,policies}.py; sim/{README.md,settings,personas,generate,events,experiment}.py, sim/examples/{personas,tasks}.csv; notebooks/01–03 *.ipynb; docs/METHODOLOGY.md; tests for each
Files changed: engine/{mvd,explain,schema}.py (strategy + range, defaults = approved); app/services/mvd_service.py, app/main.py (logging, ML hooks); requirements.txt (ML pins); CLAUDE.md §3.6–3.8, §5, §6, §7; docs/API.md (log fields); docs/DECISIONS.md; docs/TASK4_PLAN.md (superseded)
Tests: `pytest` (repo root) → 500 passed (C1 499 + C4 1); golden S1–S16 and all 57 API cases unchanged at every step; planted bugs caught (strategy ignored, no per-student bandit part, training leak in the simulation)
Decisions applied: DECISIONS.md 2026-10-14 (methodology revision, Model 1 redesign + library, Model 2 redesign + implementation, D-EVAL, D-MOVE PROPOSED, simulation rules, Colab notebooks)
Open questions for owner: use of the high duration in the Keep check; defer order and recovery timing values; D-MOVE rules; contents of D-SOURCE and D-HCP; all PROPOSED items (metric definitions, overload scope, explanation wording for other compress ratios, reward, simulation rules, TIGHT_SLACK_THRESHOLD 0.10); Model 1 range looked conservative on the test fixture (95% vs nominal 80%)
Next step: owner sends the persona task lists (P01–P10, sim/README.md format) → run notebooks/03 for the SYNTHETIC results

## 2026-10-13 — Port to the team repo (Python/FastAPI), phases 1–4 — done
Commits (dev/ravindu): 321f39c P1 golden spec frozen as JSON · 94a8584 P2 structure, CLAUDE.md v3.0, README, docs, pins · 21f23f1 P3 engine · 7897adf golden S11 text change · 5f99856 P4 FastAPI app
Files created: tests/golden/ (scenarios S01–S16.json, api_cases.json, README, tools/golden_from_node.js); engine/*; app/* (api, services, data); tests/{engine,golden,api,data}/*; CLAUDE.md, README.md, requirements.txt; docs copied from the Node project
Tests: `pytest` (repo root) → 337 passed after P4; `golden_from_node.js --check` → 16 scenarios + 57 API cases match the Node project; Node Jest 248/248 (unchanged); every Node test has a Python counterpart (mapping in the P4 report)
Decisions applied: DECISIONS.md 2026-10-13 (port, S11 golden text, impossible dates refused)
Open questions for owner: database (PostgreSQL vs Firestore); base path for orchestration; /health needs X-API-Key (team rule), see docs/API.md §7
Next step: methodology update (14 Oct)

## 2026-10-12 — Housekeeping: checkpoint v3 + draft survey committed — done
Commit: "Add checkpoint v3; survey marked DRAFT" (hash in `git log`), pushed to origin/main
Files created: docs/Component1_Checkpoint_v3.docx (Version 3, 9 Oct 2026)
Files changed: docs/Pre_test_PartA_C1_C2_C3.docx (team's updated draft: C1 Q6 is now a feasibility grid); docs/DECISIONS.md (survey marked DRAFT); docs/PROGRESS.md (real hash 09e0f49 on Task 3b)
Tests: no code changed
Decisions applied: DECISIONS.md 2026-10-12 (survey DRAFT)
Open questions for owner: see the Task 3b entry's note below, now partly outdated by the new survey grid (not changed, per owner)
Next step: Task 4 plan (stop for approval before code)

## 2026-10-12 — Task 3b: decisions of 9–10 Oct recorded (docs only) — done
Commit: 09e0f49 ("Task 3b: record 9-10 Oct decisions (one-tap recording, disruption times, pre-test)"), pushed to origin/main
Files created: docs/Pre_test_PartA_C1_C2_C3.docx (copied from Downloads; blank questionnaire, no answers or personal data)
Files changed:
- CLAUDE.md: §3.4 one-tap disruption recording + the four uses of disruption times; §3.6 Model 1 exclusion rule + provisional starting drift; §3.7 context features + provisional starting ranking; §3.8 pre-test question → parameter table; §5 structure; §6 Q1 note
- docs/DECISIONS.md: entries 2026-10-09 (one-tap recording), 2026-10-09 (disruption times), 2026-10-10 (pre-test)
- docs/PROGRESS.md: real hash 249092d on the Task 2a entry
Not done: docs/Component1_Checkpoint_v3.docx was not found on this laptop (Downloads has Component1_Checkpoint.docx and Component1_Checkpoint_Updated.docx, both "Last updated: September 2026"). Waiting for the owner to point to the v3 file.
Not created: ml-service/data/pretest_priors.json (no survey answers yet; values would be invented)
Tests: no code changed; `cd backend && npx jest` → 248 passed (run as a check)
Decisions applied: DECISIONS.md 2026-10-09 (×2), 2026-10-10
Open questions for owner: location of Component1_Checkpoint_v3.docx; CLAUDE.md §6 Q1–Q5
Next step: Task 4 (ML Model 1 on synthetic data; pin ml-service requirements first)

## 2026-10-12 — Task 2a: disruption kinds in the engine — done
Commit: 249092d ("Task 2a: disruption kinds (environment / unavailable)"), pushed to origin/main
Files created: none
Files changed:
- backend/src/engine/config.js: `TASK_TYPES`, `DISRUPTION_KINDS` (new type `urgent_work`); `ENV_FEASIBILITY` keeps only environment kinds
- backend/src/engine/fi.js: `disruptionKind()`
- backend/src/engine/mvd.js: unavailable kind removes the window from free time, skips the EF lookup (EF 1.0) and window-first; output has `disruption.kind`
- backend/src/engine/classify.js: reason `TIME_TAKEN_BY_DISRUPTION`
- backend/src/engine/explain.js: its template
- backend/src/api/validate.js: disruption and task types read from `DISRUPTION_KINDS` / `TASK_TYPES`
- backend/tests/golden/scenarios.js: R13 rule, S15 (owner-specified), S16 (time-taken, Delegate, Meeting without EF); written first, approved by owner
- backend/tests/helpers/invariants.js: nothing may sit inside an unavailable window
- backend/tests/engine/stress.test.js: random days now use both kinds
- backend/tests/engine/{fi,classify,explain,mvd}.test.js: kinds, config consistency, reason order, template, unavailable edge cases (Meeting/Fixed without EF, unknown task type, midnight clipping)
- CLAUDE.md: §3.3 step 2 (kinds), step 10 (new code), §4 config, §6 Q1 narrowed, §7 Task 2a ticked
- docs/API.md: disruption types and kinds
- docs/DECISIONS.md: 2026-10-12 entry; docs/PROGRESS.md: real hash 61fd6fe on the Task 3 entry
Tests: `cd backend && npx jest` → 248 passed (14 suites), 0 failed; `ml-service/.venv` pytest → 1 passed
Checks: the old engine failed only S15 and S16. Planted bugs (unavailable window left as free time; TIME_TAKEN reason missing) made 10 and 3 tests fail. S15 and S16 also pass through the HTTP API (goldenFlow).
Decisions applied: DECISIONS.md 2026-10-12
Open questions for owner: CLAUDE.md §6 Q1–Q5 (Q1 narrowed)
Next step: Task 4 (ML Model 1 on synthetic data; pin ml-service requirements first)

## 2026-10-08 — Task 3: Node.js API around the engine — done
Commit: 61fd6fe ("Task 3: Node.js API around the engine"), approved by owner, pushed to origin/main
Files created:
- docs/API.md: endpoint contract (approved design, updated to match the code)
- backend/src/data/repository.md, memoryStore.js: data-access interface + in-memory store
- backend/src/api/{auth,errors,validate,settings,protectedBlocks,tasks,disruptions,mvds,reviews}.js
- backend/src/services/{mvdService,clock,owned}.js
- backend/tests/data/{store.contract.js,memoryStore.test.js}
- backend/tests/api/{helpers.js,basics,tasks,mvds,reviews,goldenFlow}.test.js
Files changed:
- backend/src/app.js: `createApp({ store, clock })`, mounts `/api` routers behind `X-User-Id`, one JSON error handler
- CLAUDE.md §5: repository structure (services/, tests/api, tests/data, docs/API.md)
- docs/DECISIONS.md: 2026-10-08 entry
- docs/PROGRESS.md: real hash 928e0c6 on the previous entry
Tests: `cd backend && npx jest` → 218 passed (14 suites), 0 failed; `ml-service/.venv` pytest → 1 passed
Checks:
- Every golden scenario S1–S14 replayed through HTTP gives the same tags, slots, reasons and deadline risk as the engine tests; S11 gives 422; accepted plans keep PTVR = 0.
- Test-the-tests: dropping the `delegable` flag in the service, or removing the protected-block check on edits, each made a test fail.
- Real server started on a spare port: /health, PUT settings and the 401 without X-User-Id all behave as documented.
Decisions applied: DECISIONS.md 2026-10-08
Open questions for owner: the implementation choices listed in DECISIONS.md 2026-10-08 (object to any); CLAUDE.md §6 Q1–Q5
Next step: Task 4 (ML Model 1 on synthetic data; pin ml-service requirements first)

## 2026-10-06 — Task 2 fix: midnight-crossing disruptions clipped (S14) — done
Commit: 928e0c6 ("Task 2 fix: clip midnight-crossing disruption windows (S14)"), pushed to origin/main
Files created: none
Files changed:
- backend/src/engine/time.js: new `windowToInterval(disruption)`, which clips a window that crosses midnight at 24:00
- backend/src/engine/mvd.js: uses `windowToInterval` instead of reading start/end directly
- backend/tests/helpers/invariants.js: uses the same helper, so the gate check sees clipped windows (it previously missed them)
- backend/tests/golden/scenarios.js: new S14 (expected output written first, approved by owner)
- backend/tests/engine/stress.test.js: about 1 in 4 random windows now cross midnight
- backend/tests/engine/time.test.js: `windowToInterval` tests
- CLAUDE.md: §3.3 step 2 states the clipping rule; §6 Q9 marked resolved
- docs/DECISIONS.md: 2026-10-06 (later) entry
Checks: the old engine failed exactly S14 A1 and D2. With clipping switched off on purpose, 3 tests fail; restored, all pass.
Tests: `cd backend && npx jest` → 140 passed (8 suites), 0 failed; `ml-service/.venv` pytest → 1 passed
Decisions applied: DECISIONS.md 2026-10-06 (later)
Open questions for owner: CLAUDE.md §6 Q1–Q5
Next step: Task 3 (Node.js API around the engine)

## 2026-10-06 — Task 2 fixes: free-time note, midnight open question — done
Commit: 8fe49be ("Task 2 fixes: free-time note for LOW_URGENCY, midnight open question"), pushed to origin/main
Files created: none
Files changed:
- backend/src/engine/explain.js: `LOW_URGENCY` adds "You have free time today, so you can start it early if you like." when `freeMinutesLeft > 0`
- backend/src/engine/mvd.js: computes `freeMinutesLeft` after placement, passes it to the explanations, and returns it in the MVD
- backend/tests/engine/explain.test.js, mvd.test.js: note shown with free time (golden S2, A2), not shown when the day is full (golden S7, L1), only for LOW_URGENCY
- CLAUDE.md: §3.3 step 10 describes the note; §6 Q9 midnight-crossing disruptions
- docs/DECISIONS.md: 2026-10-06 (late night) entry
Already done before this request (commit 2977019): Q6 revision, golden S13 (approved), reason codes in §3.3 = classify.js, deadline-risk rule. Not redone.
Tests: `cd backend && npx jest` → 133 passed (8 suites), 0 failed; `ml-service/.venv` pytest → 1 passed
Decisions applied: DECISIONS.md 2026-10-06 (late night)
Open questions for owner: CLAUDE.md §6 Q9: support midnight-crossing disruptions, or reject them with a clear error? (Currently ignored silently.) Also Q1–Q5.
Next step: owner answers Q9, then Task 3 (Node.js API around the engine)

## 2026-10-06 — Task 2 fixes before Task 3 (Q6 revision, S13, deadline risk) — done
Commit: 2977019 ("Task 2 fixes: window-first inside the window, S13, deadline-risk rule"), pushed to origin/main
Files created: none
Files changed:
- backend/src/engine/mvd.js: `findSlot` window-first now tries a slot wholly inside the window first, starting at max(gap start, window start); falls back to the gap start only if the task does not fit inside the window
- backend/src/engine/classify.js: `hasDeadlineRisk` = Move and (due within `DEADLINE_RISK_DAYS` or Fi < 0.5)
- backend/src/engine/config.js: added `DEADLINE_RISK_DAYS: 1`
- backend/tests/golden/scenarios.js: new S13 (owner-specified); S12 A1 → 14:00–16:00; S6 R1, S7 L2, S8 N1 → deadlineRisk true; rules R6 and R10 rewritten. Expected outputs written first, approved by owner, then the engine was changed (the unfixed engine failed exactly those 6 tests)
- backend/tests/engine/classify.test.js, mvd.test.js: risk-rule cases updated; new test for the gap-start fallback (task longer than the window)
- CLAUDE.md: §3.3 step 6 (Q6 revision), step 9 (risk rule), step 10 (reason codes = classify.js); §4 adds DEADLINE_RISK_DAYS; §6 Q6–Q8 closed
- docs/DECISIONS.md: 2026-10-06 (night) entry
Tests: `cd backend && npx jest` → 130 passed (8 suites), 0 failed; `ml-service/.venv` pytest → 1 passed
Decisions applied: DECISIONS.md 2026-10-06 (night)
Open questions for owner: CLAUDE.md §6 Q1–Q5 (Q5 = gate "after" vs "outside"; the file uses "before or after")
Next step: Task 3 (Node.js API around the engine)

## 2026-10-06 — Housekeeping: merge C:\ copy into D:\ — done
Commit: see `git log -1` (merge commit, made after this entry was written)
Files created: `.gitkeep` in backend/src/api, backend/src/data, ml-service/app/drift, ml-service/app/bandit, ml-service/data, ml-service/notebooks (git does not track empty folders)
Files changed:
- CLAUDE.md: v2 draft from C:\ (12 rules, §8 log format, tag-by-outcome table, survey note, open question 4) merged with Q5/Q6 and the Task 2 status → v2.1. Conflicts listed as §6 Q5–Q8.
- docs/DECISIONS.md: both copies' entries combined, nothing dropped; merge entry added.
- docs/PROGRESS.md: rewritten in the §8 format; Task 1 entry taken from C:\.
- backend/src/engine/config.js + fi.js: `NORMAL_EF` renamed `OUTSIDE_WINDOW_EF` (v2 name); gate comment reworded as v2 asks (says "outside (before or after)", per the approved rule).
Tests: `cd backend && npx jest` → 122 passed, 0 failed
Decisions applied: DECISIONS.md 2026-10-06 (evening)
Open questions for owner: CLAUDE.md §6 Q5–Q8 (gate after vs outside, slot choice, reason-code names, deadline-risk rule)
Next step: owner answers §6 Q7–Q8 if desired, then Task 3 (Node.js API around the engine). The C:\Users\ravin copy can be archived or deleted.

## 2026-10-06 — Task 2: Fi + MVD engine with golden tests — done
Commit: bb0454d ("Task 2: Fi + MVD engine with golden tests"), pushed to origin/main
Files created:
- backend/src/engine/time.js: HH:MM ↔ minutes, calendar days, interval subtraction, overnight blocks
- backend/src/engine/fi.js: EF lookup (throws on `null`), feasibility gate, EF-for-Fi (Q1 + Q5), Deadline Proximity, Fi
- backend/src/engine/classify.js: placement groups A–D, placement order (Q4), tag by outcome (Q2/Q3), reason codes, deadline risk
- backend/src/engine/explain.js: one plain-language explanation per reason code, plus a deadline warning
- backend/src/engine/mvd.js: `generateMvd(input)`: free gaps → score → place A, B, C in order (window-first, one contiguous slot, compress into the largest gap) → tag/reason/explain
- backend/tests/golden/scenarios.js: S1–S12, hand-worked, Fi calculation in every comment, approved before the engine was written
- backend/tests/golden/golden.test.js: per-task Fi/EF/tag/slot/compression/reason/risk, plus PTVR = 0 per scenario
- backend/tests/helpers/invariants.js: PTVR = 0, no overlaps, inside the horizon, gate respected, ≤ 50% compression, every task explained
- backend/tests/engine/{fi,classify,time,explain,mvd,stress}.test.js: unit tests + 500 seeded random days (test fixtures, not research data)
- docs/PROGRESS.md
Files changed:
- backend/src/engine/config.js: gate comment updated; added the outside-window EF constant (1.0)
- CLAUDE.md: Q5 line in §3.1; Task 2 ticked
- docs/DECISIONS.md: Q5, Q6
Tests: `cd backend && npx jest` → 122 passed (8 suites), 0 failed
Checks: every Fi and compression % recomputed by script (0 mismatches). Test-the-tests: planted bugs (window-first off, largest-gap tie flipped, `<=` on the Keep threshold) were each caught; a planted protected-block overlap reports PTVR = 0.33.
Golden scenarios:

| # | What it checks |
|---|---|
| S1 | Morning outage: Analog in the outage, Digital after it (EF 1.0), fitting Reduce candidate → Keep (`FITS_FULLY`) |
| S2 | Long outage: Digital cannot fit after the window even at 50% → Move + deadline risk; Fi > 2 → Move (`LOW_URGENCY`) |
| S3 | Transport delay: Digital allowed in the window (EF 0.7); variable compression (33.3%) |
| S4 | Keep overflow: Fi tie broken by earlier deadline; last task reduced to exactly 50% |
| S5 | Keep task cannot fit even at 50% → Move + deadline risk (`BUDGET_EXCEEDED`) |
| S6 | Non-High tasks with Fi < 0.5 placed before other Reduce candidates; Keep if uncompressed |
| S7 | Replan after the disruption is over: EF = 1.0 for all; compress only as needed (20%) |
| S8 | Delegate = delegable AND not placed; a delegable task that fits is placed |
| S9 | Afternoon power cut: Digital before the window, Analog inside it |
| S10 | Several protected blocks (one in the window, one overnight): no task spans a block |
| S11 | `null` EF throws an error naming disruption and task type |
| S12 | Window-first (Q6): Analog goes towards the outage, leaving the morning for Digital |

Decisions applied: DECISIONS.md Q1–Q4, Q5 (Fi computed once), Q6 (window-first at gap start, S12)
Open questions for owner: none at the time (the merge later raised §6 Q5–Q8)
Next step: Task 3

## 2026-10-06 — Task 1: project skeleton — done
Commit: 5bb2fc7 ("Task 1: project skeleton for Component 1")
Files created: CLAUDE.md, .gitignore, app/README.md, docs/DECISIONS.md, backend/package.json, backend/src/app.js, backend/src/server.js, backend/src/engine/config.js, backend/tests/health.test.js, ml-service/requirements.txt, ml-service/app/__init__.py, ml-service/app/main.py, ml-service/tests/test_health.py; empty folders backend/src/{api,data}, ml-service/{data,notebooks,app/bandit,app/drift}
Files changed: none
Tests: backend `npm test` → 2 passed; ml-service `pytest` → 1 passed (1 httpx deprecation warning, harmless)
Decisions applied: DECISIONS.md 2026-10-06 (morning)
Open questions for owner: none
Next step: Task 2 (done, see above)
