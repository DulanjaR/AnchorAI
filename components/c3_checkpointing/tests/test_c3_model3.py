import json
from pathlib import Path

from components.c3_checkpointing.model3.doc_data import TOPICS, generate_split, render_input
from components.c3_checkpointing.model3.doc_metrics import parse_json, rule_reader, score_example

DATA = Path(__file__).resolve().parents[1] / "data" / "generated"


def _norm(s):
    return " ".join(s.lower().split())


def test_topics_never_overlap_between_splits():
    assert not set(TOPICS["train"]) & set(TOPICS["val"])
    assert not set(TOPICS["train"]) & set(TOPICS["test"])
    assert not set(TOPICS["val"]) & set(TOPICS["test"])


def test_generation_is_reproducible_and_documents_are_unique():
    a, b = generate_split("val"), generate_split("val")
    assert [r["output"] for r in a] == [r["output"] for r in b]
    assert len({r["document"] for r in a}) == len(a)


def test_the_answer_only_uses_words_of_the_document_or_fixed_wording():
    for r in generate_split("val"):
        ans = r["answer"]
        assert _norm(ans["stopped_at"]["last_words"]) in _norm(r["document"])  # copied, never invented
        assert all(rem["from"] in ("your plan", "your headings") or rem["from"].startswith("usual structure for a ")
                   for rem in ans["remaining"])
        assert all(r["topic"] in q for q in ans["search_queries"])


def test_reference_answers_score_perfectly_on_the_core_checks():
    for r in generate_split("val"):
        s = score_example(r["output"], r)
        assert s["valid_json"] and s["section_ok"] and s["last_words_exact"] and s["grounded"] and s["remaining_f1"] == 1.0


def test_no_part_of_the_document_is_ever_written_by_the_answer():
    for r in generate_split("val"):
        ans = json.dumps(r["answer"]).lower()
        for line in r["document"].splitlines():
            if len(line.split()) > 12:  # a whole body sentence must not be repeated in the answer
                assert line.lower() not in ans


def test_rule_reader_fails_where_there_are_no_headings():
    rows = [r for r in generate_split("test") if r["variant"] == "headingless"]
    assert rows
    assert all(not score_example(json.dumps(rule_reader(r["document"])), r)["section_ok"] for r in rows)


def test_parse_json_handles_text_around_the_object_and_garbage():
    assert parse_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert parse_json("no json here") is None
    assert parse_json('{"broken": ') is None


def test_generated_files_match_the_generator():
    path = DATA / "doc_progress_test.jsonl"
    if not path.exists():
        return
    saved = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [r["output"] for r in saved] == [r["output"] for r in generate_split("test")]
    assert saved[0]["messages"][1]["content"] == render_input(saved[0]["document"])
