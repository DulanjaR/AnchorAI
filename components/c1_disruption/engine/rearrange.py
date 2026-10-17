"""Rearranger (planning chat, 17 Oct 2026; golden R01–R08 owner-approved). Pure functions.

Finds a place for the tasks an MVD moved off today, and spreads effort tasks, over today +
`horizonDays`, never past a task's deadline. Free time = study windows − fixed blocks − tasks
already planned. Existing future tasks are NEVER changed automatically: when a moved task does
not fit, the result says `needsDecision` with options A–E (pre-computed, each with a reason),
and the student chooses. Formats: tests/golden/rearrange/README.md.

Rules (DECISIONS.md 2026-10-17, interpretations 1–11 of the README):
  order        Fi ascending (EF 1, days from today, min 0.5); ties earliest deadline, then shortest
  whole        earliest free gap before the deadline day that holds it; else the deadline day
  split        sessions MIN..MAX minutes before the deadline (unless not splittable); the whole
               task must fit, never a partial placement
  location     Campus tasks only in Campus time; Commute time takes only Analog tasks
  options      A make room on one day (lower-priority / later-deadline tasks: shorten ≤ 50% first,
               else move out, one level); B split with shortening-only room-making; C shorten the
               task itself ≤ 50% (not High priority); D delegate; E Needs a slot + deadline risk
  effort       remaining = total − done, spread evenly (5-min steps, extra to the earliest days)
               over the days before the deadline day (kept as a buffer); missed sessions reported
"""
import copy
import math
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import timedelta
from types import ModuleType
from typing import Any

from components.c1_disruption.engine import config as default_config
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.fi import compute_fi, deadline_proximity
from components.c1_disruption.engine.time import to_minutes

NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}
PLACE_WORDS = {"Commute": "commute", "Home": "at home", "Office": "at the office", "Campus": "on campus",
               "Other": "elsewhere"}


# --- small helpers ----------------------------------------------------------------------------

def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def day_label(iso: str, with_date: bool = True) -> str:
    d = Date.fromisoformat(iso)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}" if with_date else d.strftime("%a")


def deadline_label(deadline: str) -> str:
    return f"{day_label(deadline[:10])} {deadline[11:16]}"


def add_days(iso: str, n: int) -> str:
    return (Date.fromisoformat(iso) + timedelta(days=n)).isoformat()


def default_splittable(task_type: str) -> bool:
    """Interpretation 3: Digital and Analog tasks may be split, Meeting and Fixed may not."""
    return task_type in ("Digital", "Analog")


@dataclass
class Gap:
    date: str
    start: int
    end: int
    location: str | None

    @property
    def minutes(self) -> int:
        return self.end - self.start


@dataclass
class Planned:
    """An existing future task (only options A/B may change it)."""

    id: str
    title: str
    priority: str
    deadline: str
    date: str
    start: int
    end: int
    type: str = "Analog"
    splittable: bool | None = None


@dataclass
class Day:
    date: str
    windows: list[Gap]
    fixed: list[tuple[int, int]]
    planned: list[Planned]
    taken: list[tuple[int, int]] = field(default_factory=list)  # placed by this run

    def busy(self, skip: set[str] = frozenset()) -> list[tuple[int, int]]:
        return ([*self.fixed, *self.taken] + [(p.start, p.end) for p in self.planned if p.id not in skip])

    def gaps(self, skip: set[str] = frozenset(), not_before: int = 0) -> list[Gap]:
        out = []
        for w in self.windows:
            pieces = [(max(w.start, not_before), w.end)]
            for b0, b1 in sorted(self.busy(skip)):
                nxt = []
                for s, e in pieces:
                    if b1 <= s or b0 >= e:
                        nxt.append((s, e))
                        continue
                    if b0 > s:
                        nxt.append((s, b0))
                    if b1 < e:
                        nxt.append((b1, e))
                pieces = nxt
            out += [Gap(self.date, s, e, w.location) for s, e in pieces if e > s]
        return sorted(out, key=lambda g: g.start)


