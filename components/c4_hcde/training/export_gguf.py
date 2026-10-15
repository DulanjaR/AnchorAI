"""Merge the QLoRA adapter into the base model and export a quantised GGUF for Ollama.

Run on Kaggle after training (needs about 30 GB of disk and the notebook's RAM):

    python -m components.c4_hcde.training.export_gguf \
        --base-model Qwen/Qwen2.5-7B-Instruct --adapter runs/hcde-qwen7b/adapter --out runs/gguf

Produces ``hcde-q4_k_m.gguf`` (about 4.7 GB for 7B) and a ``Modelfile``. On your Mac:

    ollama create hcde -f Modelfile      # from the folder holding both files
    ollama run hcde

Steps: merge in float16 -> llama.cpp convert_hf_to_gguf.py (f16) -> llama-quantize (Q4_K_M).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

MODELFILE = """FROM ./{gguf}

# Qwen2.5 chat format (ChatML). The system prompt carries the tier tag, e.g.
# "You are the Anchor AI study assistant for university students.\\nAssistance tier: HINT"
TEMPLATE \"\"\"{{{{- if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{- range .Messages }}}}<|im_start|>{{{{ .Role }}}}
{{{{ .Content }}}}<|im_end|>
{{{{ end }}}}<|im_start|>assistant
\"\"\"
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
PARAMETER temperature 0.3
PARAMETER num_ctx 4096
"""


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=cwd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("runs/gguf"))
    ap.add_argument("--quant", default="Q4_K_M")
    ap.add_argument("--llama-cpp", type=Path, default=Path("/kaggle/working/llama.cpp"))
    ap.add_argument("--keep-merged", action="store_true", help="keep the merged float16 model folder")
    ap.add_argument("--work-dir", type=Path, default=Path("/tmp/hcde-export"),
                    help="scratch space for the ~15 GB merged model and ~15 GB f16 GGUF (Kaggle's "
                         "/kaggle/working is limited to 20 GB, so these must not go there)")
    args = ap.parse_args(argv)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from .train_qlora import _new_transformers

    merged = args.work_dir / "merged"
    args.out.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    print("merging adapter into base model (float16)...", flush=True)
    dtype_key = "dtype" if _new_transformers() else "torch_dtype"
    base = AutoModelForCausalLM.from_pretrained(args.base_model, **{dtype_key: torch.float16}, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(base, str(args.adapter)).merge_and_unload()
    model.save_pretrained(merged, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.adapter).save_pretrained(merged)
    del model, base

    lc = args.llama_cpp
    if not lc.exists():
        run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(lc)])
    # Use llama.cpp's own gguf-py instead of `pip install -r requirements`, which pins a CPU torch and
    # would break the GPU environment for the evaluation cells that run afterwards.
    run([sys.executable, "-m", "pip", "install", "-q", "sentencepiece", "protobuf"])
    env = dict(os.environ, PYTHONPATH=str(lc / "gguf-py") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    f16 = args.work_dir / "hcde-f16.gguf"
    cmd = [sys.executable, str(lc / "convert_hf_to_gguf.py"), str(merged), "--outfile", str(f16), "--outtype", "f16"]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)

    quantize = lc / "build" / "bin" / "llama-quantize"
    if not quantize.exists():
        run(["cmake", "-B", "build", "-DGGML_CUDA=OFF", "-DLLAMA_CURL=OFF"], cwd=lc)
        run(["cmake", "--build", "build", "--target", "llama-quantize", "-j", "4"], cwd=lc)
    name = f"hcde-{args.quant.lower()}.gguf"
    run([str(quantize), str(f16), str(args.out / name), args.quant])

    f16.unlink(missing_ok=True)
    if not args.keep_merged:
        shutil.rmtree(merged, ignore_errors=True)
    (args.out / "Modelfile").write_text(MODELFILE.format(gguf=name))
    print(f"\nDone: {args.out / name} and {args.out / 'Modelfile'}")
    print("Download both, put them in one folder on your Mac, then: ollama create hcde -f Modelfile")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
