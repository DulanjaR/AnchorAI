"""Does the optional task category lower Model 1's error? (planning chat, 16 Oct 2026) — SYNTHETIC

    python -m components.c1_disruption.sim.category_ablation [--seeds 11 22 …] [--trees N]

Same worlds as the full simulation (sim/data/, seeds × planted / null / misspecified), Model 1
only: the model WITH the category feature vs the same model WITHOUT it, plus B0, in cold start
(leave one persona out) and warm rolling-origin. Also the warm error per category and per
persona, so it is visible where a difference comes from. The categories are inferred from the
task titles (sim/personas.infer_category) because the tasks file has none; the generator plants
no category drift of its own (only P08's title habit is close to one). Writes
sim/results/c1_category_SYNTHETIC.md. SYNTHETIC: pipeline validation only.
"""
from collections import defaultdict
from statistics import mean, stdev
from typing import Any, Iterable

from components.c1_disruption.ml.drift import baselines
from components.c1_disruption.ml.drift.data import clean
from components.c1_disruption.ml.drift.evaluation import Predictions, gate_students, leave_one_student_out, rolling_origin, score
from components.c1_disruption.ml.drift.model import DriftModel
from components.c1_disruption.sim import settings
from components.c1_disruption.sim.experiment import VARIANTS
from components.c1_disruption.sim.generate import generate
from components.c1_disruption.sim.personas import load_personas, load_schedule, load_tasks
from components.c1_disruption.sim.profile import load_profile

WITH, WITHOUT = "model with category", "model without category"
B0 = baselines.B0NoDrift.name


def _subset(p: Predictions, keep) -> Predictions:
    idx = [i for i, r in enumerate(p.records) if keep(r)]
    return Predictions([p.records[i] for i in idx], [p.log_pred[i] for i in idx], [p.log_low[i] for i in idx],
                       [p.log_high[i] for i in idx], [p.n_seen[i] for i in idx],
                       [p.trusted[i] for i in idx] if p.trusted else [])


def compare(records: list[dict], n_estimators: int) -> dict[str, Any]:
    methods = {
        WITH: lambda: DriftModel(n_estimators=n_estimators, use_category=True),
        WITHOUT: lambda: DriftModel(n_estimators=n_estimators, use_category=False),
        B0: baselines.B0NoDrift,
    }
    out: dict[str, Any] = {"cold": {}, "warm": {}, "byCategory": {}, "byPersona": {}, "gateStudents": {}}
    categories = sorted({str(r.get("category")) for r in records})
    personas = sorted({r["studentId"] for r in records})
    for name, factory in methods.items():
        out["cold"][name] = score(leave_one_student_out(records, factory))
        warm = rolling_origin(records, factory, min_history_days=1, step_days=settings.ROLLING_STEP_DAYS)
        out["warm"][name] = score(warm)
        out["gateStudents"][name] = gate_students(warm)
        out["byCategory"][name] = {c: score(_subset(warm, lambda r, c=c: str(r.get("category")) == c)) for c in categories}
        out["byPersona"][name] = {s: score(_subset(warm, lambda r, s=s: r["studentId"] == s)) for s in personas}
    return out


def run(seeds: Iterable[int] = settings.SEEDS, variants: Iterable[str] = VARIANTS,
        n_estimators: int = settings.SIM_N_ESTIMATORS) -> dict[str, Any]:
    from pathlib import Path

    data = Path(__file__).parent / "data"
    personas = load_personas(str(data / "SYNTHETIC_personas.csv"), str(data / "SYNTHETIC_habits.csv"))
    tasks = load_tasks(str(data / "SYNTHETIC_tasks_planned.csv"), personas)
    schedule = load_schedule(str(data / "SYNTHETIC_schedule.csv"), personas)
    profile = load_profile(str(data / "SYNTHETIC_disruption_profile.csv"), personas)
    counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        counts[str(t.category)] += 1
    runs = []
    for variant in variants:
        for seed in seeds:
            world = generate(personas, tasks, seed, variant, schedule, profile)
            runs.append({"variant": variant, "seed": seed, **compare(clean(world.records), n_estimators)})
    return {"dataset": settings.DATASET, "trees": n_estimators, "categoryCounts": dict(counts), "runs": runs}