class State:
    def __init__(self, data: dict[str, Any], config: ModuleType) -> None:
        self.config = config
        self.today = data["today"]
        self.from_date = data["from"][:10]
        self.from_minute = to_minutes(data["from"][11:16]) if len(data["from"]) > 10 else 0
        self.horizon_end = add_days(self.today, int(data.get("horizonDays", config.REARRANGE_HORIZON_DAYS)))
        self.days: dict[str, Day] = {}
        for d in data.get("days", []):
            windows = [Gap(d["date"], to_minutes(w["start"]), to_minutes(w["end"]), w.get("location")) for w in d.get("windows", [])]
            fixed = [(to_minutes(f["start"]), to_minutes(f["end"])) for f in d.get("fixed", [])]
            planned = [Planned(p["id"], p.get("title", p["id"]), p["priority"], p["deadline"], d["date"],
                               to_minutes(p["start"]), to_minutes(p["end"]), p.get("type", "Analog"), p.get("splittable"))
                       for p in d.get("planned", [])]
            self.days[d["date"]] = Day(d["date"], windows, fixed, planned)

    def dates(self, last: str) -> list[str]:
        """Dates from `from` to min(last, horizon end)."""
        out, d = [], self.from_date
        end = min(last, self.horizon_end)
        while d <= end:
            out.append(d)
            d = add_days(d, 1)
        return out

    def gaps_on(self, date: str, skip: set[str] = frozenset()) -> list[Gap]:
        day = self.days.get(date)
        if day is None:
            return []
        return day.gaps(skip, self.from_minute if date == self.from_date else 0)

    def take(self, date: str, start: int, end: int) -> None:
        self.days[date].taken.append((start, end))

    def clone(self) -> "State":
        """A copy for trying an option (the config module is shared, the days are copied)."""
        other = copy.copy(self)
        other.days = copy.deepcopy(self.days)
        return other


@dataclass
class Item:
    id: str
    title: str
    type: str
    priority: str
    deadline: str
    minutes: int
    splittable: bool
    delegable: bool
    location: str | None
    min_session: int
    max_session: int
    fi: float = 0.0

    @property
    def deadline_date(self) -> str:
        return self.deadline[:10]

    @property
    def deadline_minute(self) -> int:
        return to_minutes(self.deadline[11:16])


def item_from(task: dict[str, Any], today: str, config: ModuleType, minutes: int | None = None) -> Item:
    minutes = int(task["durationMinutes"] if minutes is None else minutes)
    if minutes <= 0:
        raise EngineError(f"Task '{task.get('id')}': duration must be positive")
    splittable = task.get("splittable")
    item = Item(task["id"], task.get("title", task["id"]), task.get("type", "Analog"), task["priority"], task["deadline"],
                minutes, default_splittable(task.get("type", "Analog")) if splittable is None else bool(splittable),
                bool(task.get("delegable", False)), task.get("location"),
                int(task.get("minSession") or config.MIN_SESSION), int(task.get("maxSession") or config.MAX_SESSION))
    item.fi = compute_fi(deadline_days=deadline_proximity(today, task["deadline"], config), priority=item.priority,
                         hours=minutes / 60, ef=1.0, config=config)
    return item


def feasible(item: Item, gap: Gap) -> bool:
    """Location rules: Campus tasks only in Campus time; Commute time only for Analog tasks."""
    if item.location == "Campus" and gap.location != "Campus":
        return False
    if gap.location == "Commute" and item.type != "Analog":
        return False
    return True


def clip(item: Item, gap: Gap) -> Gap | None:
    """The part of a gap before the deadline (only the deadline day is clipped)."""
    if gap.date > item.deadline_date:
        return None
    if gap.date == item.deadline_date:
        end = min(gap.end, item.deadline_minute)
        return Gap(gap.date, gap.start, end, gap.location) if end > gap.start else None
    return gap


def usable_gaps(state: State, item: Item, dates: list[str], skip: set[str] = frozenset()) -> list[Gap]:
    out = []
    for d in dates:
        for g in state.gaps_on(d, skip):
            c = clip(item, g)
            if c is not None and feasible(item, c):
                out.append(c)
    return out


