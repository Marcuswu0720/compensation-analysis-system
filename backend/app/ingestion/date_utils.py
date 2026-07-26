"""PRD V1.8 §3: every date-like value gets normalized to a plain YYYY-MM-DD
string at the point of parsing - never a datetime-with-time string like
"2026-03-12T00:00:00" or "2026-03-12 00:00:00" (the time component in the
source files is always 00:00:00 anyway; keeping it just leaked a formatting
detail through to every downstream consumer - the web dashboard, the
download Excel, etc. - each of which would otherwise have to notice and fix
this independently). One conversion function used everywhere a date-like
cell might appear (Joining Date, Resign Date, Exit Date, and any other date
column that shows up) means the fix can't drift out of sync across call
sites again.
"""

import datetime
import re

_DATE_WITH_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]\d{2}:\d{2}:\d{2}$")


def format_date_value(value):
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        # Real bonus files have shown up with a date-column cell that openpyxl
        # reads back as a bare datetime.time (e.g. datetime.time(0, 0)) rather
        # than a date/datetime - some upstream export step lost the date part
        # and left only a time-of-day. Not JSON-serializable as-is, and
        # str(datetime.date) doesn't handle it (isinstance(time, date) is
        # False - they're unrelated types), so json.dumps() crashed the whole
        # upload instead of just leaving this one cell odd-looking. Format it
        # to a plain HH:MM:SS string like every other date-like value here,
        # rather than silently dropping it to None - it's a faithful (if
        # unhelpful-looking) rendering of exactly what the source cell had.
        return value.isoformat()
    return value


def format_date_for_display(value):
    """A second, defensive pass applied at export/read time (not just
    ingestion time): rows confirmed before this module existed already have
    a plain string baked into the database, e.g. "2026-01-04 00:00:00" from
    the old str(datetime) call - format_date_value() alone can't fix that
    retroactively since it only recognizes real datetime/date objects, not
    strings that already look like one. Stripping a redundant time-of-day
    suffix here means old rows display correctly without needing a re-upload."""
    value = format_date_value(value)
    if isinstance(value, str):
        m = _DATE_WITH_TIME_RE.match(value)
        if m:
            return m.group(1)
    return value
