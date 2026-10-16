"""Statistics for the thesis: does fine-tuning (not prompting) produce graded disclosure?

Reads judged generations.jsonl files (evaluate.py --judge) and reports, per test set:

1. Graded disclosure per condition: Spearman rank correlation between tier (0 = HUMAN_FIRST ..
   4 = EMERGENCY) and the Solution Disclosure Score, with a 95% bootstrap CI; spread from
   HUMAN_FIRST to EMERGENCY; whether the tier means rise monotonically; in-band rate; leakage at
   the two lowest tiers.
2. Separation of neighbouring tiers: difference in mean SDS and a one-sided permutation p-value.
3. Head to head (tuned vs each baseline on the same task and tier): in-band rate, mean distance
   outside the band (0 = inside), a paired sign-flip permutation test on that distance, and a
   cluster bootstrap (resampling tasks) of the difference in Spearman rho.
4. Pressure: for every condition with a "+pressure" twin, SDS without vs with pressure on the
   same task and tier, the paired permutation p-value, and the share of replies that "gave in"
   (SDS above the tier's band).

Pure Python, fixed random seed, so the numbers are reproducible.

    python -m components.c4_hcde.training.stats \
        --set it runs/b/eval/generations.jsonl runs/b/eval-pressure/generations.jsonl runs/a/eval/generations.jsonl \
        --set transfer runs/hcde-qwen7b/eval-transfer/generations.jsonl runs/b/eval-transfer/generations.jsonl \
        --rename tuned_tag=tuned_v1 --out runs/stats.md
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .tiers import DISCLOSURE_BANDS, TIER_NAMES

RNG_SEED, N_BOOT, N_PERM = 7, 2000, 10000
TIER_INDEX = {t: i for i, t in enumerate(TIER_NAMES)}


# ---------------------------------------------------------------- basic statistics
def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1  # average rank for ties
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx) ** 0.5
    syy = sum((b - my) ** 2 for b in ry) ** 0.5
    return sxy / (sxx * syy) if sxx and syy else float("nan")


def _ci(values: list[float]) -> tuple[float, float]:
    v = sorted(x for x in values if x == x)
    if not v:
        return float("nan"), float("nan")
    return v[int(0.025 * (len(v) - 1))], v[int(0.975 * (len(v) - 1))]


def perm_greater(a: list[float], b: list[float], rng: random.Random) -> float:
    """One-sided permutation p-value for mean(a) > mean(b)."""
    if not a or not b:
        return float("nan")
    obs = mean(a) - mean(b)
    pool, na, hits = a + b, len(a), 0
    for _ in range(N_PERM):
        rng.shuffle(pool)
        if mean(pool[:na]) - mean(pool[na:]) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def paired_signflip(diffs: list[float], rng: random.Random, two_sided: bool = True) -> float:
    """Permutation p-value for mean(diffs) != 0 (or > 0 when two_sided=False)."""
    if not diffs:
        return float("nan")
    obs = mean(diffs)
    hits = 0
    for _ in range(N_PERM):
        m = mean(d if rng.random() < 0.5 else -d for d in diffs)
        if (abs(m) >= abs(obs) - 1e-12) if two_sided else (m >= obs - 1e-12):
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def band_distance(tier: str, sds: float) -> float:
    lo, hi = DISCLOSURE_BANDS[tier]
    return max(0.0, lo - sds, sds - hi)


def fmt(x: float, d: int = 2) -> str:
    return "-" if x != x else f"{x:.{d}f}"


def fp(p: float) -> str:
    return "-" if p != p else ("<0.001" if p < 0.001 else f"{p:.3f}")


# ---------------------------------------------------------------- loading
def load(paths: list[Path], rename: dict[str, str]) -> dict[str, dict[tuple[str, str], dict]]:
    """condition -> (task_id, tier) -> row, for rows with a valid disclosure score. Later files win."""
    out: dict = defaultdict(dict)
    for p in paths:
        if not p.exists():
            print(f"  (missing, skipped: {p})")
            continue
        for line in p.open():
            if not line.strip():
                continue
            r = json.loads(line)
            d = r.get("disclosure") or {}
            if r.get("tier") not in TIER_INDEX or "score" not in d:
                continue
            cond = r["condition"]
            base, plus, rest = cond.partition("+")
            cond = rename.get(base, base) + plus + rest
            out[cond][(r["task_id"], r["tier"])] = {"sds": float(d["score"]), "tier": r["tier"], "task": r["task_id"]}
    return out


# ---------------------------------------------------------------- sections
def graded(data: dict, rng: random.Random) -> list[str]:
    lines = ["| Condition | n | " + " | ".join(t.title().replace("_", " ") for t in TIER_NAMES) +
             " | Spearman rho [95% CI] | Spread | Rises | In band | Leak at HF+Hint |",
             "| --- | --- | " + " | ".join("---" for _ in TIER_NAMES) + " | --- | --- | --- | --- | --- |"]
    for cond, rows in data.items():
        if "+" in cond or len({r["tier"] for r in rows.values()}) < len(TIER_NAMES):
            continue
        rs = list(rows.values())
        by_tier = {t: [r["sds"] for r in rs if r["tier"] == t] for t in TIER_NAMES}
        means = [mean(by_tier[t]) for t in TIER_NAMES]
        x, y = [TIER_INDEX[r["tier"]] for r in rs], [r["sds"] for r in rs]
        rho = spearman(x, y)
        boots = []
        for _ in range(N_BOOT):
            s = [rng.randrange(len(rs)) for _ in rs]
            boots.append(spearman([x[i] for i in s], [y[i] for i in s]))
        lo, hi = _ci(boots)
        rises = all(a <= b for a, b in zip(means, means[1:]))
        inband = mean(band_distance(r["tier"], r["sds"]) == 0 for r in rs)
        leak = mean(by_tier["HUMAN_FIRST"] + by_tier["HINT"])
        lines.append(f"| {cond} | {len(rs)} | " + " | ".join(fmt(m) for m in means) +
                     f" | {fmt(rho)} [{fmt(lo)}, {fmt(hi)}] | {fmt(means[-1] - means[0])} | "
                     f"{'yes' if rises else 'NO'} | {inband:.0%} | {fmt(leak)} |")
    return lines


def separation(data: dict, rng: random.Random) -> list[str]:
    pairs = list(zip(TIER_NAMES, TIER_NAMES[1:]))
    lines = ["| Condition | " + " | ".join(f"{a.title().replace('_', ' ')} → {b.title().replace('_', ' ')}"
                                          for a, b in pairs) + " |",
             "| --- | " + " | ".join("---" for _ in pairs) + " |"]
    for cond, rows in data.items():
        if "+" in cond:
            continue
        cells = []
        for a, b in pairs:
            la = [r["sds"] for r in rows.values() if r["tier"] == a]
            lb = [r["sds"] for r in rows.values() if r["tier"] == b]
            if not la or not lb:
                cells.append("-")
                continue
            cells.append(f"{mean(lb) - mean(la):+.2f} (p {fp(perm_greater(lb, la, rng))})")
        lines.append(f"| {cond} | " + " | ".join(cells) + " |")
    return lines


def head_to_head(data: dict, rng: random.Random) -> list[str]:
    tuned = [c for c in data if c.startswith("tuned") and "+" not in c]
    bases = [c for c in data if c.startswith("base") and "+" not in c]
    lines = ["| Tuned vs baseline | Matched | In band (tuned / base) | Distance outside band (tuned / base) | p (distance) "
             "| rho difference [95% CI] |",
             "| --- | --- | --- | --- | --- | --- |"]
    for t in tuned:
        for b in bases:
            keys = sorted(set(data[t]) & set(data[b]))
            if len(keys) < 5:
                continue
            dt = [band_distance(data[t][k]["tier"], data[t][k]["sds"]) for k in keys]
            db = [band_distance(data[b][k]["tier"], data[b][k]["sds"]) for k in keys]
            p = paired_signflip([x - y for x, y in zip(dt, db)], rng)
            tasks = sorted({k[0] for k in keys})
            by_task = defaultdict(list)
            for k in keys:
                by_task[k[0]].append(k)

            def rho_of(cond: str, ks: list) -> float:
                return spearman([TIER_INDEX[k[1]] for k in ks], [data[cond][k]["sds"] for k in ks])

            obs = rho_of(t, keys) - rho_of(b, keys)
            boots = []
            for _ in range(N_BOOT):
                ks = [k for _ in tasks for k in by_task[tasks[rng.randrange(len(tasks))]]]
                boots.append(rho_of(t, ks) - rho_of(b, ks))
            lo, hi = _ci(boots)
            lines.append(f"| {t} vs {b} | {len(keys)} | {mean(x == 0 for x in dt):.0%} / {mean(x == 0 for x in db):.0%} | "
                         f"{fmt(mean(dt))} / {fmt(mean(db))} | {fp(p)} | {obs:+.2f} [{lo:+.2f}, {hi:+.2f}] |")
    return lines


def pressure(data: dict, rng: random.Random) -> list[str]:
    lines = ["| Condition | Matched | SDS without → with pressure | Change | p | In band under pressure | Gave in |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for cond in [c for c in data if "+" not in c]:
        twin = cond + "+pressure"
        if twin not in data:
            continue
        keys = sorted(set(data[cond]) & set(data[twin]))
        if not keys:
            continue
        a = [data[cond][k]["sds"] for k in keys]
        b = [data[twin][k]["sds"] for k in keys]
        tiers = [data[twin][k]["tier"] for k in keys]
        gave_in = mean(s > DISCLOSURE_BANDS[t][1] for s, t in zip(b, tiers))
        inband = mean(band_distance(t, s) == 0 for s, t in zip(b, tiers))
        p = paired_signflip([y - x for x, y in zip(a, b)], rng, two_sided=False)
        lines.append(f"| {cond} | {len(keys)} | {fmt(mean(a))} → {fmt(mean(b))} | {mean(b) - mean(a):+.2f} | {fp(p)} | "
                     f"{inband:.0%} | {gave_in:.0%} |")
    # conditions that only exist under pressure (no twin): still report how often they gave in
    for cond in [c for c in data if c.endswith("+pressure") and c.split("+")[0] not in data]:
        rs = list(data[cond].values())
        gave_in = mean(r["sds"] > DISCLOSURE_BANDS[r["tier"]][1] for r in rs)
        inband = mean(band_distance(r["tier"], r["sds"]) == 0 for r in rs)
        lines.append(f"| {cond} (no unpressured twin) | {len(rs)} | - → {fmt(mean(r['sds'] for r in rs))} | - | - | "
                     f"{inband:.0%} | {gave_in:.0%} |")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", nargs="+", action="append", metavar=("NAME", "FILE"), required=True,
                    help="a test set name followed by its judged generations.jsonl files")
    ap.add_argument("--rename", nargs="*", default=[], help="old=new condition names, e.g. tuned_tag=tuned_v1")
    ap.add_argument("--out", type=Path, default=Path("runs/stats.md"))
    args = ap.parse_args(argv)
    rename = dict(r.split("=", 1) for r in args.rename)
    rng = random.Random(RNG_SEED)
    md = ["# HCDE statistics", "",
          "SDS = Solution Disclosure Score (0 = reveals nothing, 1 = reveals the whole solution). "
          "p-values are permutation tests (10,000 permutations), CIs are 2,000-sample bootstraps, seed 7.", ""]
    for name, *files in args.set:
        print(f"set {name}: {len(files)} file(s)")
        data = load([Path(f) for f in files], rename)
        data = dict(sorted(data.items()))
        md += [f"## {name}", "",
               "### 1. Graded disclosure (does help rise with the tier?)", "", *graded(data, rng), "",
               "### 2. Separation between neighbouring tiers (mean SDS difference, one-sided p)", "",
               *separation(data, rng), "",
               "### 3. Fine-tuned vs baselines on the same tasks", "", *head_to_head(data, rng), "",
               "### 4. Pressure test (\"just give me the answer\")", "", *pressure(data, rng), ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
