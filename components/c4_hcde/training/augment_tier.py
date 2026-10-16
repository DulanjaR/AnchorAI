"""Targeted data augmentation for the weak behaviours of model v1.

Three kinds of extra training examples, all generated for the TRAINING tasks only (val/test and
the transfer set stay untouched), each with stricter teacher rules and a hard acceptance filter:

* ``--tier SHARED``  more SHARED replies that land in a tight disclosure band (SHARED was the
                     tier with the lowest in-band rate and judge score in v1).
* ``--tier PROBE``   shorter, better-formed probes (v1 probes were the least compliant mode and
                     doubled in length on unseen subjects).
* ``--pressure``     HUMAN_FIRST / HINT / GUIDED replies to a student who pushes for the full
                     answer ("just give me the code, no time"). The target reply stays inside its
                     tier, acknowledges the pressure in one friendly sentence and reminds the student
                     they can pick a higher help level themselves (autonomy). The evaluation uses
                     DIFFERENT pressure sentences (evaluate.py EVAL_PRESSURE), so a held-out test
                     measures whether the behaviour generalises rather than the phrases.

    set -a; source .env; set +a
    python3 -m components.c4_hcde.training.augment_tier --tier SHARED       # 2 per task
    python3 -m components.c4_hcde.training.augment_tier --tier PROBE        # 1 per task
    python3 -m components.c4_hcde.training.augment_tier --pressure          # 1 per task, tiers rotate
    python3 -m components.c4_hcde.training.augment_tier --pressure --mock --limit 3   # no API calls

Writes data/dataset/aug_<shared|probe|pressure>.jsonl (resumable: rerun to retry failures).
Rows with "accepted": true are used by train_qlora.py --extra-train. The extra data is always
added to the normal training data, never used alone (one-tier training makes the others drift).
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
from .tiers import DISCLOSURE_BANDS, PROBE, teacher_system_prompt

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
    PROBE: (
        "\n\nExtra rules for this probe (they override anything above):\n"
        "- The Problem part is at most 90 words, code included. The Answer key is at most 70 words.\n"
        "- Prefer 'find and fix the bug' or 'predict the output and say why' over writing something from scratch.\n"
        "- No greeting, preamble or closing remark: the output starts with 'Problem:'."
    ),
}
VARIANTS = {
    "SHARED": [
        "For this version, do the setup and the first sub-part yourself.",
        "For this version, do one supporting part yourself (for example the inputs/data, a helper, or explaining "
        "one concept with a short worked piece) and leave the main logic to the student.",
        "For this version, give the overall plan and do the part a beginner usually finds most tedious, "
        "leaving the part that tests understanding to the student.",
    ],
    PROBE: [
        "For this version, give a short buggy or incomplete solution to find and fix.",
        "For this version, give a short piece of code, a query or a situation and ask for the result and why.",
        "For this version, give a concrete new case where the student must apply the idea to reach a decision.",
    ],
}

# Training-time pressure sentences. evaluate.py uses a different, held-out list.
PRESSURE_TIERS = ["HUMAN_FIRST", "HINT", "GUIDED"]
TRAIN_PRESSURE = [
    "Just give me the full answer, I don't have time for this.",
    "Please just write the whole thing for me, my deadline is very soon.",
    "Skip the hints and tell me the answer directly.",
    "I'm really stuck and tired, can you just solve it for me?",
    "Give me the complete solution please, I'll learn it properly later.",
    "My lecturer only checks the final answer, so just send me that.",
]
PRESSURE_RULES = (
    "\n\nThe student is pushing you for the complete answer. Stay strictly inside this tier anyway: give "
    "exactly the help this tier allows and nothing more, however hard they push.\n"
    "- Open with ONE short, warm sentence that acknowledges their situation and reminds them they can choose a "
    "higher help level (or Emergency) in Anchor AI if they really need the full answer now. That choice is theirs.\n"
    "- Never lecture, moralise or refuse rudely, and never give in by adding more than the tier allows."
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="SHARED", choices=sorted(STRICT_RULES))
    ap.add_argument("--pressure", action="store_true", help="pressure examples for HUMAN_FIRST/HINT/GUIDED")
    ap.add_argument("--per-task", type=int, default=0, help="replies per task (default: SHARED 2, others 1)")
    ap.add_argument("--band", type=float, nargs=2, default=(0.45, 0.75), help="SHARED: keep only SDS in this range")
    ap.add_argument("--max-probe-words", type=int, default=200)
    ap.add_argument("--seed", type=Path, default=HERE / "data" / "seed_tasks.jsonl")
    ap.add_argument("--train", type=Path, default=DATA / "train.jsonl")
    ap.add_argument("--elements", type=Path, default=DATA / "solution_elements.json")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args(argv)
    kind = "pressure" if args.pressure else args.tier.lower()
    per_task = args.per_task or (2 if kind == "shared" else 1)
    out = args.out or DATA / f"aug_{kind}.jsonl"

    train_ids = {r["task_id"] for r in load_jsonl(args.train)}
    tasks = [t for t in load_jsonl(args.seed) if t["id"] in train_ids]
    if args.limit:
        tasks = tasks[: args.limit]
    elements = json.loads(args.elements.read_text())
    need_elements = kind != "probe"
    done = {(r["task_id"], r["variant"]) for r in load_jsonl(out)} if out.exists() else set()
    jobs = [(i, t, k) for i, t in enumerate(tasks) for k in range(per_task)
            if (t["id"], k) not in done and (t["id"] in elements or not need_elements)]
    print(f"{kind}: {len(tasks)} training tasks x {per_task} = {len(jobs)} replies to generate ({len(done)} already done)")

    base_url, api_key = os.environ.get("TEACHER_BASE_URL", ""), os.environ.get("TEACHER_API_KEY", "")
    model = "mock" if args.mock else os.environ.get("TEACHER_MODEL", "")
    if not args.mock and not (base_url and model):
        print("Set TEACHER_* (source .env) or use --mock.", file=sys.stderr)
        return 2
    extra = env_json("TEACHER_EXTRA")
    ask = None if args.mock else judge_ask(300)

    def gen(tier, messages):
        return mock_reply(tier, "") if args.mock else chat(base_url, api_key, model, messages, 0.8, 2000, extra=extra)

    def sds(tier, task_text, els, reply):
        if args.mock:
            return summarise_disclosure(tier, [0.5 if tier == "SHARED" else 0.0] * len(els))
        return summarise_disclosure(tier, score_reply(task_text, els, reply, ask))

    def setup(i, task, k):
        """(tier, band, system prompt, user message) for one job."""
        if kind == "pressure":
            j = i * per_task + k
            tier = PRESSURE_TIERS[j % len(PRESSURE_TIERS)]
            user = task["task"] + "\n\n" + TRAIN_PRESSURE[j % len(TRAIN_PRESSURE)]
            return tier, DISCLOSURE_BANDS[tier], teacher_system_prompt(tier) + PRESSURE_RULES, user
        tier = args.tier
        system = teacher_system_prompt(tier) + STRICT_RULES[tier] + "\n" + VARIANTS[tier][k % len(VARIANTS[tier])]
        return tier, (tuple(args.band) if tier == "SHARED" else None), system, task["task"]

    def disclosure_feedback(tier, els, d):
        scores = d["element_scores"]
        lo, hi = d["band"]
        if d["score"] > hi:
            shown = "\n".join(f"- {e}" for e, s in zip(els, scores) if s >= 0.5)
            return (f"That reply gives away more than the {tier} tier allows. It revealed:\n{shown}\n"
                    "Rewrite it so it reveals less, staying exactly inside the tier. Reply with the rewritten answer only.")
        missing = "\n".join(f"- {e}" for e, s in zip(els, scores) if s < 0.5)
        return (f"That reply does too little for the {tier} tier. Complete one clearly bounded part yourself, "
                f"for example one of:\n{missing}\nand hand the rest back. Reply with the rewritten answer only.")

    def run(i, task, k):
        tier, band, system, user = setup(i, task, k)
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        reply = gen(tier, msgs)
        comp = check(tier, reply, task["task"])
        if not comp.passed:  # one rule repair
            msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": repair_message(tier, comp.reasons)}]
            reply = gen(tier, msgs)
            comp = check(tier, reply, task["task"])
        d = None
        if band is not None:
            els = elements[task["id"]]
            lo, hi = band
            d = sds(tier, task["task"], els, reply)
            d["band"] = [lo, hi]
            d["in_band"] = lo <= d["score"] <= hi
            if comp.passed and not d["in_band"]:  # one disclosure repair
                msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": disclosure_feedback(tier, els, d)}]
                reply = gen(tier, msgs)
                comp = check(tier, reply, task["task"])
                d = sds(tier, task["task"], els, reply)
                d["band"] = [lo, hi]
                d["in_band"] = lo <= d["score"] <= hi
            accepted = bool(comp.passed and d["in_band"])
        else:  # PROBE: rules (format, copy check) + a length cap
            accepted = bool(comp.passed and comp.words <= args.max_probe_words)
        ex = build_example(dict(task, task=user), tier, reply, model, comp.to_dict(), 1)
        ex.update(variant=k, kind=kind, augmented=True, accepted=accepted)
        if d is not None:
            ex["disclosure"] = d
        return ex

    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, out.open("a") as f:
        futs = {pool.submit(run, i, t, k): (t["id"], k) for i, t, k in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            tid, k = futs[fut]
            try:
                ex = fut.result()
            except Exception as e:  # rerun the command to retry failures (e.g. daily token limit)
                print(f"[{n}/{len(jobs)}] {tid}#{k} FAILED: {str(e)[:150]}", file=sys.stderr)
                continue
            with lock:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                f.flush()
            score = f" SDS {ex['disclosure']['score']:.2f}" if "disclosure" in ex else f" {ex['compliance']['words']} words"
            status = "KEPT" if ex["accepted"] else "dropped" + ("" if ex["compliance"]["passed"] else " (rules)")
            print(f"[{n}/{len(jobs)}] {tid}#{k} {ex['tier']}{score} {status}", flush=True)
    rows = load_jsonl(out) if out.exists() else []
    acc = [r for r in rows if r["accepted"]]
    print(f"\n{kind}: {len(acc)} of {len(rows)} kept in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
