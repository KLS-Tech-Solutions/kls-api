"""
Calendar dates, judged in the right timezone.

Timestamps in this project are stored and compared in UTC, which is correct —
an instant is an instant. A *date* is not an instant, and this is where that
distinction starts to matter.

The server runs UTC. India is UTC+5:30. So between 18:30 and 23:59 IST, the
server's `date.today()` is still yesterday. Any rule expressed as a calendar
day — "are they 18 today?" — decided against the server's clock is decided
against a date the person is not living in. A student registering at 11pm on
their eighteenth birthday would be told they are too young.

Ages are a legal test under Indian law about a person in India, so they are
judged on the Indian calendar.
"""

from datetime import date, datetime, timedelta, timezone

# India has a single timezone with no daylight saving, so a fixed offset is
# exactly right and avoids a dependency on the system tz database being
# present in the container.
IST = timezone(timedelta(hours=5, minutes=30))


def today_in_ist() -> date:
    """The current calendar date in India, whatever the server's clock says."""
    return datetime.now(IST).date()


def completed_years(born: date, today: date) -> int:
    """
    Age in completed years.

    The `(month, day)` tuple comparison is the whole of the birthday logic, and
    it is what makes 29 February behave: someone born on a leap day has not had
    a birthday by 28 February in a common year, and has by 1 March.
    """
    had_birthday = (today.month, today.day) >= (born.month, born.day)
    return today.year - born.year - (0 if had_birthday else 1)
