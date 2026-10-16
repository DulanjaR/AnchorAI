"""Tiny TF-IDF + cosine similarity index (standard library only).

Used twice: the Task Analyzer maps a new task to the most similar reference tasks (skill and
difficulty), and the learner memory retrieves a user's most similar past interactions (RAG).
Kept dependency-free so the backend runs anywhere; can be swapped for an embedding model later.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an the and or of to in on for with by from at as is are was were be been it its this that these those
how what which who whom why when where do does did can could should would will shall may might must i you he she we
they me my your our their them using use write explain show give make find get given into over between than then
there here also no yes if lists list write else all any each every some such only own same so too very just one two three""".split())


def stem(w: str) -> str:
    """Very light suffix stripping so 'orders'/'order', 'joins'/'joined'/'joining' match."""
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    # plurals only: stripping -ed/-ing over-merges ("placed"/"places" made a SQL task look like a UML one)
    if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    out = [stem(w) for w in words if w not in STOP and len(w) > 1]
    # bigrams help short technical phrases ("left join", "break even")
    return out + [f"{a}_{b}" for a, b in zip(out, out[1:])]


class TextIndex:
    def __init__(self, docs: list[str] | None = None):
        self.docs: list[Counter] = []
        self.df: Counter = Counter()
        for d in docs or []:
            self.add(d)

    def add(self, text: str) -> int:
        tf = Counter(tokens(text))
        self.docs.append(tf)
        self.df.update(tf.keys())
        return len(self.docs) - 1

    def _vec(self, tf: Counter) -> dict[str, float]:
        n = len(self.docs) + 1
        v = {t: (1 + math.log(c)) * math.log((n + 1) / (self.df.get(t, 0) + 1)) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, text: str, k: int = 5) -> list[tuple[int, float]]:
        q = self._vec(Counter(tokens(text)))
        scored = []
        for i, tf in enumerate(self.docs):
            d = self._vec(tf)
            s = sum(w * d.get(t, 0.0) for t, w in q.items())
            if s > 0:
                scored.append((i, s))
        return sorted(scored, key=lambda x: -x[1])[:k]


# --- semantic search with a local embedding model (Ollama), falling back to TF-IDF -------------------
import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("HCDE_EMBED_MODEL", "nomic-embed-text")


def embed(texts: list[str], timeout: float = 30.0) -> list[list[float]] | None:
    """Embeddings from Ollama (e.g. `ollama pull nomic-embed-text`); None if unavailable."""
    try:
        body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/embed", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            vecs = json.load(r)["embeddings"]
        return [_unit(v) for v in vecs]
    except Exception:
        return None


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class HybridIndex:
    """Semantic (embedding) search when Ollama embeddings are available, TF-IDF otherwise.
    `mode` says which one answered, so results stay explainable."""

    def __init__(self, docs: list[str], cache_file: str | None = None):
        self.texts = list(docs)
        self.tfidf = TextIndex(self.texts)
        self.vecs: list[list[float]] | None = None
        self.cache_file = cache_file
        self._load_or_embed()

    def _load_or_embed(self) -> None:
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                data = json.load(open(self.cache_file))
                if data.get("model") == EMBED_MODEL and data.get("n") == len(self.texts):
                    self.vecs = data["vecs"]
                    return
            except Exception:
                pass
        vecs = embed(self.texts) if self.texts else None
        if vecs:
            self.vecs = vecs
            if self.cache_file:
                os.makedirs(os.path.dirname(self.cache_file) or ".", exist_ok=True)
                json.dump({"model": EMBED_MODEL, "n": len(self.texts), "vecs": vecs}, open(self.cache_file, "w"))

    @property
    def mode(self) -> str:
        return "embedding" if self.vecs else "tfidf"

    def add(self, text: str) -> int:
        self.texts.append(text)
        self.tfidf.add(text)
        if self.vecs is not None:
            v = embed([text])
            if v:
                self.vecs.append(v[0])
            else:  # embeddings went away: stay consistent and use TF-IDF from now on
                self.vecs = None
        return len(self.texts) - 1

    last_mode: str = "tfidf"  # which method answered the most recent search

    def search(self, text: str, k: int = 5) -> list[tuple[int, float]]:
        if self.vecs:
            q = embed([text])
            if q:
                self.last_mode = "embedding"
                scored = sorted(((i, cosine(q[0], v)) for i, v in enumerate(self.vecs)), key=lambda x: -x[1])
                return scored[:k]
        self.last_mode = "tfidf"  # embedding model unreachable right now: word overlap fallback
        return self.tfidf.search(text, k)
