"""Restart-summary generators: the rule-based template (default) and the fine-tuned Qwen model (Model 2).

The learned model sits behind a safety net. Its answer is checked with the same rules used in the evaluation
(grounded in the checkpoint, no advice or code, right depth, questions kept and not answered). If any check
fails, or the model is not installed, the template summary is returned instead and the reason is reported.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..model2 import metrics
from ..model2.generate_data import SYSTEM_PROMPT, render_input
from .difficulty import format_minutes
from .summary import build_summary, summary_to_text

ROOT = Path(__file__).resolve().parents[1]
FRAME_VOCAB_FILE = ROOT / "data" / "generated" / "frame_vocab.json"
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def frame_vocab() -> set[str]:
    try:
        return set(json.loads(FRAME_VOCAB_FILE.read_text(encoding="utf-8"))["frame_vocab"])
    except (OSError, KeyError, ValueError):
        return set()


def to_training_fields(cp: dict) -> dict:
    """camelCase checkpoint (API) -> the field names used when the model was trained."""
    return {
        "goal": cp.get("goal") or None,
        "completed": cp.get("completed") or None,
        "working_point": cp.get("workingPoint") or None,
        "problem": cp.get("problem") or None,
        "next_step": cp.get("nextStep") or None,
        "resources": cp.get("resources") or None,
        "open_items": list(cp.get("openItems") or []),
    }


def build_model_input(title: str, kind: str, cp: dict, level: str, away_minutes: float) -> tuple[str, dict]:
    fields = to_training_fields(cp)
    return render_input(title, kind, level, format_minutes(away_minutes), fields), fields


def template_text(title: str, cp: dict, level: str, away_minutes: float) -> str:
    return summary_to_text(build_summary(title, cp, level, away_minutes))


def check_model_output(output: str, input_text: str, fields: dict, level: str) -> list[str]:
    """Return the reasons why an output must not be shown (empty list = it may be shown)."""
    problems = []
    if not output.strip():
        return ["empty answer"]
    g = metrics.grounding(output, input_text, frame_vocab())
    if g["rate"] > 0.02:
        problems.append("contains words that are not in the checkpoint: " + ", ".join(g["ungrounded"][:5]))
    if metrics.advice_hits(output, input_text):
        problems.append("contains advice, code or an answer")
    if not metrics.depth_policy(output, fields, level)["ok"]:
        problems.append("does not follow the depth rule for " + level)
    q = metrics.question_handling(output, fields, level, input_text)
    if q is not None and not q["ok"]:
        problems.append("does not keep the student's question as an open question")
    return problems


class LoraGenerator:
    """Qwen2.5-1.5B-Instruct plus the LoRA adapter trained in notebook 06 (loaded on first use)."""

    def __init__(self, adapter_path: str | None = None, model=None, tokenizer=None, max_new_tokens: int = 300):
        self.adapter_path = adapter_path
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens

    @classmethod
    def from_env(cls) -> LoraGenerator | None:
        path = os.environ.get("C3_LORA_PATH", "").strip()
        return cls(adapter_path=path) if path and Path(path).exists() else None

    def _load(self) -> None:
        if self.model is not None:
            return
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self.tokenizer = AutoTokenizer.from_pretrained(self.adapter_path)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        if torch.cuda.is_available():
            quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                                       bnb_4bit_compute_dtype=torch.float16)
            base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, quantization_config=quant, device_map="auto")
        else:
            base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.float32)
        self.model = PeftModel.from_pretrained(base, self.adapter_path)
        self.model.eval()

    def generate(self, input_text: str) -> str:
        self._load()
        from ..model2.lora_tools import generate_batch

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": input_text}]
        return generate_batch(self.model, self.tokenizer, [messages], max_new_tokens=self.max_new_tokens, batch_size=1)[0]


_lora_cache: dict = {}


def get_lora() -> LoraGenerator | None:
    if "gen" not in _lora_cache:
        _lora_cache["gen"] = LoraGenerator.from_env()
    return _lora_cache["gen"]


def generate_summary(mode: str, title: str, kind: str, cp: dict, level: str, away_minutes: float,
                     lora: LoraGenerator | None = None) -> dict:
    """Returns {"text", "mode" (what was actually used), "fallback_reason"}."""
    template = template_text(title, cp, level, away_minutes)
    if mode != "lora":
        return {"text": template, "mode": "template", "fallback_reason": None}

    gen = lora if lora is not None else get_lora()
    if gen is None:
        return {"text": template, "mode": "template", "fallback_reason": "The fine-tuned model is not installed on this server."}
    input_text, fields = build_model_input(title, kind, cp, level, away_minutes)
    try:
        output = gen.generate(input_text).strip()
    except Exception as exc:  # model or library problem: never break the screen
        return {"text": template, "mode": "template", "fallback_reason": f"The model could not run ({type(exc).__name__})."}
    problems = check_model_output(output, input_text, fields, level)
    if problems:
        return {"text": template, "mode": "template", "fallback_reason": "Model answer rejected: " + "; ".join(problems)}
    return {"text": output, "mode": "lora", "fallback_reason": None}
