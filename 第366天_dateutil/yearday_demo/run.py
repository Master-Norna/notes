"""Run the fixed parent and merged revisions side by side.

    python -B run.py           # print the comparison table and sweep summary
    python -B run.py --test    # assert the recorded facts (exit code 0 on success)
    python -B run.py --json out.json

Each revision runs in its own `python -I -B -S` subprocess; the demo itself
imports neither revision and needs only the standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PROBE = HERE / "probe.py"
VENDORS = {
    "parent": HERE / "vendor" / "parent",
    "merged": HERE / "vendor" / "merged",
}


def run_probe(name: str) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    out = subprocess.run(
        [sys.executable, "-I", "-B", "-S", str(PROBE), str(VENDORS[name])],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return json.loads(out.stdout)


def short_repr(text: str) -> str:
    return text.replace("relativedelta(", "rd(")


def print_table(parent: dict, merged: dict) -> None:
    print(f"{'year':>5} {'day':>4}  {'parent':<44} {'merged':<44}")
    for left, right in zip(parent["cases"], merged["cases"]):
        assert left["year"] == right["year"] and left["yearday"] == right["yearday"]
        lp = left["error"] or f"{short_repr(left['repr'])} -> {left['result']}"
        rm = right["error"] or f"{short_repr(right['repr'])} -> {right['result']}"
        print(f"{left['year']:>5} {left['yearday']:>4}  {lp:<44} {rm:<44}")


def print_sweep(parent: dict, merged: dict) -> None:
    p, m = parent["sweep"], merged["sweep"]
    print(
        f"\nsweep {p['start']}-{p['end']}: {p['years']} years, "
        f"{p['leap_years']} leap years, {p['total']} date cases"
    )
    print(f"  parent mismatches: {p['mismatch_count']}")
    print(f"  merged mismatches: {m['mismatch_count']}")
    if p["mismatches"]:
        first = p["mismatches"][0]
        last = p["mismatches"][-1]
        print(
            f"  first: {first['year']} day {first['yearday']} -> {first['actual']} "
            f"(expected {first['expected']})"
        )
        print(
            f"  last:  {last['year']} day {last['yearday']} -> {last['actual']} "
            f"(expected {last['expected']})"
        )
        print(f"  every mismatch is day 366 of a leap year: "
              f"{all(x['yearday'] == 366 for x in p['mismatches'])}")


def check(parent: dict, merged: dict) -> None:
    def case(data: dict, year: int, yearday: int) -> dict:
        for item in data["cases"]:
            if item["year"] == year and item["yearday"] == yearday:
                return item
        raise AssertionError(f"case {year}/{yearday} missing")

    assert case(parent, 2000, 366)["result"] == "2000-12-30"
    assert case(merged, 2000, 366)["result"] == "2000-12-31"
    assert case(parent, 2024, 366)["result"] == "2024-12-30"
    assert case(merged, 2024, 366)["result"] == "2024-12-31"
    assert case(parent, 2000, 365)["result"] == "2000-12-30"
    assert case(merged, 2000, 365)["result"] == "2000-12-30"
    assert case(parent, 1900, 366)["result"] == "1900-12-31"
    assert case(merged, 1900, 366)["result"] == "1900-12-31"
    assert case(parent, 1999, 366)["result"] == "1999-12-31"
    assert case(merged, 1999, 366)["result"] == "1999-12-31"
    assert case(parent, 2000, 60)["result"] == "2000-02-29"
    assert case(merged, 2000, 60)["result"] == "2000-02-29"
    assert case(parent, 2000, 59)["result"] == "2000-02-28"
    assert case(merged, 2000, 59)["result"] == "2000-02-28"
    assert case(parent, 2001, 60)["result"] == "2001-03-01"
    assert case(merged, 2001, 60)["result"] == "2001-03-01"
    assert case(parent, 2000, 367)["error"] == "ValueError: invalid year day (367)"
    assert case(merged, 2000, 367)["error"] == "ValueError: invalid year day (367)"
    assert "leapdays=-1" in case(parent, 2000, 366)["repr"]
    assert "leapdays=-1" not in case(merged, 2000, 366)["repr"]
    assert case(parent, 2000, 366)["result"] == case(parent, 2000, 365)["result"]
    assert case(merged, 2000, 366)["result"] != case(merged, 2000, 365)["result"]

    p, m = parent["sweep"], merged["sweep"]
    assert p["total"] == 146097, p["total"]
    assert p["leap_years"] == 97, p["leap_years"]
    assert p["mismatch_count"] == 97, p["mismatch_count"]
    assert m["mismatch_count"] == 0, m["mismatch_count"]
    assert all(x["yearday"] == 366 for x in p["mismatches"])
    print("all assertions passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--json", type=pathlib.Path)
    args = parser.parse_args()

    parent = run_probe("parent")
    merged = run_probe("merged")
    print_table(parent, merged)
    print_sweep(parent, merged)
    if args.json:
        args.json.write_text(
            json.dumps({"parent": parent, "merged": merged}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")
    if args.test:
        check(parent, merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
