"""ML Model 1 on a real public dataset: CESAW (SEI/CMU, professional developers).

Source: https://kilthub.cmu.edu/articles/CESAW_Project_Data_Fact_sheets/9922697
The licence is not stated, so the data is NEVER committed: download it to a folder
outside the repository and set C1_CESAW_PATH (the folder, or the CESAW_task_fact.csv file).

Mapping, one CESAW task -> one Model 1 record:
  studentId        = "D" + person_key (developer)
  estimatedMinutes = task_plan_time_minutes
  actualMinutes    = task_actual_time_minutes (CESAW already excludes interrupt time)
  taskType         = "Digital" (the original phase is kept in the extra column `phase`)
  date, startHour  = from task_actual_start_date
  priority         = "Medium" (CESAW has none)
Tasks with plan <= 0, actual <= 0 or no readable start time are dropped and counted.

Evaluation = the synthetic one (ml/drift/evaluation.py), for the model and baselines B0-B3:
cold start with developers held out in groups (COLD_FOLDS seeded groups; a developer's own
tasks are never in training when they are predicted) and rolling-origin (warm) on a seeded
sample of developers. Folds run in parallel and print progress.
Every result is labelled REAL (CESAW, professional developers), never SYNTHETIC.
"""
import csv
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from joblib import Parallel, delayed

from components.c1_disruption.ml.drift import baselines
from components.c1_disruption.ml.drift.data import log_drift
from components.c1_disruption.ml.drift.evaluation import Predictions, learning_curve, score
from components.c1_disruption.ml.drift.external import settings
from components.c1_disruption.ml.drift.model import DriftModel

Records = Sequence[Mapping[str, Any]]
Factory = Callable[[], Any]


def task_file(path: str | Path) -> Path:
    p = Path(path)
    p = p / settings.TASK_FILE if p.is_dir() else p
    if not p.is_file():
        raise FileNotFoundError(f"CESAW task file not found: {p} (set C1_CESAW_PATH to the folder or the file)")
    return p