# --- placement (automatic) ------------------------------------------------------------------------

def _whole(state: State, item: Item) -> tuple[Gap, bool] | None:
    """(gap, on deadline day) holding the whole task, earliest first; the deadline day last."""
    before = [d for d in state.dates(add_days(item.deadline_date, -1))]
    for g in usable_gaps(state, item, before):
        if g.minutes >= item.minutes:
            return g, False
    if item.deadline_date <= state.horizon_end and item.deadline_date >= state.from_date:
        for g in usable_gaps(state, item, [item.deadline_date]):
            if g.minutes >= item.minutes:
                return g, True
    return None


def _split(item: Item, gaps: list[Gap]) -> list[tuple[Gap, int, int]] | None:
    """Pieces (gap, start, minutes) that place the WHOLE task, or None (interpretation 2)."""
    pieces, rem = [], item.minutes
    for g in gaps:
        if rem == 0:
            break
        if g.minutes < item.min_session:
            continue
        piece = min(rem, g.minutes, item.max_session)
        if 0 < rem - piece < item.min_session:
            piece = rem - item.min_session
        if piece < item.min_session:
            continue
        pieces.append((g, g.start, piece))
        rem -= piece
    return pieces if rem == 0 else None


def _all_dates(state: State, item: Item) -> list[str]:
    return state.dates(item.deadline_date)


def _place_normal(state: State, item: Item) -> list[dict[str, Any]] | None:
    """Whole (before the deadline day, then the deadline day), else split. Mutates state."""
    found = _whole(state, item)
    if found is not None:
        g, _ = found
        state.take(g.date, g.start, g.start + item.minutes)
        return [{"date": g.date, "start": g.start, "end": g.start + item.minutes, "minutes": item.minutes}]
    if item.splittable:
        pieces = _split(item, usable_gaps(state, item, _all_dates(state, item)))
        if pieces:
            for g, s, m in pieces:
                state.take(g.date, s, s + m)
            return [{"date": g.date, "start": s, "end": s + m, "minutes": m} for g, s, m in pieces]
    return None


# --- reasons ------------------------------------------------------------------------------------

def _whole_reason(state: State, item: Item, gap: Gap, on_deadline_day: bool) -> str:
    when = f"{day_label(gap.date)}, {hhmm(gap.start)}–{hhmm(gap.start + item.minutes)}"
    due = deadline_label(item.deadline)
    earlier_dates = [d for d in state.dates(add_days(item.deadline_date, -1)) if d < gap.date]
    # Gaps earlier than the placement that the location rules ruled out.
    excluded = [g for d in earlier_dates + [gap.date] for g in state.gaps_on(d)
                if (g.date, g.start) < (gap.date, gap.start) and clip(item, g) and not feasible(item, g)]
    if item.location == "Campus":
        text = (f"Placed on {when}: it can only be done on campus, and this is the first campus time before its "
                f"deadline ({due}).")
        if excluded:
            places = ", ".join(f"{day_label(g.date, False)} {PLACE_WORDS.get(g.location or '', 'elsewhere')}" for g in excluded)
            text += f" Earlier free time ({places}) is not on campus."
        return text
    if on_deadline_day:
        return (f"Placed on {day_label(gap.date)} (its deadline day), {hhmm(gap.start)}–{hhmm(gap.start + item.minutes)}: "
                f"no earlier day has a free gap of {item.minutes} min.")
    small = {}
    for d in earlier_dates:
        gs = [g for g in usable_gaps(state, item, [d]) if g.minutes < item.minutes]
        if gs:
            small[d] = gs
    if small:
        if len(small) == 1:
            (d, gs), = small.items()
            free = ", ".join(f"{hhmm(g.start)}–{hhmm(g.end)}" for g in gs)
            text = (f"Placed on {when}: {day_label(d)} has free time ({free}) but no gap of {item.minutes} min, "
                    f"so the next day that holds the whole task was used (deadline {due}).")
        else:
            days = " and ".join(day_label(d) for d in small)
            text = (f"Placed on {when}: {days} have free time but no gap of {item.minutes} min, so the next day that "
                    f"holds the whole task was used (deadline {due}).")
    else:
        text = (f"Placed on {when}: the earliest free time before its deadline ({due}) that holds the whole task "
                f"({item.minutes} min).")
    commute = [g for g in excluded if g.location == "Commute"]
    if commute:
        g = commute[0]
        where = "The commute" if g.date == gap.date else f"The commute on {day_label(g.date)}"
        text += f" {where} ({hhmm(g.start)}–{hhmm(g.end)}) only takes paper-based (Analog) tasks."
    return text


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# --- options when nothing fits --------------------------------------------------------------------

