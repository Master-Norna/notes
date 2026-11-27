"""One ordering line, two pypdf builds: does plus care which operand comes first?

The parent build (`8ffe8f2`) sorts the two operands of `PageRange.__add__` by
start only.  The merge commit (`d062011`, PR #4468) also sorts by descending
stop, so an empty range such as `2:0` no longer decides whether the other
operand starts "after" its end.

    python -B run.py          # show the comparison
    python -B run.py --test   # additionally assert the expected behaviour

Both vendored trees are complete, unmodified `pypdf/` packages; the import
path is the only thing that decides which build answers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable

VENDORS = {
    "parent": HERE / "vendor" / "pypdf-parent",
    "merged": HERE / "vendor" / "pypdf-merged",
}

# verdict of `a + b` in each build: the error string, or the sum.
EXPECTED_ADDS = {
    "parent": {
        ("2:0", "2:5"): ValueError("Can't add PageRanges with gap"),
        ("2:5", "2:0"): "2:5",
        ("0:2", "5:8"): ValueError("Can't add PageRanges with gap"),
    },
    "merged": {
        ("2:0", "2:5"): "2:5",
        ("2:5", "2:0"): "2:5",
        ("0:2", "5:8"): ValueError("Can't add PageRanges with gap"),
    },
}

# how many of the ten blank pages each append kept, or error when the sum failed.
EXPECTED_APPENDS = {
    "parent": {("2:0", "2:5"): "error", ("2:5", "2:0"): 3},
    "merged": {("2:0", "2:5"): 3, ("2:5", "2:0"): 3},
}

EXPECTED_PAGES = {"2:0": [], "2:5": [2, 3, 4]}


def run_probe(vendor: Path) -> dict:
    completed = subprocess.run(
        [PYTHON, "-I", "-B", str(HERE / "probe.py"), str(vendor)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


def verdict(case: dict, key: str) -> int | str:
    if "error" in case:
        return "error"
    return case[key]


def fmt(value: int | str) -> str:
    if value == "error":
        return "gap error"
    if isinstance(value, int):
        return f"{value} pages"
    return f"= {value}"


def check(build: str, report: dict, errors: list[str]) -> None:
    for case in report["adds"]:
        want = EXPECTED_ADDS[build][(case["a"], case["b"])]
        got = verdict(case, "sum")
        if isinstance(want, ValueError):
            if got != "error":
                errors.append(f"{build}: {case['a']} + {case['b']} gave {got!r}; want the gap error")
        elif got != want:
            errors.append(f"{build}: {case['a']} + {case['b']} gave {got!r}; want {want!r}")
    for case in report["appends"]:
        want = EXPECTED_APPENDS[build][(case["a"], case["b"])]
        got = verdict(case, "appended_pages")
        if want == "error" and got != "error":
            errors.append(f"{build}: appending {case['a']} + {case['b']} kept {got} pages; want the gap error")
        elif want != "error" and got != want:
            errors.append(f"{build}: appending {case['a']} + {case['b']} kept {got}; want {want} pages")
    for name, want in EXPECTED_PAGES.items():
        got = report["ranges"][name]["pages"]
        if got != want:
            errors.append(f"{build}: {name} resolved to pages {got}; want {want}")


def main() -> int:
    test = "--test" in sys.argv
    builds = {name: run_probe(path) for name, path in VENDORS.items()}
    parent, merged = builds["parent"], builds["merged"]

    print(f"== PageRange over a document of {parent['n_pages']} pages ==")
    for name in ("2:0", "2:5"):
        print(f"PageRange({name!r:8})  ->  pages {parent['ranges'][name]['pages']}")
    if test:
        errors: list[str] = []
        check("parent", parent, errors)
        check("merged", merged, errors)

    print()
    print("== PageRange + PageRange ==")
    print(f"{'sum':>14}   parent            merged")
    for case in parent["adds"]:
        p = fmt(verdict(case, "sum"))
        m = fmt(verdict(next(c for c in merged["adds"] if (c["a"], c["b"]) == (case["a"], case["b"])), "sum"))
        print(f"{case['a'] + ' + ' + case['b']:>14}   {p:<17} {m}")

    print()
    print("== append(reader, pages=a + b) to a ten-page file ==")
    print(f"{'sum':>14}   parent            merged")
    for case in parent["appends"]:
        p = fmt(verdict(case, "appended_pages"))
        m = fmt(verdict(next(c for c in merged["appends"] if (c["a"], c["b"]) == (case["a"], case["b"])), "appended_pages"))
        print(f"{case['a'] + ' + ' + case['b']:>14}   {p:<17} {m}")

    if test:
        if errors:
            for e in errors:
                print(f"FAIL {e}")
            return 1
        print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
