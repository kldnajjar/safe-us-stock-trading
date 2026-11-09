#!/usr/bin/env python3
"""NYSE clock for the safe-us-stock-trading skill (v4.6). Standard library only, no network.

  python3 market_clock.py                 # now
  python3 market_clock.py --at 2026-11-26T15:00:00Z

Says whether the NYSE regular session is open, why not (weekend, holiday, before the open,
after the close), the early close if any, and the next open. size_trade.py uses it: a plan
can only be executable while the regular session is open.

Calendar: NYSE holidays and 1:00 p.m. early closes for 2026 and 2027 as published at
https://www.nyse.com/markets/hours-calendars (re-read 2026-11-09; identical to the list in
trader-skill). Outside those years "calendar_known" is false: weekends and hours are still
checked, holidays are not, and the output says so. A maintainer adds the next year from that
page. New York time follows the US DST rule (second Sunday of March to first Sunday of November).

Ported from trader-skill/trader-alerts/alerts.py, Copyright (c) Jake Schincariol, MIT License
(https://github.com/Jakeschincariol/trader-skill).
"""
import argparse, datetime as dt, json, sys

CALENDAR_SOURCE = "https://www.nyse.com/markets/hours-calendars"
CALENDAR_READ_ON = "2026-11-09"
NYSE_HOLIDAYS = {
    "2026-01-01": "New Year's Day",
    "2026-01-19": "Martin Luther King, Jr. Day",
    "2026-02-16": "Washington's Birthday",
    "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth National Independence Day",
    "2026-07-03": "Independence Day (observed)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving Day",
    "2026-12-25": "Christmas Day",
    "2027-01-01": "New Year's Day",
    "2027-01-18": "Martin Luther King, Jr. Day",
    "2027-02-15": "Washington's Birthday",
    "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth National Independence Day (observed)",
    "2027-07-05": "Independence Day (observed)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving Day",
    "2027-12-24": "Christmas Day (observed)",
}
NYSE_EARLY_CLOSE = {  # 1:00 p.m. New York time
    "2026-11-27": "day after Thanksgiving",
    "2026-12-24": "Christmas Eve",
    "2027-11-26": "day after Thanksgiving",
}
CALENDAR_YEARS = (2026, 2027)
OPEN, CLOSE, EARLY = dt.time(9, 30), dt.time(16, 0), dt.time(13, 0)


def CLOCK():
    """The system clock (UTC). Tests replace this function; nothing on the command line can."""
    return dt.datetime.now(dt.timezone.utc)


def _nth_sunday(year, month, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def ny_offset_hours(utc):
    y = utc.year
    start = dt.datetime(y, 3, 1, tzinfo=dt.timezone.utc).replace(
        day=_nth_sunday(y, 3, 2).day, hour=7)          # 2:00 EST = 07:00 UTC
    end = dt.datetime(y, 11, 1, tzinfo=dt.timezone.utc).replace(
        day=_nth_sunday(y, 11, 1).day, hour=6)         # 2:00 EDT = 06:00 UTC
    return -4 if start <= utc < end else -5


def to_new_york(utc):
    off = ny_offset_hours(utc)
    return utc.astimezone(dt.timezone(dt.timedelta(hours=off)))


def session(d):
    """(open, close) New York times, or (None, reason) if closed all day."""
    if d.weekday() >= 5:
        return None, "weekend"
    name = NYSE_HOLIDAYS.get(d.isoformat())
    if name:
        return None, f"NYSE holiday: {name}"
    return (OPEN, EARLY if d.isoformat() in NYSE_EARLY_CLOSE else CLOSE), ""


def status(utc=None):
    utc = (utc or CLOCK()).astimezone(dt.timezone.utc)
    ny = to_new_york(utc)
    d, t = ny.date(), ny.time().replace(tzinfo=None)
    sess, reason = session(d)
    out = dict(now_utc=utc.isoformat(timespec="seconds"), now_new_york=ny.isoformat(timespec="minutes"),
               weekday=ny.strftime("%A"), calendar_known=d.year in CALENDAR_YEARS,
               calendar_source=CALENDAR_SOURCE, calendar_read_on=CALENDAR_READ_ON,
               early_close=NYSE_EARLY_CLOSE.get(d.isoformat()), open=False, reason=reason)
    if sess:
        o, c = sess
        out["opens"], out["closes"] = o.strftime("%H:%M"), c.strftime("%H:%M")
        if o <= t < c:
            out.update(open=True, reason="regular session")
        else:
            out["reason"] = "before the open" if t < o else "after the close"
    nd = d if (sess and t < sess[0]) else d + dt.timedelta(days=1)
    for _ in range(15):
        s, _r = session(nd)
        if s:
            out["next_open_new_york"] = f"{nd.isoformat()} 09:30"
            break
        nd += dt.timedelta(days=1)
    if not out["calendar_known"]:
        out["warning"] = (f"NYSE holiday list not loaded for {d.year}: weekends and hours checked, holidays "
                          f"not; check {CALENDAR_SOURCE}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--at", default="", help="research only: ISO time with offset to evaluate instead of now")
    a = ap.parse_args(argv)
    at = None
    if a.at:
        try:
            at = dt.datetime.fromisoformat(a.at.replace("Z", "+00:00"))
        except ValueError:
            ap.error("--at must be an ISO time with a UTC offset, e.g. 2026-11-26T15:00:00Z")
        if at.tzinfo is None:
            ap.error("--at needs a UTC offset")
    print(json.dumps(status(at), indent=2))


if __name__ == "__main__":
    sys.exit(main())
