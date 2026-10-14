"""Export examples for manual review as a CSV you can open in Excel or Google Sheets.

Includes every example the compliance check flagged or whose disclosure score is outside its
tier's band, plus a random sample (default 10%) of the rest, so you also measure how often the
automatic checks miss a problem.

    python -m components.c4_hcde.training.review_sample

Fill the ``verdict`` column with keep, fix or reject. For fix, paste the corrected reply
into ``fixed_reply``. Then run split_dataset, which applies your verdicts.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from .build_dataset import DEFAULT_OUT, load_jsonl

DEFAULT_REVIEW = DEFAULT_OUT.parent / "review.csv"
FIELDS = ["task_id", "tier", "module", "difficulty", "task", "reply", "auto_passed", "auto_reasons",
          "disclosure", "disclosure_band", "verdict", "fixed_reply", "notes"]


def needs_review(r: dict) -> bool:
    d = r.get("disclosure")
    return not r["compliance"]["passed"] or (d is not None and not d["in_band"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--out", type=Path, default=DEFAULT_REVIEW)
    ap.add_argument("--rate", type=float, default=0.10, help="share of passed examples to sample")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    if args.out.exists():
        print(f"{args.out} already exists; not overwriting your verdicts. Delete it to re-sample.")
        return 1

    rows = load_jsonl(args.raw)
    flagged = [r for r in rows if needs_review(r)]
    passed = [r for r in rows if not needs_review(r)]
    rng = random.Random(args.seed)
    sample = rng.sample(passed, k=min(len(passed), max(1, round(len(passed) * args.rate)))) if passed else []
    chosen = sorted(flagged + sample, key=lambda r: (r["task_id"], r["tier"]))

    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in chosen:
            w.writerow({
                "task_id": r["task_id"], "tier": r["tier"], "module": r["module"],
                "difficulty": r["difficulty"], "task": r["messages"][1]["content"],
                "reply": r["messages"][2]["content"], "auto_passed": r["compliance"]["passed"],
                "auto_reasons": "; ".join(r["compliance"]["reasons"] + (
                    ["disclosure outside band"] if r.get("disclosure") and not r["disclosure"]["in_band"] else [])),
                "disclosure": (r.get("disclosure") or {}).get("score", ""),
                "disclosure_band": "-".join(map(str, (r.get("disclosure") or {}).get("band", []))),
                "verdict": "", "fixed_reply": "", "notes": "",
            })
    print(f"Wrote {len(chosen)} rows to {args.out}: {len(flagged)} flagged + {len(sample)} sampled from {len(passed)} that passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
