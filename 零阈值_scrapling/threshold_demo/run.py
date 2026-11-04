"""Reproduce Scrapling's find_similar threshold behaviour before and after #539.

The demo runs the real ``Selector.find_similar`` from two fixed snapshots of
``scrapling/parser.py`` (upstream parent 49eaff11 and merge 104294c2).  The
rest of the package comes from the installed ``scrapling`` distribution, so
everything except that one file is identical between the two runs.

Usage:
    python run.py            # print the comparison table
    python run.py --test     # also assert the expected contract, exit 1 on mismatch
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"

# Each case builds <div><a ref>Alpha</a><a cand>Beta</a></div>.  The reference
# is the first link; find_similar must decide whether the second one is alike.
CASES = [
    {
        "name": "no attrs vs class",
        "ref": "",
        "cand": 'class="sale"',
        "thresholds": [0, 0.2],
        "expect": [["Beta"], []],
        "why": "threshold 0 disables attribute filtering",
    },
    {
        "name": "href only vs class",
        "ref": 'href="/alpha"',
        "cand": 'href="/beta" class="sale"',
        "thresholds": [0, 0.2],
        "expect": [["Beta"], []],
        "why": "href is ignored by default, so the reference has no attributes",
    },
    {
        "name": "both no attrs",
        "ref": "",
        "cand": "",
        "thresholds": [0, 0.2],
        "expect": [["Beta"], ["Beta"]],
        "why": "two attribute-free elements are a 100% match",
    },
    {
        "name": "same class",
        "ref": 'class="product"',
        "cand": 'class="product"',
        "thresholds": [0, 0.2],
        "expect": [["Beta"], ["Beta"]],
        "why": "identical attribute value scores 1.0",
    },
    {
        "name": "extra attribute penalty",
        "ref": 'class="product"',
        "cand": 'class="product" id="x"',
        "thresholds": [0.5, 0.6],
        "expect": [["Beta"], []],
        "why": "score 1 / max(1, 2) = 0.5",
    },
    {
        "name": "different class",
        "ref": 'class="product"',
        "cand": 'class="deal"',
        "thresholds": [0, 0.2],
        "expect": [["Beta"], []],
        "why": "score 0.0 passes a 0 threshold, even before the fix",
    },
    {
        "name": "href not ignored",
        "ref": 'href="aaa"',
        "cand": 'href="zzz"',
        "ignore_attributes": [],
        "thresholds": [0, 0.2],
        "expect": [["Beta"], []],
        "why": "score 0.0 with one comparison; same shape as the class case",
    },
]


def make_html(case: dict[str, object]) -> str:
    return (
        "<html><body><div class=\"list\">"
        f"<a {case['ref']}>Alpha</a>"
        f"<a {case['cand']}>Beta</a>"
        "</div></body></html>"
    )


def worker() -> None:
    from scrapling.parser import Selector

    results = []
    for case in CASES:
        html = make_html(case)
        for threshold in case["thresholds"]:
            page = Selector(html)
            reference = page.css("a")[0]
            kwargs = {"similarity_threshold": threshold}
            if "ignore_attributes" in case:
                kwargs["ignore_attributes"] = case["ignore_attributes"]
            found = [element.text for element in reference.find_similar(**kwargs)]
            results.append(
                {
                    "name": case["name"],
                    "threshold": threshold,
                    "found": found,
                    "parser": sys.modules["scrapling.parser"].__file__,
                }
            )
    print(json.dumps(results, ensure_ascii=False))


def run_variant(variant: str) -> list[dict[str, object]]:
    import scrapling

    package = Path(scrapling.__file__).resolve().parent
    scratch = Path(tempfile.mkdtemp(prefix=f"scrapling-{variant}-"))
    target = scratch / "scrapling"
    shutil.copytree(package, target, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(VENDOR / variant / "parser.py", target / "parser.py")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(scratch) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"worker {variant} failed:\n{proc.stderr}")
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return json.loads(proc.stdout)


def main() -> None:
    before = run_variant("parent")
    after = run_variant("merge")
    if len(before) != len(after):
        raise SystemExit("variant result length mismatch")

    print(f"parent parser: {before[0]['parser']}")
    print(f"merge  parser: {after[0]['parser']}")
    print()
    header = f"{'case':<26} {'threshold':>9} {'before':<14} {'after':<14} {'expect':<14} ok"
    print(header)
    print("-" * len(header))

    before_fail = 0
    after_fail = 0
    for row_before, row_after, case in zip(before, after, [
        {**case, "threshold": threshold}
        for case in CASES
        for threshold in case["thresholds"]
    ]):
        expected = case["expect"][case["thresholds"].index(case["threshold"])]
        before_ok = row_before["found"] == expected
        after_ok = row_after["found"] == expected
        before_fail += 0 if before_ok else 1
        after_fail += 0 if after_ok else 1
        print(
            f"{str(row_before['name']):<26} {str(row_before['threshold']):>9} "
            f"{str(row_before['found']):<14} {str(row_after['found']):<14} "
            f"{str(expected):<14} {'ok' if after_ok else 'MISMATCH'}"
        )

    total = len(before)
    print()
    print(f"rows: {total}")
    print(f"before: {before_fail} mismatches")
    print(f"after:  {after_fail} mismatches")
    if "--test" in sys.argv:
        # The two expected pre-fix failures are the documented counterexample:
        # a zero threshold must disable attribute filtering.
        if after_fail or before_fail != 2:
            raise SystemExit(1)


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker()
    else:
        main()
