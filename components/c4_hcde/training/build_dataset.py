"""Generate the tier-calibrated training set with a teacher model.

For every seed task x tier, a large teacher model writes the reply using the full rubric.
The saved training example pairs that reply with the SHORT control prompt, so the student
model has to learn tier behaviour from the tag alone.

Works with any OpenAI-compatible chat endpoint (OpenRouter, Groq, Together, a local Ollama
or vLLM server, ...). Configure with environment variables:

    TEACHER_BASE_URL   e.g. https://openrouter.ai/api/v1  or  http://localhost:11434/v1
    TEACHER_API_KEY    API key (any string for local servers)
    TEACHER_MODEL      e.g. qwen/qwen-2.5-72b-instruct
    TEACHER_EXTRA      optional JSON merged into every request, e.g. for Groq gpt-oss:
                       {"reasoning_effort": "low", "include_reasoning": false}

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
import re
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


THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> blocks that reasoning models (e.g. Qwen3) put before the answer,
    so they never end up in the training data."""
    return THINK_BLOCK.sub("", text).strip()


def env_json(name: str) -> dict:
    """Optional JSON object from an environment variable (provider-specific request settings)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


class KeyPool:
    """Several API keys for one model, given as a comma-separated list. When a key reaches its
    DAILY limit (Groq reports "per day" / TPD / RPD on a 429), it is set aside and the next key is
    used. Per-minute limits are waited out instead."""

    _pools: dict[tuple[str, str], "KeyPool"] = {}
    _lock = threading.Lock()

    def __init__(self, keys: list[str]):
        self.keys = keys
        self.spent: set[str] = set()
        self.i = 0

    @classmethod
    def for_model(cls, model: str, api_key: str) -> "KeyPool":
        keys = [k.strip() for k in api_key.split(",") if k.strip()] or [""]
        with cls._lock:
            return cls._pools.setdefault((model, ",".join(keys)), cls(keys))

    def current(self) -> str:
        with self._lock:
            live = [k for k in self.keys if k not in self.spent]
            if not live:
                raise RuntimeError(f"all {len(self.keys)} API key(s) reached their daily limit for this model")
            return live[self.i % len(live)]

    def rotate(self) -> None:
        """Move on to the next key (spreads per-minute limits across keys)."""
        with self._lock:
            self.i += 1

    def live_count(self) -> int:
        with self._lock:
            return len([k for k in self.keys if k not in self.spent])

    def mark_spent(self, key: str, model: str) -> None:
        with self._lock:
            if key not in self.spent:
                self.spent.add(key)
                left = len(self.keys) - len(self.spent)
                print(f"note: key #{self.keys.index(key) + 1} hit its daily limit for {model}; "
                      f"{left} key(s) left", file=sys.stderr)


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) anchor-ai-hcde/1.0"
DAILY_LIMIT = re.compile(r"per day|\bTPD\b|\bRPD\b", re.IGNORECASE)
RETRY_IN = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def retry_seconds(message: str, header: str | None) -> float | None:
    """Seconds to wait, from a Retry-After header or Groq's 'try again in 1m2.5s' text."""
    m = RETRY_IN.search(message)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    try:
        return float(header) if header else None
    except ValueError:
        return None


