"""Run the whole SYNTHETIC simulation: every variant × seed (docs/METHODOLOGY.md §7).

    report = run("personas.csv", "tasks.csv")              # all seeds, all variants
    print(to_markdown(report))

Variants: 'planted' (persona drift as written), 'null' (no drift), 'misspecified'
(planted drift × a hidden daily factor the model cannot see).
Every table is labelled SYNTHETIC: pipeline validation, never a research finding.
"""
import random
from statistics import mean, stdev
from typing import Any, Iterable

from components.c1_disruption.ml.bandit.context import features
from components.c1_disruption.ml.bandit.linucb import PooledLinUCB
from components.c1_disruption.ml.bandit.actions import ACTIONS
from components.c1_disruption.ml.bandit.context import FEATURE_NAMES
from components.c1_disruption.ml.bandit.policies import FixedOrderPolicy, MostAcceptedPolicy, RandomPolicy
from components.c1_disruption.ml.drift import baselines
from components.c1_disruption.ml.drift.data import clean
from components.c1_disruption.ml.drift.evaluation import leave_one_student_out, learning_curve, rolling_origin, score
from components.c1_disruption.ml.drift.model import DriftModel
from components.c1_disruption.sim import settings
from components.c1_disruption.sim.events import Event, build_events, event_metrics
from components.c1_disruption.sim.generate import World, generate
from components.c1_disruption.sim.personas import load_personas, load_tasks

VARIANTS = ("planted", "null", "misspecified")
LABEL = "SYNTHETIC — pipeline validation only, not a research finding"


def model1(world: World, n_estimators: int) -> dict[str, Any]:
    records = clean(world.records)
    methods = {"model": lambda: DriftModel(n_estimators=n_estimators), **{c.name: c for c in baselines.BASELINES}}
    out: dict[str, Any] = {"records": len(records), "cold": {}, "warm": {}}
    for name, factory in methods.items():
        out["cold"][name] = score(leave_one_student_out(records, factory))
        warm = rolling_origin(records, factory, min_history_days=1, step_days=settings.ROLLING_STEP_DAYS)
        out["warm"][name] = score(warm)
        if name == "model":
            out["learningCurve"] = learning_curve(warm)
    return out


def model2(world: World, events: list[Event], seed: int) -> dict[str, list[float]]:
    """Simulated acceptance per event, in time order, for each policy (SYNTHETIC
    students accept their hidden preferredStrategy more often)."""
    actions = list(ACTIONS)
    policies = {
        "fixed order": FixedOrderPolicy(actions),
        "most accepted": MostAcceptedPolicy(actions),
        "random": RandomPolicy(actions, seed=seed),
        "bandit": PooledLinUCB(actions, dim=len(FEATURE_NAMES)),
    }
    curves: dict[str, list[float]] = {}
    for name, policy in policies.items():
        rng = random.Random(seed)  # same decision noise for every policy
        history: dict[str, list[float]] = {}
        values = []
        for e in sorted(events, key=lambda e: (e.date, e.persona_id)):
            past = history.setdefault(e.persona_id, [])
            x = features(e.engine_input, e.severity, past)
            shown = policy.rank(e.persona_id, x)[0]
            liked = world.personas[e.persona_id].preferred_strategy
            p_accept = settings.ACCEPT_IF_PREFERRED if shown == liked else settings.ACCEPT_OTHERWISE
            draw = rng.random()
            if draw < p_accept:
                value = 1.0
            elif draw < p_accept + (1 - p_accept) * settings.EDIT_SHARE_OF_NOT_ACCEPTED:
                value = 1 - 1 / max(1, len(e.raw["tasks"]))  # edit: one tag changed
            else:
                value = 0.0
            policy.update(e.persona_id, x, shown, value)
            past.append(value)
            values.append(value)
        curves[name] = values
    return curves


def _avg(rows: Iterable[dict], plan: str, key: str) -> float | None:
    values = [r[plan][key] for r in rows if plan in r and r[plan][key] is not None]
    return mean(values) if values else None


