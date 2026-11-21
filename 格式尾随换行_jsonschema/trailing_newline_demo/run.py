"""The three validators jsonschema delegates its format checks to, taken as-is
from PyPI, called the same way ``jsonschema/_format.py`` calls them.

    python -B run.py --test

``--test`` runs both groups and asserts:

  before   the bare value is accepted, and the same value plus a trailing
           newline is *also* accepted (the leak);
  guard    with a one-line shape guard in front, the bare value stays
           accepted and the trailing newline is rejected.

Nothing is installed: the packages under ``vendor/`` are the released
files, and everything else is the standard library.  No network, no writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))

import rfc3987  # noqa: E402
from fqdn import FQDN  # noqa: E402
from rfc3339_validator import validate_rfc3339  # noqa: E402

RULES = {
    "uri": "URI",
    "uri-reference": "URI_reference",
    "iri": "IRI",
    "iri-reference": "IRI_reference",
}

# (format, a valid instance, the description in the official test suite)
CASES = [
    ("date-time", "1985-04-12T23:20:50Z", "a trailing newline is invalid"),
    ("time", "08:30:06Z", "a trailing newline after a valid time"),
    ("hostname", "example.com", "trailing newline is invalid"),
    ("uri", "http://foo.bar/", "a trailing newline after a valid URI is invalid"),
    ("uri-reference", "/p", "a trailing line feed"),
    ("iri", "http://\u0192\u00f8\u00f8.\u00df\u00e5r/", "a trailing newline after a valid IRI is invalid"),
    ("iri-reference", "/\u00e2\u03c0\u03c0", "a trailing newline after a valid IRI Reference is invalid"),
]


def check(fmt: str, value: str) -> bool:
    """Mirror the call each checker in jsonschema/_format.py makes."""
    if fmt == "date-time":
        return bool(validate_rfc3339(value.upper()))
    if fmt == "time":
        # jsonschema prefixes a date so it can reuse validate_rfc3339.
        return bool(validate_rfc3339(("1970-01-01T" + value).upper()))
    if fmt == "hostname":
        return FQDN(value, min_labels=1).is_valid
    try:
        return bool(rfc3987.parse(value, rule=RULES[fmt]))
    except ValueError:
        return False


def guarded(fmt: str, value: str) -> bool:
    """The fix: refuse a trailing line feed before delegating."""
    if value.endswith("\n"):
        return False
    return check(fmt, value)


def run(group: str) -> list[dict]:
    rows = []
    for fmt, value, description in CASES:
        for label, instance in (("bare", value), ("LF", value + "\n")):
            got = (check if group == "before" else guarded)(fmt, instance)
            rows.append({
                "format": fmt,
                "instance": instance,
                "variant": label,
                "accepted": got,
                "suite": description,
            })
    return rows


def show(rows: list[dict]) -> None:
    print(f"{'format':15} {'variant':8} {'accepted':9} instance")
    for row in rows:
        print(f"{row['format']:15} {row['variant']:8} {str(row['accepted']):9} "
              f"{row['instance']!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--emit", metavar="DIR")
    args = parser.parse_args()

    before, after = run("before"), run("after")

    print("=== as shipped: the bare value and the same value with a trailing LF ===")
    show(before)
    print("\n=== with a trailing-newline guard in front of every call ===")
    show(after)

    failures = []
    for row in before:
        # Both variants are accepted today; that is the leak.
        if not row["accepted"]:
            failures.append(f"before: {row['format']} {row['variant']} unexpectedly rejected")
    for row in after:
        expected = row["variant"] == "bare"
        if row["accepted"] != expected:
            failures.append(f"after: {row['format']} {row['variant']} = {row['accepted']}, want {expected}")

    print()
    if failures:
        print("FAIL")
        for line in failures:
            print(" ", line)
        return 1
    print(f"ALL PASS  ({len(before)} cases before, {len(after)} after, "
          f"{len(CASES)} formats)")

    if args.emit:
        out = Path(args.emit)
        out.mkdir(parents=True, exist_ok=True)
        (out / "before.json").write_text(json.dumps(before, indent=1, ensure_ascii=False), encoding="utf-8")
        (out / "after.json").write_text(json.dumps(after, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out / 'before.json'} and {out / 'after.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
