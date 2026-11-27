"""
"Today" for the business, not for the server.

Render's servers run on UTC, which is 5½ hours behind India: between midnight
and 05:30 IST, date.today() is still yesterday. A step ticked done or a date
defaulted in that window would get the previous day — and the installation
date is printed on documents. India has no daylight saving, so a fixed offset
is exact (and needs no tz database in the container).
"""
from datetime import date, datetime, timedelta, timezone

BUSINESS_TZ = timezone(timedelta(hours=5, minutes=30), "IST")


def local_today() -> date:
    return datetime.now(BUSINESS_TZ).date()
