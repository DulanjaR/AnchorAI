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


def test_probe_rejects_copy_of_recent_task():
    seen = "Write a SQL query that finds products that have never been sold."
    copy = "Problem:\nWrite a SQL query that finds the products that have never been sold.\n\nAnswer key:\nLEFT JOIN sales, keep rows where sale is NULL."
    calls = []

    def fake(messages, temperature=0.2, **kw):
        calls.append(1)
        return copy if len(calls) == 1 else REPLIES["PROBE"]

    res = base.generate(seen, "PROBE", call=fake, avoid=[seen])
    assert res.passed and res.attempts == 2
    assert any("repeats a task" in r for r in res.history[0]["reasons"])


def test_partial_answer_keeps_mastery(monkeypatch):
    def fake(messages, temperature=0.2, **kw):
        if "grading" in messages[0]["content"]:
            return '{"result": "partial", "feedback": "Right idea, but write the full query."}'
        return fake_call(messages, temperature)

    monkeypatch.setattr(base.ollama_client, "chat", fake)
    c = TestClient(app)
    task = "Write a SQL query that lists students who are not enrolled in any course."
    r = c.post("/hcde/recommend", json={"user_id": "u2", "task": task}).json()
    c.post(f"/hcde/interactions/{r['interaction_id']}/respond", json={})
    c.post(f"/hcde/interactions/{r['interaction_id']}/outcome", json={"solved": True})
    p = c.post("/hcde/probes", json={"user_id": "u2"}).json()
    g = c.post(f"/hcde/probes/{p['probe_id']}/answer", json={"answer": "use a left join and IS NULL"}).json()
    assert g["result"] == "partial" and g["bkt"]["after"] == g["bkt"]["before"] and g["ledger"]["repaid"] == 0


def test_language_context_and_transfer_prior(monkeypatch):
    """Strong in loops in Python -> Java loops is tracked separately but starts from a transfer prior."""
    monkeypatch.setattr(base.ollama_client, "chat", fake_call)
    c = TestClient(app)
    py = ["Write a Python function that sums the numbers in a list using a for loop.",
          "Write a Python loop that prints every second element of a list.",
          "Write a Python function that counts the vowels in a string using a loop."]
    for t in py:
        r = c.post("/hcde/recommend", json={"user_id": "u3", "task": t}).json()
        assert r["context"] == "python"
        c.post(f"/hcde/interactions/{r['interaction_id']}/respond", json={"tier": "HUMAN_FIRST"})
        c.post(f"/hcde/interactions/{r['interaction_id']}/outcome", json={"solved": True})
    led = {(s["skill"], s["context"]): s for s in c.get("/hcde/users/u3/ledger").json()["skills"]}
    py_skill = next(k for k in led if k[1] == "python")
    assert led[py_skill]["mastery"] > 0.8

    j = c.post("/hcde/recommend", json={"user_id": "u3", "task": "Write a Java for loop that sums the numbers in an array."}).json()
    st = j["decision"]["skill_state"]
    assert j["context"] == "java" and st["observations"] == 0
    if j["skill"] == py_skill[0]:          # same concept, new language: transfer prior, not a cold start
        assert 0.3 < st["prior"] <= 0.75 and "Java" in (st["prior_note"] or "")
        assert "Java" in j["explanation"]
    led2 = {(s["skill"], s["context"]) for s in c.get("/hcde/users/u3/ledger").json()["skills"]}
    assert (j["skill"], "java") in led2 and py_skill in led2  # separate fading lines per language


GRADE_PARTIAL = ('{"result": "partial", "where": "the JOIN in your FROM clause", '
                 '"what": "an inner JOIN drops customers who have no orders, so the NULL filter never matches", '
                 '"fix": "use LEFT JOIN so every customer is kept", "why": ""}')
GRADE_PASS = '{"result": "pass", "where": "", "what": "", "fix": "", "why": "A LEFT JOIN keeps every customer and IS NULL keeps those without orders."}'


TEST_DB = ("```sql\nCREATE TABLE customers(id INTEGER, name TEXT);\nCREATE TABLE orders(id INTEGER, customer_id INTEGER);\n"
           "INSERT INTO customers VALUES (1,'Ann'),(2,'Ben'),(3,'Cal');\nINSERT INTO orders VALUES (10,1),(11,3);\n```")


def checking_call(messages, temperature=0.2, **kw):
    system = messages[0]["content"]
    if "SQLite test database" in system:
        return TEST_DB
    if "check a student's answer" in system:
        student = messages[1]["content"].split("Student answer:")[-1]
        return GRADE_PASS if "LEFT JOIN" in student.upper() else GRADE_PARTIAL
    return fake_call(messages, temperature)


