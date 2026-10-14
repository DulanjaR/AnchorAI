import json

from components.c4_hcde.training import build_dataset, label_disclosure, split_dataset
from components.c4_hcde.training.compliance import check, split_probe
from components.c4_hcde.training.disclosure import score_reply, summarise_disclosure
from components.c4_hcde.training.tiers import (DISCLOSURE_BANDS, MODES, TIER_NAMES, control_system_prompt,
                                               rubric_system_prompt)

CODE = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(20)) + "\n```"


def test_control_prompt_is_short_and_rubric_is_long():
    for mode in MODES:
        assert len(control_system_prompt(mode)) < 120
        assert len(rubric_system_prompt(mode)) > len(control_system_prompt(mode))


def test_human_first_rejects_code_and_requires_question():
    assert not check("HUMAN_FIRST", "Try it yourself first. " + CODE).passed
    assert not check("HUMAN_FIRST", "Try it yourself first.").passed
    assert check("HUMAN_FIRST", "You've done this before. What is your first attempt?").passed


def test_hint_allows_one_step_only():
    assert check("HINT", "Think about what value you need to remember as you loop.").passed
    assert not check("HINT", "1. Do this\n2. Then this\n3. Then that").passed


def test_guided_needs_blanks_for_long_code():
    assert not check("GUIDED", "Here you go:\n" + CODE).passed
    assert check("GUIDED", "Fill in the TODO:\n" + CODE).passed


def test_shared_must_hand_back():
    assert not check("SHARED", "I did the whole thing for you. Done.").passed
    assert check("SHARED", "I wrote the first part. Your turn: how will you handle empty input?").passed


def test_probe_format():
    good = "Problem:\nWrite a function that returns the smallest of four numbers without min().\n\nAnswer key:\nKeep a running minimum."
    assert split_probe(good)[1] == "Keep a running minimum."
    assert check("PROBE", good).passed
    assert not check("PROBE", "Write a function that returns the smallest number.").passed


def test_disclosure_score_and_bands():
    ask = lambda prompt: json.dumps({"scores": [1, 0.5, 0, 0]})
    scores = score_reply("task", ["a", "b", "c", "d"], "reply", ask=ask)
    d = summarise_disclosure("GUIDED", scores)
    assert d["score"] == 0.375 and d["in_band"]
    assert not summarise_disclosure("HINT", [1, 1, 1, 1])["in_band"]
    lows = [DISCLOSURE_BANDS[t][0] for t in TIER_NAMES]
    assert lows == sorted(lows)


def test_mock_pipeline_splits_by_task(tmp_path):
    raw = tmp_path / "raw.jsonl"
    assert build_dataset.main(["--mock", "--limit", "20", "--out", str(raw)]) == 0
    assert label_disclosure.main(["--mock", "--raw", str(raw), "--elements", str(tmp_path / "el.json")]) == 0
    assert split_dataset.main(["--raw", str(raw), "--review", str(tmp_path / "none.csv"), "--out-dir", str(tmp_path)]) == 0
    splits = {name: {json.loads(line)["task_id"] for line in open(tmp_path / f"{name}.jsonl")}
              for name in ("train", "val", "test")}
    assert not (splits["train"] & splits["test"]) and not (splits["train"] & splits["val"])
    row = json.loads(open(tmp_path / "train.jsonl").readline())
    assert row["messages"][0]["content"] == control_system_prompt(row["tier"])
