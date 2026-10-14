# C1 simulation results — SYNTHETIC — pipeline validation only, not a research finding

10 personas, 589 planned tasks; mean ± sd over seeds.

## Variant: planted (SYNTHETIC)

| Model 1 method | cold MAE min | warm MAE min | warm MAE log | warm coverage |
|---|---|---|---|---|
| model | 8.497 ± 0.230 | 7.248 ± 0.169 | 0.109 ± 0.002 | 0.747 ± 0.008 |
| B0 drift = 1.0 | 12.248 ± 0.301 | 12.192 ± 0.326 | 0.187 ± 0.004 | – |
| B1 global mean | 9.070 ± 0.191 | 8.970 ± 0.199 | 0.134 ± 0.002 | – |
| B2 per-student mean | 9.070 ± 0.191 | 8.035 ± 0.202 | 0.122 ± 0.001 | – |
| B3 shrinkage only | 9.070 ± 0.191 | 8.043 ± 0.118 | 0.122 ± 0.002 | – |

| Event metric (same events) | raw | corrected |
|---|---|---|
| ctrrPlanned | 0.373 ± 0.061 | 0.353 ± 0.048 |
| ctrrRealised | 0.062 ± 0.063 | 0.148 ± 0.063 |
| ptvr | 0.000 ± 0.000 | 0.000 ± 0.000 |
| feasibilityTrue | 0.929 ± 0.041 | 0.982 ± 0.041 |
| realisedFeasibility | 0.138 ± 0.138 | 0.316 ± 0.172 |
| planCompletionRate | 0.156 ± 0.176 | 0.415 ± 0.197 |
| decision-change rate | 0.023 ± 0.015 | |
| events planned / skipped (engine cannot plan, e.g. None EF) | 96.800 ± 2.168 | 33.400 ± 9.581 |
| disruptions with no effect (overlap no planned task) | 331.400 ± 39.488 | |
| top-up disruptions drawn (to reach 10 per persona) | 357.600 ± 48.320 | |
| personas short of 10 effective disruptions | 0.000 ± 0.000 | |

| Model 1 learning curve (warm, model) | n records seen | MAE min |
|---|---|---|
| | 0–0 | – |
| | 1–4 | 8.563 ± 0.651 |
| | 5–9 | – |
| | 10–19 | 8.142 ± 0.593 |
| | 20–39 | 6.761 ± 0.122 |
| | 40+ | 4.935 ± 0.340 |

| Model 2 policy (accept probabilities 0.85 / 0.3 are ASSUMPTIONS) | mean acceptance | first half | second half |
|---|---|---|---|
| fixed order | 0.609 ± 0.079 | 0.592 ± 0.072 | 0.625 ± 0.099 |
| most accepted | 0.749 ± 0.074 | 0.689 ± 0.073 | 0.808 ± 0.079 |
| random | 0.623 ± 0.064 | 0.626 ± 0.087 | 0.621 ± 0.063 |
| bandit | 0.707 ± 0.051 | 0.648 ± 0.078 | 0.765 ± 0.035 |

## Variant: null (SYNTHETIC)

| Model 1 method | cold MAE min | warm MAE min | warm MAE log | warm coverage |
|---|---|---|---|---|
| model | 4.349 ± 0.216 | 4.359 ± 0.190 | 0.079 ± 0.003 | 0.734 ± 0.009 |
| B0 drift = 1.0 | 4.185 ± 0.180 | 4.177 ± 0.175 | 0.076 ± 0.002 | – |
| B1 global mean | 4.175 ± 0.176 | 4.166 ± 0.170 | 0.075 ± 0.003 | – |
| B2 per-student mean | 4.175 ± 0.176 | 4.393 ± 0.169 | 0.080 ± 0.002 | – |
| B3 shrinkage only | 4.175 ± 0.176 | 4.171 ± 0.173 | 0.075 ± 0.002 | – |