def test_check_answer_respects_tier_and_verifies(monkeypatch):
    monkeypatch.setattr(base.ollama_client, "chat", checking_call)
    c = TestClient(app)
    task = "Write a SQL query that lists customers who have never placed an order."
    wrong = "SELECT c.name FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.id IS NULL;"

    # HINT: only WHERE to look, never the fix
    r = c.post("/hcde/recommend", json={"user_id": "u4", "task": task}).json()
    c.post(f"/hcde/interactions/{r['interaction_id']}/respond", json={"tier": "HINT"})
    k1 = c.post(f"/hcde/interactions/{r['interaction_id']}/check", json={"answer": wrong}).json()
    assert k1["result"] == "partial" and "JOIN in your FROM clause" in k1["feedback"]
    assert "LEFT JOIN" not in k1["feedback"] and "inner JOIN drops" not in k1["feedback"]
    # second try passes -> verified solved, but counted as solved-with-help (HINT) because it took 2 attempts
    k2 = c.post(f"/hcde/interactions/{r['interaction_id']}/check",
                json={"answer": wrong.replace("JOIN orders", "LEFT JOIN orders")}).json()
    assert k2["result"] == "pass" and k2["feedback"].startswith("✅") and "same" in k2["feedback"]  # proven by execution
    assert k2["outcome"]["verified"] and k2["attempt"] == 2 and k2["outcome"]["evidence_tier"] == "HINT"
    assert k2["outcome"]["ledger"]["borrowed"] == 0.35  # hint 0.25 + one corrective feedback 0.1

    # GUIDED reveals what is wrong but not the fix; EMERGENCY reveals the fix and a correct version
    for tier, must, must_not in [("GUIDED", "inner JOIN drops", "use LEFT JOIN"),
                                 ("EMERGENCY", "use LEFT JOIN", None)]:
        r = c.post("/hcde/recommend", json={"user_id": "u5", "task": task}).json()
        c.post(f"/hcde/interactions/{r['interaction_id']}/respond", json={"tier": tier})
        k = c.post(f"/hcde/interactions/{r['interaction_id']}/check", json={"answer": wrong}).json()
        assert must in k["feedback"]
        if must_not:
            assert must_not not in k["feedback"]
        else:
            assert "A correct version" in k["feedback"]


def test_python_syntax_error_is_exact():
    from components.c4_hcde.generation.check import python_syntax
    assert python_syntax("def f(x)\n    return x", "python").startswith("line 1")
    assert python_syntax("def f(x):\n    return x", "python") == ""
    assert python_syntax("I would use a loop", "python") == ""


def test_sql_execution_accepts_equivalent_answers():
    from components.c4_hcde.generation.sql_check import compare
    schema = TEST_DB.split("```sql")[1].split("```")[0]
    ref = "SELECT c.id, c.name FROM customers c LEFT JOIN orders o ON c.id = o.customer_id WHERE o.customer_id IS NULL;"
    ok = ["SELECT c.name FROM customers c LEFT JOIN orders o ON c.id = o.customer_id WHERE o.id IS NULL;",
          "SELECT name FROM customers WHERE id NOT IN (SELECT customer_id FROM orders)",
          "SELECT * FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)"]
    bad = ["SELECT c.name FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.id IS NULL",
           "SELECT name FROM customers"]
    assert all(compare("t", ref, a, schema)[0].status == "equal" for a in ok)
    assert all(compare("t", ref, a, schema)[0].status == "different" for a in bad)
    assert compare("t", ref, "SELECT nme FROM customers", schema)[0].status == "error"


def test_calibration_seeds_first_task_only():
    client = TestClient(app)
    task = "Explain the difference between TCP and UDP and when you would use each."
    user = "cal-user"
    c = client.get(f"/hcde/users/{user}/calibration", params={"task": task}).json()
    assert c["needs_calibration"] and [q["id"] for q in c["questions"]] == ["confidence", "experience", "preference"]
    low = client.post("/hcde/recommend", json={"user_id": user, "task": task,
                                               "calibration": {"confidence": 1, "experience": "never"}}).json()
    high = client.post("/hcde/recommend", json={"user_id": "cal-user-2", "task": task,
                                                "calibration": {"confidence": 5, "experience": "often"}}).json()
    p_low, p_high = low["decision"]["skill_state"]["prior"], high["decision"]["skill_state"]["prior"]
    assert p_low < bkt.prior_for(low["difficulty"]) < p_high
    assert "from your answers" in high["decision"]["skill_state"]["prior_note"]
    # answered once: not asked again for this subject
    assert not client.get(f"/hcde/users/{user}/calibration", params={"task": task}).json()["needs_calibration"]


def test_fitted_bkt_parameters_loaded():
    assert bkt.GUESS["EMERGENCY"] == 1.0  # design rule, never fitted
    assert bkt.GUESS["PROBE"] < bkt.GUESS["HUMAN_FIRST"] < bkt.GUESS["HINT"] < bkt.GUESS["GUIDED"] < bkt.GUESS["SHARED"]
    assert bkt.prior_for(1) > bkt.prior_for(3) > bkt.prior_for(5)
