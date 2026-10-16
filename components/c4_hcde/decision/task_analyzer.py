"""Task Analyzer: task text (+ optional deadline) -> TaskProfile.

The skill and difficulty are estimated from the most similar reference tasks (k nearest neighbours
over the 120 curated tasks: 100 IT + 20 business/workplace). Urgency comes from the deadline.
Everything is transparent: the profile lists the neighbours it was based on.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import os

from .text_index import HybridIndex

DATA = Path(__file__).resolve().parents[1] / "training" / "data"
TASK_FILES = [DATA / "seed_tasks.jsonl", DATA / "transfer_tasks.jsonl"]
# below this the task is treated as an unknown skill (embedding cosine is on a different scale than TF-IDF)
MIN_SIMILARITY = {"embedding": 0.55, "tfidf": 0.08}
CACHE = os.environ.get("HCDE_EMBED_CACHE", str(Path(__file__).resolve().parents[3] / "runs" / "hcde_ref_embeddings.json"))


@dataclass
class TaskProfile:
    text: str
    skill: str
    module: str
    difficulty: int                 # 1 (easy) .. 5 (hard)
    urgency: float                  # 0 (no deadline pressure) .. 1 (due now)
    minutes_left: float | None
    confidence: float               # similarity of the best matching reference task
    neighbours: list[dict] = field(default_factory=list)
    match_mode: str = "tfidf"       # "embedding" (semantic) or "tfidf" (word overlap)

    def to_dict(self) -> dict:
        return asdict(self)


def for_matching(text: str) -> str:
    """Drop details that describe data rather than the skill: column lists in brackets and
    'Tables:/Schema:/Data:' lines. 'customers(id, name)' should not make a JOIN task look like
    a normalisation task just because both mention customers and orders."""
    import re
    text = re.sub(r"\([^()]*\)", " ", text)
    text = re.sub(r"(?im)^\s*(tables?|schema|data|columns?)\s*:.*$", " ", text)
    text = re.sub(r"(?i)\b(tables?|schema|columns?)\s*:[^.\n]*", " ", text)
    return " ".join(text.split())


# Subject hints for the word-overlap fallback: a strong keyword boosts reference tasks of its module.
# (Not needed when embeddings are available, but kept: cheap and easy to explain.)
MODULE_HINTS = {
    "Database Systems": r"\b(sql|query|queries|join|joins|select|database|table|primary key|foreign key|normali[sz]e|index)\b",
    "Computer Networks": r"\b(tcp|udp|ip|dns|http|https|subnet|router|packet|network|osi|handshake)\b",
    "Operating Systems": r"\b(process|thread|deadlock|scheduling|scheduler|paging|semaphore|mutex|kernel|virtual memory)\b",
    "Web Development": r"\b(html|css|javascript|dom|react|frontend|rest api|form)\b",
    "Object-Oriented Programming": r"\b(class|inheritance|polymorphism|encapsulation|interface|object|oop)\b",
    "Data Structures and Algorithms": r"\b(array|linked list|stack|queue|tree|graph|sort|search|complexity|big o|recursion|hash)\b",
    "Software Engineering": r"\b(uml|use case|requirement|agile|scrum|testing|unit test|git|design pattern)\b",
    "Workplace": r"\b(email|excel|spreadsheet|formula|vlookup|meeting|report|presentation|manager)\b",
    "Business Management": r"\b(swot|marketing|break-even|break even|profit|revenue|cost|ratio|budget|pestle)\b",
}
MODULE_BOOST = 1.6


def module_hints(text: str) -> set[str]:
    import re
    return {m for m, pat in MODULE_HINTS.items() if re.search(pat, text, re.I)}


@lru_cache(maxsize=1)
def _reference() -> tuple[list[dict], HybridIndex]:
    tasks = []
    for f in TASK_FILES:
        if f.exists():
            tasks += [json.loads(l) for l in f.open() if l.strip()]
    return tasks, HybridIndex([f"{t['skill']}: {for_matching(t['task'])}" for t in tasks], cache_file=CACHE)


def urgency_from_deadline(minutes_left: float | None) -> float:
    if minutes_left is None:
        return 0.1
    if minutes_left <= 30:
        return 1.0
    if minutes_left <= 120:
        return 0.8
    if minutes_left <= 24 * 60:
        return 0.5
    if minutes_left <= 3 * 24 * 60:
        return 0.3
    return 0.1


def analyze(text: str, minutes_left: float | None = None, difficulty_hint: int | None = None,
            k: int = 5) -> TaskProfile:
    tasks, index = _reference()
    query = for_matching(text)
    hits = index.search(query, k=max(k, 15))
    if index.mode == "tfidf":
        hinted = module_hints(text)
        if hinted:
            hits = sorted(((i, s * (MODULE_BOOST if tasks[i]["module"] in hinted else 1.0)) for i, s in hits),
                          key=lambda x: -x[1])
    hits = hits[:k]
    neighbours = [{"id": tasks[i]["id"], "skill": tasks[i]["skill"], "module": tasks[i]["module"],
                   "difficulty": tasks[i]["difficulty"], "similarity": round(min(1.0, s), 3)} for i, s in hits]
    best = neighbours[0] if neighbours else None
    if best and best["similarity"] >= MIN_SIMILARITY[index.mode]:
        # skill = similarity-weighted vote among the neighbours (more robust than the single best match)
        votes: dict[str, float] = {}
        for n in neighbours:
            votes[n["skill"]] = votes.get(n["skill"], 0.0) + n["similarity"]
        skill = max(votes, key=votes.get)
        top = next(n for n in neighbours if n["skill"] == skill)
        module, conf = top["module"], best["similarity"]
        w = [n["similarity"] for n in neighbours]
        diff = round(sum(n["difficulty"] * s for n, s in zip(neighbours, w)) / sum(w))
    else:
        skill, module, conf, diff = "general", "General", best["similarity"] if best else 0.0, 3
    if difficulty_hint:
        diff = int(difficulty_hint)
    return TaskProfile(text=text, skill=skill, module=module, difficulty=max(1, min(5, diff)),
                       urgency=urgency_from_deadline(minutes_left), minutes_left=minutes_left,
                       confidence=round(conf, 3), neighbours=neighbours, match_mode=index.mode)
