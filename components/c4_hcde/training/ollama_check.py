"""Test the installed Ollama model (the exported GGUF) on held-out tasks, on your own Mac.

For each test task it asks the model for every mode (5 tiers + PROBE), runs the same rule checker
used on the training data, prints a table, and saves the replies in the evaluation format so they
can be disclosure-scored later with evaluate.py --from-generations ... --judge.

    python3 -m components.c4_hcde.training.ollama_check                 # 8 IT test tasks
    python3 -m components.c4_hcde.training.ollama_check --tasks 16       # all 16 IT test tasks
    python3 -m components.c4_hcde.training.ollama_check --transfer       # non-IT tasks instead

Needs Ollama running with the model created as "hcde" (ollama create hcde -f Modelfile).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

from .compliance import check
from .evaluate import save_rows, summarise, to_markdown
from .tiers import MODES, control_system_prompt

HERE = Path(__file__).parent
DATA = HERE / "data" / "dataset"


def ask(model: str, system: str, user: str, url: str, temperature: float) -> str:
    body = {"model": model, "stream": False, "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(f"{url}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["message"]["content"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="hcde")
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--tasks", type=int, default=8, help="number of test tasks (each is asked in all 6 modes)")
    ap.add_argument("--transfer", action="store_true", help="use the 20 non-IT transfer tasks")
    ap.add_argument("--temperature", type=float, default=0.0, help="0 = deterministic, like the evaluation")
    ap.add_argument("--out", type=Path, default=Path("runs/ollama-check"))
    ap.add_argument("--show", action="store_true", help="print every reply")
    args = ap.parse_args(argv)

    src = DATA / ("transfer_raw.jsonl" if args.transfer else "test.jsonl")
    rows = [json.loads(l) for l in src.open() if l.strip()]
    by_task: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_task[r["task_id"]][r["tier"]] = r
    # spread the chosen tasks across modules (round-robin) so a small run still covers every module
    per_module: dict[str, list[str]] = defaultdict(list)
    for tid in sorted(by_task):
        per_module[next(iter(by_task[tid].values()))["module"]].append(tid)
    task_ids, queues = [], [list(v) for _, v in sorted(per_module.items())]
    while len(task_ids) < args.tasks and any(queues):
        for q in queues:
            if q and len(task_ids) < args.tasks:
                task_ids.append(q.pop(0))
    print(f"{len(task_ids)} tasks x {len(MODES)} modes = {len(task_ids) * len(MODES)} replies from '{args.model}'\n")

    out_rows, t0 = [], time.time()
    for n, tid in enumerate(task_ids, 1):
        refs = by_task[tid]
        any_row = next(iter(refs.values()))
        task = any_row["messages"][1]["content"]
        reference = refs.get("EMERGENCY", any_row)["messages"][2]["content"]
        marks = []
        for mode in MODES:
            reply = ask(args.model, control_system_prompt(mode), task, args.url, args.temperature)
            c = check(mode, reply, task)
            marks.append(("ok " if c.passed else "NO ") + mode)
            out_rows.append({"condition": f"ollama_{args.model}", "task_id": tid, "module": any_row["module"],
                             "difficulty": any_row.get("difficulty"), "tier": mode, "task": task, "reply": reply,
                             "reference": reference, "compliance": c.to_dict()})
            if args.show:
                print(f"--- {tid} {mode} ({'pass' if c.passed else 'FAIL: ' + '; '.join(c.reasons)})\n{reply}\n")
        failed = " | ".join(m for m in marks if m.startswith("NO")) or "all 6 pass"
        print(f"[{n}/{len(task_ids)}] {tid} {task[:55]}...  {failed}  ({time.time() - t0:.0f}s)", flush=True)
        save_rows(args.out / "generations.jsonl", out_rows)

    summary = summarise(out_rows)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    table = to_markdown(summary)
    (args.out / "summary.md").write_text(table + "\n")
    print("\n" + table)
    fails = [r for r in out_rows if not r["compliance"]["passed"]]
    if fails:
        print("\nFailures:")
        for r in fails:
            print(f"  {r['task_id']} {r['tier']}: {'; '.join(r['compliance']['reasons'])}")
    print(f"\nSaved to {args.out}/ . Add disclosure scores later with:\n"
          f"  python3 -m components.c4_hcde.training.evaluate --from-generations {args.out}/generations.jsonl "
          f"--out {args.out} --judge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
