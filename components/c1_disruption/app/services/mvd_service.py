"""The only place that combines stored data with the (pure) MVD engine.

  generate: confirmed disruption + the user's day → proposed MVD + three-way comparison
  decide:   accept / edit / reject → final plan written to the tasks + feedback record

Nothing here happens on its own (CLAUDE.md rule 5): every step is triggered by an
explicit user request.
"""
from dataclasses import dataclass, field
from typing import Any, Literal

from components.c1_disruption.app.api.errors import bad_request, conflict
from components.c1_disruption.app.api.models import EditChange, ManualReplanItem
from components.c1_disruption.app.data.repository import Record, Repository
from components.c1_disruption.app.services.clock import Clock, iso_utc, parse_iso, to_local
from components.c1_disruption.app.services.owned import load_owned
from components.c1_disruption.app.services.planning import (
    STRATEGIES,
    DriftCorrector,
    FixedOrder,
    NoDrift,
    StrategyChooser,
)
from components.c1_disruption.engine.diff import diff_plans
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.engine.time import Interval, block_to_intervals, overlaps, to_minutes

PLACED_TAGS = ("Keep", "Reduce")
DECIDED_STATUSES = ("accepted", "edited")

Action = Literal["accept", "edit", "reject"]


@dataclass(frozen=True)
class Deps:
    store: Repository
    clock: Clock
    # ML hooks (planning.py); the defaults keep the approved behaviour.
    corrector: DriftCorrector = field(default_factory=NoDrift)
    chooser: StrategyChooser = field(default_factory=FixedOrder)


def _slot_of(entry: Record) -> Record:
    return {"tag": entry["tag"], "start": entry["start"], "end": entry["end"]}


def generate(
    deps: Deps,
    user_id: str,
    disruption: Record,
    plan_from: str | None = None,
    manual_replan: list[ManualReplanItem] | None = None,
) -> Record:
    store, clock = deps.store, deps.clock
    if not disruption.get("confirmed"):
        raise conflict("The disruption must be confirmed by the user first")
    settings = store.get("users", user_id)
    if settings is None:
        raise conflict("Set work hours first (PUT /api/me/settings)", "NO_SETTINGS")

    date = disruption["date"]
    today, now_time = to_local(clock.now())
    # Replanning starts now on the day itself; for another day (e.g. a mock
    # scenario planned ahead) it starts at the beginning of work hours.
    plan_from = plan_from or (now_time if today == date else settings["workStart"])
    manual = (
        None
        if manual_replan is None
        else [{"taskId": m.taskId, "tag": m.tag, "start": m.start, "end": m.end} for m in manual_replan]
    )

    # Second disruption on the same day (tentative, CLAUDE.md §3.3): the latest
    # finalised MVD is the new baseline; the engine runs again on what it still
    # had placed for today and is not done yet.
    finalised = [m for m in store.list("mvds", {"userId": user_id, "date": date}) if m["status"] in DECIDED_STATUSES]
    parent = finalised[-1] if finalised else None

    tasks = [t for t in store.list("tasks", {"userId": user_id, "plannedDate": date}) if t["status"] != "done"]
    if parent:
        still_placed = {e["taskId"] for e in parent["finalPlan"] if e["tag"] in PLACED_TAGS}
        tasks = [t for t in tasks if t["id"] in still_placed]
    protected_blocks = store.list("protectedBlocks", {"userId": user_id})

    # ML Model 1: corrected durations (default: drift 1.0 = the user's estimate).
    context = {"date": date, "planFrom": plan_from, "disruption": disruption}
    corrections = {t["id"]: deps.corrector.correct(user_id, t, context) for t in tasks}
    # ML Model 2: which strategy shapes the MVD (default: fixed order, approved strategy).
    ranking = deps.chooser.rank(user_id, {**context, "tasks": tasks})
    strategy_id = ranking.ranking[0]

    engine_input = {
        "date": date,
        "workHours": {"start": settings["workStart"], "end": settings["workEnd"]},
        "planFrom": plan_from,
        "disruption": {"type": disruption["type"], "start": disruption["start"], "end": disruption["end"]},
        "protectedBlocks": [
            {"id": b["id"], "label": b["label"], "start": b["start"], "end": b["end"]} for b in protected_blocks
        ],
        # estimatedHours = duration after drift correction (point); low/high = Model 1 range.
        "tasks": [
            {
                **{k: t[k] for k in ("id", "title", "type", "priority", "deadline", "delegable")},
                "estimatedHours": corrections[t["id"]].point_hours,
                "estimatedHoursLow": corrections[t["id"]].low_hours,
                "estimatedHoursHigh": corrections[t["id"]].high_hours,
            }
            for t in tasks
        ],
        "strategy": dict(STRATEGIES[strategy_id]),
    }
    # An EngineError (e.g. a None EF value) becomes 422 in the error handler.
    plan = generate_mvd(engine_input)

    task_ids = {t["id"] for t in tasks}
    comparison = {
        "original": (
            [{"taskId": e["taskId"], **_slot_of(e)} for e in parent["finalPlan"] if e["taskId"] in task_ids]
            if parent
            else [{"taskId": t["id"], "tag": None, "start": t["plannedStart"], "end": t["plannedEnd"]} for t in tasks]
        ),
        "manualReplan": manual,
        "mvd": [{"taskId": t["id"], **_slot_of(t)} for t in plan["tasks"]],
    }

    # A newer proposal for the same disruption replaces an undecided older one.
    for old in store.list("mvds", {"userId": user_id, "disruptionId": disruption["id"], "status": "proposed"}):
        store.update("mvds", old["id"], {"status": "superseded"})

    return store.create("mvds", {
        "userId": user_id,
        "disruptionId": disruption["id"],
        "parentMvdId": parent["id"] if parent else None,
        "date": date,
        "planFrom": plan_from,
        "status": "proposed",
        "input": engine_input,  # kept so any MVD can be re-run and checked later (evaluation, viva)
        "plan": plan,
        "comparison": comparison,
        "finalPlan": None,
        "createdAt": iso_utc(clock.now()),
        "decidedAt": None,
        # Logging for the evaluation (docs/METHODOLOGY.md §6).
        "policyMode": ranking.policy_mode,
        "shownPolicy": ranking.shown_policy,
        "rankingShown": ranking.ranking,
        "strategyId": strategy_id,
        "strategy": engine_input["strategy"],
        "modelOn": deps.corrector.model_on,
        "manualReplanFirst": manual is not None,
        "taskLog": [
            {
                "taskId": t["id"],
                "estimatedHours": t["estimatedHours"],
                "correctedHours": corrections[t["id"]].point_hours,
                "correctedLowHours": corrections[t["id"]].low_hours,
                "correctedHighHours": corrections[t["id"]].high_hours,
                "correctionSource": corrections[t["id"]].source,
            }
            for t in tasks
        ],
        "timeToDecisionSeconds": None,
    })


