import pytest

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.time import (
    Interval,
    block_to_intervals,
    calendar_days_between,
    overlaps,
    parse_date,
    parse_date_time,
    subtract_interval,
    to_hhmm,
    to_minutes,
    window_to_interval,
)


class TestTimeConversion:
    def test_hhmm_to_minutes_and_back(self):
        assert to_minutes("09:30") == 570
        assert to_minutes("0:05") == 5
        assert to_hhmm(570) == "09:30"
        assert to_hhmm(0) == "00:00"
        assert to_hhmm(1440) == "24:00"

    @pytest.mark.parametrize("bad", ["9.30", "24:00", "12:60", "", "09:30\n", "٠٩:٣٠"])
    def test_invalid_times_raise(self, bad):
        with pytest.raises(EngineError, match="Invalid time"):
            to_minutes(bad)


class TestDates:
    def test_calendar_days_ignore_the_time_of_day(self):
        assert calendar_days_between("2026-10-07", "2026-10-07T00:01") == 0
        assert calendar_days_between("2026-10-07", "2026-10-08T23:59") == 1
        assert calendar_days_between("2026-10-07", "2026-10-06T23:59") == -1

    def test_parse_date_time_orders_deadlines_bare_date_is_end_of_day(self):
        assert parse_date_time("2026-10-07T17:00") < parse_date_time("2026-10-07T23:59")
        assert parse_date_time("2026-10-07") == parse_date_time("2026-10-07T23:59")
        assert parse_date_time("2026-10-07T23:59") < parse_date_time("2026-10-08T00:00")

    def test_a_date_that_does_not_exist_raises(self):
        # Stricter than Node, where Date.UTC rolled 2026-02-30 over to 2 March.
        with pytest.raises(EngineError, match="Invalid date"):
            parse_date("2026-02-30")


class TestWindowToInterval:
    def test_a_normal_window_is_unchanged(self):
        assert window_to_interval({"start": "09:00", "end": "12:00"}) == Interval(540, 720)

    def test_a_window_crossing_midnight_is_clipped_at_the_end_of_the_plan_day(self):
        assert window_to_interval({"start": "20:00", "end": "02:00"}) == Interval(1200, 1440)


class TestIntervals:
    def test_touching_intervals_do_not_overlap(self):
        assert not overlaps(Interval(0, 60), Interval(60, 120))
        assert overlaps(Interval(0, 61), Interval(60, 120))

    def test_subtract_interval_splits_trims_and_removes(self):
        gaps = [Interval(0, 100), Interval(200, 300)]
        assert subtract_interval(gaps, Interval(40, 60)) == [Interval(0, 40), Interval(60, 100), Interval(200, 300)]
        assert subtract_interval(gaps, Interval(50, 250)) == [Interval(0, 50), Interval(250, 300)]
        assert subtract_interval(gaps, Interval(0, 300)) == []

    def test_a_block_crossing_midnight_becomes_two_pieces(self):
        assert block_to_intervals({"start": "22:00", "end": "06:00"}) == [Interval(1320, 1440), Interval(0, 360)]
        assert block_to_intervals({"start": "12:00", "end": "13:00"}) == [Interval(720, 780)]
        assert block_to_intervals({"start": "12:00", "end": "12:00"}) == []
