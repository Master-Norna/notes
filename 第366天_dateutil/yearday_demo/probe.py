"""Measure one vendored revision of dateutil.relativedelta.

Run as an isolated subprocess by run.py:

    python -I -B -S probe.py <vendor-root>

The vendor root is prepended to sys.path so `import dateutil.relativedelta`
resolves to the fixed revision copied into vendor/.
"""

from __future__ import annotations

import calendar
import datetime
import json
import sys

vendor_root = sys.argv[1]
sys.path.insert(0, vendor_root)

from dateutil.relativedelta import relativedelta  # noqa: E402

CASES = [
    (2000, 366),
    (2024, 366),
    (2000, 365),
    (2000, 60),
    (2000, 59),
    (2001, 60),
    (1999, 366),
    (1900, 366),
    (2000, 367),
]


def apply(year: int, yearday: int) -> dict:
    repr_text = None
    result = None
    error = None
    try:
        delta = relativedelta(yearday=yearday)
        repr_text = repr(delta)
        result = (datetime.date(year, 1, 1) + delta).isoformat()
    except Exception as exc:  # noqa: BLE001 - report the failure as data
        error = f"{type(exc).__name__}: {exc}"
    return {
        "year": year,
        "yearday": yearday,
        "repr": repr_text,
        "result": result,
        "error": error,
    }


def sweep(start: int, end: int) -> dict:
    total = 0
    leap_years = 0
    mismatches = []
    for year in range(start, end + 1):
        is_leap = calendar.isleap(year)
        leap_years += int(is_leap)
        first = datetime.date(year, 1, 1)
        upper = 366 if is_leap else 365
        for yearday in range(1, upper + 1):
            total += 1
            got = first + relativedelta(yearday=yearday)
            expected = first + datetime.timedelta(days=yearday - 1)
            if got != expected:
                mismatches.append(
                    {
                        "year": year,
                        "yearday": yearday,
                        "expected": expected.isoformat(),
                        "actual": got.isoformat(),
                    }
                )
    return {
        "start": start,
        "end": end,
        "years": end - start + 1,
        "leap_years": leap_years,
        "total": total,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


payload = {
    "python": sys.version.split()[0],
    "cases": [apply(year, yearday) for year, yearday in CASES],
    "sweep": sweep(2000, 2399),
}
print(json.dumps(payload, ensure_ascii=False))
