# Decision log

Dated record of design decisions for Component 1. Newest first.

## 2026-10-12 — Pre-test survey is a DRAFT
- `docs/Pre_test_PartA_C1_C2_C3.docx` is a **DRAFT**: the team is still finalising it. The final version will replace this file.
- Until then the pre-test mapping in CLAUDE.md §3.8 (and the 2026-10-10 entry below) stays **provisional**: question numbers and wording may change.
- Nothing else about the survey is changed now. `docs/Component1_Checkpoint_v3.docx` (Version 3, 9 Oct 2026, supersedes the September checkpoint) is added alongside it.

## 2026-10-10 — Pre-test questions set the starting values
- Component 1 has **10 questions (C1 Q1–Q10)** in the team survey `docs/Pre_test_PartA_C1_C2_C3.docx`. The answers set:
  - the **EF values** (C1 Q6–Q7) and **`MAX_COMPRESSION`** (Q10);
  - the **ML Model 1 starting drift per task type** (Q4–Q5);
  - the **ML Model 2 starting strategy ranking per disruption kind** (Q8–Q9);
  - the **synthetic-data parameters** (Q2–Q3).
- Starting values go in `ml-service/data/pretest_priors.json`, marked **PROVISIONAL** until the survey CSV arrives. **Models are trained on pilot data, not on the survey.**
- Recorded in CLAUDE.md §3.6, §3.7, §3.8 and §6 Q1. (Q1 of C1, part-time work hours, is not mapped to a parameter. The survey covers power cuts and internet failure, not transport delays or Fixed tasks.)

## 2026-10-09 — Disruption times are recorded
- Confirmed disruption start and end times are stored and used:
  - **for planning**: the remaining window (from now to the confirmed end);
  - **for ML Model 1**: training data excludes task time that overlaps a confirmed disruption (subtract the overlap, or drop the record);
  - **as ML Model 2 context**: kind, type, duration, time of day;
  - **for research statistics** and per-event metrics.
- Recorded in CLAUDE.md §3.4 (uses), §3.6 (exclusion rule) and §3.7 (context features).

## 2026-10-09 — One-tap disruption recording (app phase, after PP1)
- **Quick-reply buttons** on the +15-minute notification: Started / Power cut / Delayed / Something urgent came up.
- **Start and end times estimated from signals:** connectivity lost and restored, motion start and end, first missed Start tap.
- **New calendar events** that overlap planned tasks are detected as `urgent_work`.
- **On return:** a pre-filled "Looks like X from HH:MM to HH:MM, right?" plus "Is it still happening, until when?".
- **The user always confirms.** Fallback: from the first missed Start until return, and the user corrects it.
- Recorded in CLAUDE.md §3.4. No code change now (Flutter app, after PP1); the API already takes a confirmed start and time lost.

## 2026-10-12 — Task 2a: disruption kinds
- **Two kinds of disruption** (`DISRUPTION_KINDS` in config.js):
  - **environment**: `power_outage`, `transport_delay`, `connectivity_failure`. Conditions change; EF decides what can run in the window (unchanged rules).
  - **unavailable**: `urgent_work` (new type), `family_obligation`, `health_issue`. The student's time is taken. The window is removed from free time like a protected block: nothing is placed inside it, there is no EF lookup (so no null-EF error), no gate and no window-first; every task's Fi uses EF = 1.0.
  - *Why:* a family obligation or urgent work does not make laptop work physically impossible; it takes the time. Treating it as EF made no sense and forced invented EF values.
- **New reason code `TIME_TAKEN_BY_DISRUPTION`**: an unplaced, non-delegable task under an unavailable disruption, unless its Fi > 2 (then it stays `LOW_URGENCY`, because it is never placed anyway). Order for unplaced tasks: `DELEGABLE` → `BLOCKED_BY_DISRUPTION` → `LOW_URGENCY` → `TIME_TAKEN_BY_DISRUPTION` → `BUDGET_EXCEEDED`. It does not test whether the task would have fitted without the disruption. Explanation: "Moved to tomorrow: this time is taken by urgent work (13:00–15:00), and there is not enough free time left today, even at half length."
- **Config:** added `TASK_TYPES` and `DISRUPTION_KINDS`; `ENV_FEASIBILITY` now holds only the environment kinds (the `family_obligation` and `health_issue` rows, all null, were removed). This narrows open question CLAUDE.md §6 Q1.
- Golden **S15** (owner-specified: urgent work 13:00–15:00; D1 09:00–12:00, A2 15:00–17:00, D3 Move) and **S16** (added because S15 moves no task for lack of time: family obligation; tests `TIME_TAKEN_BY_DISRUPTION`, Delegate, and a Meeting task with no EF). Expected outputs written first and approved by the owner. The stress test now draws both kinds.

