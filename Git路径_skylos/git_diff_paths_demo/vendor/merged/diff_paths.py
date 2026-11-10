"""Verbatim extraction from skylos merged snapshot.

Source: https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py
Revision: 380b2a3e315ca05f5546139c691b678114e38dc4
License: Apache-2.0 (see ../LICENSE)
The functions below are copied without edits; only the imports and the
``_diff_root`` helper live in this module so the demo can run standalone.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from skylos.core.git_safety import (
    read_only_git_environment,
    worktree_safe_git_command,
)


def _diff_root(cwd):
    """Directory used to inspect a repository's filter configuration."""
    return Path(cwd) if cwd is not None else Path.cwd()


def _parse_unified_diff(
    diff_output: str, *, include_deletion_anchors: bool = True
) -> list[dict]:
    entries = []
    current_file = None
    in_hunk = False

    for line in diff_output.split("\n"):
        if line.startswith("diff --git "):
            current_file = None
            in_hunk = False
            continue
        if line.startswith("+++ ") and not in_hunk:
            current_file = _new_diff_header_path(line[4:])
            continue

        hunk_match = re.match(r"^@@ .+ \+(\d+)(?:,(\d+))? @@", line)
        if hunk_match:
            in_hunk = True
            if current_file is None:
                continue
            start = int(hunk_match.group(1))
            count = int(hunk_match.group(2) or 1)
            if count == 0 and not include_deletion_anchors:
                continue
            anchor = max(1, start)
            entries.append(
                {
                    "file": current_file,
                    "start": anchor,
                    "end": anchor if count == 0 else start + count - 1,
                }
            )

    return entries

def _new_diff_header_path(raw: str) -> str | None:
    from skylos.done.base import _unquote_c_style

    # Git appends a TAB after an unquoted name containing spaces. Literal
    # filename tabs, newlines and quotes use Git's C-style quoted form.
    path = raw.partition("\t")[0]
    if path.startswith('"'):
        if len(path) < 2 or not path.endswith('"'):
            raise ValueError("Cannot compare changes: malformed quoted Git path")
        path = _unquote_c_style(path[1:-1])
    if path == "/dev/null":
        return None
    if not path.startswith("b/"):
        raise ValueError("Cannot compare changes: unsupported Git path header")
    return path[2:]

def _get_per_file_diffs(
    base_ref: str = "origin/main",
    *,
    cwd: str | os.PathLike[str] | None = None,
    raise_on_error: bool = False,
) -> dict[str, str]:
    """Return a dict mapping file paths to their individual diff text."""
    try:
        diff_cmd = worktree_safe_git_command(
            ["diff", "--unified=3", f"{base_ref}...HEAD"], _diff_root(cwd)
        )
        if diff_cmd is None:
            if raise_on_error:
                raise ValueError(
                    "Cannot compare changes: the repository configures Git "
                    "content filters that could not be inspected safely"
                )
            return {}
        result = subprocess.run(
            diff_cmd,
            cwd=cwd,
            capture_output=True,
            env=read_only_git_environment(),
            # Read bytes and decode explicitly, like get_changed_line_ranges:
            # universal-newline conversion could turn bare CR inside source
            # into fake headers.
        )
        if result.returncode != 0:
            if raise_on_error:
                raise ValueError(
                    "Cannot compare changes: Git diff failed; check that the "
                    "base ref exists in the scanned repository"
                )
            return {}
    except FileNotFoundError as exc:
        if raise_on_error:
            raise ValueError("Cannot compare changes: git is not installed") from exc
        return {}

    file_diffs: dict[str, str] = {}
    current_file = None
    current_lines: list[str] = []
    in_hunk = False

    diff_output = result.stdout
    if isinstance(diff_output, bytes):
        diff_output = diff_output.decode("utf-8", errors="replace")

    for line in diff_output.split("\n"):
        if line.startswith("diff --git"):
            if current_file and current_lines:
                file_diffs[current_file] = "\n".join(current_lines)
            current_file = None
            current_lines = [line]
            in_hunk = False
        elif line.startswith("+++ ") and not in_hunk:
            # Reuse the shared header parser: Git quotes paths with non-ASCII
            # bytes, quotes or control characters, and appends a TAB after an
            # unquoted name containing spaces. A line inside a hunk that
            # happens to start with "+++ " is source text, not a new file.
            current_file = _new_diff_header_path(line[4:])
            current_lines.append(line)
        else:
            if line.startswith("@@"):
                in_hunk = True
            current_lines.append(line)

    if current_file and current_lines:
        file_diffs[current_file] = "\n".join(current_lines)

    return file_diffs
