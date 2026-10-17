# Rearranger golden scenarios R01–R08 — DRAFT

Hand-worked, test-first (planning chat, 17 Oct 2026). **Status: DRAFT until the owner approves them;
no rearranger code exists yet.** After approval, `engine/rearrange.py` must reproduce `expected` exactly.

The rearranger finds a place for the tasks an MVD moved off today (and spreads effort tasks), over
today + 7 days, never past a task's deadline. It **never changes existing future tasks by itself**:
when nothing fits it returns `needsDecision` with options A–E for the student to choose.

## Format

```text
input
  today        the MVD day (YYYY-MM-DD)
  from         earliest moment to place anything (moved tasks: the next day, 00:00)
  horizonDays  7
  days[]       date, windows[] {start, end, location}, fixed[] {label, start, end},
               planned[] (existing future tasks: id, title, type, priority, deadline, start, end)
               free time = windows − fixed − planned; a day not listed has no free time
  moved[]      id, title, type, priority, deadline, durationMinutes (Model 1 corrected point;
               the estimate when the gate is closed), durationSource, splittable, delegable, location
  effort[]     id, title, type, priority, deadline, totalEffortMinutes, actualMinutesDone,
               minSession, maxSession, splittable, location, sessions[] (earlier plan: date, start,
               end, minutes, done)
workings       the hand calculation, step by step
expected
  placements[]     taskId, date, start, end, minutes, session ("i/n" or null), reason
  needsDecision[]  taskId, shortfallMinutes, reason, options[] {code A–E, available, changes[], reason}
  missedSessions[] (effort tasks) taskId, date, minutes
  warnings[]
```

## Rules used (owner-approved design, 17 Oct 2026)

- Order: Fi ascending (EF 1, days from `today`, minimum 0.5); ties: earliest deadline, then shortest.
- Whole task in the earliest free gap before the deadline; the deadline day only if nothing earlier fits.
- Else split into sessions of `MIN_SESSION` (30) to `MAX_SESSION` (120) minutes before the deadline,
  unless not splittable.
- Campus tasks only in Campus time; Commute time takes only Analog tasks.
- Nothing fits → no decision; options A–E, each with a reason sentence.
- Effort tasks: remaining = total − done, spread evenly over the days before the deadline day (kept
  free as a buffer); a missed session → re-spread the rest; early warning when remaining effort >
  free time before the deadline.

## PROPOSED interpretations (to confirm with R01–R08)

1. **Search starts at `from`**: moved tasks from the next day (the MVD already used today's time);
   effort tasks from `from` as well (R07: today).
2. **A split must place the whole task**; a piece is `min(remaining, gap, maxSession)`, and a piece
   that would leave less than `minSession` is shortened so the rest is at least `minSession`.
   No partial placement happens automatically.
3. **`splittable` defaults** to true for Digital and Analog tasks, false for Meeting and Fixed.
4. **Shortfall** = duration − the minutes that the automatic split could place (not splittable:
   duration − the largest feasible gap).
5. **Option A** (one day, whole task): days before the deadline day first, then the deadline day.
   Only planned tasks of **lower priority or a later deadline** may yield. Shortening (each ≤ 50%,
   least urgent first) is tried before moving a task out. A shortened task keeps its start and ends
   earlier; the moved task follows it. A task moved out gets one rearranger attempt (the normal
   rules, from its own day); if that fails, option A is not offered on that day.
6. **Option B** (split): since the automatic split already failed, B is a split that may also use
   option A's room-making **by shortening only** (no task moved out).
7. **Option C** (shorten the moved task, ≤ 50%): offered unless the task is **High** priority; it
   shortens to what fits in the free time without touching anything else (using a split if splittable).
8. **Option D** only if the task is delegable; **E** is always offered (Needs a slot + deadline risk +
   shortfall minutes).
9. **Effort spreading**: per-day minutes = remaining ÷ days, rounded down to 5 min, with the left-over
   5-minute steps added to the **earliest** days; clamped to min/max session (fewer days if a day's
   share would be below `minSession`). A session goes in the earliest gap of its day that holds it.
10. **Location**: only the two rules above; a Home/Office/Other task may use any non-Commute time.
11. **Reason sentences**: the wording in `expected` is PROPOSED text, same style as the MVD explanations.