# --- decisions -------------------------------------------------------------

def _to_final(t: Record) -> Record:
    return {"taskId": t["id"], "tag": t["tag"], "start": t["start"], "end": t["end"], "reason": t["reason"], "edited": False}


def _apply_edits(mvd: Record, changes: list[EditChange]) -> tuple[list[Record], list[Record]]:
    """Applies the user's edits to the proposed plan. An edit may not overlap a
    protected block (PTVR must stay 0, approved 8 Oct 2026)."""
    final = [_to_final(t) for t in mvd["plan"]["tasks"]]
    by_id = {e["taskId"]: e for e in final}
    blocks: list[tuple[Interval, str]] = [
        (iv, b["label"]) for b in mvd["input"]["protectedBlocks"] for iv in block_to_intervals(b)
    ]
    seen: set[str] = set()
    edits: list[Record] = []

    for change in changes:
        task_id = change.taskId
        entry = by_id.get(task_id)
        if entry is None:
            raise bad_request(f"Task '{task_id}' is not in this MVD")
        if task_id in seen:
            raise bad_request(f"Task '{task_id}' is changed twice")
        seen.add(task_id)

        before = _slot_of(entry)
        tag = change.tag if change.tag is not None else entry["tag"]
        start = change.start if change.start is not None else entry["start"]
        end = change.end if change.end is not None else entry["end"]

        if tag in PLACED_TAGS:
            if not start or not end:
                raise bad_request(f"Task '{task_id}' needs 'start' and 'end' to be {tag}")
            slot = Interval(to_minutes(start), to_minutes(end))
            if slot.end <= slot.start:
                raise bad_request(f"Task '{task_id}': 'end' must be after 'start'")
            hit = next((label for iv, label in blocks if overlaps(slot, iv)), None)
            if hit is not None:
                raise bad_request(f"Task '{task_id}' overlaps the protected block '{hit}'", "PROTECTED_BLOCK_OVERLAP")
        else:
            start = end = None  # Move and Delegate have no slot today

        entry.update(tag=tag, start=start, end=end, edited=True)
        edits.append({"taskId": task_id, "before": before, "after": _slot_of(entry)})
    return final, edits


def decide(
    deps: Deps,
    user_id: str,
    mvd_id: str,
    action: Action,
    changes: list[EditChange] | None = None,
    reason: str | None = None,
) -> Record:
    store, clock = deps.store, deps.clock
    mvd = load_owned(store, "mvds", mvd_id, user_id, "MVD")
    if mvd["status"] != "proposed":
        raise conflict(f"This MVD is already {mvd['status']}; it can be decided only once")

    # All input is checked BEFORE anything is written, so a bad request never
    # leaves a half-applied decision.
    final_plan: list[Record] | None = None
    edits: list[Record] | None = None
    if action == "accept":
        final_plan = [_to_final(t) for t in mvd["plan"]["tasks"]]
    elif action == "edit":
        final_plan, edits = _apply_edits(mvd, changes or [])
    else:
        final_plan = None

    # Accepted and edited plans are written to the shared task data, which is
    # what Component 3 (Keep) and Component 4 (Delegate) read.
    for entry in final_plan or []:
        store.update("tasks", entry["taskId"], {
            "mvdTag": entry["tag"], "mvdStart": entry["start"], "mvdEnd": entry["end"], "mvdId": mvd["id"],
        })

    now = clock.now()
    at = iso_utc(now)
    seconds = (now - parse_iso(mvd["createdAt"])).total_seconds()
    # Structured edit diff: which tags the user changed (decision-change / reward).
    tag_changes = (
        diff_plans(mvd["plan"], {"tasks": [{"id": e["taskId"], "tag": e["tag"]} for e in final_plan]})["changed"]
        if action == "edit"
        else []
    )
    # Feedback is the reward signal for ML Model 2: accept +, edit partial, reject −.
    store.create("feedback", {
        "userId": user_id,
        "mvdId": mvd["id"],
        "disruptionId": mvd["disruptionId"],
        "action": action,
        "edits": edits,
        "reason": reason if action == "reject" else None,
        "at": at,
        "tagChanges": tag_changes,
        "totalTasks": len(mvd["plan"]["tasks"]),
        "timeToDecisionSeconds": seconds,
    })

    status: dict[str, Any] = {"accept": "accepted", "edit": "edited", "reject": "rejected"}
    return store.update(
        "mvds", mvd["id"],
        {"status": status[action], "finalPlan": final_plan, "decidedAt": at, "timeToDecisionSeconds": seconds},
    )
