"""Detect the language / tool a task is in (the "context" level of the capability profile).

Subject (Database Systems) -> Skill (joins) -> Context (sql / python / java / excel ...).
The skill is the transferable concept; the context is the syntax/tool the student must use.
A student strong in loops in Python can still need help with loops in Java.

Rules are transparent keyword/syntax cues, checked in order; the first strong match wins.
"""
from __future__ import annotations

import re

LABELS = {
    "email": "email", "report": "reports", "presentation": "presentations", "essay": "essays",
    "calculation": "hand calculation", "case_analysis": "case analysis",
    "python": "Python", "java": "Java", "javascript": "JavaScript", "typescript": "TypeScript", "csharp": "C#",
    "cpp": "C++", "c": "C", "php": "PHP", "sql": "SQL", "html_css": "HTML/CSS", "excel": "Excel",
    "bash": "the shell", "general": "general",
}

# (context, pattern) - explicit names first, then syntax cues
RULES: list[tuple[str, str]] = [
    ("typescript", r"\btypescript\b|\.tsx?\b|:\s*(string|number|boolean)\s*[;=)]"),
    ("javascript", r"\bjavascript\b|\bnode\.?js\b|\breact\b|\bjs\b|\bconsole\.log\b|=>\s*\{|\bconst\s+\w+\s*="),
    ("java", r"\bjava\b(?!script)|public\s+static\s+void\s+main|System\.out\.print|\bArrayList<|\.java\b"),
    ("csharp", r"\bc#|\bc\s*sharp\b|\.net\b|Console\.Write(Line)?\b|\busing\s+System\b"),
    ("cpp", r"\bc\+\+|\bcpp\b|std::|#include\s*<iostream>|\bcout\s*<<"),
    ("c", r"\bin\s+c\b|\bc\s+(program|language|code|function)\b|#include\s*<stdio\.h>|\bprintf\s*\(|\bmalloc\s*\("),
    ("php", r"\bphp\b|<\?php|\$_(GET|POST)\b"),
    ("python", r"\bpython\b|\bdef\s+\w+\s*\(|\bprint\s*\(|\bpandas\b|\bnumpy\b|\.py\b|\bpip\b|\blist comprehension\b"),
    ("sql", r"\bsql\b|\bmysql\b|\bpostgres(ql)?\b|\bselect\b.+\bfrom\b|\bjoin\b|\bgroup by\b|\bwhere\b.+=|\bquery\b"),
    ("html_css", r"\bhtml\b|\bcss\b|<div|<form|\bflexbox\b|\bselector\b"),
    ("excel", r"\bexcel\b|\bspreadsheet\b|\bvlookup\b|\bxlookup\b|\bpivot table\b|=\s*(SUM|IF|VLOOKUP|INDEX)\("),
    ("bash", r"\bbash\b|\bshell script\b|\blinux command\b|\bterminal\b|\bchmod\b|\bgrep\b"),
    # non-code formats: the same concept (persuasion, structure, a ratio) in a different medium
    ("email", r"\be-?mail\b|\bwrite to my (manager|lecturer|boss|client)\b"),
    ("presentation", r"\bpresentation\b|\bslides?\b|\bpitch\b|\bdeck\b"),
    ("report", r"\breport\b|\bproposal\b|\bmemo\b|\bexecutive summary\b"),
    ("essay", r"\bessay\b|\bargument(ative)?\b|\breflection\b|\bliterature review\b"),
    ("case_analysis", r"\bswot\b|\bpestle?\b|\bcase study\b|\bporter'?s five\b|\bmarketing mix\b|\b4ps\b"),
    ("calculation", r"\bcalculate\b|\bcompute\b|\bfind the\b.*\b(point|ratio|value|rate)\b|\bRs\.?\s?\d|\$\d|\d+\s?%"),
]

# when the task names no language, the subject implies one
MODULE_DEFAULT = {"Database Systems": "sql", "Workplace": "general", "Business Management": "general"}


def detect(text: str, module: str | None = None) -> str:
    for ctx, pat in RULES:
        if re.search(pat, text, re.IGNORECASE | re.DOTALL):
            return ctx
    return MODULE_DEFAULT.get(module or "", "general")


def label(ctx: str) -> str:
    return LABELS.get(ctx, ctx)


# How much of a concept transfers from one context to another (0..1). Hand-set, explainable starting values;
# pilot data can later learn them (students strong at X in A who also do well at X in B -> higher similarity).
FAMILIES = {
    "programming": {"python", "java", "javascript", "typescript", "csharp", "cpp", "c", "php"},
    "c_like": {"java", "csharp", "cpp", "c", "javascript", "typescript", "php"},
    "scripting": {"python", "javascript", "typescript", "php", "bash"},
    "data": {"sql", "excel", "python"},
    "writing": {"email", "report", "presentation", "essay"},
    "business": {"calculation", "excel", "case_analysis", "report"},
}
PAIR = {
    frozenset({"java", "csharp"}): 0.8, frozenset({"javascript", "typescript"}): 0.85, frozenset({"c", "cpp"}): 0.8,
    frozenset({"report", "essay"}): 0.6, frozenset({"email", "report"}): 0.5, frozenset({"report", "presentation"}): 0.5,
    frozenset({"calculation", "excel"}): 0.5, frozenset({"sql", "excel"}): 0.35,
}


def similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if frozenset({a, b}) in PAIR:
        return PAIR[frozenset({a, b})]
    if "general" in (a, b):
        return 0.3
    shared = [f for f, members in FAMILIES.items() if a in members and b in members]
    if "c_like" in shared:
        return 0.65
    if "programming" in shared:
        return 0.55  # general-purpose languages: control flow, functions, data structures carry over
    if shared:
        return 0.45
    return 0.2  # different worlds (e.g. SQL -> essay): only the general idea transfers
