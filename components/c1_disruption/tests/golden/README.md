# Golden spec (frozen 13 Oct 2026)

Language-neutral copy of Component 1's approved behaviour, exported from the Node
project (`anchor-ai-component1`, commit `2bfedfa`) before the port to Python.
**This folder is the spec.** The Python engine and API must reproduce it exactly.
Never change an expected value to make a test pass; report the mismatch to the owner
(CLAUDE.md rule 7).

| File | What |
|---|---|
| `scenarios/S01.json` … `S16.json` | Golden scenarios S1–S16: engine input + expected output |
| `api_cases.json` | 57 HTTP cases from the Node API tests (basics, settings, protected blocks, tasks, reviews, disruptions, MVDs) |
| `tools/golden_from_node.js` | Exporter / checker against the old Node project (read-only) |

## Scenario files

`input` is the exact engine input. `expected` holds:

- **Approved fields** (hand-worked by the owner, test-first, in `scenarios.js`):
  per task `fi`, `efUsed`, `tag`, `start`, `end`, `compressionPct`, `reason`,
  `deadlineRisk`; per protected block `tag`, `start`, `end`, `reason`.
- **Engine-captured fields** (output of the approved Node engine, not hand-worked):
  per task `group` and `explanation`; per block `explanation`; `order` (placement
  order = order of `tasks` in the engine output), `horizon`, `disruptionKind`,
  `freeMinutesLeft`, `warnings`.
- `workings`: the hand-written Fi calculations from the `scenarios.js` comments
  (scenario level and per task). Documentation only, not compared.
- S11 has `expected.error` instead: the engine must raise an error whose message
  matches `messageRegex` (approved) and equals `message` (captured); over HTTP it is
  `422` with that message.

Comparison: `fi` after rounding to 3 decimal places (rule R12); everything else exactly.
JSON writes `1.0` as `1`; numeric equality is meant.

## Deliberate changes after the freeze

Only with owner approval, each in its own commit and logged in `docs/DECISIONS.md`.
The Node text is kept next to the new one so the Node checker still verifies it.

| Date | Where | Change |
|---|---|---|
| 13 Oct 2026 | `S11.json` `expected.error.message` | `(null in config.js; …)` → `(null in engine/config.py; …)`; old text kept as `nodeMessage` |

`tools/golden_from_node.js --write` regenerates from Node and would undo these; use `--check`.

## Rules used for the expected outputs (copied from `scenarios.js`)

