#!/usr/bin/env python3
"""pypdf #4144: a negative startxref pointer crashes before / after the fix.

The demo imports two complete, fixed pypdf snapshots from vendor/ and feeds
each one the same crafted PDF: a valid one-page file whose trailing
``startxref`` offset has been negated.  No pypdf installation is needed.

Run from the repository root:

    python -B -S 负指针_pypdf/negative_startxref_demo/run.py --test

The parent (pre-fix) snapshot raises ``ValueError: negative seek value -257``.
The merge snapshot normalizes the pointer to zero, reuses the #3157 repair
path, and reads the page with a warning.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSIONS = {
    "parent": {
        "sha": "b78c2aa5301ee4fb1ee024b9838923945ab357b6",
        "role": "merge parent (before #4144)",
    },
    "merge": {
        "sha": "91a73b5e8e9701efdad26b865964c2a53cb110b3",
        "role": "#4144 merge",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CHILD = r"""
import io, json, logging, sys

def deny_socket(event, args):
    if event.startswith("socket."):
        raise RuntimeError("offline demo: socket event blocked: " + event)

sys.addaudithook(deny_socket)
sys.path.insert(0, sys.argv[1])
import pypdf
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []
    def emit(self, record):
        self.messages.append(record.getMessage())

def probe(label, payload, strict=False):
    handler = Capture()
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        reader = PdfReader(io.BytesIO(payload), strict=strict)
        outcome = {"ok": True, "pages": len(reader.pages)}
    except Exception as exc:
        outcome = {"ok": False, "type": type(exc).__name__, "message": str(exc)}
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    outcome["label"] = label
    outcome["strict"] = strict
    outcome["warnings"] = handler.messages
    return outcome

# Build one valid PDF, then rewrite only the trailing pointer.  The writer is
# from the same snapshot, so every other byte is a normal pypdf document.
buffer = io.BytesIO()
writer = PdfWriter()
writer.add_blank_page(100, 100)
writer.write(buffer)
healthy = buffer.getvalue()
marker = healthy.rfind(b"startxref")
eof = healthy.rfind(b"%%EOF")
offset = int(healthy[marker:eof].split(b"\n")[1].strip())
tail = healthy[eof + 5:]

def with_pointer(value):
    return healthy[:marker] + ("startxref\n%d\n%%%%EOF" % value).encode() + tail

negative = with_pointer(-offset)
zero = with_pointer(0)

