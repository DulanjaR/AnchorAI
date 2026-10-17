"""Rule-based reference reader and evaluation metrics for Model 3 (document progress).

The rule reader is the honest baseline: it uses only headings, a "Plan:" line and TODO placeholders. The learned model
has to beat it where rules are weak (documents with no plan, other heading styles) and must stay valid and grounded.
"""
from __future__ import annotations

import json
import re

from .doc_data import DOC_TYPES, SYNONYMS

_LABEL_TO_TYPE = {v["label"].lower(): k for k, v in DOC_TYPES.items()}


def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", s.lower()))


def parse_json(text: str) -> dict | None:
    """The first JSON object in the model answer, or None."""
    try:
        start = text.index("{")
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else None
    except (ValueError, json.JSONDecodeError):
        return None


_KNOWN = {n.lower() for spec in DOC_TYPES.values() for n in spec["sections"]} | {w.lower() for ws in SYNONYMS.values() for w in ws}


def _heading_name(line: str) -> str | None:
    m = re.match(r"^(?:#{1,3}\s+|\d+\.\s+)(.+)$", line.strip())
    if m:
        return m.group(1).strip()
    t = line.strip()
    if t.lower() in _KNOWN:  # a bare line that is a well-known section name (the rules know every name the data uses)
        return t
    if t and t != "TODO" and t.isupper() and len(t.split()) <= 3 and re.fullmatch(r"[A-Z ]+", t):
        return t.title()
    return None


def rule_reader(document: str) -> dict:
    lines = document.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    label = title.split(":")[-1].strip().lower()
    topic = title.split(":")[0].strip().lower()
    dtype = _LABEL_TO_TYPE.get(label)
    plan = None
    sections: list[tuple[str, list[str]]] = []
    for ln in lines[1:]:
        if ln.startswith("Plan:"):
            plan = [p.strip() for p in ln[5:].split(",") if p.strip()]
            continue
        name = _heading_name(ln)
        if name:
            sections.append((name, []))
        elif sections and ln.strip():
            sections[-1][1].append(ln.strip())
    written = [(n, b) for n, b in sections if b and b != ["TODO"]]
    placeholders = [n for n, b in sections if b == ["TODO"]]
    cur_name, cur_body = written[-1] if written else ("", [])
    body = " ".join(cur_body)
    last_words = " ".join(body.split()[-10:])
    full = DOC_TYPES[dtype]["sections"] if dtype else []
    ends_mid = bool(body) and not body.rstrip().endswith((".", "?", "!"))
    names = plan or full
    idx = names.index(cur_name) if cur_name in names else -1
    later = names[idx + 1:] if idx >= 0 else []
    if placeholders:
        later, src = placeholders, "your headings"
    elif plan:
        src = "your plan"
    else:
        src = f"usual structure for a {DOC_TYPES[dtype]['phrase']}" if dtype else "usual structure"
    phrase = DOC_TYPES[dtype]["phrase"] if dtype else "document"
    targets = [cur_name] + later
    return {"stopped_at": {"section": cur_name, "last_words": last_words, "ends_mid_sentence": ends_mid},
            "remaining": [{"item": n, "from": src} for n in later],
            "search_queries": [f"how to write the {n.lower()} section of a {phrase} about {topic}" for n in targets[:3]]}


def _prf(pred: set, gold: set) -> tuple[float, float, float]:
    if not pred and not gold:
        return 1.0, 1.0, 1.0
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score_example(output: str, row: dict) -> dict:
    obj = parse_json(output)
    gold = row["answer"]
    doc_norm = _norm(row["document"])
    res = {"valid_json": obj is not None, "section_ok": False, "last_words_exact": False, "midsentence_ok": False,
           "remaining_f1": 0.0, "source_ok": False, "queries_ok": False, "grounded": False, "queries_count_ok": False}
    if obj is None:
        return res
    st = obj.get("stopped_at") or {}
    rem = obj.get("remaining") or []
    qs = obj.get("search_queries") or []
    res["section_ok"] = _norm(str(st.get("section", ""))) == _norm(gold["stopped_at"]["section"])
    lw = _norm(str(st.get("last_words", "")))
    res["last_words_exact"] = bool(lw) and lw == _norm(gold["stopped_at"]["last_words"])
    res["grounded"] = bool(lw) and lw in doc_norm  # copied from the document, nothing invented
    res["midsentence_ok"] = bool(st.get("ends_mid_sentence")) == gold["stopped_at"]["ends_mid_sentence"]
    pred_items = [_norm(str(r.get("item", ""))) for r in rem if isinstance(r, dict)]
    gold_items = [_norm(r["item"]) for r in gold["remaining"]]
    res["remaining_f1"] = _prf(set(pred_items), set(gold_items))[2]
    gold_src = {r["from"] for r in gold["remaining"]}
    pred_src = {str(r.get("from", "")) for r in rem if isinstance(r, dict)}
    res["source_ok"] = pred_src == gold_src
    res["queries_count_ok"] = len(qs) == len(gold["search_queries"])
    topic = _norm(row["topic"])
    targets = [_norm(r) for r in pred_items] + [_norm(st.get("section", ""))]
    res["queries_ok"] = all(any(t and t[:5] in _norm(str(q)) for t in targets) and topic in _norm(str(q)) for q in qs) and (len(qs) > 0 or not gold["search_queries"])
    return res


def summarise(scores: list[dict]) -> dict:
    keys = list(scores[0])
    return {k: round(100 * sum(float(s[k]) for s in scores) / len(scores), 1) for k in keys}
