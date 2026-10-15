"""Small text helpers shared by the data generator, the metrics and the Colab notebooks (no dependencies)."""
from __future__ import annotations

import re

_PRONOUNS = [
    (r"\bi'm\b", "you're"), (r"\bi've\b", "you've"), (r"\bi'll\b", "you'll"), (r"\bi'd\b", "you'd"),
    (r"\bi am\b", "you are"), (r"\bi was\b", "you were"), (r"\bi\b", "you"), (r"\bmyself\b", "yourself"),
    (r"\bmy\b", "your"), (r"\bmine\b", "yours"), (r"\bme\b", "you"),
]


def to_you(text: str) -> str:
    out = text
    for pattern, repl in _PRONOUNS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def cap(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    first = text.split()[0]
    if any(ch in first for ch in "._0123456789") or first != first.lower():
        return text
    return text[0].upper() + text[1:]


def sentence(text: str) -> str:
    text = text.strip().rstrip(".,;:!")
    return text if text.endswith("?") else text + "."


def tokens(text: str) -> list[str]:
    return [t for t in (x.strip(".'-") for x in re.findall(r"[a-z0-9_.'\-]+", text.lower())) if t]
