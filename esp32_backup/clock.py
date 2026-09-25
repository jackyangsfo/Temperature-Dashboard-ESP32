"""Clock / calendar helpers (NTP + local time).

Requires WiFi. ESP32 RTC is set to UTC via ntptime; local display applies
TIMEZONE_OFFSET_HOURS from config (e.g. -7 for US Pacific).
"""

import time

import config

_synced = False
_last_sync_ms = 0
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _offset_s():
    return int(getattr(config, "TIMEZONE_OFFSET_HOURS", 0)) * 3600


def _sync_interval_ms():
    return int(getattr(config, "NTP_SYNC_S", 3600)) * 1000


def is_synced():
    return _synced


def sync(force=False):
    """Fetch time from NTP. Returns True on success."""
    global _synced, _last_sync_ms
    now_ms = time.ticks_ms()
    if (
        _synced
        and not force
        and time.ticks_diff(now_ms, _last_sync_ms) < _sync_interval_ms()
    ):
        return True
    try:
        import ntptime

        host = getattr(config, "NTP_HOST", "") or "pool.ntp.org"
        ntptime.host = host
        ntptime.settime()  # UTC into RTC
        _synced = True
        _last_sync_ms = now_ms
        print("NTP OK", format_date(), format_time())
        return True
    except Exception as e:
        print("NTP fail:", e)
        return False


def _local_tuple():
    """Local time tuple, or None if RTC not set / year still 2000."""
    try:
        t = time.time() + _offset_s()
    except OverflowError:
        return None
    tm = time.localtime(t)
    # MicroPython epoch; unset RTC often shows year 2000
    if tm[0] < 2020:
        return None
    return tm


def format_date():
    """e.g. 'Thu Sep 24' or '--'."""
    tm = _local_tuple()
    if tm is None:
        return "--"
    # tm: (Y, M, D, h, m, s, weekday, yearday)
    return "%s %s %d" % (_DAYS[tm[6]], _MONTHS[tm[1] - 1], tm[2])


def format_time():
    """e.g. '12:59' (24h) or '--:--'."""
    tm = _local_tuple()
    if tm is None:
        return "--:--"
    return "%02d:%02d" % (tm[3], tm[4])


def format_calendar_line():
    """Single ASCII line for the e-paper header."""
    tm = _local_tuple()
    if tm is None:
        return "Clock --"
    return "%s %s %d  %02d:%02d" % (
        _DAYS[tm[6]],
        _MONTHS[tm[1] - 1],
        tm[2],
        tm[3],
        tm[4],
    )