| Event metric (same events) | raw | corrected |
|---|---|---|
| ctrrPlanned | 0.373 ± 0.061 | 0.347 ± 0.075 |
| ctrrRealised | 0.208 ± 0.065 | 0.223 ± 0.028 |
| ptvr | 0.000 ± 0.000 | 0.000 ± 0.000 |
| feasibilityTrue | 0.986 ± 0.032 | 0.986 ± 0.032 |
| realisedFeasibility | 0.475 ± 0.140 | 0.577 ± 0.112 |
| planCompletionRate | 0.555 ± 0.184 | 0.657 ± 0.139 |
| decision-change rate | 0.006 ± 0.009 | |
| events planned / skipped (engine cannot plan, e.g. None EF) | 96.800 ± 2.168 | 33.400 ± 9.581 |
| disruptions with no effect (overlap no planned task) | 331.400 ± 39.488 | |
| top-up disruptions drawn (to reach 10 per persona) | 357.600 ± 48.320 | |
| personas short of 10 effective disruptions | 0.000 ± 0.000 | |

| Model 1 learning curve (warm, model) | n records seen | MAE min |
|---|---|---|
| | 0–0 | – |
| | 1–4 | 4.885 ± 0.415 |
| | 5–9 | – |
| | 10–19 | 4.664 ± 0.354 |
| | 20–39 | 4.191 ± 0.176 |
| | 40+ | 3.367 ± 0.268 |

| Model 2 policy (accept probabilities 0.85 / 0.3 are ASSUMPTIONS) | mean acceptance | first half | second half |
|---|---|---|---|
| fixed order | 0.609 ± 0.079 | 0.592 ± 0.072 | 0.625 ± 0.099 |
| most accepted | 0.749 ± 0.074 | 0.689 ± 0.073 | 0.808 ± 0.079 |
| random | 0.623 ± 0.064 | 0.626 ± 0.087 | 0.621 ± 0.063 |
| bandit | 0.707 ± 0.051 | 0.648 ± 0.078 | 0.765 ± 0.035 |

## Variant: misspecified (SYNTHETIC)

| Model 1 method | cold MAE min | warm MAE min | warm MAE log | warm coverage |
|---|---|---|---|---|
| model | 16.258 ± 0.331 | 16.732 ± 1.232 | 0.247 ± 0.010 | 0.720 ± 0.015 |
| B0 drift = 1.0 | 17.954 ± 0.600 | 17.900 ± 0.623 | 0.271 ± 0.005 | – |
| B1 global mean | 16.128 ± 0.564 | 16.029 ± 0.536 | 0.241 ± 0.006 | – |
| B2 per-student mean | 16.128 ± 0.564 | 17.747 ± 0.903 | 0.265 ± 0.014 | – |
| B3 shrinkage only | 16.128 ± 0.564 | 16.741 ± 0.879 | 0.250 ± 0.006 | – |

| Event metric (same events) | raw | corrected |
|---|---|---|
| ctrrPlanned | 0.373 ± 0.061 | 0.360 ± 0.067 |
| ctrrRealised | 0.100 ± 0.042 | 0.176 ± 0.062 |
| ptvr | 0.000 ± 0.000 | 0.000 ± 0.000 |
| feasibilityTrue | 0.905 ± 0.077 | 0.980 ± 0.045 |
| realisedFeasibility | 0.218 ± 0.071 | 0.476 ± 0.106 |
| planCompletionRate | 0.251 ± 0.097 | 0.537 ± 0.135 |
| decision-change rate | 0.025 ± 0.013 | |
| events planned / skipped (engine cannot plan, e.g. None EF) | 96.800 ± 2.168 | 33.400 ± 9.581 |
| disruptions with no effect (overlap no planned task) | 331.400 ± 39.488 | |
| top-up disruptions drawn (to reach 10 per persona) | 357.600 ± 48.320 | |
| personas short of 10 effective disruptions | 0.000 ± 0.000 | |

| Model 1 learning curve (warm, model) | n records seen | MAE min |
|---|---|---|
| | 0–0 | – |
| | 1–4 | 20.845 ± 5.056 |
| | 5–9 | – |
| | 10–19 | 18.355 ± 1.855 |
| | 20–39 | 14.179 ± 0.983 |
| | 40+ | 12.580 ± 1.690 |

| Model 2 policy (accept probabilities 0.85 / 0.3 are ASSUMPTIONS) | mean acceptance | first half | second half |
|---|---|---|---|
| fixed order | 0.609 ± 0.079 | 0.592 ± 0.072 | 0.625 ± 0.099 |
| most accepted | 0.749 ± 0.074 | 0.689 ± 0.073 | 0.808 ± 0.079 |
| random | 0.623 ± 0.064 | 0.626 ± 0.087 | 0.621 ± 0.063 |
| bandit | 0.707 ± 0.051 | 0.648 ± 0.078 | 0.765 ± 0.035 |

