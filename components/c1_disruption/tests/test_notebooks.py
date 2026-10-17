"""The Colab notebooks stay thin and valid (planning chat, 17 Oct 2026): a setup cell that clones
only once and installs only the notebook packages, a "cell 2" to restart from, progress lines,
charts labelled SYNTHETIC or REAL, code cells that parse, and no outputs committed."""
import ast
import json
from pathlib import Path

import pytest

NOTEBOOKS = sorted((Path(__file__).parents[1] / "notebooks").glob("*.ipynb"))
REQUIREMENTS = Path(__file__).parents[1] / "notebooks" / "requirements.txt"


def load(path):
    nb = json.loads(path.read_text(encoding="utf-8"))
    return nb, [c for c in nb["cells"] if c["cell_type"] == "code"]


def test_there_are_notebooks():
    assert [p.name for p in NOTEBOOKS] == ["01_model1_drift.ipynb", "02_model2_strategy.ipynb", "03_simulation_report.ipynb",
                                           "04_model1_cesaw.ipynb"]


def test_notebook_requirements_are_only_what_the_notebooks_need():
    names = [line.split("==")[0].split(">=")[0].strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert names == ["numpy", "scipy", "scikit-learn", "quantile-forest", "joblib", "pandas", "matplotlib"]


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook(path):
    nb, code = load(path)
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    assert all(c.get("id") for c in nb["cells"])  # nbformat 4.5 cell ids
    setup, cell2 = "".join(code[0]["source"]), "".join(code[1]["source"])
    # Cell 1: clone only if missing (no nested clone), absolute path, notebook packages only, restart message.
    assert '"git", "clone", "--depth", "1", "-b", "dev/ravindu"' in setup
    assert "if IN_COLAB and not os.path.isdir(ROOT)" in setup and '"/content/AnchorAI"' in setup
    assert "components/c1_disruption/notebooks/requirements.txt" in setup
    assert "components/c1_disruption/requirements.txt" not in setup  # not the web server's packages
    assert "Runtime → Restart session, then run from cell 2" in setup and "raise SystemExit" in setup
    # Cell 2: works on its own after a restart.
    assert "os.chdir(ROOT)" in cell2 and "sys.path.insert(0, ROOT)" in cell2 and "progress = Progress()" in cell2
    # Labelled data source, progress and charts.
    label = "REAL" if path.name == "04_model1_cesaw.ipynb" else "SYNTHETIC"
    first = "".join(nb["cells"][0]["source"])
    assert label in first and ("SYNTHETIC" in first) == (label == "SYNTHETIC")
    source = "".join("".join(c["source"]) for c in code)
    assert "progress" in source and "charts." in source
    for cell in code:
        text = "".join(cell["source"])
        ast.parse(text)  # plain Python only: no ! or % lines
        assert not cell["outputs"] and cell["execution_count"] is None, "commit notebooks without outputs"
    # Chart titles say SYNTHETIC / REAL: enforced by charts._check when the notebook runs.
    chart_cells = "".join("".join(c["source"]) for c in code if "charts." in "".join(c["source"]))
    assert label in chart_cells


def test_chart_titles_must_say_synthetic_or_real():
    pytest.importorskip("matplotlib")
    from components.c1_disruption.ml import charts

    with pytest.raises(ValueError, match="SYNTHETIC or REAL"):
        charts.learning_curve({}, "Model 1 learning curve")


def test_charts_draw(tmp_path):
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    from components.c1_disruption.ml import charts

    rows = [{"nFrom": 0, "nTo": 5, "maeMinutes": 9.0}, {"nFrom": 5, "nTo": None, "maeMinutes": 6.0}]
    figs = [
        charts.mae_by_method({"model": {"cold start": 9, "warm": 7}, "B0": {"cold start": 12, "warm": 12}}, "x (SYNTHETIC)"),
        charts.learning_curve({"model": rows}, "x (SYNTHETIC)"),
        charts.predicted_vs_actual([(60, 80, 75), (30, 25, 28)], "x (REAL)"),
        charts.gate_per_student({"P01": 1.0, "P02": 0.0}, "x (SYNTHETIC)"),
        charts.acceptance_over_time({"bandit": [1, 0, 1] * 10}, "x (SYNTHETIC)", window=5),
    ]
    for i, fig in enumerate(figs):
        fig.savefig(tmp_path / f"{i}.png")
    assert len(list(tmp_path.glob("*.png"))) == 5


def test_progress_prints_elapsed_seconds():
    from components.c1_disruption.ml.progress import Progress, say

    lines = []
    progress = Progress(out=lines.append)
    progress("training fold 3/5…")
    say(None, "nothing")  # no progress function: silent
    assert len(lines) == 1 and lines[0].startswith("[") and lines[0].endswith("s] training fold 3/5…")
