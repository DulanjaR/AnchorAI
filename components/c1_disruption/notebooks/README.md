# notebooks (Google Colab)

Experiments only (Task 4 drift model, Task 5 bandit simulation). Notebooks call code in
`ml/` and `sim/`; they hold no logic of their own, so everything they show is also
covered by pytest. Every result made from synthetic data is labelled **SYNTHETIC**
(CLAUDE.md rule 6).

The first cell of every notebook clones the `dev/ravindu` branch and installs C1's
pinned requirements (set up in Phase 5).
