"""Reproduce the five diff shapes from skylos PR #1196, parent vs merged.

Each case builds a throwaway Git repository with two commits and asks both
revisions of ``_get_per_file_diffs`` what they see.  The interesting output is
not a verdict on the code: it is the mapping itself.

Run:  python run.py [--test]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))

from parent import diff_paths as parent_parser  # noqa: E402
from merged import diff_paths as merged_parser  # noqa: E402

OLD = b"@login_required\ndef view():\n    return 1\n"
NEW = b"def view():\n    return 1\n"

CASES = [
    ("quoted_non_ascii_path", "vues_caf\u00e9.py", OLD, NEW),
    ("unquoted_path_with_space", "my views.py", OLD, NEW),
    (
        "hunk_line_looks_like_header",
        "evil.js",
        b'const note = "";\n',
        b"const note = `\n++ b/victim.js\n`;\n",
    ),
    (
        "bare_cr_fabricates_header",
        "app.py",
        b'note = "a\rdiff --git a/zz/zz b/zz/zz"\n@login_required\ndef view():\n    return 1\n',
        b'note = "a\rdiff --git a/zz/zz b/zz/zz"\n\ndef view():\n    return 1\n',
    ),
    (
        "non_utf8_source_bytes",
        "latin1.py",
        b'note = "caf\xe9"\n@login_required\ndef view():\n    return 1\n',
        b'note = "caf\xe9"\n\ndef view():\n    return 1\n',
    ),
]


def git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.safecrlf=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def repo_with_change(tmp: Path, name: str, before: bytes, after: bytes) -> Path:
    root = tmp / "repo"
    root.mkdir()
    git(root, "init", "-q")
    path = root / "src" / name
    path.parent.mkdir(parents=True)
    path.write_bytes(before)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "add")
    path.write_bytes(after)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "change")
    return root


def removed_lines(diff_text: str) -> list[str]:
    return [line for line in diff_text.split("\n") if line.startswith("-") and not line.startswith("---")]


def inspect(parser, root: Path) -> dict:
    record: dict = {}
    try:
        diffs = parser._get_per_file_diffs("HEAD~1", cwd=root)
    except Exception as exc:  # noqa: BLE001 - the failure is the observation
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record
    record["files"] = list(diffs)
    record["removed"] = {path: removed_lines(text) for path, text in diffs.items()}
    record["complete"] = any(
        any("@login_required" in line for line in lines) for lines in record["removed"].values()
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    rows = []
    for case_name, filename, before, after in CASES:
        with tempfile.TemporaryDirectory(prefix="diff-path-") as tmp:
            root = repo_with_change(Path(tmp), filename, before, after)
            parent = inspect(parent_parser, root)
            merged = inspect(merged_parser, root)
            ranges = parent_parser._parse_unified_diff(
                subprocess.run(
                    ["git", "-c", "core.autocrlf=false", "diff", "--unified=3", "HEAD~1...HEAD"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                ).stdout.decode("utf-8", errors="replace")
            )
            rows.append(
                {
                    "case": case_name,
                    "file": filename,
                    "parent": parent,
                    "merged": merged,
                    "shared_ranges": ranges,
                }
            )

    if args.test:
        expected = {
            "quoted_non_ascii_path": ([], ["src/vues_caf\u00e9.py"]),
            "unquoted_path_with_space": (["src/my views.py\t"], ["src/my views.py"]),
            "hunk_line_looks_like_header": (["victim.js"], ["src/evil.js"]),
            "bare_cr_fabricates_header": (["src/app.py"], ["src/app.py"]),
            "non_utf8_source_bytes": (None, ["src/latin1.py"]),
        }
        for row in rows:
            want_parent, want_merged = expected[row["case"]]
            got_parent = row["parent"].get("files")
            if want_parent is None:
                assert "error" in row["parent"], row
            else:
                assert got_parent == want_parent, (row["case"], got_parent, want_parent)
            assert row["merged"].get("files") == want_merged, (row["case"], row["merged"])

        # the parent lost the removed decorator in two cases even though it did
        # produce a diff for the file; the merged parser keeps it in all four
        # Python cases.
        assert rows[0]["parent"].get("complete") is False
        assert rows[0]["merged"].get("complete") is True
        assert rows[3]["parent"].get("complete") is False
        assert rows[3]["merged"].get("complete") is True
        assert rows[4]["merged"].get("complete") is True
        print("ALL PASS")
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    for row in rows:
        print(f"\n## {row['case']} ({row['file']})")
        print(f"parent: {row['parent']}")
        print(f"merged: {row['merged']}")
        print(f"shared ranges: {row['shared_ranges']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
