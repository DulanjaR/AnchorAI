"""Evaluate tier calibration on the held-out test tasks.

Three conditions, so the result separates what fine-tuning adds from what prompting gives:

* ``base_tag``    base model, short control tag only   (lower bound)
* ``base_rubric`` base model, full rubric in the prompt (strong prompted baseline)
* ``tuned_tag``   base model + QLoRA adapter, short tag (the contribution)

Metrics per condition and tier: tier-compliance rate (compliance.py), mean words and code
lines, and with --judge the Solution Disclosure Score (mean, share inside the tier's band, and
whether it rises from HUMAN_FIRST to EMERGENCY) plus 1-5 judge scores for tier adherence and
correctness. PROBE rows are scored for format only.

    python -m components.c4_hcde.training.evaluate --base-model Qwen/Qwen2.5-7B-Instruct \
        --adapter runs/hcde-qwen7b/adapter --out runs/hcde-qwen7b/eval

    # add disclosure + judge scores (TEACHER_* env vars; JUDGE_MODEL to use a different model)
    python -m components.c4_hcde.training.evaluate ... --judge

    # transfer test on the 20 non-IT tasks (never trained on)
    python -m components.c4_hcde.training.evaluate ... --test data/dataset/transfer_raw.jsonl \
        --elements data/dataset/transfer_elements.json --out runs/eval-transfer --judge
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .compliance import check
from .disclosure import score_reply, summarise_disclosure
from .train_qlora import _new_transformers
from .tiers import MODES, PROBE, TIER_NAMES, TIERS, control_system_prompt, rubric_system_prompt

HERE = Path(__file__).parent
CONDITIONS = ["base_tag", "base_rubric", "tuned_tag"]

JUDGE_PROMPT = """You are grading a study assistant's reply to an IT student.
The assistant was required to follow this assistance tier:

{rubric}

Student request:
{task}

Assistant reply:
{reply}