## 2026-10-08 — Task 3 API design (docs/API.md)
- **API contract approved** as written in `docs/API.md`, with the four defaults:
  1. Disruption window = `start` + `timeLostMinutes` (the user confirms "time lost", CLAUDE.md §3.4).
  2. An edited plan that overlaps a protected block is refused (`400 PROTECTED_BLOCK_OVERLAP`), so PTVR stays 0 for user edits too.
  3. `X-User-Id` header as a stand-in for Firebase Auth until a teammate sets it up.
  4. `severity` is stored for the bandit (Task 5) but does not change the MVD.
- Implementation choices made within that design (approved by the owner with Task 3, 8 Oct 2026):
  - A disruption report must carry `confirmed: true`, so "no MVD without user confirmation" (rule 5) is explicit in every request.
  - `planFrom` defaults to now (Asia/Colombo) on the day itself, otherwise to work start (mock scenarios planned ahead).
  - Each MVD stores its exact engine `input`, so it can be re-run and checked later.
  - A newer proposal for the same disruption marks an undecided older one `superseded`; each MVD can be decided once (`409` after).
  - Second disruption (tentative §3.3): replans only the parent MVD's Keep/Reduce tasks that are not done.
  - Mark Done without Start Task is allowed; `actualMinutes` is then null.

## 2026-10-06 (later) — midnight-crossing disruptions clipped
- **Decision:** a disruption window that crosses midnight is **clipped at the end of the plan day**: a power cut 20:00–02:00 is treated as 20:00–24:00 for today's plan. The part after midnight belongs to tomorrow's plan. Implemented once in `windowToInterval` (time.js) and used by both the engine and the test invariants, so the "no blocked task inside the window" check can no longer miss such windows. Closes CLAUDE.md §6 Q9 (recorded in the entry below).
- *Why:* before this, the engine ignored such a window without an error and scheduled Digital work into an evening power cut.
- Golden **S14** (expected output written first, approved by the owner): work 16:00–23:00, power cut 20:00–02:00, dinner 19:00–19:30 → D1 Digital 16:00–19:00, A1 Analog 20:00–22:00, D2 Digital Move (`BLOCKED_BY_DISRUPTION`, deadline risk). The 500-day stress test now includes midnight-crossing windows (about 1 in 4).

## 2026-10-06 (late night) — free-time note, midnight disruptions
- **Free-time note for LOW_URGENCY:** when a task is moved with reason `LOW_URGENCY` and free time is left today after placement, its explanation adds: "You have free time today, so you can start it early if you like." The tag stays Move; the engine never places group D tasks itself (no auto-actions), it only tells the student the option exists. The engine output now also includes `freeMinutesLeft`.
- **Midnight-crossing disruptions:** recorded as an open question (CLAUDE.md §6 Q9). The engine currently ignores such a window without an error; a check placed a Digital task 18:00–21:00 during a 20:00–02:00 outage. Not changed yet; owner to decide between supporting it and rejecting it with a clear error.
- Re-confirmed (already done in the night entry below, commit 2977019): Q6 revision, golden S13, reason codes in CLAUDE.md §3.3 = `classify.js`, deadline-risk rule = moved AND (due today or tomorrow OR Fi < 0.5).

## 2026-10-06 (night) — fixes before Task 3
- **Q6 revised (replaces the Q6 wording below):** a task with EF ≥ 0.3 is placed **inside the disruption window first**, starting at **max(gap start, window start)**, when it fits wholly inside the window. Only if it does not fit inside the window does it start at the gap start (a gap that overlaps the window), and otherwise the earliest gap that holds it. *Why:* under the old wording an Analog task started at the gap start, before the outage, and took the normal-condition time that Digital work needed (new golden S13: reading 13:00–17:00, coding 09:00–13:00, report 17:00–18:00 at 50%). Golden S12 A1 changes from 13:00–15:00 to 14:00–16:00.
- **Deadline-risk rule:** a task gets `deadlineRisk` when it is tagged **Move** and is **due today or tomorrow, or Fi < 0.5**. Same in code (`DEADLINE_RISK_DAYS = 1` in config.js) and CLAUDE.md §3.3. Golden S6 R1, S7 L2 and S8 N1 change to `deadlineRisk: true`. Delegate tasks do not get the warning.
- **Reason codes:** CLAUDE.md §3.3 now lists exactly the codes in `classify.js` (+ `PROTECTED_BLOCK`). Closes CLAUDE.md §6 Q6–Q8.
- Expected outputs were written first and approved by the owner before the engine was changed.

