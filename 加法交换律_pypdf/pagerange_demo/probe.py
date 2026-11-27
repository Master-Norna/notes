"""Import the vendored pypdf at the given path, report what PageRange.__add__ does.

usage: python -I -B probe.py <vendor-dir>
"""

import io
import json
import sys

sys.path.insert(0, sys.argv[1])
from pypdf import PageRange, PdfReader, PdfWriter  # noqa: E402

N = 10

ADDS = (("2:0", "2:5"), ("2:5", "2:0"), ("0:2", "5:8"))
APPENDS = (("2:0", "2:5"), ("2:5", "2:0"))


def add_case(a: str, b: str) -> dict:
    try:
        return {"a": a, "b": b, "sum": str(PageRange(a) + PageRange(b))}
    except ValueError as err:
        return {"a": a, "b": b, "error": str(err)}


def blank_doc() -> io.BytesIO:
    writer = PdfWriter()
    for _ in range(N):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf


def append_case(a: str, b: str) -> dict:
    try:
        merged = PdfWriter()
        merged.append(PdfReader(blank_doc()), pages=PageRange(a) + PageRange(b))
        return {"a": a, "b": b, "appended_pages": len(merged.pages)}
    except ValueError as err:
        return {"a": a, "b": b, "error": str(err)}


def range_note(name: str) -> dict:
    start, stop, step = PageRange(name).indices(N)
    return {"pages": list(range(start, stop, step))}


report = {
    "n_pages": N,
    "ranges": {name: range_note(name) for name in ("2:0", "2:5")},
    "adds": [add_case(a, b) for a, b in ADDS],
    "appends": [append_case(a, b) for a, b in APPENDS],
}
print(json.dumps(report, ensure_ascii=False, indent=2))
