"""Tier-calibrated data for the public-benchmark tasks (run after public_tasks).

    set -a; source .env; set +a
    python -m components.c4_hcde.training.public_data test     # held-out public test set (~60 API calls)
    python -m components.c4_hcde.training.public_data train    # training data, all six modes (~1,500 calls)
    python -m components.c4_hcde.training.public_data gate     # only the acceptance step (no API calls)
    python -m components.c4_hcde.training.public_data verify   # correctness + leakage check of accepted replies
    python -m components.c4_hcde.training.public_data train --mock   # offline smoke test

``test``  writes the teacher's full EMERGENCY answer for each held-out task (the teacher privately
          sees the benchmark solution), extracts its solution elements, and writes
          data/dataset/public_test.jsonl in the same shape as test.jsonl (one row per mode).
``train`` generates all six modes for the training tasks (build_dataset), scores and repairs them
          against their disclosure bands (label_disclosure), then runs ``gate``.
``gate``  accepts a reply only if it passes the tier rules AND (for the five tiers) lands inside its
          disclosure band. The v1 data was reviewed by hand; this automatic gate replaces manual review
          for the public data, plus a random sample in public_review.csv for a human spot-check.

Everything is resumable: rerun the same command after a rate-limit stop.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from . import build_dataset, label_disclosure
from .tiers import MODES, PROBE, control_system_prompt

HERE = Path(__file__).parent
DATA = HERE / "data"
DS = DATA / "dataset"
ELEMENTS = DS / "public_elements.json"


def load(path: Path) -> list[dict]:
    return build_dataset.load_jsonl(path)


def dump(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def cmd_test(args) -> int:
    raw = DS / "public_test_raw.jsonl"
    common = ["--mock"] if args.mock else []
    build_dataset.main(["--seed", str(DATA / "public_seed_test.jsonl"), "--out", str(raw), "--tiers", "EMERGENCY",
                        "--workers", str(args.workers)] + common)
    label_disclosure.main(["--raw", str(raw), "--elements", str(ELEMENTS), "--workers", str(args.workers)] + common)
    elements = json.loads(ELEMENTS.read_text()) if ELEMENTS.exists() else {}
    seeds = {t["id"]: t for t in load(DATA / "public_seed_test.jsonl")}
    refs = {r["task_id"]: r for r in load(raw)}
    rows, missing = [], []
    for tid, t in seeds.items():
        if tid not in refs or tid not in elements:
            missing.append(tid)
            continue
        ref = refs[tid]["messages"][2]["content"]
        for mode in MODES:
            rows.append({"task_id": tid, "module": t["module"], "skill": t["skill"], "difficulty": t["difficulty"],
                         "tier": mode, "source": t["source"], "domain": t["domain"],
                         "messages": [{"role": "system", "content": control_system_prompt(mode)},
                                      {"role": "user", "content": t["task"]},
                                      {"role": "assistant", "content": ref}]})
    dump(DS / "public_test.jsonl", rows)
    print(f"public_test.jsonl: {len(rows) // len(MODES)} tasks x {len(MODES)} modes"
          + (f"; {len(missing)} tasks still missing (rerun): {missing}" if missing else ""))
    return 0


def cmd_gate(args) -> int:
    raw = load(DS / "public_raw.jsonl")
    out = []
    for r in raw:
        comp_ok = r["compliance"]["passed"]
        d = r.get("disclosure")
        if r["tier"] == PROBE:
            accepted = comp_ok
        else:
            accepted = bool(comp_ok and d and d.get("in_band"))
        out.append(dict(r, accepted=accepted, augmented=True, kind="public"))
    dump(DS / "public_train.jsonl", out)
    by: dict[str, list[bool]] = {}
    for r in out:
        by.setdefault(r["tier"], []).append(r["accepted"])
    for tier in MODES:
        if tier in by:
            print(f"  {tier:12s} {sum(by[tier])}/{len(by[tier])} accepted")
    acc = [r for r in out if r["accepted"]]
    print(f"public_train.jsonl: {len(acc)} of {len(out)} accepted")
    sample = random.Random(1).sample(acc, min(args.review, len(acc)))
    with (DS / "public_review.csv").open("w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel reads it as UTF-8
        w = csv.writer(f)
        w.writerow(["task_id", "tier", "sds", "task", "reply", "YOUR verdict (ok / bad)"])
        for r in sample:
            w.writerow([r["task_id"], r["tier"], (r.get("disclosure") or {}).get("score", ""),
                        r["messages"][1]["content"], r["messages"][2]["content"], ""])
    print(f"spot-check sample: {DS / 'public_review.csv'} ({len(sample)} replies)")
    return 0


VERIFY_PROMPT = """You are checking one reply that a study assistant wrote for a student, before it is used as a
training example. Be strict: a wrong or leaky example teaches the assistant to be wrong or leaky.

