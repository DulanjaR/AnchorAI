"""Add a Solution Disclosure Score to every tier reply in the raw dataset.

Run after build_dataset (it needs each task's EMERGENCY reply as the reference):

    python -m components.c4_hcde.training.label_disclosure
    python -m components.c4_hcde.training.label_disclosure --raw data/dataset/transfer_raw.jsonl \
        --elements data/dataset/transfer_elements.json

Writes the score into each row (``disclosure``) and caches the extracted solution elements per
task, which the evaluation reuses. Resumable: rows that already have a score are skipped.
Replies outside their tier's disclosure band are flagged for review.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .build_dataset import DEFAULT_OUT, load_jsonl
from .disclosure import extract_elements, score_reply, summarise_disclosure
from .tiers import PROBE

DEFAULT_ELEMENTS = DEFAULT_OUT.parent / "solution_elements.json"


def mock_ask(prompt: str) -> str:
    if "JSON array" in prompt:
        return '["identify the inputs", "core loop logic", "edge case handling", "final answer"]'
    reply = prompt.split("Assistant reply:", 1)[1]
    n = 4
    if "full solution" in reply:
        return json.dumps({"scores": [1] * n})
    if "first half" in reply:
        return json.dumps({"scores": [1, 1, 0.5, 0]})
    if "TODO" in reply:
        return json.dumps({"scores": [0.5, 0.5, 0, 0]})
    return json.dumps({"scores": [0] * n})


def write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--elements", type=Path, default=DEFAULT_ELEMENTS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args(argv)
    ask = mock_ask if args.mock else None

    rows = load_jsonl(args.raw)
    elements: dict[str, list[str]] = json.loads(args.elements.read_text()) if args.elements.exists() else {}
    refs = {r["task_id"]: r for r in rows if r["tier"] == "EMERGENCY"}

    # Step 1: solution elements per task, from its EMERGENCY reply.
    todo = [tid for tid in refs if tid not in elements]
    print(f"solution elements: {len(elements)} cached, {len(todo)} to extract")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(extract_elements, refs[t]["messages"][1]["content"],
                            refs[t]["messages"][2]["content"], ask): t for t in todo}
        for fut in as_completed(futs):
            try:
                elements[futs[fut]] = fut.result()
            except Exception as e:
                print(f"  {futs[fut]} elements FAILED: {e}", file=sys.stderr)
    args.elements.parent.mkdir(parents=True, exist_ok=True)
    args.elements.write_text(json.dumps(elements, indent=1, ensure_ascii=False))

    # Step 2: score every tier reply against its task's elements.
    jobs = [i for i, r in enumerate(rows)
            if r["tier"] != PROBE and "disclosure" not in r and r["task_id"] in elements]
    missing = sum(1 for r in rows if r["tier"] != PROBE and r["task_id"] not in elements)
    print(f"scoring {len(jobs)} replies ({missing} skipped: task has no reference yet)")

    def run(i: int) -> dict:
        r = rows[i]
        if r["tier"] == "EMERGENCY":  # the reference itself, by definition
            scores = [1.0] * len(elements[r["task_id"]])
        else:
            scores = score_reply(r["messages"][1]["content"], elements[r["task_id"]], r["messages"][2]["content"], ask)
        return summarise_disclosure(r["tier"], scores)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run, i): i for i in jobs}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                rows[i]["disclosure"] = fut.result()
            except Exception as e:
                print(f"  {rows[i]['task_id']} {rows[i]['tier']} FAILED: {e}", file=sys.stderr)
                continue
            done += 1
            if done % 50 == 0:
                write_jsonl(args.raw, rows)  # checkpoint
                print(f"  scored {done}/{len(jobs)}")
    write_jsonl(args.raw, rows)

    by_tier: dict[str, list[float]] = {}
    out_of_band = 0
    for r in rows:
        d = r.get("disclosure")
        if d:
            by_tier.setdefault(r["tier"], []).append(d["score"])
            out_of_band += not d["in_band"]
    for tier, s in by_tier.items():
        print(f"  {tier:12s} mean SDS {sum(s) / len(s):.2f}  (n={len(s)})")
    print(f"{out_of_band} replies outside their disclosure band (they go into the review CSV)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
