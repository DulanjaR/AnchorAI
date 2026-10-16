"""Optional task category as a Model 1 feature (planning chat, 16 Oct 2026). SYNTHETIC fixtures."""
import math

import numpy as np
import pytest

from components.c1_disruption.engine import config
from components.c1_disruption.ml.drift import settings
from components.c1_disruption.ml.drift.corrector import ModelCorrector
from components.c1_disruption.ml.drift.data import CATEGORY_FEATURE_NAMES, FEATURE_NAMES, feature_names, features
from components.c1_disruption.ml.drift.evaluation import rolling_origin, score
from components.c1_disruption.ml.drift.model import DriftModel
from components.c1_disruption.sim.personas import infer_category, load_personas, load_tasks
from components.c1_disruption.tests.api.client import setup
from components.c1_disruption.tests.ml import fixtures

REC = {"studentId": "a", "taskType": "Digital", "priority": "High", "estimatedMinutes": 60, "actualMinutes": 60,
       "date": "2026-10-07", "startHour": 10}


# --- features ---------------------------------------------------------------------------------

def test_category_columns_are_one_hot_and_missing_is_all_zero():
    assert config.TASK_CATEGORIES == ("coding", "writing", "reading", "revision")
    assert feature_names(True) == FEATURE_NAMES + CATEGORY_FEATURE_NAMES and feature_names(False) == FEATURE_NAMES
    X = features([{**REC, "category": "writing"}, REC, {**REC, "category": None}, {**REC, "category": "gaming"}], True)
    cats = X[:, len(FEATURE_NAMES):]
    assert cats.tolist() == [[0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert features([REC], False).shape == (1, len(FEATURE_NAMES))  # without the feature: as before


def test_the_category_is_on_by_default():
    assert settings.USE_CATEGORY is True and DriftModel().use_category is True


# --- it works when there is a category effect, and degrades gracefully when there is none -------

def category_world(effect: float, seed: int = 3) -> list[dict]:
    """SYNTHETIC: 6 students, all Digital; 'writing' tasks run over by `effect` (log), others not."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(6):
        for d in range(20):
            for _ in range(3):
                category = ("coding", "writing", "reading")[rng.integers(3)]
                est = float(rng.choice([30, 60, 90]))
                log = (effect if category == "writing" else 0.0) + rng.normal(0, 0.05)
                out.append({"studentId": f"s{s}", "taskType": "Digital", "priority": "Medium", "estimatedMinutes": est,
                            "actualMinutes": est * math.exp(log), "date": f"2026-09-{d + 1:02d}",
                            "startHour": int(rng.integers(8, 20)), "category": category, "dataset": "SYNTHETIC"})
    return out


def warm_mae(records, use_category):
    factory = lambda: DriftModel(n_estimators=40, use_category=use_category)
    return score(rolling_origin(records, factory, min_history_days=2, step_days=6))["maeMinutes"]


def test_the_model_tells_categories_apart_when_they_differ():
    records = category_world(effect=0.5)
    assert DriftModel(n_estimators=10).fit(records).uses_category
    assert warm_mae(records, True) < 0.6 * warm_mae(records, False)


def test_data_without_categories_still_works_and_gives_the_same_kind_of_model():
    data = fixtures.records()  # no category at all, like CESAW
    with_cat, without = DriftModel(n_estimators=40, use_category=True).fit(data), DriftModel(n_estimators=40, use_category=False).fit(data)
    q = [{"studentId": s, "taskType": "Digital", "priority": "High", "estimatedMinutes": 60, "date": "2026-10-07",
          "startHour": 10} for s in ("s1", "s4", "new")]
    assert with_cat.use_category and not with_cat.uses_category  # no categories in the data → no columns
    assert with_cat.predict(q) == without.predict(q) and with_cat.trust == without.trust  # exactly the old model


def test_a_model_saved_before_the_category_existed_predicts_without_it():
    model = DriftModel(n_estimators=20, use_category=False).fit(fixtures.records())
    del model.use_category, model.category_used  # what an unpickled 15-Oct model looks like
    assert model.uses_category is False
    (p,) = model.predict([{**REC, "studentId": "s1", "category": "writing"}])
    assert np.isfinite(p.log_point)


# --- the API and the corrector ----------------------------------------------------------------

TASK = {"title": "Essay", "type": "Analog", "priority": "High", "estimatedHours": 1, "deadline": "2026-10-07T23:59",
        "plannedDate": "2026-10-07"}


def test_the_api_accepts_an_optional_category_and_stores_it_only_when_set():
    ctx = setup()
    plain = ctx.call("POST", "/api/tasks", body=TASK).json()
    assert "category" not in plain  # existing clients see exactly the old task object
    task = ctx.call("POST", "/api/tasks", body={**TASK, "category": "writing"}).json()
    assert task["category"] == "writing"
    patched = ctx.call("PATCH", f"/api/tasks/{task['id']}", body={"title": "Essay v2"}).json()
    assert patched["category"] == "writing"  # a PATCH without it keeps it
    bad = ctx.call("POST", "/api/tasks", body={**TASK, "category": "gaming"})
    assert bad.status_code == 400 and "category" in bad.json()["error"]["message"]


def test_the_corrector_passes_the_category_to_the_model():
    seen = []

    class Spy(DriftModel):
        def predict(self, records):
            seen.extend(records)
            return super().predict(records)

    model = Spy(n_estimators=20).fit(category_world(effect=0.3))
    ModelCorrector(model).correct("s1", {**TASK, "estimatedHours": 1, "category": "writing"}, {"date": "2026-10-07"})
    ModelCorrector(model).correct("s1", {**TASK, "estimatedHours": 1}, {"date": "2026-10-07"})
    assert [r["category"] for r in seen] == ["writing", None]


# --- SYNTHETIC tasks: optional column, otherwise inferred from the title ------------------------

@pytest.mark.parametrize(("title", "category"), [
    ("Lab sheet 3: debug code", "coding"), ("Write test cases for lab sheet code", "coding"),
    ("Module B assignment: section 2", "writing"), ("Lit review: write synthesis", "writing"),
    ("PP1 slides: polish", "writing"), ("Lit review: read papers 1-3", "reading"),
    ("Lab sheet 2: read brief", "reading"), ("Module D flashcards", "revision"),
    ("Module C lecture notes review", "revision"), ("Module D past lecture slides", "revision"),
    ("Check LMS and plan the week", None), ("PP1 group sync call", None),
])
def test_infer_category_from_titles(title, category):
    assert infer_category(title) == category


def test_a_category_column_overrides_the_title_rule(tmp_path):
    personas = tmp_path / "p.csv"
    personas.write_text("personaId,label,workStart,workEnd,driftDigital,driftAnalog,driftMeeting,driftFixed,noiseSd\n"
                        "P01,SYNTHETIC: x,08:00,18:00,1,1,1,1,0.1\n", encoding="utf-8")
    tasks = tmp_path / "t.csv"
    head = "personaId,day,taskId,title,type,priority,estimatedMinutes,deadlineInDays,category\n"
    tasks.write_text(head + "P01,1,t1,Lab sheet 1: questions,Digital,High,60,1,writing\n"
                            "P01,1,t2,Lab sheet 1: questions,Digital,High,60,1,\n", encoding="utf-8")
    loaded = load_tasks(str(tasks), load_personas(str(personas)))
    assert [t.category for t in loaded] == ["writing", "coding"]
    tasks.write_text(head + "P01,1,t1,Lab,Digital,High,60,1,gaming\n", encoding="utf-8")
    with pytest.raises(ValueError, match="category"):
        load_tasks(str(tasks), load_personas(str(personas)))
