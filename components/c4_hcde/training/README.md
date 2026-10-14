# HCDE training: the assistance-calibrated model

We fine-tune an open-weight model (Qwen2.5-7B-Instruct, QLoRA) to learn two behaviours from a
short tag in the system prompt:

1. **Assistance tiers**: `Assistance tier: HUMAN_FIRST | HINT | GUIDED | SHARED | EMERGENCY`.
   The model must reveal more of the solution as the tier rises, from nothing to everything.
2. **Probes**: `Mode: PROBE` writes a short unaided check on the same skill, with a new surface,
   plus an answer key. The Capability Ledger uses probes to verify that a student can now do a
   task alone.

How much a reply gives away is measured by the **Solution Disclosure Score (SDS)**, 0-1, against
the task's full reference solution (`disclosure.py`). Each tier has a target band
(`tiers.DISCLOSURE_BANDS`).

## Files

| File | Purpose |
| --- | --- |
| `tiers.py` | Tier rules, disclosure bands, probe rules, and the three prompt styles (short tag, full rubric, teacher) |
| `data/seed_tasks.jsonl` | 100 IT tasks across 8 modules, difficulty 1-5 |
| `data/transfer_tasks.jsonl` | 20 Business Management and workplace tasks, **test only**, never trained on |
| `build_dataset.py` | Teacher model writes every task x (5 tiers + probe) |
| `compliance.py` | Fast rule checks per tier (code in low tiers, length, hand-back, probe format) |
| `disclosure.py`, `label_disclosure.py` | Solution Disclosure Score with an LLM judge |
| `review_sample.py` | CSV of flagged replies + a 10% sample for manual review |
| `split_dataset.py` | Applies your verdicts, splits by task (75 / 10 / 15), stratified by module |
| `train_qlora.py` | QLoRA training, loss on the reply only |
| `evaluate.py` | 3 conditions: base + tag, base + full rubric, fine-tuned + tag |
| `export_gguf.py` | Merge + quantise to GGUF for Ollama |
| `kaggle_train.ipynb` | Runs train, evaluate and export on a free Kaggle T4 |

## Runbook

### 1. Generate the data (your Mac, from the repo root)

The data scripts use only the Python standard library. Use an **open-weight** teacher: the
terms of ChatGPT and Claude restrict using their outputs to train other models.

```bash
# Groq (free tier)
export TEACHER_BASE_URL=https://api.groq.com/openai/v1
export TEACHER_API_KEY=...            # your key
export TEACHER_MODEL=llama-3.3-70b-versatile

# or OpenRouter
# export TEACHER_BASE_URL=https://openrouter.ai/api/v1
# export TEACHER_MODEL=qwen/qwen-2.5-72b-instruct

M=components.c4_hcde.training
D=components/c4_hcde/training/data

python3 -m $M.build_dataset                       # 600 replies; rerun to resume or retry failures
python3 -m $M.label_disclosure                    # disclosure score for every tier reply
python3 -m $M.review_sample                       # -> data/dataset/review.csv

python3 -m $M.build_dataset --seed $D/transfer_tasks.jsonl --out $D/dataset/transfer_raw.jsonl
python3 -m $M.label_disclosure --raw $D/dataset/transfer_raw.jsonl --elements $D/dataset/transfer_elements.json
```

If you hit rate limits, add `--workers 1`.

### 2. Review (about 1 hour)

Open `data/dataset/review.csv`. For each row set `verdict` to `keep`, `fix` (and paste a
corrected reply into `fixed_reply`) or `reject`. Check above all that low tiers do not leak the
answer and that the code in EMERGENCY replies is correct. Then:

```bash
python3 -m $M.split_dataset
git add components/c4_hcde/training/data && git commit -m "HCDE training data" && git push
```

### 3. Train, evaluate, export (Kaggle)

Upload `kaggle_train.ipynb` to Kaggle, turn on GPU T4 x1 and Internet, add the secrets listed
in its first cell, and run all cells in order. Download `hcde-results.zip` and the `gguf` folder.

### 4. Run it on your Mac

```bash
cd ~/Downloads/gguf
ollama create hcde -f Modelfile
ollama run hcde
```

## What the evaluation must show

- **Tier compliance**: `tuned_tag` beats `base_tag` clearly and matches or beats `base_rubric`,
  with a prompt about 20 times shorter.
- **Disclosure rises with tier**: mean SDS goes up from Human First to Emergency, with most
  replies inside their band.
- **Transfer**: the same pattern holds on the 20 non-IT tasks. That shows the model learned to
  control how much it helps, rather than memorising IT answers.
- **Correctness**: judge scores for correctness do not drop after fine-tuning.

If fine-tuning does not beat the full-rubric prompt, report that as a finding. The next step
is DPO on disclosure targets (after 17 Oct).
