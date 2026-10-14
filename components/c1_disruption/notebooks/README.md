# notebooks (Google Colab)

Experiments only. Notebooks call code in `ml/` and `sim/`; they hold no logic of their own, so
everything they show is also covered by pytest. Every result made from synthetic data is
labelled **SYNTHETIC** (CLAUDE.md rule 6). Commit them without outputs (a test checks).

| Notebook | What |
|---|---|
| `01_model1_drift.ipynb` | Model 1 vs baselines B0–B3: cold start, warm, coverage, learning curve |
| `02_model2_strategy.ipynb` | strategy distinctness, simulated acceptance for each Model 2 policy |
| `03_simulation_report.ipynb` | all variants (planted / null / misspecified) × seeds → markdown report |

The first cell of every notebook clones the `dev/ravindu` branch, installs C1's pinned
requirements and prints the Python version (supported: 3.11–3.13). Open in Colab with
*File → Open notebook → GitHub*, or upload the file. By default they use the tiny example in
`sim/examples/`; point `PERSONAS` / `TASKS` at your own files to use the persona task lists.
