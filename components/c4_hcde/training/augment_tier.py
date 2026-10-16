"""Targeted data augmentation for one weak tier (default SHARED).

Generates extra examples of a tier for the TRAINING tasks only (val/test stay untouched), with
stricter rules than the original teacher prompt, then keeps only replies that pass the rule check
AND land in a tight disclosure band. The result is added to the normal training data (never used
alone: training on one tier only makes the model drift on the others).

    set -a; source .env; set +a
    python3 -m components.c4_hcde.training.augment_tier                    # SHARED, 2 per task
    python3 -m components.c4_hcde.training.augment_tier --per-task 1       # cheaper
    python3 -m components.c4_hcde.training.augment_tier --mock --limit 3   # no API calls

Writes data/dataset/aug_<tier>.jsonl (resumable). Rows with "accepted": true are used by
train_qlora.py --extra-train.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .build_dataset import build_example, chat, env_json, load_jsonl, mock_reply, repair_message
from .compliance import check
from .disclosure import judge_ask, score_reply, summarise_disclosure
from .tiers import TIERS, teacher_system_prompt

HERE = Path(__file__).parent
DATA = HERE / "data" / "dataset"

STRICT_RULES = {
    "SHARED": (
        "\n\nExtra rules for this reply (they override anything above):\n"
        "- Do ONE clearly bounded part yourself, roughly a third to a half of the work, and show that part complete.\n"
        "- Hand back a NAMED remaining part that contains the key reasoning of the task. The student's part must "
        "never be a single trivial step such as a final return statement, one division or filling one value.\n"
        "- Never include the complete working answer anywhere: not in comments, examples, tables or a 'for reference'.\n"
        "- End with ONE question that asks the student to make a real decision or check: a choice between two "
        "approaches, an edge case, or an interpretation of the result."
    ),
}
VARIANTS = [
    "For this version, do the setup and the first sub-part yourself.",
    "For this version, do one supporting part yourself (for example the inputs/data, a helper, or explaining "
    "one concept with a short worked piece) and leave the main logic to the student.",
    "For this version, give the overall plan and do the part a beginner usually finds most tedious, "
    "leaving the part that tests understanding to the student.",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="SHARED", choices=sorted(STRICT_RULES))
    ap.add_argument("--per-task", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--band", type=float, nargs=2, default=(0.45, 0.75), help="keep only SDS inside this range")
    ap.add_argument("--seed", type=Path, default=HERE / "data" / "seed_tasks.jsonl")
    ap.add_argument("--train", type=Path, default=DATA / "train.jsonl")
    ap.add_argument("--elements", type=Path, default=DATA / "solution_elements.json")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args(argv)
    out = args.out or DATA / f"aug_{args.tier.lower()}.jsonl"
    lo, hi = args.band

    train_ids = {r["task_id"] for r in load_jsonl(args.train)}
    tasks = [t for t in load_jsonl(args.seed) if t["id"] in train_ids]
    if args.limit:
        tasks = tasks[: args.limit]
    elements = json.loads(args.elements.read_text())
    done = {(r["task_id"], r["variant"]) for r in load_jsonl(out)}
    jobs = [(t, k) for t in tasks for k in range(args.per_task) if (t["id"], k) not in done and t["id"] in elements]
    print(f"{len(tasks)} training tasks x {args.per_task} = {len(jobs)} {args.tier} replies to generate "
          f"({len(done)} already done); keep SDS in [{lo}, {hi}]")

    base_url, api_key = os.environ.get("TEACHER_BASE_URL", ""), os.environ.get("TEACHER_API_KEY", "")
    model = "mock" if args.mock else os.environ.get("TEACHER_MODEL", "")
    if not args.mock and not (base_url and model):
        print("Set TEACHER_* (source .env) or use --mock.", file=sys.stderr)
        return 2
    extra = env_json("TEACHER_EXTRA")
    ask = None if args.mock else judge_ask(300)
    tier = args.tier

    def gen(messages):
        return mock_reply(tier, "") if args.mock else chat(base_url, api_key, model, messages, 0.8, 2000, extra=extra)

    def sds(task_text, els, reply):
        if args.mock:
            return summarise_disclosure(tier, [0.5] * len(els))
        return summarise_disclosure(tier, score_reply(task_text, els, reply, ask))

    def run(task, k):
        els = elements[task["id"]]
        system = teacher_system_prompt(tier) + STRICT_RULES[tier] + "\n" + VARIANTS[k % len(VARIANTS)]
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": task["task"]}]
        reply = gen(msgs)
        comp = check(tier, reply, task["task"])
        if not comp.passed:  # one rule repair
            msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": repair_message(tier, comp.reasons)}]
            reply = gen(msgs)
            comp = check(tier, reply, task["task"])
        d = sds(task["task"], els, reply)
        if comp.passed and not lo <= d["score"] <= hi:  # one disclosure repair against the tight band
            scores = d["element_scores"]
            if d["score"] > hi:
                shown = "\n".join(f"- {e}" for e, s in zip(els, scores) if s >= 0.5)
                fb = (f"That reply does too much of the work for a shared reply. It revealed:\n{shown}\n"
                      "Keep only one bounded part done by you and hand the rest back as a named part for the student, "
                      "with no complete answer anywhere. Reply with the rewritten answer only.")
            else:
                missing = "\n".join(f"- {e}" for e, s in zip(els, scores) if s < 0.5)
                fb = (f"That reply does too little for a shared reply. Complete one clearly bounded part yourself "
                      f"(about a third to half of the work), for example one of:\n{missing}\n"
                      "and hand the rest back. Reply with the rewritten answer only.")
            msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": fb}]
            reply = gen(msgs)
            comp = check(tier, reply, task["task"])
            d = sds(task["task"], els, reply)
        ex = build_example(task, tier, reply, model, comp.to_dict(), 1)
        ex.update(variant=k, disclosure=d, augmented=True,
                  accepted=bool(comp.passed and lo <= d["score"] <= hi))
        return ex

    lock, kept = threading.Lock(), 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool, out.open("a") as f:
        futs = {pool.submit(run, t, k): (t["id"], k) for t, k in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            tid, k = futs[fut]
            try:
                ex = fut.result()
            except Exception as e:  # rerun the command to retry failures (e.g. daily token limit)
                print(f"[{i}/{len(jobs)}] {tid}#{k} FAILED: {str(e)[:150]}", file=sys.stderr)
                continue
            with lock:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                f.flush()
            kept += ex["accepted"]
            print(f"[{i}/{len(jobs)}] {tid}#{k} SDS {ex['disclosure']['score']:.2f} "
                  f"{'KEPT' if ex['accepted'] else 'dropped' + ('' if ex['compliance']['passed'] else ' (rules)')}")
    rows = load_jsonl(out)
    acc = [r for r in rows if r["accepted"]]
    if acc:
        mean = sum(r["disclosure"]["score"] for r in acc) / len(acc)
        print(f"\n{len(acc)} of {len(rows)} kept in {out.name} (mean SDS {mean:.2f}). "
              f"Train with: train_qlora ... --extra-train {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
