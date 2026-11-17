"""Compare three skylos versions on the same workflow cases.

    python -B run.py --test     # assert the recorded matrix
    python -B run.py --table    # print the matrix as a Markdown table
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"

VERSIONS = [
    ("v560", "v5.6.0"),
    ("parent", "父版 a5024d7"),
    ("merge", "合并版 1a105bd"),
]

D = "SKY-D340"
X = "SKY-D327"

# Measured with `python -B run.py --json` on 2026-11-17; the article's table is
# this matrix rendered.
EXPECTED: dict[str, dict[str, list[list[object]]]] = {
    "v560": {
        "d327_alias_run": [[X, 7]],
        "d327_env_repeats_command": [],
        "d327_escaped_run": [],
        "d327_ignore_first_of_two": [],
        "d327_name_repeats_command": [],
        "d327_quoted_name_oneline": [],
        "d327_trailing_comment": [],
        "d327_two_identical_steps": [[X, 7]],
        "d340_comment_above_run": [[D, 9]],
        "d340_quoted_name_block": [[D, 8]],
        "d340_quoted_name_oneline": [],
        "d340_trailing_comment": [],
    },
    "parent": {
        "d327_alias_run": [[X, 7]],
        "d327_env_repeats_command": [],
        "d327_escaped_run": [],
        "d327_ignore_first_of_two": [],
        "d327_name_repeats_command": [],
        "d327_quoted_name_oneline": [],
        "d327_trailing_comment": [],
        "d327_two_identical_steps": [[X, 7]],
        "d340_comment_above_run": [],
        "d340_quoted_name_block": [],
        "d340_quoted_name_oneline": [],
        "d340_trailing_comment": [],
    },
    "merge": {
        "d327_alias_run": [[X, 7], [X, 9]],
        "d327_env_repeats_command": [[X, 9]],
        "d327_escaped_run": [[X, 8]],
        "d327_ignore_first_of_two": [[X, 9]],
        "d327_name_repeats_command": [[X, 7]],
        "d327_quoted_name_oneline": [[X, 7]],
        "d327_trailing_comment": [],
        "d327_two_identical_steps": [[X, 7], [X, 9]],
        "d340_comment_above_run": [],
        "d340_quoted_name_block": [[D, 7]],
        "d340_quoted_name_oneline": [[D, 7]],
        "d340_trailing_comment": [],
    },
}


def scan(version: str) -> dict[str, list[list[object]]]:
    out = subprocess.run(
        [sys.executable, "-B", str(HERE / "scan_one.py"), str(HERE / "vendor" / version), str(CASES)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(out.stdout)


def cell(findings: list[list[object]]) -> str:
    if not findings:
        return "未报出"
    return "、".join(f"第 {line} 行" for _, line in findings)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--table"
    results = {version: scan(version) for version, _ in VERSIONS}

    if mode == "--json":
        print(json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True))
        return 0

    if mode == "--table":
        names = [case.stem for case in sorted(CASES.glob("*.yml"))]
        head = "| 用例 | " + " | ".join(label for _, label in VERSIONS) + " |"
        rule = "| --- | " + " | ".join("---" for _ in VERSIONS) + " |"
        print(head)
        print(rule)
        for name in names:
            row = [cell(results[version].get(name, [])) for version, _ in VERSIONS]
            print(f"| `{name}` | " + " | ".join(row) + " |")
        return 0

    if mode == "--test":
        failures = []
        for version, label in VERSIONS:
            wanted = EXPECTED[version]
            got = results[version]
            for name in sorted(set(wanted) | set(got)):
                if wanted.get(name) != got.get(name):
                    failures.append(
                        f"{label} / {name}: 期望 {wanted.get(name)}，实得 {got.get(name)}"
                    )
        if failures:
            print("FAIL")
            for line in failures:
                print(" ", line)
            return 1
        print("ALL PASS")
        return 0

    raise SystemExit(f"unknown mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
