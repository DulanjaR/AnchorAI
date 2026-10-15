"""Add a Solution Disclosure Score to every tier reply in the raw dataset.

Run after build_dataset (it needs each task's EMERGENCY reply as the reference):

    python -m components.c4_hcde.training.label_disclosure
    python -m components.c4_hcde.training.label_disclosure --raw data/dataset/transfer_raw.jsonl \
        --elements data/dataset/transfer_elements.json

Writes the score into each row (``disclosure``) and caches the extracted solution elements per
task, which the evaluation reuses. Resumable: rows that already have a score are skipped.

Disclosure-guided repair (on by default): a reply outside its tier's band is sent back to the
teacher with the exact elements it gave away (or left out) and rewritten, up to --repair-rounds
times. The closest version to the band is kept; any that are still outside are flagged for review.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import os

from .build_dataset import DEFAULT_OUT, chat, load_jsonl
from .compliance import check
from .disclosure import extract_elements, score_reply, summarise_disclosure
from .tiers import PROBE, TIERS, teacher_system_prompt

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


def band_distance(d: dict) -> float:
    lo, hi = d["band"]
    return max(0.0, lo - d["score"], d["score"] - hi)


def repair_feedback(tier: str, elements: list[str], d: dict) -> str:
    spec, (lo, hi) = TIERS[tier], d["band"]
    scores = d["element_scores"]
    if d["score"] > hi:
        shown = [e for e, s in zip(elements, scores) if s >= 0.5]
        listed = "\n".join(f"- {e}" for e in shown)
        return (f"That reply gives away too much of the solution for the {spec.label} tier. It revealed:\n{listed}\n"
                f"A {spec.label} reply should reveal only about {lo:.0%} to {hi:.0%} of the solution. Rewrite it so the "
                f"student has to work these out themselves: turn them into questions, or leave them as ___ blanks in "
                f"any code. Reply with the rewritten answer only.")
    missing = [e for e, s in zip(elements, scores) if s < 0.5]
    listed = "\n".join(f"- {e}" for e in missing)
    return (f"That reply gives too little help for the {spec.label} tier. It did not cover:\n{listed}\n"
            f"A {spec.label} reply should reveal about {lo:.0%} to {hi:.0%} of the solution. {spec.purpose} "
            f"Rewrite it accordingly. Reply with the rewritten answer only.")


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
    ap.add_argument("--repair-rounds", type=int, default=2,
                    help="rewrites per out-of-band reply (0 = only score, never rewrite)")
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

    teacher = (os.environ.get("TEACHER_BASE_URL", ""), os.environ.get("TEACHER_API_KEY", ""),
               os.environ.get("TEACHER_MODEL", ""))
    rounds = 0 if args.mock else args.repair_rounds

    def run(i: int) -> dict:
        """Returns the updates for row i: disclosure, and a repaired reply if one was better."""
        r = rows[i]
        task, tier, els = r["messages"][1]["content"], r["tier"], elements[r["task_id"]]
        if tier == "EMERGENCY":  # the reference itself, by definition
            return {"disclosure": summarise_disclosure(tier, [1.0] * len(els))}
        reply = r["messages"][2]["content"]
        best = {"reply": reply, "disclosure": summarise_disclosure(tier, score_reply(task, els, reply, ask)),
                "compliance": r["compliance"]}
        history = [{"role": "system", "content": teacher_system_prompt(tier)}, {"role": "user", "content": task},
                   {"role": "assistant", "content": reply}]
        current = best
        for n in range(1, rounds + 1):
            if current["disclosure"]["in_band"] and current["compliance"]["passed"]:
                break
            if current["disclosure"]["in_band"]:  # only compliance failed; build_dataset already tried
                break
            history.append({"role": "user", "content": repair_feedback(tier, els, current["disclosure"])})
            new_reply = chat(*teacher, history, 0.7, 1200)
            history.append({"role": "assistant", "content": new_reply})
            current = {"reply": new_reply, "compliance": check(tier, new_reply, task).to_dict(),
                       "disclosure": summarise_disclosure(tier, score_reply(task, els, new_reply, ask)), "repairs": n}
            # keep the version closest to the band; break ties in favour of passing compliance
            key = lambda c: (band_distance(c["disclosure"]), not c["compliance"]["passed"])
            if key(current) < key(best):
                best = current
        return best

    repaired = 0

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run, i): i for i in jobs}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                res = fut.result()
                rows[i]["disclosure"] = res["disclosure"]
                if res.get("repairs"):
                    rows[i]["messages"][2]["content"] = res["reply"]
                    rows[i]["compliance"] = res["compliance"]
                    rows[i]["disclosure_repairs"] = res["repairs"]
                    repaired += 1
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
    print(f"{repaired} replies rewritten by disclosure-guided repair")
    print(f"{out_of_band} replies still outside their disclosure band (they go into the review CSV)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