## 2026-10-06 (evening) — single working copy, C:\ merged into D:\
- **One repo folder:** `D:\RESEARCH PROJECT\anchor-ai-component1` is the only working copy; it is connected to GitHub (`ravindu912/anchor-ai-component1`). The C:\Users\ravin copy (Task 1 commit only, no remote) was merged into it and should no longer be edited.
- **CLAUDE.md v2.1:** the C:\ v2 draft (12 rules, progress-log format, tag-by-outcome table, pre-test survey note) merged with the Task 2 decisions (Q5, Q6). Where the two disagreed, the later owner-approved decisions were kept and the differences were listed as open questions (CLAUDE.md §6, Q5–Q8): gate "after" vs "outside", slot choice, reason-code names, deadline-risk rule.
- **Config name:** `NORMAL_EF` renamed to `OUTSIDE_WINDOW_EF`, the name in the v2 draft. Same value (1.0), same behaviour.

## 2026-10-06 (engine approval, Q6)
- **Q6, window-first as written + S12:** a task with EF ≥ 0.3 first tries free gaps that overlap the disruption window and starts at the **gap start**, even if that is before the window begins. Golden scenario S12 was added (S1–S11 did not test window-first) and approved. Task 2 engine approved.

## 2026-10-06 (scenario approval, Q5)
- **Q5, Fi computed once (option a):** Fi is computed once, before placement, using the EF of the intended slot (EF < 0.3 → 1.0; EF ≥ 0.3 with the window still ahead → disruption EF; window over → 1.0). It is not recomputed after placement. *Why:* Fi decides the order, the order decides the slot, and the slot decides EF (Q1). Computing Fi once breaks that loop, keeps the engine deterministic and makes each Fi easy to explain. *Trade-off:* a task with EF ≥ 0.3 that ends up outside the window keeps the disruption EF (e.g. golden S3, A1). The 11 golden scenarios were approved as written.

## 2026-10-06 (afternoon) — engine rules for Task 2 (golden-scenario review, Q1–Q4)
- **Time-slot placement:** the engine assigns each placed task a start and end time, not just a total-hours budget. Free time = work hours from now, minus protected blocks (as intervals). This makes the PTVR = 0 check meaningful.
- **Feasibility gate (revised):** EF < 0.3 means the task cannot be placed *inside* the disruption window. It may still be placed outside the window (before or after it), and becomes Move only if it does not fit there. *Replaces the morning rule "EF < 0.3 → Move, regardless of Fi", which threw away usable time after the disruption.*
- **Q1, EF definition:** EF = feasibility under the conditions of the slot the task would run in. Inside the window → the disruption's EF from config.js; outside → 1.0. Gated tasks therefore always use EF = 1.0 in Fi. The Fi formula text is unchanged. *Why:* dividing by 0.1 after the gate already blocked the task double-counted the disruption: EF = 0.1 inflated Fi tenfold, so urgent laptop work in a power outage was wrongly Moved before the revised gate could place it after the outage.
- **Q2, tag by outcome:** Keep = placed in full; Reduce = placed and compressed (up to 50%); Move = not placed; a Reduce candidate that fits with 0% compression is tagged Keep (reason code `FITS_FULLY`). Matters because Component 3 receives Keep tasks.
- **Q3, Delegate:** Delegate = flagged delegable AND not placed. A delegable task that fits is placed normally. §3.2 wording fixed.
- **Q4, ordering:** Keep candidates sorted by Fi ascending; ties → earliest deadline, then shortest duration. When over budget, the last task in that order is reduced first.
- **Low Fi, not High priority:** a task with Fi < 0.5 that is not High priority is an early Reduce candidate, placed before the other Reduce candidates; if it fits uncompressed it is tagged Keep.
- **Test-first approval:** golden scenario expected outputs are written to disk and approved by the owner before engine code is written.

## 2026-10-06 (morning) — Task 1 setup
- Fi encodings fixed: Priority High = 1, Medium = 2, Low = 3; deadline proximity in days, floored at 0.5; duration in hours (after drift correction).
- ~~Hard feasibility gate: EF < 0.3 → Move, regardless of Fi.~~ Superseded the same afternoon (see above).
- Reduce compresses by up to 50%, only as much as the time budget needs.
- EF values for connectivity failure, family obligation, health issue, and Meeting/Fixed task types remain open (null in config.js). Evidence will come from the team pre-test survey.
