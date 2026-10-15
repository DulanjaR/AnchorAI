"""Generate the tier-calibrated training set with a teacher model.

For every seed task x tier, a large teacher model writes the reply using the full rubric.
The saved training example pairs that reply with the SHORT control prompt, so the student
model has to learn tier behaviour from the tag alone.

Works with any OpenAI-compatible chat endpoint (OpenRouter, Groq, Together, a local Ollama
or vLLM server, ...). Configure with environment variables:

    TEACHER_BASE_URL   e.g. https://openrouter.ai/api/v1  or  http://localhost:11434/v1
    TEACHER_API_KEY    API key (any string for local servers)
    TEACHER_MODEL      e.g. qwen/qwen-2.5-72b-instruct

Run from the repo root:

    python -m components.c4_hcde.training.build_dataset
    python -m components.c4_hcde.training.build_dataset --mock --limit 4   # offline smoke test

The run is resumable: finished (task, tier) pairs in the output file are skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .compliance import check
from .tiers import MODES, control_system_prompt, teacher_system_prompt

HERE = Path(__file__).parent
DEFAULT_SEED = HERE / "data" / "seed_tasks.jsonl"
DEFAULT_OUT = HERE / "data" / "dataset" / "raw.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def chat(base_url: str, api_key: str, model: str, messages: list[dict], temperature: float,
         max_tokens: int, retries: int = 5) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.load(resp)
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            # 429 / 5xx are retried with backoff; other errors are real problems.
            if e.code not in (408, 429, 500, 502, 503, 504) or attempt == retries - 1:
                raise RuntimeError(f"teacher HTTP {e.code}: {e.read()[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1:
                raise RuntimeError(f"teacher unreachable: {e}") from e
        time.sleep(min(60, 2 ** attempt + random.random()))
    raise RuntimeError("unreachable")


def mock_reply(tier: str, task: str) -> str:
    """Deterministic compliant-looking replies for offline tests."""
    return {
        "HUMAN_FIRST": "You have handled problems like this before, so give it a go first. What is your first attempt?",
        "HINT": "Think about which value you need to keep track of as you go through the input.",
        "GUIDED": "1. What are the inputs?\n2. What should the output be?\n```python\ndef solve(x):\n    # TODO\n    ...\n```",
        "SHARED": "Here is the plan and the first half done for you. Now it is your turn: how would you handle the edge cases?",
        "EMERGENCY": "Here is the full solution with a short explanation of each step. " * 4,
        "PROBE": "Problem:\nWrite a function that returns the smallest of four numbers without using min().\n\n"
                 "Answer key:\nCompare pairwise and keep the running smallest; must handle equal values.",
    }[tier]


def repair_message(tier: str, reasons: list[str]) -> str:
    return (f"That reply breaks the {tier} rules: {'; '.join(reasons)}. Rewrite it so it follows the "
            f"{tier} rules exactly, using the example's amount of help. Reply with the rewritten answer only.")


def build_example(task: dict, tier: str, reply: str, teacher: str, compliance: dict, attempts: int) -> dict:
    return {
        "task_id": task["id"],
        "module": task["module"],
        "skill": task["skill"],
        "difficulty": task["difficulty"],
        "tier": tier,
        "teacher_model": teacher,
        "attempts": attempts,
        "compliance": compliance,
        "messages": [
            {"role": "system", "content": control_system_prompt(tier)},
            {"role": "user", "content": task["task"]},
            {"role": "assistant", "content": reply},
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tiers", nargs="+", default=MODES, choices=MODES,
                    help="tiers to generate; PROBE = the unaided check-problem behaviour")
    ap.add_argument("--limit", type=int, default=0, help="only the first N tasks (0 = all)")
    ap.add_argument("--workers", type=int, default=4, help="parallel requests; lower it if you hit rate limits")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--mock", action="store_true", help="no API calls; write canned replies")
    args = ap.parse_args(argv)

    base_url = os.environ.get("TEACHER_BASE_URL", "")
    api_key = os.environ.get("TEACHER_API_KEY", "")
    model = "mock" if args.mock else os.environ.get("TEACHER_MODEL", "")
    if not args.mock and not (base_url and model):
        print("Set TEACHER_BASE_URL, TEACHER_API_KEY and TEACHER_MODEL (or use --mock).", file=sys.stderr)
        return 2

    tasks = load_jsonl(args.seed)
    if args.limit:
        tasks = tasks[: args.limit]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = {(r["task_id"], r["tier"]) for r in load_jsonl(args.out)}
    jobs = [(t, tier) for t in tasks for tier in args.tiers if (t["id"], tier) not in done]
    print(f"{len(tasks)} tasks x {len(args.tiers)} tiers: {len(done)} done, {len(jobs)} to generate")

    lock = threading.Lock()

    def run(task: dict, tier: str) -> dict:
        messages = [{"role": "system", "content": teacher_system_prompt(tier)},
                    {"role": "user", "content": task["task"]}]
        reply, result, attempts = "", None, 0
        # If the first reply breaks the tier, send it back with the exact reasons and ask for a
        # rewrite. The second reply is kept either way and flagged, so the review step can decide.
        for attempts in (1, 2):
            reply = mock_reply(tier, task["task"]) if args.mock else chat(
                base_url, api_key, model, messages, args.temperature, args.max_tokens)
            result = check(tier, reply, task["task"])
            if result.passed:
                break
            messages = messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": repair_message(tier, result.reasons)},
            ]
        return build_example(task, tier, reply, model, result.to_dict(), attempts)

    failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool, args.out.open("a") as out:
        futures = {pool.submit(run, t, tier): (t["id"], tier) for t, tier in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            key = futures[fut]
            try:
                ex = fut.result()
            except Exception as e:  # keep going; a rerun picks up what failed
                failed += 1
                print(f"[{i}/{len(jobs)}] {key} FAILED: {e}", file=sys.stderr)
                continue
            with lock:
                out.write(json.dumps(ex, ensure_ascii=False) + "\n")
                out.flush()
            flag = "ok" if ex["compliance"]["passed"] else "FLAGGED " + "; ".join(ex["compliance"]["reasons"])
            print(f"[{i}/{len(jobs)}] {key[0]} {key[1]}: {flag}")

    rows = load_jsonl(args.out)
    flagged = sum(not r["compliance"]["passed"] for r in rows)
    print(f"\n{len(rows)} examples in {args.out} ({flagged} flagged by the compliance check, {failed} request failures)")
    if failed:
        print("Run the same command again to retry the failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