def _yieldable(p: Planned, item: Item) -> bool:
    return default_config.PRIORITY_SCORE[p.priority] > default_config.PRIORITY_SCORE[item.priority] or p.deadline > item.deadline


def _before(day: Day, gap: Gap, item: Item) -> Planned | None:
    """The yieldable planned task that ends exactly where the gap starts (it can be cut at its end)."""
    for p in day.planned:
        if p.end == gap.start and _yieldable(p, item):
            return p
    return None


def _why_yields(p: Planned) -> str:
    return f"{p.priority} priority, due {day_label(p.deadline[:10])}"


def _candidate_days(state: State, item: Item) -> list[str]:
    before = state.dates(add_days(item.deadline_date, -1))
    last = [item.deadline_date] if state.from_date <= item.deadline_date <= state.horizon_end else []
    return before + last


def _option_a(state: State, item: Item, config: ModuleType) -> dict[str, Any]:
    for date in _candidate_days(state, item):
        day = state.days.get(date)
        if day is None:
            continue
        # 1. Shorten the yieldable task right before a gap (≤ 50%).
        tried_cut = 0
        for g in usable_gaps(state, item, [date]):
            p = _before(day, g, item)
            if p is None:
                continue
            max_cut = math.floor((p.end - p.start) * config.MAX_COMPRESSION)
            tried_cut = max(tried_cut, max_cut)
            if g.minutes + max_cut >= item.minutes:
                cut = item.minutes - g.minutes
                start = p.end - cut
                return {"code": "A", "available": True,
                        "changes": [{"taskId": p.id, "action": "shorten", "date": date, "start": hhmm(p.start),
                                     "end": hhmm(p.end - cut), "minutesCut": cut},
                                    {"taskId": item.id, "action": "place", "date": date, "start": hhmm(start),
                                     "end": hhmm(start + item.minutes), "minutes": item.minutes}],
                        "reason": (f"Make room on {day_label(date)}: shorten \"{p.title}\" ({_why_yields(p)}) by {cut} min "
                                   f"to {hhmm(p.start)}–{hhmm(p.end - cut)}, then do the whole task "
                                   f"{hhmm(start)}–{hhmm(start + item.minutes)}.")}
        # 2. Move yieldable tasks out, least urgent first, until a gap holds the task.
        yieldable = [p for p in day.planned if _yieldable(p, item)]
        yieldable.sort(key=lambda p: -compute_fi(deadline_days=deadline_proximity(state.today, p.deadline, config),
                                                 priority=p.priority, hours=(p.end - p.start) / 60, ef=1.0, config=config))
        removed: list[Planned] = []
        for p in yieldable:
            removed.append(p)
            skip = {r.id for r in removed}
            gaps = [g for g in usable_gaps(state, item, [date], skip) if g.minutes >= item.minutes]
            if not gaps:
                continue
            trial = state.clone()
            tday = trial.days[date]
            tday.planned = [q for q in tday.planned if q.id not in skip]
            g = gaps[0]
            trial.take(date, g.start, g.start + item.minutes)
            moves = []
            for r in removed:  # one rearranger attempt each, from its own day
                r_item = Item(r.id, r.title, r.type, r.priority, r.deadline, r.end - r.start,
                              default_splittable(r.type) if r.splittable is None else r.splittable, False, None,
                              config.MIN_SESSION, config.MAX_SESSION)
                placed = _place_normal(trial, r_item)
                if placed is None:
                    moves = None
                    break
                moves += [{"taskId": r.id, "action": "move", "date": s["date"], "start": hhmm(s["start"]),
                           "end": hhmm(s["end"])} for s in placed]
            if moves is None:
                break
            where = ", ".join(f"{day_label(m['date'])} {m['start']}–{m['end']}" for m in moves)
            names = " and ".join(f"\"{r.title}\" ({_why_yields(r)})" for r in removed)
            text = (f"Make room on {day_label(date)}: move {names} to {where}, then do the whole task "
                    f"{day_label(date, False)} {hhmm(g.start)}–{hhmm(g.start + item.minutes)}.")
            if tried_cut:
                text += f" Shortening {'it' if len(removed) == 1 else 'them'} by half would free only {tried_cut} min."
            return {"code": "A", "available": True,
                    "changes": moves + [{"taskId": item.id, "action": "place", "date": date, "start": hhmm(g.start),
                                         "end": hhmm(g.start + item.minutes), "minutes": item.minutes}],
                    "reason": text}
    return {"code": "A", "available": False, "changes": [],
            "reason": "Not possible: no day before the deadline can make enough room without touching more urgent tasks."}


