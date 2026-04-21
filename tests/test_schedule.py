"""Where: schedule tests. What: verify accepted grammar and next-run calculation. Why: catch scheduler regressions early."""

from datetime import datetime
from zoneinfo import ZoneInfo

from scheduled_agent_runner.schedule import next_run_at, parse_schedule


def test_parse_weekdays_schedule() -> None:
    spec = parse_schedule("weekdays 09:30")
    assert spec.kind == "weekdays"
    assert spec.value == "09:30"


def test_parse_one_time_schedule() -> None:
    spec = parse_schedule("in 5m")
    assert spec.kind == "once_minutes"
    assert spec.value == "5"


def test_next_run_for_one_time_schedule() -> None:
    spec = parse_schedule("in 5m")
    reference = datetime(2026, 4, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-21T08:05:00+00:00"


def test_next_run_for_daily_schedule() -> None:
    spec = parse_schedule("daily 09:30")
    reference = datetime(2026, 4, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-21T09:30:00+00:00"


def test_parse_invalid_schedule_raises() -> None:
    try:
        parse_schedule("tomorrow morning")
    except ValueError as exc:
        assert "Unsupported schedule" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid schedule.")
