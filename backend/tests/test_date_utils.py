import datetime

from app.ingestion.date_utils import format_date_for_display, format_date_value


def test_format_date_value_converts_real_datetime_objects():
    assert format_date_value(datetime.datetime(2026, 1, 4)) == "2026-01-04"
    assert format_date_value(datetime.date(2026, 1, 4)) == "2026-01-04"
    assert format_date_value("already-a-string") == "already-a-string"
    assert format_date_value(None) is None


def test_format_date_for_display_strips_stale_time_suffix_from_old_rows():
    """Regression test: a row confirmed before format_date_value() existed
    already has a plain string baked into the database, e.g.
    "2026-01-04 00:00:00" from the old str(datetime) call - that string is
    no longer a real datetime object, so format_date_value() alone can't
    fix it. format_date_for_display() is the defensive second pass applied
    at export time so old rows display correctly without a re-upload."""
    assert format_date_for_display("2026-01-04 00:00:00") == "2026-01-04"
    assert format_date_for_display("2026-01-04T00:00:00") == "2026-01-04"
    assert format_date_for_display("2026-01-04") == "2026-01-04"
    assert format_date_for_display(datetime.datetime(2026, 1, 4)) == "2026-01-04"
    assert format_date_for_display(None) is None
    assert format_date_for_display("Outstation") == "Outstation"  # non-date strings pass through untouched