def _option_b(state: State, item: Item, config: ModuleType) -> dict[str, Any]:
    if not item.splittable:
        return {"code": "B", "available": False, "changes": [], "reason": "Not possible: this task cannot be split."}
    changes, parts, rem, cut_ids = [], [], item.minutes, set()
    for g in usable_gaps(state, item, _all_dates(state, item)):
        if rem == 0:
            break
        day = state.days[g.date]
        target = min(rem, item.max_session)
        p = _before(day, g, item)
        cut_max = math.floor((p.end - p.start) * config.MAX_COMPRESSION) if p and p.id not in cut_ids else 0
        effective = g.minutes + min(cut_max, max(0, target - g.minutes))
        if effective < item.min_session:
            continue
        piece = min(rem, effective, item.max_session)
        if 0 < rem - piece < item.min_session:
            piece = rem - item.min_session
        if piece < item.min_session:
            continue
        cut = max(0, piece - g.minutes)
        start = g.start - cut
        note = ""
        if cut:
            cut_ids.add(p.id)
            changes.append({"taskId": p.id, "action": "shorten", "date": g.date, "start": hhmm(p.start),
                            "end": hhmm(p.end - cut), "minutesCut": cut})
            note = f", after shortening \"{p.title}\" by {cut} min"
        changes.append({"taskId": item.id, "action": "place", "date": g.date, "start": hhmm(start),
                        "end": hhmm(start + piece), "minutes": piece})
        parts.append(f"{day_label(g.date)} {hhmm(start)}–{hhmm(start + piece)} ({piece} min{note})")
        rem -= piece
    if rem:
        return {"code": "B", "available": False, "changes": [],
                "reason": "Not possible: even with room made by shortening other tasks, the free time is not enough."}
    days = len({c["date"] for c in changes if c["taskId"] == item.id})
    return {"code": "B", "available": True, "changes": changes,
            "reason": f"Split across {NUMBER_WORDS.get(days, days)} days: {_join(parts)}."}


def _capacity(item: Item, gaps: list[Gap]) -> list[Gap]:
    """What fits without touching anything: every gap ≥ minSession (capped at maxSession) if
    splittable, else the largest gap."""
    if item.splittable:
        return [g for g in gaps if g.minutes >= item.min_session]
    if not gaps:
        return []
    best = max(g.minutes for g in gaps)
    return [next(g for g in gaps if g.minutes == best)]


def _fit_minutes(item: Item, gaps: list[Gap]) -> int:
    return sum(min(g.minutes, item.max_session) if item.splittable else g.minutes for g in _capacity(item, gaps))


