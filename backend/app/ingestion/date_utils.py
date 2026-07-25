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


def format_date_value(value):
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value
