"""End-to-end test of the HCDE loop with a fake model (no Ollama needed)."""
import os
import tempfile

os.environ.setdefault("HCDE_DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/hcde_test.db")

from fastapi.testclient import TestClient  # noqa: E402

from components.c4_hcde.app import service  # noqa: E402
from components.c4_hcde.app.main import app  # noqa: E402
from components.c4_hcde.decision import bkt  # noqa: E402
from components.c4_hcde.generation import base  # noqa: E402

REPLIES = {
    "HUMAN_FIRST": "You have done joins before, so have a go yourself first, then share your attempt and I'll review it.",
    "HINT": "Which kind of join keeps every customer even when there is no matching order? Try it and come back.",
    "GUIDED": "1. Which join keeps all customers?\n2. How do you spot a missing order?\n```sql\nSELECT c.name FROM customers c\n___ JOIN orders o ON ___\nWHERE ___;\n```\nFill in the blanks.",
    "SHARED": "I'll write the SELECT and FROM part; your part is the join condition and the filter.\n```sql\nSELECT c.id, c.name\nFROM customers c\n-- your part: join and filter\n```\nYour turn: which would you choose, LEFT JOIN or NOT EXISTS, and why?",
    "EMERGENCY": "```sql\nSELECT c.id, c.name\nFROM customers c\nLEFT JOIN orders o ON c.id = o.customer_id\nWHERE o.customer_id IS NULL;\n```\nA LEFT JOIN keeps every customer; customers with no order get NULLs, which the WHERE keeps. Later, revisit outer joins.",
    "PROBE": "Problem:\nThis query should list products that were never sold but returns nothing. Find and fix the bug.\n```sql\nSELECT p.name FROM products p JOIN sales s ON p.id = s.product_id WHERE s.product_id IS NULL;\n```\n\nAnswer key:\nAn INNER JOIN drops unsold products, so the NULL filter never matches. Use LEFT JOIN. Must: (1) spot the inner join, (2) explain why rows vanish, (3) switch to LEFT JOIN.",
}


def fake_call(messages, temperature=0.2, **kw):
    system = messages[0]["content"]
    if "grading" in system:
        return '{"pass": true, "feedback": "Correct: the LEFT JOIN keeps unsold products."}'
    tier = "PROBE" if "Mode: PROBE" in system else system.rsplit("Assistance tier: ", 1)[1].strip()
    return REPLIES[tier]


def test_full_loop(monkeypatch):
    monkeypatch.setattr(base.ollama_client, "chat", fake_call)
    c = TestClient(app)
    task = "Write a SQL query that lists customers who have never placed an order. Tables: customers(id, name), orders(id, customer_id)."

    r = c.post("/hcde/recommend", json={"user_id": "u1", "task": task}).json()
    assert r["skill"] == "joins" and r["recommended_tier"] in base.TEMPERATURE
    assert r["explanation"].startswith("Recommended:")

    # student overrides to SHARED: allowed, recorded, and borrowed help is logged
    r2 = c.post(f"/hcde/interactions/{r['interaction_id']}/respond", json={"tier": "SHARED"}).json()
    assert r2["chosen_tier"] == "SHARED" and r2["overridden"] and r2["generation"]["passed"]
    out = c.post(f"/hcde/interactions/{r['interaction_id']}/outcome", json={"solved": True}).json()
    assert out["ledger"]["borrowed"] == 0.75 and out["ledger"]["outstanding"] == 0.75

    # emergency help adds borrowed capability but no mastery evidence
    r3 = c.post("/hcde/recommend", json={"user_id": "u1", "task": task, "minutes_left": 15}).json()
    c.post(f"/hcde/interactions/{r3['interaction_id']}/respond", json={"tier": "EMERGENCY"})
    out3 = c.post(f"/hcde/interactions/{r3['interaction_id']}/outcome", json={"solved": True}).json()
    assert out3["bkt"]["after"] == out3["bkt"]["before"] and out3["ledger"]["outstanding"] == 1.75

    # a passed probe repays borrowed help and raises mastery
    p = c.post("/hcde/probes", json={"user_id": "u1", "skill": "joins"}).json()
    assert "Answer key" not in p["problem"]  # the key is never sent to the student
    g = c.post(f"/hcde/probes/{p['probe_id']}/answer", json={"answer": "Change JOIN to LEFT JOIN."}).json()
    assert g["passed"] and g["ledger"]["repaid"] == 1.0 and g["ledger"]["outstanding"] == 0.75
    assert g["bkt"]["after"] > g["bkt"]["before"]

    # memory: the next similar task mentions the past ones
    r4 = c.post("/hcde/recommend", json={"user_id": "u1", "task": "List customers with no orders using SQL"}).json()
    assert r4["decision"]["memory"]["similar"]


def test_guardrail_regenerates(monkeypatch):
    calls = []

    def leaky(messages, temperature=0.2, **kw):
        calls.append(1)
        if len(calls) == 1:  # first HINT reply gives the whole query: must be rejected
            return "```sql\nSELECT c.id\nFROM customers c\nLEFT JOIN orders o ON c.id = o.customer_id\nWHERE o.customer_id IS NULL;\n```"
        return REPLIES["HINT"]

    res = base.generate("list customers with no orders", "HINT", call=leaky)
    assert res.passed and res.attempts == 2 and not res.history[0]["passed"]


def test_bkt_ignores_emergency_success():
    assert bkt.update(0.4, "EMERGENCY", True).after == 0.4
    assert bkt.update(0.4, "HUMAN_FIRST", True).after > bkt.update(0.4, "GUIDED", True).after > 0.4
