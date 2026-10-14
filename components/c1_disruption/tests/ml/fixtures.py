"""SYNTHETIC test fixture for ML Model 1 (pipeline checks only, not research data).

Each student has a hidden log drift offset; Digital tasks run a further +0.2;
noise is normal on the log scale. The real simulation (sim/) uses the owner's
persona task lists instead.
"""
import math

import numpy as np

DATASET = "SYNTHETIC"
OFFSETS = {"s1": 0.4, "s2": 0.25, "s3": 0.0, "s4": -0.2, "s5": 0.1, "s6": 0.3}
DIGITAL_EFFECT = 0.2
NOISE_SD = 0.12


def records(days: int = 20, per_day: int = 3, seed: int = 7, offsets: dict[str, float] = OFFSETS,
            digital_effect: float = DIGITAL_EFFECT, noise_sd: float = NOISE_SD) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for student, offset in offsets.items():
        for d in range(days):
            date = f"2026-09-{d + 1:02d}"
            for _ in range(per_day):
                task_type = ("Digital", "Analog", "Meeting")[rng.integers(3)]
                estimated = float(rng.choice([30, 45, 60, 90, 120, 180]))
                true_log = offset + (digital_effect if task_type == "Digital" else 0.0)
                actual = estimated * math.exp(true_log + rng.normal(0, noise_sd))
                out.append({
                    "studentId": student, "taskType": task_type, "priority": ("High", "Medium", "Low")[rng.integers(3)],
                    "estimatedMinutes": estimated, "actualMinutes": round(actual, 1), "date": date,
                    "startHour": int(rng.integers(8, 21)), "dataset": DATASET,
                })
    return out
