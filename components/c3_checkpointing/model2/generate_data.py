"""Generate the synthetic checkpoint -> restart-summary data set for Model 2.

Run from the repository root:
    python -m components.c3_checkpointing.model2.generate_data

Design rules (they implement the C3 scope and the boundary with C4):
  * The summary only restates the student's checkpoint text; it never adds code, answers or advice.
  * First person is rewritten as second person ("I need to" -> "you need to").
  * The Difficulty line sets the depth: Low = stopped-at + next step, Medium adds goal and problem,
    High adds completed work, resources and the open items (as a list).
  * A field the student left empty is simply left out.
  * A question the student wrote is repeated as an open question and is never answered.
  * Train, validation and test use different task families, so the test set measures generalisation.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

from ..app.difficulty import format_minutes, predict_difficulty
from .scenarios import FAMILIES
from .textutils import cap, sentence, to_you, tokens

SEED = 42
QUOTA = {"train": 144, "val": 16, "test": 24}  # examples per difficulty level
TYPES = ["quick_message", "meeting", "other_task", "break"]
TYPE_WEIGHTS = [0.25, 0.30, 0.30, 0.15]
MINUTES = [5, 10, 20, 45, 90, 180, 300, 600, 1440]

SYSTEM_PROMPT = (
    "You write restart summaries for students who return to an interrupted task. "
    "Use only the information in the checkpoint. "
    "The Difficulty line sets the length: Low = two short sentences, Medium = a short paragraph, "
    "High = a fuller summary that also lists the open items. "
    "Rewrite first person as second person (I -> you). "
    "Never add code, answers, advice or new facts. "
    "If the student wrote a question, repeat it as an open question and do not answer it. "
    "Leave out anything the student did not write."
)

FORMAT_CUE = {
    "Low": "Summary format: SHORT - two sentences, only where you stopped and the next step; no goal, no files, no open items.",
    "Medium": "Summary format: STANDARD - one paragraph with goal, where you stopped, the open problem and the next step; no files, no open-items list.",
    "High": "Summary format: FULL - one paragraph with goal, completed work, where you stopped, the open problem, the next step and files, then the open items as a list.",
}


def render_input(title: str, kind: str, level: str, away: str, f: dict) -> str:
    items = f.get("open_items") or []
    return "\n".join([
        f"Task: {title}",
        f"Task type: {kind}",
        f"Difficulty: {level}",
        f"Time away: {away}",
        f"Goal: {f.get('goal') or '(not written)'}",
        f"Completed work: {f.get('completed') or '(not written)'}",
        f"Working point: {f.get('working_point') or '(not written)'}",
        f"Problem or decision: {f.get('problem') or '(not written)'}",
        f"Next step: {f.get('next_step') or '(not written)'}",
        f"Resources: {f.get('resources') or '(not written)'}",
        f"Open items: {'; '.join(items) if items else '(none)'}",
        FORMAT_CUE[level],
    ])


def render_output(title: str, level: str, away: str, f: dict, rng: random.Random) -> str:
    wp, nxt = f.get("working_point"), f.get("next_step")
    if level == "Low":
        if wp and nxt:
            return rng.choice([
                f'You were working on "{title}" and stopped at {to_you(wp)}. Your next step is to {to_you(nxt)}.',
                f'Quick reminder for "{title}": you stopped at {to_you(wp)}. Next, {to_you(nxt)}.',
                f'"{title}": you stopped at {to_you(wp)}. Next up: {to_you(nxt)}.',
            ])
        if wp:
            return f'You were working on "{title}" and stopped at {to_you(wp)}.'
        if nxt:
            return f'You were working on "{title}". Your next step is to {to_you(nxt)}.'
        return f'No checkpoint text was written for "{title}".'

    parts = [rng.choice([f'Welcome back to "{title}".', f'You are back on "{title}".', f'Picking up "{title}" again.'])]
    if rng.random() < 0.9:
        parts.append(rng.choice([f"You were away for about {away}.", f"It has been about {away} since you stopped."]))
    if f.get("goal"):
        parts.append(rng.choice([f"Your goal is to {to_you(f['goal'])}.", f"You wanted to {to_you(f['goal'])}."]))
    if level == "High" and f.get("completed"):
        parts.append(rng.choice([f"Already finished: {to_you(f['completed'])}.",
                                 f"You have already finished {to_you(f['completed'])}."]))
    if wp:
        parts.append(rng.choice([f"You stopped at {to_you(wp)}.", f"Where you left off: {to_you(wp)}."]))
    if f.get("problem"):
        q = to_you(f["problem"])
        if q.strip().endswith("?"):
            parts.append(rng.choice([f"You were wondering: {cap(q)}", f"An open question: {cap(q)}"]))
        else:
            parts.append(rng.choice([f"Open problem: {sentence(cap(q))}", f"The open problem is this: {sentence(q)}"]))
    if nxt:
        parts.append(rng.choice([f"Your next step is to {to_you(nxt)}.", f"Next, {to_you(nxt)}."]))
    if level == "High" and f.get("resources"):
        parts.append(rng.choice([f"Files and resources: {to_you(f['resources'])}.", f"You were using {to_you(f['resources'])}."]))

    text = " ".join(parts)
    if level == "High":
        items = f.get("open_items") or []
        if len(items) >= 2:
            text += "\nStill open in your files:\n" + "\n".join(f"- {to_you(i)}" for i in items)
        elif len(items) == 1:
            text += f" Still open in your files: {to_you(items[0])}."
    if len(parts) == 1 + (1 if any("away" in p or "since you stopped" in p for p in parts) else 0):
        text = f'No checkpoint text was written for "{title}".'
    return text


def sample_fields(fam: dict, rng: random.Random) -> dict:
    f = {}
    if rng.random() < 0.88:
        f["goal"] = rng.choice(fam["goal"])
    if rng.random() < 0.85:
        f["completed"] = rng.choice(fam["completed"])
    if rng.random() < 0.96:
        f["working_point"] = rng.choice(fam["working_point"])
    if rng.random() < 0.80:
        f["problem"] = rng.choice(fam["problem"])
    if rng.random() < 0.96:
        f["next_step"] = rng.choice(fam["next_step"])
    if rng.random() < 0.80:
        f["resources"] = rng.choice(fam["resources"])
    k = rng.choice([0, 1, 2, 3, 3, 4, 5]) if fam["open_items"] else 0
    f["open_items"] = rng.sample(fam["open_items"], min(k, len(fam["open_items"])))
    if not f.get("working_point") and not f.get("next_step"):
        f["working_point"] = rng.choice(fam["working_point"])
    return f


def generate_split(split: str, rng: random.Random) -> list[dict]:
    families = [name for name, fam in FAMILIES.items() if fam["split"] == split]
    counts = {"Low": 0, "Medium": 0, "High": 0}
    rows, seen = [], set()
    attempts = 0
    while any(counts[l] < QUOTA[split] for l in counts):
        attempts += 1
        if attempts > 200000:
            raise RuntimeError("could not fill the quota for " + split)
        name = rng.choice(families)
        fam = FAMILIES[name]
        f = sample_fields(fam, rng)
        minutes = rng.choice(MINUTES)
        kind_type = rng.choices(TYPES, TYPE_WEIGHTS)[0]
        complexity = rng.choice(fam["complexity"])
        level = predict_difficulty(minutes, complexity, len(f["open_items"]), kind_type)["level"]
        if counts[level] >= QUOTA[split]:
            continue
        title = rng.choice(fam["titles"])
        away = format_minutes(minutes)
        user = render_input(title, fam["kind"], level, away, f)
        if user in seen:
            continue
        seen.add(user)
        out = render_output(title, level, away, f, rng)
        counts[level] += 1
        rows.append({
            "id": f"{split}-{len(rows):04d}", "split": split, "family": name, "level": level,
            "minutes": minutes, "interruption_type": kind_type, "complexity": complexity, "kind": fam["kind"],
            "fields": f, "input": user, "output": out,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": out},
            ],
            "synthetic": True,
        })
    rng.shuffle(rows)
    for i, r in enumerate(rows):
        r["id"] = f"{split}-{i:04d}"
    return rows


def frame_vocabulary(rows: list[dict]) -> list[str]:
    vocab: set[str] = set()
    for r in rows:
        known = set(tokens(r["input"]))
        vocab.update(t for t in tokens(r["output"]) if t not in known)
    return sorted(vocab)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="components/c3_checkpointing/data/generated")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_rows = {}
    for split in ("train", "val", "test"):
        rows = generate_split(split, random.Random(SEED + {"train": 0, "val": 1, "test": 2}[split]))
        all_rows[split] = rows
        with open(out / f"restart_summary_{split}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(split, len(rows), {l: sum(1 for r in rows if r["level"] == l) for l in ("Low", "Medium", "High")})
    vocab = frame_vocabulary(all_rows["train"])
    (out / "frame_vocab.json").write_text(json.dumps({"system_prompt": SYSTEM_PROMPT, "frame_vocab": vocab}, indent=1), encoding="utf-8")
    print("frame vocabulary size:", len(vocab))


if __name__ == "__main__":
    main()
