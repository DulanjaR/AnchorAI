import pytest

from components.c1_disruption.engine import config
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.fi import (
    compute_fi,
    deadline_proximity,
    disruption_kind,
    ef_for_fi,
    is_blocked_by_disruption,
    lookup_ef,
)


class TestDisruptionKinds:
    @pytest.mark.parametrize(
        ("disruption_type", "kind"),
        [
            ("power_outage", "environment"),
            ("transport_delay", "environment"),
            ("connectivity_failure", "environment"),
            ("urgent_work", "unavailable"),
            ("family_obligation", "unavailable"),
            ("health_issue", "unavailable"),
        ],
    )
    def test_kind(self, disruption_type, kind):
        assert disruption_kind(disruption_type) == kind

    def test_unknown_disruption_type_raises(self):
        with pytest.raises(EngineError, match="alien_invasion"):
            disruption_kind("alien_invasion")

    def test_config_is_consistent(self):
        # EF rows exist exactly for the environment kinds, with every task type.
        environment = {t for t, k in config.DISRUPTION_KINDS.items() if k == "environment"}
        assert set(config.ENV_FEASIBILITY) == environment
        for row in config.ENV_FEASIBILITY.values():
            assert set(row) == set(config.TASK_TYPES)

    def test_config_values_are_the_approved_node_values(self):
        assert config.PRIORITY_SCORE == {"High": 1, "Medium": 2, "Low": 3}
        assert (config.FEASIBILITY_GATE, config.OUTSIDE_WINDOW_EF, config.DEADLINE_MIN_DAYS) == (0.3, 1.0, 0.5)
        assert (config.DEADLINE_RISK_DAYS, config.KEEP_THRESHOLD, config.MAX_COMPRESSION) == (1, 0.5, 0.5)
        assert config.REDUCE_RANGE == (0.5, 2.0)
        assert config.ENV_FEASIBILITY["power_outage"] == {"Digital": 0.1, "Analog": 1.2, "Meeting": None, "Fixed": None}
        assert config.ENV_FEASIBILITY["transport_delay"] == {"Digital": 0.7, "Analog": 1.2, "Meeting": None, "Fixed": None}
        assert set(config.ENV_FEASIBILITY["connectivity_failure"].values()) == {None}


class TestLookupEf:
    def test_returns_the_config_value(self):
        assert lookup_ef("power_outage", "Digital") == 0.1
        assert lookup_ef("transport_delay", "Analog") == 1.2

    def test_none_ef_raises_naming_the_disruption_and_task_type(self):
        with pytest.raises(EngineError, match=r"connectivity_failure[\s\S]*Analog"):
            lookup_ef("connectivity_failure", "Analog")
        with pytest.raises(EngineError, match=r"power_outage[\s\S]*Meeting"):
            lookup_ef("power_outage", "Meeting")

    def test_unknown_disruption_or_task_type_raises(self):
        with pytest.raises(EngineError, match="alien_invasion"):
            lookup_ef("alien_invasion", "Digital")
        with pytest.raises(EngineError, match="Gaming"):
            lookup_ef("power_outage", "Gaming")


class TestFeasibilityGate:
    def test_below_0_3_is_blocked_0_3_and_above_is_not(self):
        assert is_blocked_by_disruption(0.1)
        assert is_blocked_by_disruption(0.29)
        assert not is_blocked_by_disruption(0.3)
        assert not is_blocked_by_disruption(0.7)


class TestEfForFi:
    def test_blocked_task_uses_normal_ef(self):
        assert ef_for_fi(0.1, True) == 1.0

    def test_feasible_task_uses_the_disruption_ef_while_the_window_is_ahead(self):
        assert ef_for_fi(0.7, True) == 0.7
        assert ef_for_fi(1.2, True) == 1.2

    def test_once_the_window_is_over_every_task_uses_1(self):
        assert ef_for_fi(0.7, False) == 1.0
        assert ef_for_fi(1.2, False) == 1.0


class TestDeadlineProximity:
    def test_due_today_is_floored_at_0_5(self):
        assert deadline_proximity("2026-10-07", "2026-10-07T23:59") == 0.5

    def test_overdue_is_also_floored(self):
        assert deadline_proximity("2026-10-07", "2026-10-05T12:00") == 0.5

    def test_counts_calendar_days_ignoring_time_of_day(self):
        assert deadline_proximity("2026-10-07", "2026-10-08T00:30") == 1
        assert deadline_proximity("2026-10-07", "2026-10-12T23:59") == 5

    def test_works_across_a_month_boundary(self):
        assert deadline_proximity("2026-10-30", "2026-11-02T09:00") == 3


class TestComputeFi:
    def test_formula(self):
        # 0.5 × 1 / (2 × 1.2) = 0.2083…
        assert compute_fi(deadline_days=0.5, priority="High", hours=2, ef=1.2) == pytest.approx(0.2083, abs=1e-4)
        # 5 × 3 / (1 × 1.2) = 12.5
        assert compute_fi(deadline_days=5, priority="Low", hours=1, ef=1.2) == 12.5

    def test_higher_priority_gives_lower_fi(self):
        high = compute_fi(deadline_days=1, priority="High", hours=1, ef=1)
        low = compute_fi(deadline_days=1, priority="Low", hours=1, ef=1)
        assert high < low

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"priority": "Urgent"}, "priority"),
            ({"hours": 0}, "Duration"),
            ({"hours": None}, "Duration"),
            ({"ef": 0}, "EF"),
        ],
    )
    def test_rejects_bad_input(self, kwargs, message):
        args = {"deadline_days": 1, "priority": "High", "hours": 1, "ef": 1, **kwargs}
        with pytest.raises(EngineError, match=message):
            compute_fi(**args)
