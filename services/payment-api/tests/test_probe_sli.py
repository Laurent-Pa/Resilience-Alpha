"""SLI de la sonde : calcul pur, sans base."""

from datetime import UTC, datetime, timedelta, timezone

from payment_api.domain import probe_sli

NOW = datetime(2026, 10, 21, 10, 30, 42, 123, tzinfo=UTC)


def test_window_covers_complete_minutes_only():
    start, end = probe_sli.minute_window(NOW, 60)
    assert end == datetime(2026, 10, 21, 10, 30, tzinfo=UTC)  # minute en cours exclue
    assert end - start == timedelta(minutes=60)


def test_series_fills_empty_minutes_with_zero():
    start, _ = probe_sli.minute_window(NOW, 3)
    points = probe_sli.success_series({start: 12}, start, 3, 5.0)
    assert [p.minute for p in points] == [start + timedelta(minutes=i) for i in range(3)]
    assert [p.success_count for p in points] == [12, 0, 0]
    assert [p.success_pct for p in points] == [100.0, 0.0, 0.0]


def test_rate_is_capped_but_raw_count_is_kept():
    start, _ = probe_sli.minute_window(NOW, 1)
    (point,) = probe_sli.success_series({start: 13}, start, 1, 5.0)
    assert (point.success_count, point.success_pct) == (13, 100.0)


def test_minutes_match_by_instant_whatever_the_timezone():
    """Postgres peut renvoyer les minutes dans le fuseau de sa session."""
    start, _ = probe_sli.minute_window(NOW, 1)
    paris = timezone(timedelta(hours=2))
    (point,) = probe_sli.success_series({start.astimezone(paris): 6}, start, 1, 5.0)
    assert (point.success_count, point.success_pct) == (6, 50.0)


def test_expected_count_follows_the_cadence():
    start, _ = probe_sli.minute_window(NOW, 1)
    (point,) = probe_sli.success_series({}, start, 1, 7.0)
    assert point.expected_count == 8.57
