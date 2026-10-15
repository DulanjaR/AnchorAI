"""Read-only analysis of the student's text files (code and documents).

Only small facts are extracted (headings, open items, function names). The file text is never returned
or stored. Mirrors analyzeFile in app/static/core.js and adds .docx support.
"""
from __future__ import annotations

import io
import re
from typing import Any

SOURCE_EXT = {"py", "js", "html", "css", "java", "php"}
TEXT_EXT = {"md", "txt"}
DOCX_EXT = {"docx"}
SUPPORTED_EXT = SOURCE_EXT | TEXT_EXT | DOCX_EXT
MAX_BYTES = 2 * 1024 * 1024

_TODO = re.compile(r"\b(TODO|FIXME)\b[:\s-]*(.*)$", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]*>")


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _strip_tags(text: str) -> str:
    return _TAGS.sub("", text).strip()


def _unique(items: list[str], limit: int) -> list[str]:
    return list(dict.fromkeys(items))[:limit]


def _result(name: str, ext: str, line_count: int, todos, open_items, done_items, headings, symbols) -> dict:
    return {
        "supported": True,
        "name": name,
        "ext": ext,
        "lineCount": line_count,
        "todos": todos,
        "openItems": open_items,
        "doneItems": done_items,
        "headings": _unique(headings, 5),
        "symbols": _unique(symbols, 8),
        "openCount": len(todos) + len(open_items),
    }


def analyze_text(name: str, text: str) -> dict:
    ext = _ext(name)
    is_source = ext in SOURCE_EXT
    is_text = ext in TEXT_EXT
    if not (is_source or is_text):
        return {"supported": False, "name": name, "ext": ext, "reason": "type not supported"}

    lines = str(text or "").splitlines() or [""]
    todos: list[dict] = []
    open_items: list[str] = []
    done_items: list[str] = []
    headings: list[str] = []
    symbols: list[str] = []

    for i, raw in enumerate(lines, start=1):
        t = raw.strip()
        m = _TODO.search(t)
        if m:
            body = re.sub(r"(-->|\*/)\s*$", "", m.group(2)).strip()
            todos.append({"line": i, "text": body or t})
        if is_text:
            h = re.match(r"^#{1,3}\s+(.*)$", t)
            if h:
                headings.append(h.group(1).strip())
            h = re.match(r"^[-*]\s+\[ \]\s+(.*)$", t)
            if h:
                open_items.append(h.group(1).strip())
            h = re.match(r"^[-*]\s+\[[xX]\]\s+(.*)$", t)
            if h:
                done_items.append(h.group(1).strip())
        if ext == "html":
            title = re.search(r"<title[^>]*>(.*?)</title>", t, re.IGNORECASE)
            if title:
                headings.append(_strip_tags(title.group(1)))
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.IGNORECASE)
            if h1:
                headings.append(_strip_tags(h1.group(1)))
        s = None
        if ext in ("js", "html"):
            s = re.search(r"\bfunction\s+([A-Za-z_$][\w$]*)", t) or re.search(
                r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", t
            )
        elif ext == "py":
            s = re.match(r"^(?:def|class)\s+(\w+)", t)
        elif ext in ("java", "php"):
            s = re.search(r"\bclass\s+(\w+)", t) or (re.search(r"\bfunction\s+(\w+)", t) if ext == "php" else None)
        if s:
            symbols.append(s.group(1))

    return _result(name, ext, len(lines), todos, open_items, done_items, headings, symbols)


def analyze_docx(name: str, data: bytes) -> dict:
    """Word documents: headings, '[ ]' / '[x]' checklist lines and TODO/FIXME notes."""
    from docx import Document  # imported lazily so the rest of the module has no heavy dependency

    try:
        doc = Document(io.BytesIO(data))
    except Exception:  # corrupt or not a real .docx
        return {"supported": False, "name": name, "ext": "docx", "reason": "could not read the document"}

    todos: list[dict] = []
    open_items: list[str] = []
    done_items: list[str] = []
    headings: list[str] = []
    paragraphs = doc.paragraphs
    for i, p in enumerate(paragraphs, start=1):
        t = p.text.strip()
        if not t:
            continue
        style = (p.style.name or "") if p.style is not None else ""
        if style.lower().startswith("heading") or style.lower() == "title":
            headings.append(t)
        m = _TODO.search(t)
        if m:
            todos.append({"line": i, "text": m.group(2).strip() or t})
        h = re.match(r"^(?:[-*]\s+)?\[ \]\s+(.*)$", t)
        if h:
            open_items.append(h.group(1).strip())
        h = re.match(r"^(?:[-*]\s+)?\[[xX]\]\s+(.*)$", t)
        if h:
            done_items.append(h.group(1).strip())
    return _result(name, "docx", len(paragraphs), todos, open_items, done_items, headings, [])


def analyze_file(name: str, data: bytes) -> dict:
    ext = _ext(name)
    if ext not in SUPPORTED_EXT:
        return {"supported": False, "name": name, "ext": ext, "reason": "type not supported"}
    if len(data) > MAX_BYTES:
        return {"supported": False, "name": name, "ext": ext, "reason": "file is larger than 2 MB"}
    if ext in DOCX_EXT:
        return analyze_docx(name, data)
    return analyze_text(name, data.decode("utf-8", errors="replace"))


def suggest_from_file(insight: dict[str, Any]) -> dict:
    """Suggestions are facts copied from the file; the student decides whether to use them."""
    if not insight or not insight.get("supported"):
        return {}
    out = {"resources": insight["name"]}
    if insight["doneItems"]:
        out["completed"] = f"Done in {insight['name']}: " + "; ".join(insight["doneItems"][:5])
    elif insight["symbols"]:
        out["completed"] = f"{insight['name']} contains: " + ", ".join(insight["symbols"])
    if insight["todos"]:
        first = insight["todos"][0]
        out["workingPoint"] = f"{insight['name']}, line {first['line']}: {first['text']}"
    elif insight["openItems"]:
        out["workingPoint"] = f"{insight['name']}: {insight['openItems'][0]}"
    return out