def _start(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%m/%d/%Y %H:%M")
    except ValueError:  # missing value, or the one malformed row
        return None


def load_cesaw(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Model 1 records and a report of what was dropped."""
    report = {"rows": 0, "droppedPlanNotPositive": 0, "droppedActualNotPositive": 0,
              "droppedNoStartTime": 0, "kept": 0, "developers": 0}
    records: list[dict[str, Any]] = []
    with open(task_file(path), newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            report["rows"] += 1
            plan, actual = float(row["task_plan_time_minutes"]), float(row["task_actual_time_minutes"])
            if plan <= 0:
                report["droppedPlanNotPositive"] += 1
                continue
            if actual <= 0:
                report["droppedActualNotPositive"] += 1
                continue
            start = _start(row["task_actual_start_date"])
            if start is None:
                report["droppedNoStartTime"] += 1
                continue
            records.append({
                "studentId": f"D{row['person_key']}", "taskType": settings.TASK_TYPE, "priority": settings.PRIORITY,
                "estimatedMinutes": plan, "actualMinutes": actual, "date": start.date().isoformat(),
                "startHour": start.hour, "phase": row["phase_short_name"], "project": row["project_key"],
            })
    report["kept"] = len(records)
    report["developers"] = len({r["studentId"] for r in records})
    return records, report


def methods(n_estimators: int = settings.N_ESTIMATORS) -> dict[str, Factory]:
    return {"model": lambda: DriftModel(n_estimators=n_estimators), **{c.name: c for c in baselines.BASELINES}}


def _by_developer(records: Records) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in records:
        out[r["studentId"]].append(r)
    return out


def _fit_predict(factories: Mapping[str, Factory], train: Records, test: Records, n_seen: int) -> dict[str, Predictions]:
    result = {}
    for name, factory in factories.items():
        result[name] = Predictions()
        result[name].add(test, factory().fit(train), n_seen=n_seen)
    return result


def _merge(parts: list[dict[str, Predictions]], names: Sequence[str]) -> dict[str, Predictions]:
    merged = {name: Predictions() for name in names}
    for part in parts:
        for name, p in part.items():
            m = merged[name]
            m.records += p.records
            m.log_pred += p.log_pred
            m.log_low += p.log_low
            m.log_high += p.log_high
            m.n_seen += p.n_seen
    return merged


def cold_groups(developers: Sequence[str], folds: int = settings.COLD_FOLDS) -> list[list[str]]:
    """Seeded split of the developers into `folds` groups of (almost) equal size."""
    order = sorted(developers)
    random.Random(settings.COLD_SEED).shuffle(order)
    return [sorted(order[i::folds]) for i in range(min(folds, len(order)))]


def cold_start(records: Records, factories: Mapping[str, Factory], n_jobs: int = settings.N_JOBS,
               folds: int = settings.COLD_FOLDS) -> dict[str, Predictions]:
    """Cold start: each group of developers is held out in turn; train on all other developers,
    predict the group's tasks with n = 0 (none of their own records seen)."""
    jobs = []
    for group in cold_groups(sorted({r["studentId"] for r in records}), folds):
        held = set(group)
        jobs.append(delayed(_fit_predict)(factories, [r for r in records if r["studentId"] not in held],
                                          [r for r in records if r["studentId"] in held], 0))
    return _merge(Parallel(n_jobs=n_jobs, verbose=10)(jobs), list(factories))


def warm_developers(records: Records) -> list[str]:
    """Seeded sample of developers with enough working days to be evaluated warm."""
    eligible = sorted(d for d, tasks in _by_developer(records).items()
                      if len({r["date"] for r in tasks}) >= settings.WARM_MIN_DAYS)
    return sorted(random.Random(settings.WARM_SEED).sample(eligible, min(settings.WARM_DEVELOPERS, len(eligible))))


def warm_start(records: Records, factories: Mapping[str, Factory], developers: Sequence[str],
               step_days: int = settings.WARM_STEP_DAYS, n_jobs: int = settings.N_JOBS) -> dict[str, Predictions]:
    """Rolling-origin as in ml/drift/evaluation.py (min history 1 day), only for `developers`,
    with one origin per `step_days` of the developer's own days."""
    own = _by_developer(records)
    jobs = []
    for d in developers:
        others = [r for r in records if r["studentId"] != d]
        days = sorted({r["date"] for r in own[d]})
        for i in range(1, len(days), step_days):
            window = set(days[i:i + step_days])
            past = [r for r in own[d] if r["date"] < days[i]]
            test = [r for r in own[d] if r["date"] in window]
            jobs.append(delayed(_fit_predict)(factories, others + past, test, len(past)))
    return _merge(Parallel(n_jobs=n_jobs, verbose=10)(jobs), list(factories))


def evaluate(records: Records, n_estimators: int = settings.N_ESTIMATORS, n_jobs: int = settings.N_JOBS,
             folds: int = settings.COLD_FOLDS, warm_sample: Sequence[str] | None = None) -> dict[str, Any]:
    factories = methods(n_estimators)
    sample = list(warm_sample) if warm_sample is not None else warm_developers(records)
    cold = cold_start(records, factories, n_jobs, folds)
    warm = warm_start(records, factories, sample, n_jobs=n_jobs)
    return {
        "label": settings.LABEL, "trees": n_estimators, "coldFolds": folds, "warmDevelopers": sample,
        "cold": {name: score(p) for name, p in cold.items()},
        "warm": {name: score(p) for name, p in warm.items()},
        "learningCurve": learning_curve(warm["model"]),
    }


def describe(records: Records) -> dict[str, float]:
    """How hard the data is: spread of the real log(actual / estimate)."""
    y = log_drift(records)
    return {"meanLogRatio": float(y.mean()), "sdLogRatio": float(y.std()), "medianLogRatio": float(np.median(y))}


def to_markdown(report: dict[str, Any], dropped: Mapping[str, int], shape: Mapping[str, float]) -> str:
    def f(v: float | None, digits: int = 3) -> str:
        return "–" if v is None else f"{v:.{digits}f}"

    lines = [
        f"# Model 1 on CESAW — {report['label']}",
        "",
        "External validation of Model 1 on real estimation errors. Limitation: these are professional "
        "software developers, not students, and CESAW has no priority or task type (every task is `Digital`, "
        "`Medium`). Data: CESAW (SEI/CMU), not committed (licence not stated).",
        "",
        f"- Tasks in the file: {dropped['rows']}; kept {dropped['kept']} from {dropped['developers']} developers.",
        f"- Dropped: plan ≤ 0: {dropped['droppedPlanNotPositive']}; actual ≤ 0: {dropped['droppedActualNotPositive']}; "
        f"no readable start time: {dropped['droppedNoStartTime']}.",
        f"- Real log(actual ÷ estimate): mean {f(shape['meanLogRatio'])}, median {f(shape['medianLogRatio'])}, "
        f"sd {f(shape['sdLogRatio'])}.",
        f"- Model: quantile forest, {report['trees']} trees (production default 200). Warm evaluation: seeded sample of "
        f"{len(report['warmDevelopers'])} developers with ≥ {settings.WARM_MIN_DAYS} working days, one origin per "
        f"{settings.WARM_STEP_DAYS} of their days. Cold start covers every developer: {report['coldFolds']} seeded "
        "groups of developers, each held out in turn (none of a developer's own tasks in training).",
        "",
    ]
    for part, title in (("cold", "Cold start — developers held out in groups (n = 0)"),
                        ("warm", "Warm — rolling-origin (sampled developers)")):
        lines += [f"## {title}", "", "| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n |", "|---|---|---|---|---|"]
        for name, s in report[part].items():
            lines.append(f"| {name} | {f(s['maeMinutes'], 2)} | {f(s['maeLog'])} | {f(s['coverage'])} | {s['n']} |")
        lines.append("")
    lines += ["## Learning curve (warm, model)", "", "| Developer's records seen | MAE minutes | n |", "|---|---|---|"]
    for row in report["learningCurve"]:
        label = f"{row['nFrom']}–{row['nTo'] - 1}" if row["nTo"] else f"{row['nFrom']}+"
        lines.append(f"| {label} | {f(row['maeMinutes'], 2)} | {row['n']} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """python -m components.c1_disruption.ml.drift.external.cesaw [--path P] [--out FILE] [--trees N]"""
    import argparse

    from components.c1_disruption.app.settings import c1_settings

    here = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=c1_settings.cesaw_path)
    parser.add_argument("--out", default=str(here / "docs" / "results" / "c1_model1_cesaw.md"))
    parser.add_argument("--trees", type=int, default=settings.N_ESTIMATORS)
    parser.add_argument("--jobs", type=int, default=settings.N_JOBS)
    args = parser.parse_args(argv)
    if not args.path:
        parser.error("set C1_CESAW_PATH or pass --path (folder with CESAW_task_fact.csv)")
    records, dropped = load_cesaw(args.path)
    report = evaluate(records, args.trees, args.jobs)
    text = to_markdown(report, dropped, describe(records))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(text)


if __name__ == "__main__":
    main()