def _option_c(item: Item, gaps: list[Gap], config: ModuleType) -> dict[str, Any]:
    if item.priority == "High":
        return {"code": "C", "available": False, "changes": [], "reason": "Not offered: High-priority tasks are not shortened."}
    fit = _fit_minutes(item, gaps)
    if fit < item.minutes * (1 - config.MAX_COMPRESSION) or fit <= 0:
        return {"code": "C", "available": False, "changes": [],
                "reason": "Not possible: even at half length it does not fit in the free time before the deadline."}
    changes, parts = [], []
    for g in _capacity(item, gaps):
        m = min(g.minutes, item.max_session) if item.splittable else min(g.minutes, item.minutes)
        changes.append({"taskId": item.id, "action": "place", "date": g.date, "start": hhmm(g.start),
                        "end": hhmm(g.start + m), "minutes": m})
        parts.append(f"{day_label(g.date, False)} {hhmm(g.start)}–{hhmm(g.start + m)}")
    cut = item.minutes - fit
    return {"code": "C", "available": True, "changes": changes,
            "reason": (f"Shorten it to {fit} min (by {cut} min, {round(100 * cut / item.minutes)}%) and do it in the free time: "
                       f"{_join(parts)}. Nothing else changes.")}


def _needs_decision(state: State, item: Item, config: ModuleType) -> dict[str, Any]:
    gaps = usable_gaps(state, item, _all_dates(state, item))
    fit = _fit_minutes(item, gaps)
    shortfall = item.minutes - fit
    due = deadline_label(item.deadline)
    if not gaps:
        reason = f"There is no free time before the deadline ({due}). You choose:"
    elif item.splittable:
        free = ", ".join(f"{day_label(g.date, False)} {hhmm(g.start)}–{hhmm(g.end)}" for g in gaps)
        reason = f"No free time before the deadline ({due}) holds {item.minutes} min: only {fit} min are free ({free}). You choose:"
    else:
        best = _capacity(item, gaps)[0]
        reason = (f"No free time before the deadline ({due}) holds {item.minutes} min: the largest free gap is "
                  f"{best.minutes} min ({day_label(best.date, False)} {hhmm(best.start)}–{hhmm(best.end)}) and the task "
                  f"cannot be split. You choose:")
    options = [
        _option_a(state, item, config),
        _option_b(state, item, config),
        _option_c(item, gaps, config),
        {"code": "D", "available": True, "changes": [{"taskId": item.id, "action": "delegate"}],
         "reason": "Delegate it: you marked it as something others (or AI help) could do."}
        if item.delegable else
        {"code": "D", "available": False, "changes": [], "reason": "Not offered: it is not marked as something others could do."},
        {"code": "E", "available": True,
         "changes": [{"taskId": item.id, "action": "needsSlot", "deadlineRisk": True, "shortfallMinutes": shortfall}],
         "reason": (f"Keep it as \"Needs a slot\": it is due {day_label(item.deadline_date)} and {shortfall} min of free time "
                    f"are missing, so its deadline is at risk.")},
    ]
    return {"taskId": item.id, "shortfallMinutes": shortfall, "reason": reason, "options": options}


# --- effort tasks -------------------------------------------------------------------------------

