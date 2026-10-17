"""Synthetic data for Model 3: reading an unfinished text document and saying where the student stopped,
what is still missing and what to search for.

The model never writes any part of the document. Its answer is a short JSON record:
  stopped_at       the section the student was in and the last words written (copied from the document)
  remaining        sections still to do, each with where the information comes from
                   ("your plan", "your headings" or "usual structure for a <document type>")
  search_queries   one web-search phrase per open section (the app turns them into links; nothing is generated)

Run from the repository root:
    python -m components.c3_checkpointing.model3.doc_data
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

SEED = 7
COUNTS = {"train": 640, "val": 64, "test": 128}

DOC_TYPES = {
    "lab_report": {"label": "Lab report", "phrase": "lab report", "sections": ["Introduction", "Aim", "Method", "Results", "Discussion", "Conclusion", "References"]},
    "project_proposal": {"label": "Project proposal", "phrase": "project proposal", "sections": ["Introduction", "Background", "Objectives", "Method", "Risks", "Conclusion", "References"]},
    "essay": {"label": "Essay", "phrase": "essay", "sections": ["Introduction", "Background", "Analysis", "Discussion", "Conclusion", "References"]},
    "requirements_doc": {"label": "Requirements document", "phrase": "software requirements document", "sections": ["Introduction", "Scope", "Requirements", "Design", "Testing", "Risks", "Summary"]},
    "study_notes": {"label": "Study notes", "phrase": "set of study notes", "sections": ["Summary", "Key Points", "Examples", "Questions", "References"]},
}

TOPICS = {
    "train": ["sorting algorithms", "database normalisation", "network latency", "password hashing", "user authentication", "web accessibility",
              "cloud storage", "machine learning basics", "version control", "memory management", "http caching", "unit testing",
              "binary search trees", "operating system scheduling", "api design", "data visualisation", "mobile app performance",
              "sql injection", "agile planning", "image compression"],
    "val": ["recursion", "encryption keys", "responsive layouts", "message queues"],
    "test": ["graph traversal", "dns resolution", "load balancing", "code review", "relational joins", "regular expressions", "docker containers", "event driven design"],
}

SENT = {
    "Introduction": ["This {kind} looks at {topic}.", "{Topic} matters because many systems depend on it.", "The main question here is how {topic} works in practice.", "First, a short overview of {topic} is given."],
    "Aim": ["The aim is to measure how {topic} behaves under different settings.", "We want to show the effect of {topic} with a small experiment.", "The second aim is to compare two ways of handling {topic}."],
    "Background": ["{Topic} has been studied for many years.", "Earlier work describes two common approaches to {topic}.", "The course notes explain the basic terms used for {topic}.", "Most textbooks start from a simple model of {topic}."],
    "Objectives": ["The first objective is to describe how {topic} is used today.", "The second objective is to build a small prototype that uses {topic}.", "The last objective is to check the prototype with a few users."],
    "Scope": ["This document covers {topic} for the first release only.", "Reporting and admin screens are not part of the first release.", "The system will run in a normal web browser."],
    "Method": ["The experiment was run on a laptop with the default settings.", "Each test about {topic} was repeated five times.", "The results were written to a csv file after every run.", "The code for {topic} was kept in one repository."],
    "Requirements": ["The system must let a user log in with a password.", "The system must store the data about {topic} safely.", "Every page must load in under three seconds.", "Users must be able to export their data."],
    "Design": ["The design uses three layers: interface, logic and storage.", "A class diagram for {topic} is shown in figure 1.", "The storage layer keeps one table for each main concept."],
    "Analysis": ["One argument is that {topic} is easier to learn than it looks.", "The evidence about {topic} points in two directions.", "A second point is that the cost of {topic} grows with the size of the system."],
    "Results": ["The first run of {topic} took twelve seconds.", "After the change the same run took only four seconds.", "Table 1 lists all the measurements for {topic}.", "The error rate stayed below two percent."],
    "Discussion": ["The numbers suggest that {topic} has a large effect.", "One limit is that only a small sample was tested.", "A different setup for {topic} might give other results."],
    "Testing": ["Unit tests were written for the main functions of {topic}.", "A short user test was planned with five students.", "Failed tests are listed in the appendix."],
    "Risks": ["The biggest risk is that {topic} takes longer than planned.", "A second risk is that the data may not be available in time.", "Each risk has a person who watches it."],
    "Key Points": ["{Topic} has a simple core idea.", "The most important term to remember is the main rule of {topic}.", "There are two common mistakes with {topic}."],
    "Examples": ["Example one shows {topic} in a very small program.", "Example two uses {topic} on real data.", "The lecturer's example about {topic} is on slide twelve."],
    "Questions": ["Why does {topic} become slow for large inputs?", "When should {topic} not be used?", "How can {topic} be tested?"],
    "Summary": ["In short, {topic} is a central part of the system.", "The main points about {topic} are listed above."],
    "Conclusion": ["In conclusion, {topic} worked as expected.", "The main finding is that {topic} improves the result.", "More work on {topic} is needed in the future."],
    "References": ["Smith, J. (2019). Introduction to {topic}. Pearson.", "Lecture notes, week 4, on {topic}.", "Brown, A. (2021). Practical {topic}. O'Reilly."],
}


SYNONYMS = {
    "Method": ["Methodology", "Procedure", "Method and materials"], "Results": ["Findings", "Observations"],
    "Conclusion": ["Conclusions", "Final remarks"], "Background": ["Literature review"], "Risks": ["Risk assessment"],
    "Testing": ["Test plan"], "Objectives": ["Goals"], "Discussion": ["Analysis of results"], "Requirements": ["Functional requirements"],
}


def _fill(template: str, topic: str, kind: str) -> str:
    return template.format(topic=topic, Topic=topic[0].upper() + topic[1:], kind=kind)


def _heading(name: str, idx: int, style: str) -> str:
    if style == "markdown":
        return f"## {name}"
    if style == "numbered":
        return f"{idx + 1}. {name}"
    if style == "bare":
        return name  # a line with just the heading words, the way many students write
    return name.upper()  # caps


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def build_document(rng: random.Random, split: str) -> dict:
    dtype = rng.choice(list(DOC_TYPES))
    spec = DOC_TYPES[dtype]
    topic = rng.choice(TOPICS[split])
    title = f"{topic[0].upper() + topic[1:]}: {spec['label']}"
    style = rng.choice(["markdown", "numbered", "caps", "bare", "bare"])
    variant = rng.choices(["outline", "placeholders", "plain", "headingless"], [0.25, 0.20, 0.30, 0.25])[0]
    names = spec["sections"]
    shown = [rng.choice(SYNONYMS[n]) if (variant == "plain" and n in SYNONYMS and rng.random() < 0.6) else n for n in names]
    full = [[_fill(t, topic, spec["phrase"]) for t in rng.sample(SENT[n], k=min(len(SENT[n]), rng.randint(2, 4)))] for n in names]

    # where the student stopped: section k, with s sentences written (s == len means the section is finished)
    k = rng.randrange(len(names))
    s = rng.randint(1, len(full[k]))
    written = [list(sec) for sec in full[:k]] + [full[k][:s]]
    partial = s < len(full[k])
    cut_mid = partial and rng.random() < 0.3
    if cut_mid:
        words = written[-1][-1].rstrip(".").split()
        written[-1][-1] = " ".join(words[: max(2, int(len(words) * 0.6))])

    lines = [f"# {title}" if style == "markdown" else title, ""]
    if variant == "outline":
        lines += ["Plan: " + ", ".join(names), ""]
    for i, sec in enumerate(written):
        if variant != "headingless":
            lines += [_heading(shown[i], i, style)]
        lines += [" ".join(sec), ""]
    if variant == "placeholders":
        for i in range(len(written), len(names)):
            lines += [_heading(names[i], i, style), "TODO", ""]
    text = "\n".join(lines).strip() + "\n"

    cur = shown[k] if variant != "headingless" else names[k]
    body_words = " ".join(written[-1]).split()
    last_words = " ".join(body_words[-10:])
    ends_mid = cut_mid
    later = names[k + 1:]
    if variant == "outline":
        src = "your plan"
    elif variant == "placeholders":
        src = "your headings"
    else:
        src = f"usual structure for a {spec['phrase']}"
    remaining = [{"item": n, "from": src} for n in later]
    queries = [f"how to write the {n.lower()} section of a {spec['phrase']} about {topic}" for n in ([names[k]] + later)[:3]]
    answer = {"stopped_at": {"section": cur, "last_words": last_words, "ends_mid_sentence": ends_mid},
              "remaining": remaining, "search_queries": queries}
    return {"split": split, "doc_type": dtype, "topic": topic, "variant": variant, "style": style, "document": text, "answer": answer}


SYSTEM_PROMPT = (
    "You read an unfinished text document that a student was writing before an interruption. "
    "Answer with one JSON object and nothing else, with the keys stopped_at, remaining and search_queries. "
    "stopped_at has the section the student was in, the last words written (copied exactly from the document) "
    "and whether the last sentence is cut off. remaining lists the sections still to do, each with where it comes from: "
    "'your plan', 'your headings' or 'usual structure for a <document type>'. "
    "search_queries has one web-search phrase for each open section. "
    "Never write any part of the document, never give advice, never add facts."
)


def render_input(document: str) -> str:
    return "Document:\n" + document


def to_row(item: dict, idx: int) -> dict:
    user = render_input(item["document"])
    out = json.dumps(item["answer"], ensure_ascii=False)
    return {"id": f"{item['split']}-{idx:04d}", **item, "input": user, "output": out,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user},
                         {"role": "assistant", "content": out}], "synthetic": True}


def generate_split(split: str) -> list[dict]:
    rng = random.Random(SEED + {"train": 0, "val": 1, "test": 2}[split])
    rows, seen = [], set()
    while len(rows) < COUNTS[split]:
        item = build_document(rng, split)
        if item["document"] in seen:
            continue
        seen.add(item["document"])
        rows.append(to_row(item, len(rows)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="components/c3_checkpointing/data/generated")
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        rows = generate_split(split)
        with open(out / f"doc_progress_{split}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        by = {v: sum(1 for r in rows if r["variant"] == v) for v in ("outline", "placeholders", "plain", "headingless")}
        print(split, len(rows), by)


if __name__ == "__main__":
    main()
