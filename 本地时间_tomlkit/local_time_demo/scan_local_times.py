#!/usr/bin/env python3
"""Find TOML local times that carry an offset (tomlkit <= 0.15.1 wrote these).

The pattern is a value that starts with a time and then a UTC offset, e.g.

    start = 07:32:00+02:00

TOML 1.0 has no such type: a local time has no offset, and an offset
date-time needs a date. Every parser rejects it, so a file written this way
by tomlkit from a tz-aware ``datetime.time`` cannot be read back.

Usage (no third-party packages needed):

    python -B -S 本地时间_tomlkit/local_time_demo/scan_local_times.py PATH [PATH ...]

PATH may be a .toml file or a directory (searched recursively for *.toml).
Exit code is 1 when a hit is found or a file does not parse.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# A time literal immediately followed by an offset, not preceded by a date.
PATTERN = re.compile(r"(?<![\d:])(\d{2}:\d{2}:\d{2}(?:\.\d+)?)([+-]\d{2}:\d{2}|Z)\b")
DATE_BEFORE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]$")


def inside_string(line: str, index: int) -> bool:
    """Cheap quote count: the match sits inside a string if a quote is open."""
    quote = ""
    i = 0
    while i < index:
        ch = line[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        i += 1
    return bool(quote)


def scans(text: str) -> list[tuple[int, int, str]]:
    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in PATTERN.finditer(line):
            if DATE_BEFORE.search(line[: match.start()]):
                continue  # 1979-05-27T07:32:00+02:00 is a legal offset date-time
            if inside_string(line, match.start()):
                continue
            hits.append((number, match.start() + 1, match.group(0)))
    return hits


def tomllib_error(text: str) -> str | None:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        return None
    try:
        tomllib.loads(text)
    except Exception as exc:  # TOMLDecodeError
        return f"{type(exc).__name__}: {exc}"
    return None


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.toml")))
        else:
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help=".toml files or directories")
    args = parser.parse_args()

    files = collect(args.paths)
    if not files:
        print("no .toml files found")
        return 0

    hits = 0
    rejected = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        found = scans(text)
        error = tomllib_error(text)
        if error:
            rejected += 1
        if found:
            for line, col, value in found:
                print(f"{path.as_posix()}:{line}:{col}  {value}")
            hits += len(found)
            if error:
                print(f"{path.as_posix()}: tomllib rejects this file: {error}")
        elif error:
            print(f"{path.as_posix()}: no offset on a time, but rejected: {error}")
        else:
            print(f"{path.as_posix()}: clean")

    print(
        f"--- {len(files)} file(s) scanned, {hits} hit(s), "
        f"{rejected} rejected by tomllib"
    )
    return 1 if hits or rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