def _effort(state: State, task: dict[str, Any], config: ModuleType) -> tuple[list, list, list]:
    """(placements, missed sessions, warnings) for one effort task."""
    done = float(task.get("actualMinutesDone") or 0)
    remaining = int(task["totalEffortMinutes"] - done)
    missed = [{"taskId": task["id"], "date": s["date"], "minutes": s["minutes"]} for s in task.get("sessions", [])
              if not s.get("done") and s["date"] < state.from_date]
    if remaining <= 0:
        return [], missed, []
    item = item_from({**task, "durationMinutes": remaining}, state.today, config)
    item.splittable = True
    days = []
    for d in state.dates(add_days(item.deadline_date, -1)):
        gs = [g for g in usable_gaps(state, item, [d]) if g.minutes >= item.min_session]
        if gs:
            days.append(d)
    warnings = []
    free = sum(g.minutes for g in usable_gaps(state, item, days))
    if remaining > free:
        warnings.append({"taskId": item.id, "code": "EFFORT_AT_RISK",
                         "message": f"\"{item.title}\": {remaining} min of work left but only {free} min free before "
                                    f"{day_label(item.deadline_date)} (the deadline day is kept as a buffer)."})
    if not days:
        return [], missed, warnings
    step = config.EFFORT_STEP_MINUTES
    n = len(days)
    while n > 1 and remaining / n < item.min_session:
        n -= 1
    days = days[:n]
    base = (remaining // n // step) * step
    shares = [base] * n
    extra = remaining - base * n
    i = 0
    while extra > 0:
        add = min(step, extra)
        shares[i % n] += add
        extra -= add
        i += 1
    shares = [min(s, item.max_session) for s in shares]
    placements, pieces = [], []
    for d, share in zip(days, shares):
        gap = next((g for g in usable_gaps(state, item, [d]) if g.minutes >= share), None)
        if gap is None:
            continue
        state.take(d, gap.start, gap.start + share)
        pieces.append((d, gap.start, share))
    lo, hi = min(shares), max(shares)
    per = f"{lo} min a day" if lo == hi else f"{lo}–{hi} min a day"
    buffer = day_label(item.deadline_date)
    if missed:
        when = " and ".join(day_label(m["date"]) for m in missed)
        lead = (f"Effort task re-spread: the session of {when} was missed, so the {remaining} min left are spread over "
                f"the {len(pieces)} days before the deadline ({buffer} is kept free as a buffer): {per}.")
    else:
        lead = (f"Effort task: {remaining} min left, spread evenly over the {len(pieces)} days before the deadline "
                f"({buffer} is kept free as a buffer): {per}.")
    for k, (d, s, m) in enumerate(pieces, 1):
        placements.append({"taskId": item.id, "date": d, "start": hhmm(s), "end": hhmm(s + m), "minutes": m,
                           "session": f"{k}/{len(pieces)}", "reason": f"{lead} Session {k} of {len(pieces)}."})
    return placements, missed, warnings


# --- entry point ------------------------------------------------------------------------------

def rearrange(data: dict[str, Any], config: ModuleType = default_config) -> dict[str, Any]:
    """Rearranger result for the input format of tests/golden/rearrange/README.md."""
    state = State(data, config)
    items = [item_from(t, state.today, config) for t in data.get("moved", [])]
    items.sort(key=lambda i: (i.fi, i.deadline, i.minutes))
    placements, decisions, warnings, missed = [], [], [], []
    for item in items:
        whole = _whole(state, item)
        if whole is not None:
            g, on_deadline = whole
            reason = _whole_reason(state, item, g, on_deadline)
            state.take(g.date, g.start, g.start + item.minutes)
            placements.append({"taskId": item.id, "date": g.date, "start": hhmm(g.start), "end": hhmm(g.start + item.minutes),
                               "minutes": item.minutes, "session": None, "reason": reason})
            continue
        pieces = _split(item, usable_gaps(state, item, _all_dates(state, item))) if item.splittable else None
        if pieces:
            lead = (f"Split into {len(pieces)} sessions: no free gap before the deadline ({deadline_label(item.deadline)}) "
                    f"holds all {item.minutes} min.")
            for k, (g, s, m) in enumerate(pieces, 1):
                state.take(g.date, s, s + m)
                placements.append({"taskId": item.id, "date": g.date, "start": hhmm(s), "end": hhmm(s + m), "minutes": m,
                                   "session": f"{k}/{len(pieces)}",
                                   "reason": f"{lead} Session {k} of {len(pieces)}: {day_label(g.date)}, "
                                             f"{hhmm(s)}–{hhmm(s + m)} ({m} min)."})
            continue
        decisions.append(_needs_decision(state, item, config))
    for task in data.get("effort", []):
        p, m, w = _effort(state, task, config)
        placements += p
        missed += m
        warnings += w
    out: dict[str, Any] = {}
    if missed:
        out["missedSessions"] = missed
    out.update(placements=placements, needsDecision=decisions, warnings=warnings)
    return out