The assistant had to follow this assistance tier:
{rubric}

Student task:
{task}

Verified correct solution from the benchmark (the student never sees this):
{reference}

Assistant reply:
{reply}

Check two things:
- correct: everything the reply states, shows or implies is technically correct (code would run and do what it
  claims; numbers and formulas are right; for a probe, the problem is solvable and its answer key is right and
  consistent). A reply that says nothing technical (e.g. only encouragement) counts as correct.
- within_tier: the reply gives no more help than the tier allows, including in code comments, examples or
  "e.g." hints (e.g. a GUIDED blank whose comment gives the answer, a HUMAN_FIRST reply that names the method,
  a SHARED reply that leaves the student only a trivial step).
Answer with JSON only: {{"correct": true, "within_tier": true, "why": "one short sentence"}}"""


def cmd_verify(args) -> int:
    """Second filter for accepted public replies: correctness + tier leakage, judged against the benchmark's
    own solution (the human spot-check found wrong code and answers hidden in comments that the SDS gate
    alone lets through)."""
    import re
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .disclosure import judge_ask
    from .tiers import rubric_system_prompt

    path = DS / "public_train.jsonl"
    rows = load(path)
    seeds = {t["id"]: t for t in load(DATA / "public_seed_train.jsonl")}
    ask = judge_ask(300)
    todo = [i for i, r in enumerate(rows) if r["accepted"] and "verify" not in r]
    print(f"verifying {len(todo)} accepted replies")

    def run(i):
        r = rows[i]
        prompt = VERIFY_PROMPT.format(rubric=rubric_system_prompt(r["tier"]), task=r["messages"][1]["content"],
                                      reference=seeds[r["task_id"]]["reference"], reply=r["messages"][2]["content"])
        text = ask(prompt)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        v = json.loads(m.group(0), strict=False)
        return {"correct": bool(v.get("correct")), "within_tier": bool(v.get("within_tier")), "why": str(v.get("why", ""))[:200]}

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run, i): i for i in todo}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                rows[i]["verify"] = fut.result()
            except Exception as e:  # unverified rows are rejected below, rerun to retry
                print(f"  {rows[i]['task_id']} {rows[i]['tier']} FAILED: {str(e)[:120]}")
                continue
            done += 1
            if done % 50 == 0:
                dump(path, rows)
                print(f"  verified {done}/{len(todo)}")
    for r in rows:
        if r["accepted"]:
            v = r.get("verify")
            r["accepted"] = bool(v and v["correct"] and v["within_tier"])
            if not r["accepted"]:
                r["rejected_by"] = "verify" if v else "verify (not run)"
    dump(path, rows)
    by: dict[str, list[int]] = {}
    for r in rows:
        if "verify" in r:
            by.setdefault(r["tier"], []).append(r["accepted"])
    for tier in MODES:
        if tier in by:
            print(f"  {tier:12s} {sum(by[tier])}/{len(by[tier])} passed verification")
    print(f"public_train.jsonl: {sum(r['accepted'] for r in rows)} of {len(rows)} accepted after verification")
    return 0


def cmd_train(args) -> int:
    raw = DS / "public_raw.jsonl"
    common = ["--mock"] if args.mock else []
    build_dataset.main(["--seed", str(DATA / "public_seed_train.jsonl"), "--out", str(raw),
                        "--workers", str(args.workers)] + common)
    label_disclosure.main(["--raw", str(raw), "--elements", str(ELEMENTS), "--workers", str(args.workers),
                           "--repair-rounds", str(args.repair_rounds)] + common)
    return cmd_gate(args)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["test", "train", "gate", "verify"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--repair-rounds", type=int, default=1)
    ap.add_argument("--review", type=int, default=20, help="replies in the spot-check sample")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args(argv)
    return {"test": cmd_test, "train": cmd_train, "gate": cmd_gate, "verify": cmd_verify}[args.step](args)


if __name__ == "__main__":
    raise SystemExit(main())
