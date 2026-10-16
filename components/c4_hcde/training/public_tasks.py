"""Build the public-benchmark task bank (proposal section 3.2).

Task content for the generation layer is drawn from named public benchmarks:

* Information Technology: MBPP, HumanEval, CodeAlpaca-20k
* Data Science: DS-1000 (real practitioner questions; pandas, numpy, scikit-learn, scipy)
* Business Management: FinQA, ConvFinQA (financial reasoning over annual-report figures)

Each task keeps the benchmark's own reference solution (``reference``), which the teacher sees
privately so its replies are correct, and a fixed share per domain is held out as a public test
set (``split: test``) that the model never trains on. Selection is seeded, so the same command
always builds the same bank.

    python -m components.c4_hcde.training.public_tasks            # downloads from GitHub
    python -m components.c4_hcde.training.public_tasks --cache /tmp/pub   # reuse downloads

Writes data/public_tasks.jsonl (all tasks with their split) and data/public_seed_train.jsonl /
data/public_seed_test.jsonl (seed format for build_dataset).
Evol-Instruct-Code (named in the proposal) is only distributed through Hugging Face and is left
out of this offline-reproducible build; OpenStax texts are textbooks, not task sets.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import random
import re
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
SOURCES = {
    "mbpp": "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl",
    "humaneval": "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz",
    "codealpaca": "https://raw.githubusercontent.com/sahil280114/codealpaca/master/data/code_alpaca_20k.json",
    "ds1000": "https://raw.githubusercontent.com/xlang-ai/DS-1000/main/data/ds1000.jsonl.gz",
    "finqa": "https://raw.githubusercontent.com/czyssrs/FinQA/main/dataset/test.json",
    "convfinqa": "https://raw.githubusercontent.com/czyssrs/ConvFinQA/main/data.zip",
}
# tasks per source (train + test); test share per domain below
COUNTS = {"mbpp": 18, "humaneval": 10, "codealpaca": 14, "ds1000": 40, "finqa": 26, "convfinqa": 14}
TEST_PER_DOMAIN = 10


def fetch(name: str, cache: Path | None) -> bytes:
    fn = SOURCES[name].rsplit("/", 1)[1]
    if cache and (cache / fn).exists():
        return (cache / fn).read_bytes()
    with urllib.request.urlopen(SOURCES[name], timeout=120) as r:
        data = r.read()
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / fn).write_bytes(data)
    return data


def words(s: str) -> int:
    return len(s.split())


SKILL_WORDS = [("recurs", "recursion"), ("sort", "sorting"), ("dictionar", "dictionaries"), ("regex", "regex"),
               ("regular expression", "regex"), ("string", "strings"), ("tuple", "tuples"), ("matrix", "matrices"),
               ("list", "lists"), ("array", "arrays"), ("prime", "number theory"), ("binary", "binary"),
               ("class", "classes"), ("loop", "loops"), ("sum", "arithmetic")]


def it_meta(text: str) -> tuple[str, str]:
    t = text.lower()
    if re.search(r"\bsql\b|\btable\b|select ", t):
        return "Database Systems", "sql"
    if re.search(r"html|css|javascript|\bjs\b|react|web page", t):
        return "Web Development", "web"
    skill = next((s for k, s in SKILL_WORDS if k in t), "functions")
    module = "Data Structures and Algorithms" if skill in {"sorting", "recursion", "matrices", "binary"} else "Programming Fundamentals"
    return module, skill


def mbpp(raw: bytes, rng: random.Random) -> list[dict]:
    rows = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
    rows = [r for r in rows if 11 <= r["task_id"] <= 510 and 4 <= len(r["code"].strip().splitlines()) <= 15]
    out = []
    for r in rng.sample(rows, COUNTS["mbpp"]):
        module, skill = it_meta(r["text"])
        out.append(dict(domain="IT", module=module, skill=skill, difficulty=2, source="MBPP", source_id=str(r["task_id"]),
                        task=f"{r['text'].strip()} Your function should pass this test: `{r['test_list'][0]}`",
                        reference=r["code"].replace("\r\n", "\n").strip()))
    return out


def humaneval(raw: bytes, rng: random.Random) -> list[dict]:
    rows = [json.loads(l) for l in gzip.decompress(raw).decode().splitlines() if l.strip()]
    rows = [r for r in rows if words(r["prompt"]) <= 160]
    out = []
    for r in rng.sample(rows, COUNTS["humaneval"]):
        module, skill = it_meta(r["prompt"])
        out.append(dict(domain="IT", module=module, skill=skill, difficulty=3, source="HumanEval", source_id=r["task_id"],
                        task="Complete this Python function so that it does what its docstring says.\n\n```python\n"
                             + r["prompt"].strip("\n") + "\n```",
                        reference=(r["prompt"] + r["canonical_solution"]).strip()))
    return out


def codealpaca(raw: bytes, rng: random.Random) -> list[dict]:
    rows = json.loads(raw)
    rows = [r for r in rows if 40 <= len(r["instruction"]) <= 300 and len(r["input"]) <= 200
            and 4 <= len(r["output"].strip().splitlines()) <= 25
            and re.match(r"(write|create|implement|design|develop|generate|construct|build)\b", r["instruction"].lower())]
    out = []
    for r in rng.sample(rows, COUNTS["codealpaca"]):
        text = r["instruction"].strip() + (f"\nInput: {r['input'].strip()}" if r["input"].strip() else "")
        module, skill = it_meta(text)
        out.append(dict(domain="IT", module=module, skill=skill, difficulty=2, source="CodeAlpaca-20k",
                        source_id=str(rows.index(r)), task=text, reference=r["output"].strip()))
    return out


DS_LIBS = {"Pandas": 13, "Numpy": 11, "Sklearn": 8, "Scipy": 8}


def ds1000(raw: bytes, rng: random.Random) -> list[dict]:
    rows = [json.loads(l) for l in gzip.decompress(raw).decode().splitlines() if l.strip()]
    out = []
    for lib, n in DS_LIBS.items():
        pool = []
        for r in rows:
            m = r["metadata"]
            if m["library"] != lib or m["perturbation_type"] != "Origin":
                continue
            text = re.split(r"\n\s*A:\s*\n", r["prompt"], maxsplit=1)[0]
            text = re.sub(r"^\s*Problem:\s*", "", text).strip()
            if 25 <= words(text) <= 230:
                pool.append((r, text))
        for r, text in rng.sample(pool, n):
            name = {"Sklearn": "scikit-learn"}.get(lib, lib.lower())
            out.append(dict(domain="DS", module="Data Science", skill=name, difficulty=4 if lib in ("Sklearn", "Scipy") else 3,
                            source="DS-1000", source_id=str(r["metadata"]["problem_id"]),
                            task=f"{text}\n\n(Use {name}.)", reference=r["reference_code"].strip()))
    return out


def _facts(gold: dict) -> str:
    return "\n".join("- " + re.sub(r"\s+", " ", v).strip(" ;") for v in gold.values())


def _company(filename: str) -> str:
    return filename.split("/")[0]


def _fin_skill(program: str) -> str:
    ops = re.findall(r"(add|subtract|multiply|divide|exp|greater|table_\w+)\(", program)
    if "subtract" in ops and "divide" in ops:
        return "percentage change"
    if "divide" in ops:
        return "ratios and percentages"
    if "subtract" in ops:
        return "differences"
    return "financial calculation"


def finqa(raw: bytes, rng: random.Random) -> list[dict]:
    rows = [r for r in json.loads(raw) if 1 <= len(r["qa"]["steps"]) <= 3 and 1 <= len(r["qa"]["gold_inds"]) <= 3
            and words(_facts(r["qa"]["gold_inds"])) <= 140]
    out = []
    for r in rng.sample(rows, COUNTS["finqa"]):
        qa = r["qa"]
        out.append(dict(domain="BM", module="Business Management", skill=_fin_skill(qa["program"]),
                        difficulty=min(4, 1 + len(qa["steps"])), source="FinQA", source_id=r["id"],
                        task=f"These figures come from the annual report of {_company(r['filename'])}:\n{_facts(qa['gold_inds'])}\n\n"
                             f"Question: {qa['question'].strip()}",
                        reference=f"Calculation: {qa['program']}\nAnswer: {qa['answer']}"))
    return out


def convfinqa(raw: bytes, rng: random.Random) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(raw))
    rows = json.loads(z.read("data/train.json"))
    rows = [r for r in rows if "qa" in r and 3 <= len(r["annotation"]["dialogue_break"]) <= 4
            and 1 <= len(r["qa"]["gold_inds"]) <= 3 and words(_facts(r["qa"]["gold_inds"])) <= 140]
    out = []
    for r in rng.sample(rows, COUNTS["convfinqa"]):
        a = r["annotation"]
        qs = "\n".join(f"{i}. {q.strip()}" for i, q in enumerate(a["dialogue_break"], 1))
        steps = "\n".join(f"{i}. {p} = {v}" for i, (p, v) in enumerate(zip(a["turn_program"], a["exe_ans_list"]), 1))
        out.append(dict(domain="BM", module="Business Management", skill="multi-step financial calculation", difficulty=3,
                        source="ConvFinQA", source_id=r["id"],
                        task=f"These figures come from the annual report of {_company(r['filename'])}:\n{_facts(r['qa']['gold_inds'])}\n\n"
                             f"Answer these questions in order:\n{qs}",
                        reference=f"Step by step:\n{steps}"))
    return out


BUILDERS = {"mbpp": mbpp, "humaneval": humaneval, "codealpaca": codealpaca, "ds1000": ds1000,
            "finqa": finqa, "convfinqa": convfinqa}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, help="folder to keep the downloaded benchmark files")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", type=Path, default=DATA)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    tasks: list[dict] = []
    for name, build in BUILDERS.items():
        got = build(fetch(name, args.cache), rng)
        print(f"{name}: {len(got)} tasks")
        tasks += got
    # ids and a stratified test split per domain (spread over the sources of that domain)
    by_domain: dict[str, list[dict]] = {}
    for t in tasks:
        by_domain.setdefault(t["domain"], []).append(t)
    for dom, ts in by_domain.items():
        for i, t in enumerate(ts, 1):
            t["id"] = f"pub-{dom.lower()}-{i:03d}"
        order = list(range(len(ts)))
        rng.shuffle(order)
        # round-robin over sources so every benchmark is represented in the test set
        by_src: dict[str, list[int]] = {}
        for i in order:
            by_src.setdefault(ts[i]["source"], []).append(i)
        test, srcs = set(), list(by_src)
        while len(test) < TEST_PER_DOMAIN:
            for s in srcs:
                if by_src[s] and len(test) < TEST_PER_DOMAIN:
                    test.add(by_src[s].pop())
        for i, t in enumerate(ts):
            t["split"] = "test" if i in test else "train"
    keys = ["id", "domain", "module", "skill", "difficulty", "task", "source", "source_id", "split", "reference"]
    tasks = [{k: t[k] for k in keys} for t in tasks]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    def dump(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    dump(args.out_dir / "public_tasks.jsonl", tasks)
    dump(args.out_dir / "public_seed_train.jsonl", [t for t in tasks if t["split"] == "train"])
    dump(args.out_dir / "public_seed_test.jsonl", [t for t in tasks if t["split"] == "test"])
    from collections import Counter
    print(Counter((t["domain"], t["split"]) for t in tasks))
    print(Counter(t["source"] for t in tasks if t["split"] == "test"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
