"""ML Model 2 (strategy personalizer). Simulated students here are SYNTHETIC test
fixtures with a hidden preferred strategy; pipeline checks only."""
import copy
import random

import numpy as np
import pytest

from components.c1_disruption.app.services.planning import STRATEGIES, reward
from components.c1_disruption.ml.bandit.actions import distinctness
from components.c1_disruption.ml.bandit.context import FEATURE_NAMES, features
from components.c1_disruption.ml.bandit.linucb import PooledLinUCB
from components.c1_disruption.ml.bandit.policies import (
    BanditChooser,
    FixedOrderPolicy,
    MostAcceptedPolicy,
    RandomPolicy,
)
from components.c1_disruption.tests.api.client import setup
from components.c1_disruption.tests.engine.test_stress import SEED, random_day, seeded_random
from components.c1_disruption.tests.golden.loader import load_scenarios, scenario

ACTIONS = list(STRATEGIES)


# --- reward -------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("action", "changed", "total", "value"),
    [("accept", 0, 4, 1.0), ("reject", 0, 4, 0.0), ("edit", 1, 4, 0.75), ("edit", 4, 4, 0.0), ("edit", 0, 0, 1.0)],
)
def test_reward(action, changed, total, value):
    assert reward(action, changed, total) == value


def test_unknown_decision_has_no_reward():
    with pytest.raises(ValueError):
        reward("maybe")


# --- distinctness ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scenario_inputs():
    rand = seeded_random(SEED)
    golden = [s["input"] for s in load_scenarios() if "error" not in s["expected"]]
    return golden + [random_day(rand) for _ in range(200)]


def test_every_pair_of_actions_differs_on_some_scenarios(scenario_inputs):
    report = distinctness(scenario_inputs)
    assert report["scenarios"] == len(scenario_inputs)
    assert report["neverDiffer"] == []
    assert all(0 < share < 1 for share in report["pairs"].values())


def test_actions_that_never_differ_are_reported():
    actions = {"a": {"compressRatio": 0.5}, "b": {"compressRatio": 0.5}, "c": {"compressRatio": 0}}
    report = distinctness([scenario("S3")["input"], scenario("S4")["input"]], actions)
    assert report["neverDiffer"] == [("a", "b")]


def test_unplannable_scenarios_are_skipped():
    assert distinctness([scenario("S11")["input"]])["scenarios"] == 0


# --- context -----------------------------------------------------------------------------------

def test_context_features_for_golden_s1():
    data = copy.deepcopy(scenario("S1")["input"])  # power cut, plan from 09:00, Wednesday
    x = dict(zip(FEATURE_NAMES, features(data, severity=3, past_rewards=[1, 0])))
    assert (x["bias"], x["kind_unavailable"], x["severity"], x["morning"], x["evening"], x["weekend"]) == (1, 0, 1, 1, 0, 0)
    assert x["digital_share"] == pytest.approx(1 / 3)
    # 09:00–18:00 minus lunch = 480 min free, 5.5 h = 330 planned → slack 150/480.
    assert x["slack_ratio"] == pytest.approx(150 / 480)
    assert x["past_acceptance"] == 0.5


def test_no_history_uses_the_neutral_prior():
    x = dict(zip(FEATURE_NAMES, features(scenario("S15")["input"], severity=1)))
    assert (x["past_acceptance"], x["past_events"], x["kind_unavailable"], x["severity"]) == (0.5, 0.0, 1, 0)


# --- learning ------------------------------------------------------------------------------------------

def simulate(policy, preferences, events=40, seed=1):
    """SYNTHETIC students: each accepts only their hidden preferred action (noise 10%)."""
    rng = random.Random(seed)
    x = features(scenario("S3")["input"], severity=2)
    accepted = {s: [] for s in preferences}
    for _ in range(events):
        for student, liked in preferences.items():
            top = policy.rank(student, x)[0]
            r = 1.0 if (top == liked) != (rng.random() < 0.1) else 0.0
            policy.update(student, x, top, r)
            accepted[student].append(r)
    return x, accepted