Score two things from 1 (poor) to 5 (excellent):
- tier: how well the reply gives exactly the amount of help the tier allows (too much help is as bad as too little)
- correct: technical correctness of whatever the reply does say
Answer with JSON only, e.g. {{"tier": 4, "correct": 5, "why": "one short sentence"}}"""


def load_rows(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def system_prompt(condition: str, tier: str) -> str:
    return rubric_system_prompt(tier) if condition == "base_rubric" else control_system_prompt(tier)


def generate_all(model, tokenizer, prompts: list[list[dict]], max_new_tokens: int, batch_size: int) -> list[str]:
    import torch

    tokenizer.padding_side = "left"
    outs: list[str] = []
    for i in range(0, len(prompts), batch_size):
        batch = [tokenizer.apply_chat_template(p, add_generation_prompt=True, tokenize=False) for p in prompts[i:i + batch_size]]
        enc = tokenizer(batch, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                 pad_token_id=tokenizer.pad_token_id)
        for row in gen[:, enc["input_ids"].shape[1]:]:
            outs.append(tokenizer.decode(row, skip_special_tokens=True).strip())
        print(f"  generated {min(i + batch_size, len(prompts))}/{len(prompts)}", flush=True)
    return outs


def judge(rows: list[dict], elements: dict[str, list[str]], checkpoint=None) -> None:
    """Score replies with the LLM judge. Resumable: rows that already have a judge result and a
    disclosure score (without errors) are skipped, so a rerun only does what is missing."""
    from .build_dataset import chat

    base_url, key, model = (os.environ.get(k, "") for k in ("TEACHER_BASE_URL", "TEACHER_API_KEY", "TEACHER_MODEL"))
    judge_model = os.environ.get("JUDGE_MODEL") or model
    for i, r in enumerate(rows, 1):
        if r["tier"] == PROBE:
            continue
        done_j = "judge" in r and "error" not in r["judge"]
        done_d = r["task_id"] not in elements or ("disclosure" in r and "error" not in r["disclosure"])
        if done_j and done_d:
            continue
        prompt = JUDGE_PROMPT.format(rubric=rubric_system_prompt(r["tier"]), task=r["task"], reply=r["reply"])
        try:
            from .disclosure import judge_ask
            text = judge_ask(200)(prompt)
            m = re.search(r"\{.*\}", text, re.DOTALL)
            r["judge"] = json.loads(m.group(0)) if m else {"error": text[:200]}
        except Exception as e:  # a failed grade should not lose the generations
            r["judge"] = {"error": str(e)[:200]}
        if r["task_id"] in elements:
            try:
                r["disclosure"] = summarise_disclosure(r["tier"], score_reply(r["task"], elements[r["task_id"]], r["reply"]))
            except Exception as e:
                r["disclosure"] = {"error": str(e)[:200]}
        if checkpoint:
            checkpoint()
        if i % 10 == 0:
            print(f"  judged {i}/{len(rows)}", flush=True)


def summarise(rows: list[dict]) -> dict:
    agg: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        agg[(r["condition"], r["tier"])]["pass"].append(r["compliance"]["passed"])
        agg[(r["condition"], r["tier"])]["words"].append(r["compliance"]["words"])
        agg[(r["condition"], r["tier"])]["code"].append(r["compliance"]["code_lines"])
        j = r.get("judge") or {}
        for k in ("tier", "correct"):
            if isinstance(j.get(k), (int, float)):
                agg[(r["condition"], r["tier"])]["judge_" + k].append(j[k])
        d = r.get("disclosure") or {}
        if "score" in d:
            agg[(r["condition"], r["tier"])]["sds"].append(d["score"])
            agg[(r["condition"], r["tier"])]["sds_in_band"].append(d["in_band"])
    out: dict = {}
    for cond in CONDITIONS:
        per_tier, all_pass = {}, []
        for tier in MODES:
            a = agg.get((cond, tier))
            if not a:
                continue
            all_pass += a["pass"]
            per_tier[tier] = {
                "n": len(a["pass"]), "compliance": round(mean(a["pass"]), 3),
                "mean_words": round(mean(a["words"]), 1), "mean_code_lines": round(mean(a["code"]), 1),
                **{k: round(mean(v), 2) for k, v in a.items() if (k.startswith("judge_") or k.startswith("sds")) and v},
            }
        if per_tier:
            words = [per_tier[t]["mean_words"] for t in TIER_NAMES if t in per_tier]
            sds = [per_tier[t]["sds"] for t in TIER_NAMES if "sds" in per_tier.get(t, {})]
            out[cond] = {"overall_compliance": round(mean(all_pass), 3),
                         "words_increase_with_tier": all(a <= b for a, b in zip(words, words[1:])),
                         # non-decreasing across tiers AND a real spread (>= 0.5) from the lowest to the highest tier
                         "sds_increases_with_tier": (all(a <= b for a, b in zip(sds, sds[1:])) and sds[-1] - sds[0] >= 0.5)
                         if len(sds) > 1 else None,
                         "tiers": per_tier}
    return out


def to_markdown(summary: dict) -> str:
    lines = ["| Condition | Tier | n | Compliance | SDS | SDS in band | Mean words | Code lines | Judge tier | Judge correct |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for cond, s in summary.items():
        for tier, t in s["tiers"].items():
            label = TIERS[tier].label if tier in TIERS else "Probe"
            band = f"{t['sds_in_band']:.0%}" if "sds_in_band" in t else ""
            lines.append(f"| {cond} | {label} | {t['n']} | {t['compliance']:.0%} | {t.get('sds', '')} | {band} | "
                         f"{t['mean_words']} | {t['mean_code_lines']} | {t.get('judge_tier', '')} | {t.get('judge_correct', '')} |")
        rising = {True: "yes", False: "NO", None: "-"}[s["sds_increases_with_tier"]]
        lines.append(f"| **{cond}** | **all** | | **{s['overall_compliance']:.0%}** | rises: {rising} | | | | | |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--adapter", type=Path, help="adapter dir; omit to run only the base conditions")
    ap.add_argument("--test", type=Path, default=HERE / "data" / "dataset" / "test.jsonl")
    ap.add_argument("--elements", type=Path, default=HERE / "data" / "dataset" / "solution_elements.json",
                    help="solution elements from label_disclosure, for the disclosure score")
    ap.add_argument("--out", type=Path, default=Path("runs/eval"))
    ap.add_argument("--conditions", nargs="+", default=CONDITIONS, choices=CONDITIONS)
    ap.add_argument("--limit", type=int, default=0, help="first N test examples only")
    ap.add_argument("--max-new-tokens", type=int, default=700)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--no-4bit", action="store_true")
    ap.add_argument("--judge", action="store_true", help="also score with an LLM judge (TEACHER_* env vars)")
    ap.add_argument("--from-generations", type=Path,
                    help="skip generation: load a saved generations.jsonl and only judge + summarise (no GPU needed)")
    ap.add_argument("--judge-conditions", nargs="+", choices=CONDITIONS,
                    help="judge only these conditions (saves API calls)")
    args = ap.parse_args(argv)

    if args.from_generations:
        rows = load_rows(args.from_generations)
        print(f"loaded {len(rows)} saved replies from {args.from_generations}")
        return finish(args, rows)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    test = load_rows(args.test)
    if args.limit:
        test = test[: args.limit]
    conditions = [c for c in args.conditions if c != "tuned_tag" or args.adapter]

    cuda = torch.cuda.is_available()
    dtype = torch.bfloat16 if cuda and torch.cuda.is_bf16_supported() else torch.float16
    kwargs: dict = {}
    if cuda and not args.no_4bit:
        from transformers import BitsAndBytesConfig
        kwargs = {"quantization_config": BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype), "device_map": {"": 0},
                  ("dtype" if _new_transformers() else "torch_dtype"): dtype}
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.chat_template is None:
        from .train_qlora import FALLBACK_TEMPLATE
        tokenizer.chat_template = FALLBACK_TEMPLATE
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.base_model, **kwargs)
    model.eval()

    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(args.adapter))
        model.eval()

    rows: list[dict] = []
    for cond in conditions:
        print(f"{cond}: {len(test)} prompts")
        prompts = [[{"role": "system", "content": system_prompt(cond, r["tier"])},
                    {"role": "user", "content": r["messages"][1]["content"]}] for r in test]
        if args.adapter and cond != "tuned_tag":
            with model.disable_adapter():
                replies = generate_all(model, tokenizer, prompts, args.max_new_tokens, args.batch_size)
        else:
            replies = generate_all(model, tokenizer, prompts, args.max_new_tokens, args.batch_size)
        for r, reply in zip(test, replies):
            rows.append({"condition": cond, "task_id": r["task_id"], "module": r["module"],
                         "difficulty": r["difficulty"], "tier": r["tier"], "task": r["messages"][1]["content"],
                         "reply": reply, "reference": r["messages"][2]["content"],
                         "compliance": check(r["tier"], reply, r["messages"][1]["content"]).to_dict()})

    return finish(args, rows)


def save_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def finish(args, rows: list[dict]) -> int:
    out_rows = args.out / "generations.jsonl"
    save_rows(out_rows, rows)  # save the replies before judging, so a judge failure never loses them
    if args.judge:
        print("judging...")
        elements = json.loads(args.elements.read_text()) if args.elements.exists() else {}
        if not elements:
            print(f"  no solution elements at {args.elements}; disclosure scores skipped")
        todo = [r for r in rows if not args.judge_conditions or r["condition"] in args.judge_conditions]
        judge(todo, elements, checkpoint=lambda: save_rows(out_rows, rows))
    save_rows(out_rows, rows)
    summary = summarise(rows)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    table = to_markdown(summary)
    (args.out / "summary.md").write_text(table + "\n")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