def chat(base_url: str, api_key: str, model: str, messages: list[dict], temperature: float,
         max_tokens: int, retries: int = 5, extra: dict | None = None) -> str:
    """One chat completion from an OpenAI-compatible endpoint. ``api_key`` may hold several
    comma-separated keys (see KeyPool)."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
               **(extra or {})}
    body = json.dumps(payload).encode()
    pool = KeyPool.for_model(model, api_key)
    attempt, waits = 0, 0
    while True:
        key = pool.current()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {key}",
            # Cloudflare (in front of Groq and others) blocks Python's default "Python-urllib" agent
            # with error 1010, so identify as a normal client.
            "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.load(resp)
            return strip_reasoning(data["choices"][0]["message"]["content"] or "")
        except urllib.error.HTTPError as e:
            detail = e.read()[:400]
            # A provider that rejects one of the optional settings: retry once without them.
            if e.code == 400 and extra:
                print(f"note: {model} rejected the extra settings {sorted(extra)}; retrying without them",
                      file=sys.stderr)
                return chat(base_url, api_key, model, messages, temperature, max_tokens, retries)
            message = detail.decode("utf-8", "replace")
            # A key that is out of daily quota: switch to the next key (does not use up a retry).
            if e.code == 429 and DAILY_LIMIT.search(message):
                pool.mark_spent(key, model)
                continue
            # Per-minute limit: try the next key straight away; once every key has been tried,
            # wait as long as the provider asks. These short waits do not use up retries.
            if e.code == 429 and waits < 60:
                waits += 1
                pool.rotate()
                if waits % max(1, pool.live_count()) == 0:
                    time.sleep(min(90.0, retry_seconds(message, e.headers.get("retry-after") if e.headers else None)
                                   or 5.0) + random.random())
                continue
            # 429 / 5xx are retried with backoff; other errors are real problems.
            attempt += 1
            if e.code not in (408, 429, 500, 502, 503, 504) or attempt >= retries:
                raise RuntimeError(f"teacher HTTP {e.code}: {detail!r}") from e
            # Providers such as Groq say how long to wait on 429; honour it (capped at 2 minutes).
            wait = e.headers.get("retry-after") if e.headers else None
            if wait:
                try:
                    time.sleep(min(120.0, float(wait)) + random.random())
                    continue
                except ValueError:
                    pass
        except (urllib.error.URLError, TimeoutError) as e:
            attempt += 1
            if attempt >= retries:
                raise RuntimeError(f"teacher unreachable: {e}") from e
        time.sleep(min(60, 2 ** attempt + random.random()))


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


def reference_note(task: dict) -> str:
    """Public-benchmark tasks carry the benchmark's own correct solution. The teacher sees it privately,
    so its replies are correct; the training example never contains it (only the task and the reply)."""
    ref = (task.get("reference") or "").strip()
    if not ref:
        return ""
    return ("\n\nA verified correct solution, for YOUR reference only. Never mention that you were given it, and "
            "reveal only as much of it as this tier allows (for EMERGENCY, give the full correct answer; you may "
            "write it in your own way):\n" + ref)


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
    ap.add_argument("--max-tokens", type=int, default=2000,
                    help="reply length cap; reasoning models count their thinking towards it")
    ap.add_argument("--mock", action="store_true", help="no API calls; write canned replies")
    ap.add_argument("--redo", nargs="+", default=[], metavar="TASK_ID",
                    help="discard the saved replies for these tasks (only the --tiers given) and generate them again")
    args = ap.parse_args(argv)

    extra = env_json("TEACHER_EXTRA")
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
    if args.redo:
        redo = set(args.redo)
        existing = load_jsonl(args.out)
        keep = [r for r in existing if not (r["task_id"] in redo and r["tier"] in args.tiers)]
        backup = args.out.with_suffix(".before_redo.jsonl")
        backup.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing))
        args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
        print(f"--redo: removed {len(existing) - len(keep)} saved replies (backup: {backup.name})")
    done = {(r["task_id"], r["tier"]) for r in load_jsonl(args.out)}
    jobs = [(t, tier) for t in tasks for tier in args.tiers if (t["id"], tier) not in done]
    print(f"{len(tasks)} tasks x {len(args.tiers)} tiers: {len(done)} done, {len(jobs)} to generate")

    lock = threading.Lock()

    def run(task: dict, tier: str) -> dict:
        messages = [{"role": "system", "content": teacher_system_prompt(tier) + reference_note(task)},
                    {"role": "user", "content": task["task"]}]
        reply, result, attempts = "", None, 0
        # If the first reply breaks the tier, send it back with the exact reasons and ask for a
        # rewrite. The second reply is kept either way and flagged, so the review step can decide.
        for attempts in (1, 2):
            reply = mock_reply(tier, task["task"]) if args.mock else chat(
                base_url, api_key, model, messages, args.temperature, args.max_tokens, extra=extra)
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
