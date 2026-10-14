"""LoRA training and generation helpers for Model 2.

This file is used twice: the Colab notebooks include its source, and the local tests run the same code
on a tiny random model, so a mistake here is caught before any GPU time is spent.
"""
import inspect
import time

import torch
from torch.utils.data import Dataset
from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments, set_seed

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def encode_row(tok, row, max_len=1024):
    """Tokenise one chat example; only the assistant answer is trained on (the prompt is masked with -100)."""
    prompt = tok.apply_chat_template(row["messages"][:2], tokenize=False, add_generation_prompt=True)
    full = tok.apply_chat_template(row["messages"], tokenize=False)
    if not full.startswith(prompt):
        raise ValueError("chat template does not start with the prompt for " + row.get("id", "?"))
    prompt_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    full_ids = tok(full, add_special_tokens=False)["input_ids"]
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]
    n = min(len(full_ids), max_len)
    return {"input_ids": full_ids[:n], "attention_mask": [1] * n, "labels": labels[:n]}


class ListDataset(Dataset):
    def __init__(self, items):
        self.items = items

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def attach_lora(model, quantized, r=16, alpha=32, dropout=0.05):
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    if quantized:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    config = LoraConfig(r=r, lora_alpha=alpha, lora_dropout=dropout, bias="none", task_type="CAUSAL_LM",
                        target_modules=LORA_TARGETS)
    return get_peft_model(model, config)


def training_arguments(output_dir, epochs, lr, batch_size, accum, has_eval, fp16, seed):
    kwargs = dict(
        output_dir=output_dir, num_train_epochs=epochs, per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size, gradient_accumulation_steps=accum, learning_rate=lr,
        lr_scheduler_type="cosine", warmup_steps=5, logging_steps=5, save_strategy="no", report_to="none",
        fp16=fp16, seed=seed, remove_unused_columns=False,
    )
    if has_eval:
        accepted = inspect.signature(TrainingArguments.__init__).parameters
        kwargs["eval_strategy" if "eval_strategy" in accepted else "evaluation_strategy"] = "epoch"
    return TrainingArguments(**kwargs)


def train(model, tok, train_rows, val_rows, out_dir, epochs=5, lr=2e-4, batch_size=4, accum=4, fp16=True,
          max_len=1024, seed=42):
    set_seed(seed)
    train_items = [encode_row(tok, r, max_len) for r in train_rows]
    val_items = [encode_row(tok, r, max_len) for r in val_rows]
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    args = training_arguments(out_dir, epochs, lr, batch_size, accum, bool(val_items), fp16, seed)
    trainer = Trainer(model=model, args=args, train_dataset=ListDataset(train_items),
                      eval_dataset=ListDataset(val_items) if val_items else None, data_collator=collator)
    model.config.use_cache = False
    start = time.time()
    result = trainer.train()
    model.config.use_cache = True
    info = {
        "seconds": round(time.time() - start, 1), "train_loss": float(result.training_loss),
        "epochs": epochs, "learning_rate": lr, "batch_size": batch_size, "grad_accumulation": accum,
        "max_len": max_len, "seed": seed, "n_train": len(train_items), "n_val": len(val_items),
        "longest_example_tokens": max(len(i["input_ids"]) for i in train_items),
        "history": trainer.state.log_history,
    }
    return trainer, info


@torch.no_grad()
def generate_batch(model, tok, message_lists, max_new_tokens=300, batch_size=8):
    """Greedy generation for a list of chat prompts (system + user messages); returns the answers."""
    model.eval()
    tok.padding_side = "left"
    answers = []
    for i in range(0, len(message_lists), batch_size):
        chunk = message_lists[i:i + batch_size]
        prompts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in chunk]
        enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tok.pad_token_id)
        for j in range(len(chunk)):
            new_tokens = out[j][enc["input_ids"].shape[1]:]
            answers.append(tok.decode(new_tokens, skip_special_tokens=True).strip())
    return answers
