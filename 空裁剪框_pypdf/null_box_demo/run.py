"""Replay pypdf #4375: a null page box in the fallback chain.

Two snapshots of the library are vendored:

  vendor/base-8eeb0509   py-pdf/pypdf @ 8eeb0509  (parent of the fix)
  vendor/merge-049dbfb3  py-pdf/pypdf @ 049dbfb3  (merge of PR #4375)

Every case runs in its own isolated interpreter (`-I -B`) with one snapshot
on sys.path, because both snapshots install the same top-level package name.

Usage:
  python -B run.py --test            # compare both snapshots, exit 1 on mismatch
  python -B run.py                   # same, plus the per-case table
  python -B run.py --emit DIR        # write the sample PDFs into DIR
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

BASE = "base-8eeb0509"
MERGE = "merge-049dbfb3"

CASES = [
    ("healthy", "a page without the entry", "ok"),
    ("null-cropbox/trimbox-first", "read /TrimBox first", "ok"),
    ("null-cropbox/cropbox-first", "read /CropBox first, then /TrimBox", "ok"),
    ("null-cropbox/artbox-first", "read /ArtBox first", "ok"),
    ("null-cropbox/bleedbox-first", "read /BleedBox first", "ok"),
    ("indirect-null/trimbox-first", "/CropBox points at an indirect null", "ok"),
    ("null-cropbox/scale-by", "writer.add_page(...).scale_by(0.5)", "ok"),
    ("null-cropbox/after-cropbox-read", "what /CropBox holds after reading it once", "ok"),
]

# What each case should do on the merged snapshot. The parent snapshot is
# measured, not asserted: its failures are the point of the replay.
EXPECT = {
    "healthy": (True, [0.0, 0.0, 100.0, 200.0]),
    "null-cropbox/trimbox-first": (True, [0.0, 0.0, 100.0, 200.0]),
    "null-cropbox/cropbox-first": (True, {"cropbox": [0.0, 0.0, 100.0, 200.0], "trimbox": [0.0, 0.0, 100.0, 200.0]}),
    "null-cropbox/artbox-first": (True, [0.0, 0.0, 100.0, 200.0]),
    "null-cropbox/bleedbox-first": (True, [0.0, 0.0, 100.0, 200.0]),
    "indirect-null/trimbox-first": (True, [0.0, 0.0, 100.0, 200.0]),
    "null-cropbox/scale-by": (True, [0.0, 0.0, 50.0, 100.0]),
    "null-cropbox/after-cropbox-read": (True, {"type": "RectangleObject", "value": [0.0, 0.0, 100.0, 200.0]}),
}


def _pdf_bytes(indirect: bool = False) -> bytes:
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import NameObject, NullObject

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=200)
    page = writer.pages[0]
    value = writer._add_object(NullObject()) if indirect else NullObject()
    page[NameObject("/CropBox")] = value
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _box(value):
    return [round(float(v), 3) for v in value]


def _run_case(case: str):
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    if case == "healthy":
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=200)
        buf = BytesIO()
        writer.write(buf)
        return _box(PdfReader(BytesIO(buf.getvalue())).pages[0].trimbox)

    if case == "null-cropbox/trimbox-first":
        return _box(PdfReader(BytesIO(_pdf_bytes())).pages[0].trimbox)

    if case == "null-cropbox/cropbox-first":
        page = PdfReader(BytesIO(_pdf_bytes())).pages[0]
        first = _box(page.cropbox)
        return {"cropbox": first, "trimbox": _box(page.trimbox)}

    if case == "null-cropbox/artbox-first":
        return _box(PdfReader(BytesIO(_pdf_bytes())).pages[0].artbox)

    if case == "null-cropbox/bleedbox-first":
        return _box(PdfReader(BytesIO(_pdf_bytes())).pages[0].bleedbox)

    if case == "indirect-null/trimbox-first":
        return _box(PdfReader(BytesIO(_pdf_bytes(indirect=True))).pages[0].trimbox)

    if case == "null-cropbox/scale-by":
        writer = PdfWriter()
        page = writer.add_page(PdfReader(BytesIO(_pdf_bytes())).pages[0])
        page.scale_by(0.5)
        return _box(page.mediabox)

    if case == "null-cropbox/after-cropbox-read":
        page = PdfReader(BytesIO(_pdf_bytes())).pages[0]
        page.cropbox
        raw = page.get("/CropBox")
        return {"type": type(raw).__name__, "value": _box(raw)}

    raise SystemExit(f"unknown case: {case}")


def _emit(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, indirect in (("null-cropbox.pdf", False), ("indirect-null-cropbox.pdf", True)):
        (directory / name).write_bytes(_pdf_bytes(indirect))
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=200)
    buf = BytesIO()
    writer.write(buf)
    (directory / "healthy.pdf").write_bytes(buf.getvalue())
    print(f"wrote 3 PDFs into {directory}")


def _worker(vendor: str, case: str) -> None:
    root = HERE / "vendor" / vendor
    sys.path.insert(0, str(root))
    import pypdf

    if Path(pypdf.__file__).resolve().parent != (root / "pypdf").resolve():
        raise SystemExit(f"imported {pypdf.__file__}, expected the vendored snapshot")
    try:
        print(json.dumps({"ok": True, "value": _run_case(case)}))
    except Exception as exc:  # noqa: BLE001 - the error text is the observation
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))


def _measure(vendor: str) -> dict[str, dict]:
    out = {}
    for case, _, _ in CASES:
        proc = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--worker", vendor, case],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            out[case] = {"ok": False, "error": (proc.stderr or proc.stdout).strip().splitlines()[-1]}
            continue
        out[case] = json.loads(proc.stdout.strip().splitlines()[-1])
    return out


def _short(result: dict) -> str:
    if result["ok"]:
        return json.dumps(result["value"], ensure_ascii=False)
    return result["error"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", nargs=2, metavar=("VENDOR", "CASE"))
    parser.add_argument("--emit", metavar="DIR")
    parser.add_argument("--json", metavar="PATH")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.worker:
        _worker(*args.worker)
        return 0

    if args.emit:
        _emit(Path(args.emit))
        return 0

    base = _measure(BASE)
    merge = _measure(MERGE)
    if args.json:
        Path(args.json).write_text(
            json.dumps({"base": base, "merge": merge}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"{'case':<34} {'parent 8eeb0509':<58} {'merged 049dbfb3'}")
    print("-" * 150)
    failures = 0
    base_bad = 0
    for case, desc, _ in CASES:
        b, m = base[case], merge[case]
        if not b["ok"]:
            base_bad += 1
        expected_ok, expected_value = EXPECT[case]
        good = (m["ok"] == expected_ok) and (not expected_ok or m["value"] == expected_value)
        if not good:
            failures += 1
        print(f"{case:<34} {_short(b)[:56]:<58} {_short(m)[:56]}{'' if good else '   <-- MISMATCH'}")
    print()
    print(f"parent snapshot failed {base_bad}/{len(CASES)} cases; merged snapshot failed {failures}/{len(CASES)}")
    if args.test:
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
