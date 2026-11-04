#!/usr/bin/env python3
"""Report the trailing ``startxref`` pointer (and any ``/Prev``) of a PDF.

A PDF ends with ``startxref``, one byte offset, and ``%%EOF``; an updated file
also carries ``/Prev`` offsets in its trailer dictionary.  This script reads
the last kilobyte and says where those numbers point.  It is a triage aid,
not a validator: a positive offset that lands inside the file can still point
at the wrong object, and a ``/Prev`` chain can run deeper than this window.

Usage:

    python scan_startxref.py PATH [PATH ...]

A PATH may be a glob such as ``ptr/*.pdf``.

Exit code is 1 when at least one pointer is negative or missing, so the
command can be used in a loop over a batch.
"""
from __future__ import annotations

import re
import sys
from glob import glob
from pathlib import Path

TAIL_BYTES = 1024
STARTXREF = re.compile(rb"startxref\s+(-?\d+)\s+%%EOF")
PREV = re.compile(rb"/Prev\s+(-?\d+)")


def describe(value: int, size: int, target: bytes) -> str:
    if value < 0:
        n = -value
        return "negative, %d byte%s before the file starts" % (n, "" if n == 1 else "s")
    if value == 0:
        return "zero, points at byte 0"
    if value >= size:
        return "past the end, file is %d bytes" % size
    head = target[:12].replace(b"\r", b" ").replace(b"\n", b" ").decode("latin-1")
    return "inside file, starts %r" % head


def scan(path: Path) -> tuple[str, bool]:
    data = path.read_bytes()
    tail = data[-TAIL_BYTES:]
    starts = STARTXREF.findall(tail)
    prevs = PREV.findall(tail)
    if not starts:
        return "no startxref/%%EOF in the last %d bytes" % TAIL_BYTES, True
    start = int(starts[-1])
    target = data[start:] if 0 <= start < len(data) else b""
    parts = ["startxref %d: %s" % (start, describe(start, len(data), target))]
    bad = start < 0
    for raw in prevs:
        value = int(raw)
        parts.append("/Prev %d: %s" % (value, describe(value, len(data), b"")))
        bad = bad or value < 0
    return "; ".join(parts), bad


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    bad = 0
    for pattern in argv:
        names = sorted(glob(pattern)) if any(ch in pattern for ch in "*?[") else [pattern]
        if not names:
            print(f"{pattern:20} no file matches")
            bad += 1
            continue
        for name in names:
            path = Path(name)
            try:
                verdict, is_bad = scan(path)
            except OSError as exc:
                print(f"{path.name:20} {exc}")
                bad += 1
                continue
            bad += int(is_bad)
            print(f"{path.name:20} {verdict}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
