"""Dry run of the Model 2 training code on a tiny random model (CPU, no download of model weights).

Skipped automatically when torch / transformers / peft are not installed or the tokenizer cannot be fetched.
"""
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
pytest.importorskip("peft")

DATA = Path(__file__).resolve().parents[1] / "data" / "generated" / "restart_summary_train.jsonl"


@pytest.fixture(scope="module")
def tok():
    try:
        t = transformers.AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
    except Exception as exc:  # offline or hub unavailable
        pytest.skip(f"tokenizer not available: {exc}")
    if t.pad_token is None:
        t.pad_token = t.eos_token
    return t


@pytest.fixture(scope="module")
def rows():
    if not DATA.exists():
        pytest.skip("generated data not found")
    return [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()][:12]


def test_prompt_is_masked_and_only_the_answer_is_trained(tok, rows):
    from components.c3_checkpointing.model2.lora_tools import encode_row

    row = rows[0]
    enc = encode_row(tok, row)
    kept = [t for t in enc["labels"] if t != -100]
    assert tok.decode(kept).strip().startswith(row["output"][:40])
    assert tok.decode(kept).strip().endswith("<|im_end|>")
    assert enc["labels"][0] == -100
    assert len(enc["input_ids"]) == len(enc["labels"]) == len(enc["attention_mask"])


def test_every_example_fits_in_the_context_window(tok):
    from components.c3_checkpointing.model2.lora_tools import encode_row

    all_rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]
    longest = max(len(encode_row(tok, r, max_len=10_000)["input_ids"]) for r in all_rows)
    assert longest < 1024, longest


def test_training_and_generation_run_end_to_end_on_a_tiny_model(tok, rows, tmp_path):
    from components.c3_checkpointing.model2.lora_tools import attach_lora, generate_batch, train

    cfg = transformers.Qwen2Config(vocab_size=len(tok), hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                                   num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=2048)
    model = transformers.Qwen2ForCausalLM(cfg)
    model = attach_lora(model, quantized=False)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    assert 0 < trainable < total

    trainer, info = train(model, tok, rows[:8], rows[8:12], str(tmp_path / "out"), epochs=1, batch_size=2, accum=1,
                          fp16=False, max_len=1024)
    assert info["n_train"] == 8 and info["n_val"] == 4
    assert info["train_loss"] == info["train_loss"] and info["train_loss"] < 1e3  # finite (not NaN)
    evals = [h["eval_loss"] for h in info["history"] if "eval_loss" in h]
    assert evals and all(l == l and l < 1e3 for l in evals)

    model.save_pretrained(str(tmp_path / "adapter"))
    assert (tmp_path / "adapter" / "adapter_config.json").exists()

    answers = generate_batch(model, tok, [r["messages"][:2] for r in rows[:3]], max_new_tokens=4, batch_size=2)
    assert len(answers) == 3 and all(isinstance(a, str) for a in answers)