def test_two_students_get_different_top_strategies_for_the_same_disruption():
    bandit = PooledLinUCB(ACTIONS, dim=len(FEATURE_NAMES))
    x, accepted = simulate(bandit, {"saver": "no_compress", "squeezer": "default"})
    assert bandit.rank("saver", x)[0] == "no_compress"
    assert bandit.rank("squeezer", x)[0] == "default"
    for history in accepted.values():
        assert np.mean(history[-10:]) > np.mean(history[:10])  # acceptance rises


def test_a_new_student_starts_from_the_shared_part():
    bandit = PooledLinUCB(ACTIONS, dim=len(FEATURE_NAMES))
    x, _ = simulate(bandit, {f"s{i}": "compress_25" for i in range(4)})
    assert bandit.rank("newcomer", x)[0] == "compress_25"


def test_most_accepted_baseline_learns_per_student():
    policy = MostAcceptedPolicy(ACTIONS)
    x = np.ones(len(FEATURE_NAMES))
    policy.update("a", x, "compress_25", 1.0)
    policy.update("a", x, "default", 0.0)
    # Tried and accepted first; untried (prior 0.5) in catalogue order; rejected last.
    assert policy.rank("a", x) == ["compress_25", "no_compress", "deadline_first", "evening_first", "default"]
    assert policy.rank("b", x) == ACTIONS  # nothing known: catalogue order


def test_fixed_and_random_baselines():
    x = np.ones(len(FEATURE_NAMES))
    assert FixedOrderPolicy(ACTIONS).rank("a", x) == ACTIONS
    assert RandomPolicy(ACTIONS, seed=3).rank("a", x) == RandomPolicy(ACTIONS, seed=3).rank("a", x)
    assert sorted(RandomPolicy(ACTIONS).rank("a", x)) == sorted(ACTIONS)


# --- chooser and policy modes ----------------------------------------------------------------------------

def context_of(scenario_id, severity=2):
    return {"engineInput": scenario(scenario_id)["input"], "severity": severity}


def test_fixed_order_mode_shows_the_catalogue_but_still_learns():
    chooser = BanditChooser("fixed_order")
    ranking = chooser.rank("a", context_of("S3"))
    assert (ranking.policy_mode, ranking.shown_policy, ranking.ranking) == ("fixed_order", "fixed_order", ACTIONS)
    chooser.learn("a", ranking.features, "default", 1.0)
    assert chooser.rewards["a"] == [1.0]


def test_randomised_mode_shows_both_rankings_and_logs_which():
    chooser = BanditChooser("randomised", seed=5)
    shown = {chooser.rank("a", context_of("S3")).shown_policy for _ in range(30)}
    assert shown == {"bandit", "fixed_order"}


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="policy mode"):
        BanditChooser("greedy")


def ready_day(**hooks):
    ctx = setup("2026-10-07T09:00", **hooks)
    ctx.call("PUT", "/api/me/settings", body={"workStart": "09:00", "workEnd": "13:00"})
    for title, hours in (("Exam revision", 3), ("Worksheet", 2)):
        ctx.call("POST", "/api/tasks", body={"title": title, "type": "Analog", "priority": "High", "estimatedHours": hours,
                                              "deadline": "2026-10-07T23:59", "plannedDate": "2026-10-07"})
    report = ctx.call("POST", "/api/disruptions", body={"date": "2026-10-07", "type": "transport_delay", "start": "09:00",
                                                         "timeLostMinutes": 60, "severity": 3, "confirmed": True}).json()
    return ctx, report


def test_default_service_logs_reward_and_has_no_bandit_features():
    ctx, report = ready_day()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    ctx.call("POST", f"/api/mvds/{mvd['id']}/accept")
    assert mvd["banditFeatures"] == []
    assert ctx.store.list("feedback")[0]["reward"] == 1.0


def test_bandit_mode_through_the_api_logs_context_and_learns_from_decisions():
    chooser = BanditChooser("bandit")
    ctx, report = ready_day(chooser=chooser)
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    assert (mvd["policyMode"], mvd["shownPolicy"]) == ("bandit", "bandit")
    assert len(mvd["banditFeatures"]) == len(FEATURE_NAMES)
    assert mvd["strategy"] == STRATEGIES[mvd["strategyId"]]
    ctx.call("POST", f"/api/mvds/{mvd['id']}/reject")
    assert chooser.rewards["u1"] == [0.0]
    assert ctx.store.list("feedback")[0]["reward"] == 0.0
