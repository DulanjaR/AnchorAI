"""QLoRA fine-tuning of the tier-calibrated generator.

Uses plain transformers + peft (no TRL), so it does not break when a hosted notebook
ships a newer library version. Loss is computed on the assistant reply only.

Kaggle / Colab (one T4 or better), from the repo root:

    python -m components.c4_hcde.training.train_qlora \
        --base-model Qwen/Qwen2.5-7B-Instruct --out runs/hcde-qwen7b

Defaults fit a 15 GB T4 (batch 1 x 16 accumulation). Still out of memory: --max-len 768,
or --base-model Qwen/Qwen2.5-3B-Instruct.
CPU smoke test (no GPU, tiny model, 4-bit off):

    python -m components.c4_hcde.training.train_qlora --base-model sshleifer/tiny-gpt2 \
        --no-4bit --max-steps 2 --out /tmp/smoke
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data" / "dataset"

FALLBACK_TEMPLATE = (
    "{% for m in messages %}<|{{ m['role'] }}|>\n{{ m['content'] }}\n{% endfor %}"
    "{% if add_generation_prompt %}<|assistant|>\n{% endif %}"
)


def load_rows(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _new_transformers() -> bool:
    import transformers

    return int(transformers.__version__.split(".")[0]) >= 5


def make_training_args(cls, **kwargs):
    """Build TrainingArguments across transformers versions: drop arguments a version does not know."""
    import inspect

    known = set(inspect.signature(cls.__init__).parameters)
    unknown = sorted(k for k in kwargs if k not in known)
    if unknown:
        print(f"note: this transformers version ignores {unknown}")
    return cls(**{k: v for k, v in kwargs.items() if k in known})


def encode(tokenizer, messages: list[dict], max_len: int) -> dict:
    """Token ids for the whole chat, with labels masked to the assistant reply."""
    prompt_ids = tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True, tokenize=True)
    full_ids = tokenizer.apply_chat_template(messages, tokenize=True)
    if hasattr(prompt_ids, "input_ids"):  # newer tokenizers may return a BatchEncoding
        prompt_ids, full_ids = prompt_ids["input_ids"], full_ids["input_ids"]
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError("chat template is not prefix-stable; cannot mask the prompt reliably")
    if tokenizer.eos_token_id is not None and full_ids[-1] != tokenizer.eos_token_id:
        full_ids = full_ids + [tokenizer.eos_token_id]
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]
    full_ids, labels = full_ids[:max_len], labels[:max_len]
    return {"input_ids": full_ids, "attention_mask": [1] * len(full_ids), "labels": labels}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--train", type=Path, default=DATA / "train.jsonl")
    ap.add_argument("--val", type=Path, default=DATA / "val.jsonl")
    ap.add_argument("--out", type=Path, default=Path("runs/hcde-adapter"))
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--max-steps", type=int, default=-1, help="override epochs (smoke tests)")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--lora-dropout", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-4bit", action="store_true", help="full-precision LoRA (CPU smoke tests)")
    args = ap.parse_args(argv)

    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    # Use one GPU. With two visible (Kaggle "T4 x2") the Trainer wraps the model in DataParallel,
    # which copies the 4-bit model and gathers the huge output tensor on GPU 0 -> out of memory.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq, Trainer,
                              TrainingArguments, set_seed)

    set_seed(args.seed)
    cuda = torch.cuda.is_available()
    bf16 = cuda and torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if bf16 else torch.float16

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.chat_template is None:
        tokenizer.chat_template = FALLBACK_TEMPLATE
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_rows, val_rows = load_rows(args.train), load_rows(args.val)
    train_ds = [encode(tokenizer, r["messages"], args.max_len) for r in train_rows]
    val_ds = [encode(tokenizer, r["messages"], args.max_len) for r in val_rows]
    lengths = sorted(len(x["input_ids"]) for x in train_ds)
    truncated = sum(1 for r in train_rows if len(encode(tokenizer, r["messages"], 10**9)["input_ids"]) > args.max_len)
    print(f"train {len(train_ds)} / val {len(val_ds)} examples; tokens median {lengths[len(lengths)//2]}, "
          f"max {lengths[-1]}; truncated {truncated}")

    load_kwargs: dict = {}
    use_4bit = cuda and not args.no_4bit
    if use_4bit:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype)
        load_kwargs["device_map"] = {"": 0}
        load_kwargs["dtype" if _new_transformers() else "torch_dtype"] = compute_dtype
    model = AutoModelForCausalLM.from_pretrained(args.base_model, **load_kwargs)
    if use_4bit:
        # Not peft's prepare_model_for_kbit_training: it casts the embedding and output layers
        # (~1B weights for Qwen's 152k vocabulary) to float32, ~4 GB extra, which does not fit a T4.
        model.config.use_cache = False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()

    # All linear projections of the transformer blocks; falls back to whatever exists.
    wanted = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    names = {n.split(".")[-1] for n, _ in model.named_modules()}
    targets = [t for t in wanted if t in names] or ["c_attn", "c_proj"]
    model = get_peft_model(model, LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
        target_modules=targets, bias="none", task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

    steps_per_epoch = math.ceil(len(train_ds) / (args.batch_size * args.grad_accum))
    total_steps = args.max_steps if args.max_steps > 0 else math.ceil(steps_per_epoch * args.epochs)
    targs = make_training_args(
        TrainingArguments,
        output_dir=str(args.out / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        lr_scheduler_type="cosine",
        warmup_steps=max(1, round(total_steps * 0.05)),
        weight_decay=0.0,
        logging_steps=max(1, steps_per_epoch // 4),
        eval_strategy="epoch" if args.max_steps < 0 else "no",
        save_strategy="epoch" if args.max_steps < 0 else "no",
        save_total_limit=1,
        load_best_model_at_end=args.max_steps < 0,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        gradient_checkpointing=use_4bit,
        gradient_checkpointing_kwargs={"use_reentrant": False} if use_4bit else None,
        bf16=bf16,
        fp16=cuda and not bf16,
        optim="paged_adamw_8bit" if use_4bit else "adamw_torch",
        report_to="none",
        seed=args.seed,
        use_cpu=not cuda,
    )
    trainer = Trainer(
        model=model, args=targs, train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100),
    )
    t0 = time.time()
    trainer.train()
    metrics = trainer.evaluate() if val_ds else {}

    adapter_dir = args.out / "adapter"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    meta = {
        "base_model": args.base_model, "train_examples": len(train_ds), "val_examples": len(val_ds),
        "max_len": args.max_len, "epochs": args.epochs, "max_steps": args.max_steps, "lr": args.lr,
        "effective_batch": args.batch_size * args.grad_accum, "lora": {"r": args.lora_r, "alpha": args.lora_alpha,
        "dropout": args.lora_dropout, "targets": targets}, "quantized_4bit": use_4bit,
        "eval": metrics, "train_minutes": round((time.time() - t0) / 60, 1),
        "log_history": trainer.state.log_history,
    }
    (args.out / "training_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(f"Saved adapter to {adapter_dir} (eval loss {metrics.get('eval_loss')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