```
R1  Fi = max(daysUntilDeadline, 0.5) × priorityScore / (hours × EF).
    daysUntilDeadline = calendar days between plan date and deadline date
    (due today = 0 → floored to 0.5).
    EF (Q1) = feasibility in the slot the task would run in:
      - disruption EF < 0.3 → task can only run outside the window → EF = 1.0
      - disruption EF ≥ 0.3 and the window is still inside the planning horizon
        → the task would run in the window (window-first, R6) → disruption EF
      - the window is entirely before the horizon (already over) → EF = 1.0
    Fi is computed ONCE, before placement. (The null check still happens for
    every task, even if EF ends up as 1.0.)
R2  Planning horizon = [max(workStart, planFrom), workEnd]. Free gaps =
    horizon − protected blocks. Protected blocks outside work hours are still
    returned as Protect but don't affect placement.
R3  Groups, placed in this order:
      A. Fi < 0.5 AND High          (Keep candidates)
      B. Fi < 0.5 AND not High      (Reduce candidates, placed first — 6a)
      C. 0.5 ≤ Fi ≤ 2.0             (Reduce candidates)
      D. Fi > 2.0                   (never placed)
    Within every group (Q4): Fi ascending, ties → earliest absolute deadline,
    then shortest duration. Tasks are placed one by one in this order, so when
    time runs out, the LAST task in the order is the one that gets reduced.
R4  A task is placed as ONE contiguous slot (never split across a protected
    block or a gap).
R5  Feasible gaps: disruption EF ≥ 0.3 → any free gap; disruption EF < 0.3 →
    free gaps with the disruption window cut out (before or after it).
R6  Uncompressed slot choice (Q6 revised 6 Oct 2026, approved),
    for EF ≥ 0.3 tasks while the window is active ("window-first", saves normal
    time for tasks that need it):
      a) INSIDE the window: earliest gap where the task fits wholly inside
         gap ∩ window, starting at max(gap start, window start);
      b) else a gap that overlaps the window and holds the whole task, starting
         at the gap start (the old Q6 rule);
      c) else the earliest gap that holds the whole task, at the gap start.
    Blocked tasks (EF < 0.3) use only (c), on gaps with the window cut out.
R7  If no gap fits the whole duration: compress into the LARGEST feasible gap
    (least compression = "only as much as needed"; ties → earliest), filling
    it, provided gap ≥ 50% of duration. Otherwise the task is unplaced. A task
    can also be compressed simply because no single gap is long enough (R4).
R8  Tags by outcome (Q2): placed uncompressed → Keep; placed compressed →
    Reduce; unplaced → Delegate if delegable, else Move (Q3). Group D → unplaced.
R9  Reason code, one per task (precedence top-down):
      Placed:   REDUCE_BUDGET (compressed) > OUTSIDE_DISRUPTION_WINDOW (EF<0.3)
                > KEEP_URGENT (group A) | FITS_FULLY (groups B, C)
      Unplaced: DELEGABLE > BLOCKED_BY_DISRUPTION (EF<0.3) > LOW_URGENCY (Fi>2)
                > BUDGET_EXCEEDED
      Protected blocks: PROTECTED_BLOCK
R10 deadlineRisk = true iff tag is Move AND (due today or tomorrow OR Fi < 0.5).
    (Revised 6 Oct 2026, approved; was "due today OR Fi < 0.5".)
R11 compressionPct = round(100 × (1 − placedMinutes / estimatedMinutes), 1 dp).
R12 fi is compared to 3 decimal places; efUsed is the EF that went into Fi.
R13 Disruption kinds (Task 2a, 12 Oct 2026, approved):
      environment (power_outage, transport_delay, connectivity_failure):
        rules R1–R12 as above (EF decides what can run in the window).
      unavailable (urgent_work, family_obligation, health_issue): the window
        is removed from free time like a protected block. Nothing is placed in
        it, there is no EF lookup (so no null-EF error) and no window-first;
        every task's Fi uses EF = 1.0 (it can only run outside the window).
    Reason for an unplaced task (R9 extended), first match wins:
      DELEGABLE > BLOCKED_BY_DISRUPTION > LOW_URGENCY (Fi > 2)
      > TIME_TAKEN_BY_DISRUPTION (kind unavailable) > BUDGET_EXCEEDED
```

Every scenario must also pass the invariants: PTVR = 0, no overlapping tasks, every
slot inside the horizon, no EF < 0.3 task inside the window, nothing inside an
unavailable window, compression within 0–50%, every task explained.

## API case format (`api_cases.json`)

Each case starts with an **empty store** and a **fixed clock** at `now`
(default `defaultNow`, Asia/Colombo local time). `fixture` names a list of steps in
`fixtures` that runs first. Steps run in order:

- **HTTP step:** `as` (value of `X-User-Id`; `null` = header not sent), `method`,
  `path`, optional `body`, `rawBody` (sent as-is, for malformed JSON), `headers`,
  `expect`, and `save` (stores the response body under a name).
- **`{"setNow": "YYYY-MM-DDTHH:MM"}`** moves the clock.
- **Store step:** `{"store": {"collection", "where"}, "expect"}` lists the
  repository's records (insertion order) filtered by exact field values.

`${name.field}` in any string is replaced by a saved value; a string that is only
`${name}` is replaced by the whole saved object. A body `{"$task": {...}}` or
`{"$disruption": {...}}` is the matching entry in `templates` with those fields
overridden; `"$omit": [..]` removes fields.

`expect` keys: `status`; `equals` (exact); `match` (partial: objects need only the
listed keys, arrays need the same length and match element by element);
`length`; `errorCode` / `messageRegex` (on `body.error`); `at`: a list of
`{path, find?, pluck?, equals? | match?}` checks on a dotted path inside the body
(`""` = the body), where `find` picks the first array element matching an object and
`pluck` maps an array to one field. The string `"<any-string>"` matches any string.

For the Python app (team stack): the runner sends `X-API-Key` on every request
(shared `require_api_key`) and maps `/api` to the configured API prefix.

## Re-checking against the Node project

```
node tools/golden_from_node.js --check "D:\RESEARCH PROJECT\anchor-ai-component1"
```

Checks: (1) approved fields equal `scenarios.js`; (2) every field equals the Node
engine output; (3) every scenario replayed through the Node HTTP API gives the same
plan; (4) all API cases pass against the Node Express app. Needs the old project's
`backend/node_modules`. `--write` regenerates `scenarios/` (only needed if the Node
spec itself changed, which it should not).
