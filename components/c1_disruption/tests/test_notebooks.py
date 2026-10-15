"""The Colab notebooks stay thin and valid: setup cell first, code cells parse."""
import ast
import json
from pathlib import Path

import pytest

NOTEBOOKS = sorted((Path(__file__).parents[1] / "notebooks").glob("*.ipynb"))


def test_there_are_notebooks():
    assert [p.name for p in NOTEBOOKS] == ["01_model1_drift.ipynb", "02_model2_strategy.ipynb", "03_simulation_report.ipynb",
                                                  "04_model1_cesaw.ipynb"]


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook(path):
    nb = json.loads(path.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    setup = "".join(code[0]["source"])
    assert "git clone --depth 1 -b dev/ravindu" in setup
    assert "pip install -q -r components/c1_disruption/requirements.txt" in setup
    # Notebooks on real data say REAL (never SYNTHETIC); all others say SYNTHETIC.
    label = "REAL" if path.name == "04_model1_cesaw.ipynb" else "SYNTHETIC"
    first = "".join(nb["cells"][0]["source"])
    assert label in first
    assert ("SYNTHETIC" in first) == (label == "SYNTHETIC")
    for cell in code:
        # Shell (!) and magic (%) lines are Colab-only; the rest must be valid Python.
        source = "".join(line for line in cell["source"] if not line.lstrip().startswith(("!", "%")))
        ast.parse(source)
        assert not cell["outputs"], "commit notebooks without outputs"
