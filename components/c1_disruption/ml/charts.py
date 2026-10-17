"""Charts for the notebooks (planning chat, 17 Oct 2026). matplotlib is a notebook
dependency only (notebooks/requirements.txt), imported inside each function.

Every chart title must say where the data comes from — SYNTHETIC or REAL — and a title
without one of them is refused, so no chart can hide that its data is synthetic.
"""
from typing import Any, Mapping, Sequence

LABELS = ("SYNTHETIC", "REAL")


def _check(title: str) -> None:
    if not any(label in title for label in LABELS):
        raise ValueError(f"Chart title must say SYNTHETIC or REAL: {title!r}")


def _plt():
    import matplotlib.pyplot as plt

    return plt


def mae_by_method(scores: Mapping[str, Mapping[str, float | None]], title: str):
    """Bar chart. scores: {method: {"cold start": mae, "warm": mae}} in minutes."""
    _check(title)
    plt = _plt()
    methods = list(scores)
    parts = list(dict.fromkeys(p for s in scores.values() for p in s))
    fig, ax = plt.subplots(figsize=(8, 4))
    width = 0.8 / max(len(parts), 1)
    for j, part in enumerate(parts):
        values = [scores[m].get(part) or 0.0 for m in methods]
        bars = ax.bar([i + j * width for i in range(len(methods))], values, width, label=part)
        ax.bar_label(bars, fmt="%.1f", fontsize=8)
    ax.set_xticks([i + width * (len(parts) - 1) / 2 for i in range(len(methods))], methods, rotation=15, ha="right")
    ax.set_ylabel("MAE (minutes)  — lower is better")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig


def learning_curve(curves: Mapping[str, Sequence[Mapping[str, Any]]], title: str):
    """Line chart of MAE against the student's records seen. curves: {label: learning_curve rows}."""
    _check(title)
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7, 4))
    for label, rows in curves.items():
        points = [(f"{r['nFrom']}–{r['nTo'] - 1}" if r["nTo"] else f"{r['nFrom']}+", r["maeMinutes"])
                  for r in rows if r.get("maeMinutes") is not None]
        if points:
            ax.plot([p[0] for p in points], [p[1] for p in points], marker="o", label=label)
    ax.set_xlabel("the student's own finished tasks seen so far")
    ax.set_ylabel("MAE (minutes)")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig


def predicted_vs_actual(points: Sequence[tuple[float, float, float]], title: str):
    """Scatter, log-log. points: (estimated, actual, predicted) minutes. The raw estimate is
    shown too (grey), so the correction is visible against trusting the estimate."""
    _check(title)
    plt = _plt()
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    est = [p[0] for p in points]
    actual = [p[1] for p in points]
    pred = [p[2] for p in points]
    ax.scatter(actual, est, s=8, alpha=0.35, color="grey", label="raw estimate")
    ax.scatter(actual, pred, s=8, alpha=0.5, label="Model 1 prediction")
    lo = max(min(min(actual), min(est), min(pred)), 1)
    hi = max(max(actual), max(est), max(pred))
    ax.plot([lo, hi], [lo, hi], color="black", linewidth=1, label="perfect")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("actual minutes")
    ax.set_ylabel("predicted minutes")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig


def gate_per_student(open_share: Mapping[str, float], title: str):
    """Bar chart: for each student, the share of runs (or 1/0 for one run) in which the
    earned-trust gate was open at their last evaluation point."""
    _check(title)
    plt = _plt()
    students = list(open_share)
    values = [open_share[s] for s in students]
    fig, ax = plt.subplots(figsize=(max(6, 0.35 * len(students)), 3.5))
    ax.bar(students, values, color=["tab:green" if v >= 0.5 else "tab:red" for v in values])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("gate open (share)")
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=90 if len(students) > 15 else 0)
    fig.tight_layout()
    return fig


def acceptance_over_time(curves: Mapping[str, Sequence[float]], title: str, window: int = 15):
    """Line chart: moving average of simulated acceptance per policy, in event order."""
    _check(title)
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4))
    for name, values in curves.items():
        if len(values) < window:
            continue
        smooth = [sum(values[i - window:i]) / window for i in range(window, len(values) + 1)]
        ax.plot(range(window, len(values) + 1), smooth, label=name)
    ax.set_xlabel("event number (time order)")
    ax.set_ylabel(f"acceptance (moving average of {window})")
    ax.set_ylim(0, 1)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig
