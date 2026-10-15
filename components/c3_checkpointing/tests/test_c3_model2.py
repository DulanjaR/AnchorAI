import json
import random
from pathlib import Path

import pytest

from components.c3_checkpointing.app.difficulty import predict_difficulty
from components.c3_checkpointing.app.summary import build_summary, summary_to_text
from components.c3_checkpointing.model2 import metrics
from components.c3_checkpointing.model2.textutils import cap, sentence, to_you
from components.c3_checkpointing.model2.generate_data import (
    QUOTA, SYSTEM_PROMPT, frame_vocabulary, generate_split,
)
from components.c3_checkpointing.model2.scenarios import FAMILIES


@pytest.fixture(scope="module")
def data():
    rows = {s: generate_split(s, random.Random(42 + i)) for i, s in enumerate(("train", "val", "test"))}
    vocab = set(frame_vocabulary(rows["train"]))
    return rows, vocab


def test_first_person_becomes_second_person():
    assert to_you("how do i keep the selected room?") == "how do you keep the selected room?"
    assert to_you("i cannot decide, my laptop fails") == "you cannot decide, your laptop fails"
    assert to_you("i am not sure and i was late") == "you are not sure and you were late"
    assert to_you("replace the links with my real profiles") == "replace the links with your real profiles"
    assert to_you("the Wi-Fi is fine") == "the Wi-Fi is fine"


def test_capitalisation_and_sentence_helpers():
    assert cap("how do you sort?") == "How do you sort?"
    assert cap("contact.html is broken") == "contact.html is broken"
    assert cap("FR12 is missing") == "FR12 is missing"
    assert sentence("add a button;") == "add a button."
    assert sentence("is it safe?") == "is it safe?"


def test_splits_use_different_task_families(data):
    rows, _ = data
    fam = {s: {r["family"] for r in rows[s]} for s in rows}
    assert not (fam["train"] & fam["test"]) and not (fam["train"] & fam["val"]) and not (fam["val"] & fam["test"])


def test_levels_are_balanced_and_match_the_rule(data):
    rows, _ = data
    for split, rs in rows.items():
        for level in ("Low", "Medium", "High"):
            assert sum(1 for r in rs if r["level"] == level) == QUOTA[split]
        for r in rs:
            f = r["fields"]
            assert predict_difficulty(r["minutes"], r["complexity"], len(f["open_items"]), r["interruption_type"])["level"] == r["level"]


def test_no_duplicate_inputs_across_the_data(data):
    rows, _ = data
    inputs = [r["input"] for rs in rows.values() for r in rs]
    assert len(inputs) == len(set(inputs))


def test_messages_are_well_formed(data):
    rows, _ = data
    for r in rows["val"]:
        roles = [m["role"] for m in r["messages"]]
        assert roles == ["system", "user", "assistant"]
        assert r["messages"][0]["content"] == SYSTEM_PROMPT
        assert r["messages"][1]["content"] == r["input"] and r["messages"][2]["content"] == r["output"]
        assert r["synthetic"] is True


def test_reference_outputs_are_grounded_advice_free_and_follow_the_depth_policy(data):
    rows, vocab = data
    for split in ("train", "val", "test"):
        for r in rows[split]:
            s = metrics.score_example(r["output"], r, vocab)
            assert s["grounded_ok"], (r["id"], metrics.grounding(r["output"], r["input"], vocab)["ungrounded"])
            assert s["no_advice"], (r["id"], s["advice"])
            assert s["policy_ok"], (r["id"], metrics.depth_policy(r["output"], r["fields"], r["level"]))
            assert s["question_ok"] in (None, True), r["id"]
            assert s["second_person_ok"], (r["id"], metrics.first_person_words(r["output"]))
            assert s["length_ok"] and s["rouge_l"] == pytest.approx(1.0)


def test_summary_length_grows_with_level(data):
    rows, _ = data
    mean = {l: sum(len(r["output"].split()) for r in rows["train"] if r["level"] == l) / QUOTA["train"] for l in ("Low", "Medium", "High")}
    assert mean["Low"] < mean["Medium"] < mean["High"]


def test_metrics_catch_advice_new_facts_and_answers(data):
    rows, vocab = data
    r = next(x for x in rows["test"] if x["level"] == "Medium" and (x["fields"].get("problem") or "").endswith("?"))
    bad = r["output"] + " You should try using a different framework, for example Django, and make sure to add tests."
    s = metrics.score_example(bad, r, vocab)
    assert not s["no_advice"] and not s["grounded_ok"]
    assert metrics.question_handling(bad, r["fields"], "Medium", r["input"])["answered"] is True
    assert metrics.advice_hits("```python\nprint(1)\n```")


def test_metrics_catch_wrong_depth(data):
    rows, vocab = data
    r = next(x for x in rows["test"] if x["level"] == "High" and x["fields"].get("goal") and x["fields"].get("completed"))
    low_like = f'You stopped at {r["fields"]["working_point"]}. Your next step is to {r["fields"]["next_step"]}.'
    assert metrics.depth_policy(low_like, r["fields"], "High")["ok"] is False
    long_for_low = next(x for x in rows["test"] if x["level"] == "Low" and x["fields"].get("goal"))
    leaked = long_for_low["output"] + f' Your goal is to {long_for_low["fields"]["goal"]}.'
    assert "goal" in metrics.depth_policy(leaked, long_for_low["fields"], "Low")["leaked"]


def test_words_the_student_wrote_are_not_counted_as_advice():
    assert metrics.advice_hits("You were using the uml class diagram.", "Resources: uml class diagram") == []
    assert metrics.advice_hits("You were using the uml class diagram.", "") != []


def test_first_person_left_in_a_summary_is_detected():
    assert metrics.first_person_words("You stopped at the cart. I need to fix my query.") == ["i", "my"]
    assert metrics.first_person_words("You need to fix your query.") == []


def test_depth_check_accepts_the_template_wording_for_open_items(data):
    rows, _ = data
    r = next(x for x in rows["test"] if x["level"] == "High" and len(x["fields"]["open_items"]) >= 2 and x["fields"].get("goal"))
    f = r["fields"]
    template = "Open items found in your own files: " + "; ".join(f["open_items"])
    full = " ".join(filter(None, [f.get("goal"), f.get("completed"), f.get("working_point"), f.get("problem"),
                                  f.get("next_step"), f.get("resources"), template]))
    assert metrics.depth_policy(full, f, "High")["ok"]


def test_rouge_l_basic():
    assert metrics.rouge_l("a b c d", "a b c d") == pytest.approx(1.0)
    assert metrics.rouge_l("a b c d", "x y z") == 0.0
    assert 0 < metrics.rouge_l("a b c d", "a x c d") < 1


def test_template_baseline_is_grounded_but_uses_a_different_format(data):
    rows, vocab = data
    r = next(x for x in rows["test"] if x["level"] == "High")
    f = r["fields"]
    cp = {"goal": f.get("goal"), "completed": f.get("completed"), "workingPoint": f.get("working_point"),
          "problem": f.get("problem"), "nextStep": f.get("next_step"), "resources": f.get("resources"), "openItems": f["open_items"]}
    text = summary_to_text(build_summary("T", cp, "High", 300))
    assert metrics.advice_hits(text) == []
    assert metrics.rouge_l(text, r["output"]) < 1.0


def test_committed_data_files_match_the_generator():
    path = Path(__file__).resolve().parents[1] / "data" / "generated" / "restart_summary_test.jsonl"
    if not path.exists():
        pytest.skip("data not generated")
    committed = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    fresh = generate_split("test", random.Random(44))
    assert [c["input"] for c in committed] == [f["input"] for f in fresh]
    assert len({c["family"] for c in committed}) == len([n for n, f in FAMILIES.items() if f["split"] == "test"])