def run_world(world: World, n_estimators: int = settings.SIM_N_ESTIMATORS) -> dict[str, Any]:
    events, skipped = build_events(world, n_estimators)
    rows = [event_metrics(world, e) for e in events]
    compared = [r for r in rows if "corrected" in r]
    summary = {
        plan: {key: _avg(compared, plan, key) for key in
               ("ctrrPlanned", "ctrrRealised", "ptvr", "feasibilityTrue", "realisedFeasibility", "planCompletionRate")}
        for plan in ("raw", "corrected")
    }
    changes = [r["decisionChangeRate"] for r in compared]
    return {
        "dataset": settings.DATASET, "seed": world.seed, "variant": world.variant,
        "model1": model1(world, n_estimators),
        "events": {"total": len(rows), "compared": len(compared), "summary": summary,
                   "skippedUnplannable": len(skipped), "skippedReasons": sorted({s.reason for s in skipped}),
                   "decisionChangeRate": mean(changes) if changes else None,
                   "tightSlackEvents": sum(r["tightSlack"] for r in rows), "rows": rows},
        "model2": model2(world, events, world.seed),
    }


def run(personas_csv: str, tasks_csv: str, seeds: Iterable[int] = settings.SEEDS,
        variants: Iterable[str] = VARIANTS, n_estimators: int = settings.SIM_N_ESTIMATORS) -> dict[str, Any]:
    personas = load_personas(personas_csv)
    tasks = load_tasks(tasks_csv, personas)
    runs = [run_world(generate(personas, tasks, seed, variant), n_estimators) for variant in variants for seed in seeds]
    return {"label": LABEL, "dataset": settings.DATASET, "personas": len(personas), "tasks": len(tasks), "runs": runs}


def _mean_sd(values: list[float]) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "–"
    return f"{mean(values):.3f}" + (f" ± {stdev(values):.3f}" if len(values) > 1 else "")


def to_markdown(report: dict[str, Any]) -> str:
    lines = [f"# C1 simulation results — {report['label']}", "",
             f"{report['personas']} personas, {report['tasks']} planned tasks; mean ± sd over seeds.", ""]
    for variant in dict.fromkeys(r["variant"] for r in report["runs"]):
        runs = [r for r in report["runs"] if r["variant"] == variant]
        lines += [f"## Variant: {variant} (SYNTHETIC)", "", "| Model 1 method | cold MAE min | warm MAE min | warm MAE log | warm coverage |",
                  "|---|---|---|---|---|"]
        for name in runs[0]["model1"]["warm"]:
            lines.append("| " + " | ".join([
                name,
                _mean_sd([r["model1"]["cold"][name]["maeMinutes"] for r in runs]),
                _mean_sd([r["model1"]["warm"][name]["maeMinutes"] for r in runs]),
                _mean_sd([r["model1"]["warm"][name]["maeLog"] for r in runs]),
                _mean_sd([r["model1"]["warm"][name]["coverage"] for r in runs]),
            ]) + " |")
        lines += ["", "| Event metric (same events) | raw | corrected |", "|---|---|---|"]
        for key in ("ctrrPlanned", "ctrrRealised", "ptvr", "feasibilityTrue", "realisedFeasibility", "planCompletionRate"):
            lines.append(f"| {key} | " + " | ".join(_mean_sd([r["events"]["summary"][p][key] for r in runs]) for p in ("raw", "corrected")) + " |")
        lines.append(f"| decision-change rate | {_mean_sd([r['events']['decisionChangeRate'] for r in runs])} | |")
        lines.append(f"| events planned / skipped (engine cannot plan, e.g. None EF) | "
                     f"{_mean_sd([r['events']['total'] for r in runs])} | {_mean_sd([r['events']['skippedUnplannable'] for r in runs])} |")
        lines += ["", "| Model 2 policy | mean simulated acceptance |", "|---|---|"]
        for name in runs[0]["model2"]:
            lines.append(f"| {name} | {_mean_sd([mean(r['model2'][name]) if r['model2'][name] else None for r in runs])} |")
        lines.append("")
    return "\n".join(lines)