print(json.dumps({
    "version": pypdf.__version__,
    "offset": offset,
    "healthy": probe("healthy", healthy),
    "negative": probe("negative", negative),
    "zero": probe("zero", zero),
    "negative_strict": probe("negative_strict", negative, True),
    "zero_strict": probe("zero_strict", zero, True),
}))
"""


def run_child(label: str) -> dict:
    package = ROOT / "vendor" / label
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-S", "-c", CHILD, str(package)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": ""},
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"child {label} failed with exit code {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def compact(result: dict) -> str:
    if result["ok"]:
        return f"ok pages={result['pages']} warnings={len(result['warnings'])}"
    return f"{result['type']}: {result['message']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="run all assertions")
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--output", type=Path, help="also write the JSON report here")
    args = parser.parse_args()

    if not (sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.no_site):
        command = [
            sys.executable,
            "-I",
            "-B",
            "-S",
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ]
        raise SystemExit(subprocess.call(command))

    results = {}
    for label in ("parent", "merge"):
        results[label] = run_child(label)
        results[label]["source_sha"] = VERSIONS[label]["sha"]
        results[label]["source_role"] = VERSIONS[label]["role"]
        results[label]["source_files"] = sum(
            1 for p in (ROOT / "vendor" / label / "pypdf").rglob("*") if p.is_file()
        )
        results[label]["source_sha256"] = {
            str(p.relative_to(ROOT)): sha256(p)
            for p in sorted((ROOT / "vendor" / label / "pypdf").rglob("*"))
            if p.is_file()
        }

    parent = results["parent"]
    merge = results["merge"]
    failures = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    for label, data in results.items():
        check(data["offset"] == 256, f"{label}: expected offset 256, got {data['offset']}")
        check(data["healthy"]["ok"] and data["healthy"]["pages"] == 1, f"{label}: healthy PDF")
        check(data["healthy"]["warnings"] == [], f"{label}: healthy PDF should not warn")

    check(
        parent["zero"]["ok"] and parent["zero"]["pages"] == 1,
        "parent: zero pointer should already be recovered by #3157",
    )
    check(
        parent["zero"]["warnings"]
        == ["incorrect startxref pointer(4)", "parsing for Object Streams"],
        f"parent: unexpected zero-pointer warnings {parent['zero']['warnings']}",
    )
    check(
        not parent["negative"]["ok"]
        and parent["negative"]["type"] == "ValueError"
        and parent["negative"]["message"] == "negative seek value -257",
        f"parent: expected ValueError(-257), got {compact(parent['negative'])}",
    )
    check(
        not parent["negative_strict"]["ok"]
        and parent["negative_strict"]["type"] == "ValueError",
        "parent: strict negative should also leak ValueError",
    )

    check(
        merge["zero"]["warnings"]
        == ["incorrect startxref pointer(4)", "parsing for Object Streams"],
        f"merge: zero pointer should match #3157 behavior, got {merge['zero']['warnings']}",
    )
    check(
        merge["negative"]["ok"] and merge["negative"]["pages"] == 1,
        f"merge: negative pointer should recover, got {compact(merge['negative'])}",
    )
    check(
        merge["negative"]["warnings"]
        == [
            "Negative startxref pointer (-256), treating it as zero.",
            "incorrect startxref pointer(4)",
            "parsing for Object Streams",
        ],
        f"merge: unexpected negative warnings {merge['negative']['warnings']}",
    )
    check(
        not merge["negative_strict"]["ok"]
        and merge["negative_strict"]["type"] == "PdfReadError"
        and merge["negative_strict"]["message"] == "Broken xref table",
        f"merge: strict negative should be PdfReadError, got {compact(merge['negative_strict'])}",
    )
    check(
        merge["negative_strict"]["warnings"]
        == ["Negative startxref pointer (-256), treating it as zero."],
        f"merge: strict negative warnings {merge['negative_strict']['warnings']}",
    )
    check(
        not merge["zero_strict"]["ok"]
        and merge["zero_strict"]["type"] == "PdfReadError"
        and merge["zero_strict"]["message"] == "Broken xref table",
        "merge: strict zero should be PdfReadError",
    )
    check(merge["zero_strict"]["warnings"] == [], "merge: strict zero should not warn")

    report = {
        "demo": "pypdf-negative-startxref",
        "python": sys.version.split()[0],
        "versions": {
            label: {
                "pypdf": data["version"],
                "sha": data["source_sha"],
                "role": data["source_role"],
                "files": data["source_files"],
            }
            for label, data in results.items()
        },
        "cases": {
            label: {
                key: data[key]
                for key in ("healthy", "zero", "negative", "negative_strict", "zero_strict")
            }
            for label, data in results.items()
        },
        "assertions": {
            "passed": not failures,
            "failures": failures,
        },
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Python {report['python']}  (two complete pypdf snapshots, no install)")
        print(f"{'case':22} {'parent b78c2aa':32} {'merge 91a73b5':32}")
        print("-" * 90)
        for key in ("healthy", "zero", "negative", "negative_strict", "zero_strict"):
            print(f"{key:22} {compact(parent[key]):32} {compact(merge[key]):32}")
        if failures:
            print("\nFAIL")
            for failure in failures:
                print(" -", failure)
        else:
            print(
                "\nPASS: parent leaks ValueError(-257); merge warns, recovers one page, "
                "and raises PdfReadError in strict mode."
            )

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
