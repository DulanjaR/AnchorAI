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
from components.c1_disruption.sim.events import CANNOT_PLAN, NO_EFFECT, Event, build_events, event_metrics
from components.c1_disruption.sim.generate import World, generate
from components.c1_disruption.sim.personas import load_personas, load_schedule, load_tasks
from components.c1_disruption.sim.profile import load_profile

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
                   "noEffect": sum(s.kind == NO_EFFECT for s in skipped),
                   "skippedUnplannable": sum(s.kind == CANNOT_PLAN for s in skipped),
                   "skippedByType": {t: sum(s.kind == CANNOT_PLAN and s.type == t for s in skipped)
                                     for t in sorted({s.type for s in skipped if s.kind == CANNOT_PLAN})},
                   "perPersona": {pid: sum(e.persona_id == pid for e in events) for pid in sorted(world.personas)},
                   "profile": world.profile_report,
                   "skippedReasons": sorted({s.reason for s in skipped if s.kind == CANNOT_PLAN}),
                   "decisionChangeRate": mean(changes) if changes else None,
                   "tightSlackEvents": sum(r["tightSlack"] for r in rows), "rows": rows},
        "model2": model2(world, events, world.seed),
    }


def run(personas_csv: str, tasks_csv: str, seeds: Iterable[int] = settings.SEEDS,
        variants: Iterable[str] = VARIANTS, n_estimators: int = settings.SIM_N_ESTIMATORS,
        schedule_csv: str | None = None, habits_csv: str | None = None,
        profile_csv: str | None = None) -> dict[str, Any]:
    """schedule_csv: per-day blocks (free-time windows etc.); habits_csv: special habits;
    profile_csv: per-persona disruption profile (sim/profile.py). All optional; without
    them the persona's fixed work hours, plain drift and random disruptions are used."""
    personas = load_personas(personas_csv, habits_csv)
    tasks = load_tasks(tasks_csv, personas)
    schedule = load_schedule(schedule_csv, personas) if schedule_csv else None
    profile = load_profile(profile_csv, personas) if profile_csv else None
    runs = [run_world(generate(personas, tasks, seed, variant, schedule, profile), n_estimators)
            for variant in variants for seed in seeds]
    return {"label": LABEL, "dataset": settings.DATASET, "personas": len(personas), "tasks": len(tasks),
            "scheduled": schedule is not None, "profiled": profile is not None, "runs": runs}


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
        lines.append(f"| disruptions with no effect (overlap no planned task) | "
                     f"{_mean_sd([r['events']['noEffect'] for r in runs])} | |")
        if runs[0]["events"].get("profile"):
            lines.append(f"| top-up disruptions drawn (to reach 10 per persona) | "
                         f"{_mean_sd([sum(p['topUp'] for p in r['events']['profile'].values()) for r in runs])} | |")
            lines.append(f"| personas short of 10 effective disruptions | "
                         f"{_mean_sd([sum(p['shortfall'] > 0 for p in r['events']['profile'].values()) for r in runs])} | |")
        lines += ["", "| Model 1 learning curve (warm, model) | n records seen | MAE min |", "|---|---|---|"]
        for i, row in enumerate(runs[0]["model1"]["learningCurve"]):
            label = f"{row['nFrom']}–{row['nTo'] - 1}" if row["nTo"] else f"{row['nFrom']}+"
            values = [r["model1"]["learningCurve"][i]["maeMinutes"] for r in runs]
            lines.append(f"| | {label} | {_mean_sd(values)} |")
        lines += ["", "| Model 2 policy (accept probabilities 0.85 / 0.3 are ASSUMPTIONS) | mean acceptance | first half | second half |",
                  "|---|---|---|---|"]
        for name in runs[0]["model2"]:
            def half(values, second):
                if not values:
                    return None
                k = len(values) // 2
                part = values[k:] if second else values[:k]
                return mean(part) if part else None
            lines.append("| " + " | ".join([
                name,
                _mean_sd([mean(r["model2"][name]) if r["model2"][name] else None for r in runs]),
                _mean_sd([half(r["model2"][name], False) for r in runs]),
                _mean_sd([half(r["model2"][name], True) for r in runs]),
            ]) + " |")
        lines.append("")
    return "\n".join(lines)


def summary(report: dict[str, Any]) -> dict[str, Any]:
    """The report without per-event rows (small enough to commit)."""
    runs = []
    for r in report["runs"]:
        events = {k: v for k, v in r["events"].items() if k != "rows"}
        runs.append({**r, "events": events})
    return {**report, "runs": runs}


def main(argv: list[str] | None = None) -> None:
    """python -m components.c1_disruption.sim.experiment [--out DIR] [--seeds 11 22 …]
    Runs the full SYNTHETIC simulation on sim/data/ (the notebook 03 logic) and writes
    c1_simulation_SYNTHETIC.md and .json to DIR (default sim/results/)."""
    import argparse
    import json
    from pathlib import Path

    here = Path(__file__).parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(here / "results"))
    parser.add_argument("--seeds", type=int, nargs="*", default=list(settings.SEEDS))
    parser.add_argument("--variants", nargs="*", default=list(VARIANTS))
    parser.add_argument("--trees", type=int, default=settings.SIM_N_ESTIMATORS)
    args = parser.parse_args(argv)
    data = here / "data"
    report = run(str(data / "SYNTHETIC_personas.csv"), str(data / "SYNTHETIC_tasks_planned.csv"),
                 seeds=args.seeds, variants=args.variants, n_estimators=args.trees,
                 schedule_csv=str(data / "SYNTHETIC_schedule.csv"), habits_csv=str(data / "SYNTHETIC_habits.csv"),
                 profile_csv=str(data / "SYNTHETIC_disruption_profile.csv"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "c1_simulation_SYNTHETIC.md").write_text(to_markdown(report) + "\n", encoding="utf-8", newline="\n")
    (out / "c1_simulation_SYNTHETIC.json").write_text(json.dumps(summary(report), indent=1) + "\n", encoding="utf-8",
                                                      newline="\n")
    print(to_markdown(report))


if __name__ == "__main__":
    main()