def _ms(values: list[float | None], digits: int = 3) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "–"
    return f"{mean(values):.{digits}f}" + (f" ± {stdev(values):.{digits}f}" if len(values) > 1 else "")


def to_markdown(report: dict[str, Any]) -> str:
    counts = ", ".join(f"{c}: {n}" for c, n in sorted(report["categoryCounts"].items()))
    lines = [
        "# Model 1: does the task category help? — SYNTHETIC — pipeline validation only, not a research finding",
        "",
        f"Same worlds as the full simulation; Model 1 with vs without the category feature ({report['trees']} trees), "
        "mean ± sd over seeds. Categories are inferred from task titles (no category column in the tasks file); "
        f"tasks per category: {counts} ('None' = no category: meetings, planning, admin). The generator plants no "
        "category drift (only persona P08's writing-task habit is close to one), so a small or zero gain is the "
        "expected honest outcome.",
        "",
    ]
    verdicts = []
    for variant in dict.fromkeys(r["variant"] for r in report["runs"]):
        runs = [r for r in report["runs"] if r["variant"] == variant]
        lines += [f"## Variant: {variant} (SYNTHETIC)", "",
                  "| Method | cold MAE min | warm MAE min | warm MAE log | warm coverage | students: gate open / closed (warm) |",
                  "|---|---|---|---|---|---|"]
        for name in (WITH, WITHOUT, B0):
            g = [r["gateStudents"][name] for r in runs]
            gate = "no gate" if all(c is None for c in g) else \
                f"{_ms([c['open'] for c in g if c])} open / {_ms([c['closed'] for c in g if c])} closed"
            lines.append(f"| {name} | {_ms([r['cold'][name]['maeMinutes'] for r in runs])} | "
                         f"{_ms([r['warm'][name]['maeMinutes'] for r in runs])} | {_ms([r['warm'][name]['maeLog'] for r in runs])} | "
                         f"{_ms([r['warm'][name]['coverage'] for r in runs])} | {gate} |")
        diff = [r["warm"][WITH]["maeMinutes"] - r["warm"][WITHOUT]["maeMinutes"] for r in runs]
        better = sum(d < 0 for d in diff)
        lines += ["", f"Warm MAE difference (with − without): {_ms(diff)} min; the category version is lower in "
                  f"{better} of {len(diff)} seeds.", ""]
        verdicts.append((variant, mean(diff), better, len(diff)))
        lines += ["| Warm MAE min by category | with | without | B0 |", "|---|---|---|---|"]
        for c in runs[0]["byCategory"][WITH]:
            lines.append(f"| {c} | " + " | ".join(_ms([r["byCategory"][m][c]["maeMinutes"] for r in runs]) for m in (WITH, WITHOUT, B0)) + " |")
        lines += ["", "| Warm MAE min by persona | with | without | B0 |", "|---|---|---|---|"]
        for s in runs[0]["byPersona"][WITH]:
            lines.append(f"| {s} | " + " | ".join(_ms([r["byPersona"][m][s]["maeMinutes"] for r in runs]) for m in (WITH, WITHOUT, B0)) + " |")
        lines.append("")
    summary = "; ".join(f"{v}: {d:+.3f} min (lower in {b}/{n} seeds)" for v, d, b, n in verdicts)
    lines[4:4] = [f"**Summary (warm MAE, with − without category):** {summary}. Negative = the category helps.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).parent / "results"))
    parser.add_argument("--seeds", type=int, nargs="*", default=list(settings.SEEDS))
    parser.add_argument("--variants", nargs="*", default=list(VARIANTS))
    parser.add_argument("--trees", type=int, default=settings.SIM_N_ESTIMATORS)
    args = parser.parse_args(argv)
    report = run(args.seeds, args.variants, args.trees)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    text = to_markdown(report)
    (out / "c1_category_SYNTHETIC.md").write_text(text + "\n", encoding="utf-8", newline="\n")
    (out / "c1_category_SYNTHETIC.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, "replace").decode(encoding))


if __name__ == "__main__":
    main()
