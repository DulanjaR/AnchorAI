# notebooks (Google Colab)

Experiments only. Notebooks call code in `ml/` and `sim/`; they hold no logic of their own, so
everything they compute is also covered by pytest. Every result and chart made from synthetic data
is labelled **SYNTHETIC**, from CESAW **REAL** (CLAUDE.md rule 6; `ml/charts.py` refuses a chart
title without one of them). Commit them without outputs (a test checks).

C1 has **two ML models**; the four notebooks are experiments on them:

| Notebook | Model | What it shows |
|---|---|---|
| `01_model1_drift.ipynb` | Model 1 | one training run step by step; Model 1 vs baselines B0–B3 (cold start, warm); charts: MAE by method, learning curve, predicted vs actual minutes, earned-trust gate per persona; saves the format-2 model for the API (SYNTHETIC) |
| `02_model2_strategy.ipynb` | Model 2 | strategy distinctness; simulated decisions per policy; chart: acceptance over time per policy (SYNTHETIC; accept rates are assumptions) |
| `03_simulation_report.ipynb` | both + engine | the whole component on all variants × seeds → the markdown report; charts per variant (SYNTHETIC) |
| `04_model1_cesaw.ipynb` | Model 1 | external validation on REAL data (CESAW, professional developers); `QUICK = True` (default) is a short preview, the committed results file uses the full run |

## Running in Colab

1. *File → Open notebook → GitHub* (or upload the file).
2. Run **cell 1**. It clones `dev/ravindu` into `/content/AnchorAI` only if it is not there yet,
   installs only `notebooks/requirements.txt` (numpy, scipy, scikit-learn, quantile-forest, joblib,
   pandas, matplotlib — no web server) and prints the versions.
3. If it says **"Runtime → Restart session, then run from cell 2"** (a package such as numpy was
   replaced while loaded), do exactly that: restart, then run from cell 2 onward.
4. Every long step prints a progress line with elapsed seconds, e.g. `[  12.4s] training fold 3/5…`.
   Files the notebooks write (the model, the report) go to `/content/c1_outputs`; notebook 01
   downloads the model files.

Outside Colab, cell 1 uses the repository the notebook is in and installs nothing; outputs go to the
system temp folder (`c1_outputs`). Supported Python: 3.11–3.13.
