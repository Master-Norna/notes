"""Offline, real-package three-revision reproduction of pypdf PR #4150.
Python >= 3.11. Run: python -B -S run.py --test [--json] [--output result.json]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PROVENANCE_SHA256 = "9a4abe006cc44b427d76dd790a87bc3f1ec43a8898da0db0de6df5e9982f09d1"
COMMITS = {
    "parent": "a23cc36da7a8e86f2b551b7a6eed1d8798301c73",
    "intermediate": "ad63551501ef8ad03ca91a8d1e5246a79319a048",
    "merge": "ccd8dc470e13915d384fb8b4c93a351cc1d79ae6",
}
NEWLINES = {"LF": b"\n", "CR": b"\r", "CRLF": b"\r\n"}
COUNTS = (0, 1, 999, 1000, 1001, 2000)


class VerificationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def deny_network(event, args):
    if event.startswith("socket."):
        raise RuntimeError("Network forbidden by demo socket audit hook: " + event)


def environment():
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "platform": sys.platform,
        "os_name": os.name,
        "windows_version": list(sys.getwindowsversion()) if sys.platform == "win32" else None,
        "recursion_limit": sys.getrecursionlimit(),
        "isolated": bool(sys.flags.isolated),
        "no_site": bool(sys.flags.no_site),
        "dont_write_bytecode": sys.dont_write_bytecode,
        "socket_policy": "audit hook rejects every socket.* event",
    }


def verify_sources(label=None):
    """Fail closed before import, including absent or unlisted package files."""
    manifest_path = ROOT / "provenance.json"
    raw = manifest_path.read_bytes()
    require(digest(raw) == PROVENANCE_SHA256, "provenance.json SHA-256 mismatch")
    manifest = json.loads(raw)
    require({s["label"]: s["commit"] for s in manifest["snapshots"]} == COMMITS,
            "Unexpected snapshot identities")
    require(digest((ROOT / "LICENSE").read_bytes()) == manifest["top_level_license_sha256"],
            "Top-level LICENSE SHA-256 mismatch")
    verified = []
    for row in manifest["snapshots"]:
        if label is not None and row["label"] != label:
            continue
        snapshot = ROOT / "vendor" / row["label"]
        actual = {p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()}
        expected = {entry["path"] for entry in row["files"]}
        require(actual == expected, f"{row['label']}: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
        for entry in row["files"]:
            path = snapshot / entry["path"]
            require(not path.is_symlink(), f"Symlink forbidden: {path}")
            data = path.read_bytes()
            require(len(data) == entry["bytes"] and digest(data) == entry["sha256"],
                    f"SHA-256 mismatch: {row['label']}/{entry['path']}")
        verified.append({"label": row["label"], "commit": row["commit"],
                         "files_verified": len(row["files"]),
                         "file_bytes_verified": sum(e["bytes"] for e in row["files"]),
                         "archive_sha256": row["archive_sha256"]})
    return manifest, verified


def socket_audit_self_test():
    import socket
    try:
        socket.socket()
    except RuntimeError as exc:
        require("Network forbidden by demo" in str(exc), "Unexpected socket rejection")
        return {"attempt": "socket.socket() (no network connection)", "blocked": True}
    raise VerificationError("Socket audit hook failed to block socket construction")


class BodyGuard(io.BytesIO):
    """Observe actual read ranges, not just the final stream position."""
    def __init__(self, data, body_start):
        super().__init__(data)
        self.body_start = body_start
        self.maximum_read_end = 0
        self.body_read_attempts = 0

    def read(self, size=-1):
        start = self.tell()
        end = len(self.getbuffer()) if size < 0 else min(start + size, len(self.getbuffer()))
        if end > self.body_start:
            self.body_read_attempts += 1
            raise VerificationError("Parser attempted to scan the 1001st comment body")
        result = super().read(size)
        self.maximum_read_end = max(self.maximum_read_end, start + len(result))
        return result

    def readline(self, size=-1):
        raise VerificationError("Unexpected readline bypass of body guard")

    def readinto(self, buffer):
        raise VerificationError("Unexpected readinto bypass of body guard")

    def read1(self, size=-1):
        return self.read(size)


# pypdf remains unimported until each worker has verified its own snapshot.
def worker(label):
    manifest, verified = verify_sources(label)
    snapshot = ROOT / "vendor" / label
    sys.path.insert(0, str(snapshot))
    import pypdf
    from pypdf.errors import LimitReachedError
    from pypdf.generic import (
        ArrayObject, BooleanObject, DictionaryObject, IndirectObject,
        NullObject, read_object,
    )
    require(Path(pypdf.__file__).resolve() == snapshot / "pypdf/__init__.py", "Imported wrong pypdf")
    # Do not import tests.utils: unrelated Pillow/pytest dependencies are not needed.
    row = next(s for s in manifest["snapshots"] if s["label"] == label)
    source = (snapshot / "tests/utils.py").read_text("utf-8")
    nodes = ast.parse(source).body
    helpers = []
    for item in row["extracted_helpers"]:
        node = next(n for n in nodes if getattr(n, "name", None) == item["name"])
        text = ast.get_source_segment(source, node)
        require(digest(text.encode("utf-8")) == item["source_segment_utf8_sha256"],
                "Upstream helper source mismatch: " + item["name"])
        helpers.append(text)
    namespace = {"sys": sys, "DictionaryObject": DictionaryObject, "IndirectObject": IndirectObject}
    exec(compile("from __future__ import annotations\n" + "\n\n".join(helpers),
                 str(snapshot / "tests/utils.py") + " [AST source segments]", "exec"), namespace)
    reader = namespace["ReaderDummy"]()

    class LogCapture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.messages = []

        def emit(self, record):
            self.messages.append(record.getMessage())

    capture = LogCapture()
    logger = logging.getLogger("pypdf")
    logger.addHandler(capture)
    logger.propagate = False

    def normalize(value):
        if isinstance(value, IndirectObject):
            return {"idnum": value.idnum, "generation": value.generation}
        if isinstance(value, BooleanObject):
            return value.value
        if isinstance(value, NullObject):
            return None
        if isinstance(value, dict):
            return {str(k): normalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        if isinstance(value, bytes):
            return {"hex": value.hex()}
        if isinstance(value, str):
            return str(value)
        if isinstance(value, float):
            return float(value)
        if isinstance(value, int):
            return int(value)
        raise VerificationError("Unrecognized result type: " + type(value).__name__)

    def observe(data):
        capture.messages.clear()
        stream = io.BytesIO(data)
        try:
            value = read_object(stream, reader)
            return {"type": type(value).__name__, "value": normalize(value),
                    "position": stream.tell(), "remaining_hex": stream.read().hex(),
                    "warnings": list(capture.messages)}
        except Exception as exc:
            if isinstance(exc, VerificationError):
                raise
            return {"error": type(exc).__name__, "message": str(exc),
                    "typed_limit_error": isinstance(exc, LimitReachedError),
                    "position": stream.tell(), "remaining_bytes": len(data) - stream.tell(),
                    "warnings": list(capture.messages)}

    boundary = []
    for newline_name, newline in NEWLINES.items():
        for count in COUNTS:
            prefix = (b"% comment" + newline + b" \t") * count
            data = prefix + b"42 tail"
            outcome = observe(data)
            boundary.append({"newline": newline_name, "comments": count,
                             "prefix_bytes": len(prefix), **outcome})
            if label != "parent" and count > 1000:
                require(outcome.get("error") == "LimitReachedError" and outcome["typed_limit_error"],
                        f"{label}: expected typed limit at {count} {newline_name}")
                require(outcome["position"] == 1000 * len(b"% comment" + newline + b" \t"),
                        "Limit must leave stream at the 1001st percent sign")
            elif label == "parent" and count >= 999 and "error" in outcome:
                require(outcome["error"] == "RecursionError", "Unexpected old-version failure")
            else:
                require(outcome.get("value") == 42 and outcome.get("remaining_hex") == b" tail".hex(),
                        f"{label}: wrong value/tail for {count} {newline_name}")

    guarded = []
    for newline_name, newline in NEWLINES.items():
        if label == "parent":
            guarded.append({"newline": newline_name, "status": "not_applicable",
                            "reason": "No bounded helper; old recursion behavior is observed in boundary cases without a fixed failure threshold."})
            continue
        prefix = (b"% comment" + newline + b" \t") * 1000
        stream = BodyGuard(prefix + b"%" + b"x" * 100_000, len(prefix) + 1)
        try:
            read_object(stream, reader)
        except Exception as exc:
            require(not isinstance(exc, VerificationError), str(exc))
            outcome = {"newline": newline_name, "error": type(exc).__name__,
                       "position": stream.tell(), "expected_percent_position": len(prefix),
                       "body_start": len(prefix) + 1, "body_bytes": 100_000,
                       "maximum_read_end": stream.maximum_read_end,
                       "body_read_attempts": stream.body_read_attempts}
            require(isinstance(exc, LimitReachedError) and stream.tell() == len(prefix),
                    "Guarded stream must fail at next percent sign")
            require(stream.maximum_read_end == len(prefix) + 1 and stream.body_read_attempts == 0,
                    "1001st comment body was scanned")
            guarded.append(outcome)
        else:
            raise VerificationError("Excess comments unexpectedly accepted")

    # Same byte input, ReaderDummy, profiler and direct ArrayObject entry as upstream.
    array_input = b"[" + b" ".join([b"123", b"4.5", b"12 0 R"] * 100) + b"]"
    stream = io.BytesIO(array_input)
    require(sys.getprofile() is None, "Run without an existing Python profiler")
    array, calls = namespace["count_function_calls"](ArrayObject.read_from_stream, stream, reader)
    require(sys.getprofile() is None, "Upstream helper did not restore profiler")
    require(len(array) == 300 and stream.read() == b"", "Array parse failed")
    for offset in range(0, 300, 3):
        require(normalize(array[offset]) == 123 and normalize(array[offset + 1]) == 4.5
                and normalize(array[offset + 2]) == {"idnum": 12, "generation": 0},
                "Array element changed")
    require(calls == (901 if label == "intermediate" else 601), "Unexpected Python call count")

    eof_inputs = {
        "empty": b"",
        "unterminated_comment": b"% no line ending",
        "terminated_comment_without_object": b"% c\n",
        "comment_then_only_whitespace": b"% c\n \t\r\n",
        "number_at_eof": b"42",
    }
    eof = [{"case": name, "input_hex": data.hex(), **observe(data)} for name, data in eof_inputs.items()]

    # Representative correctness only: no expanding timing or throughput benchmark.
    tokens = [
        ("integer", b"42", "NumberObject", 42),
        ("float", b"4.5", "FloatObject", 4.5),
        ("name", b"/Name", "NameObject", "/Name"),
        ("true", b"true", "BooleanObject", True),
        ("false", b"false", "BooleanObject", False),
        ("null", b"null", "NullObject", None),
        ("literal_string", b"(hello)", "TextStringObject", "hello"),
        ("hex_string", b"<6869>", "TextStringObject", "hi"),
        ("array", b"[1 2 3]", "ArrayObject", [1, 2, 3]),
        ("dictionary", b"<< /Answer 42 >>", "DictionaryObject", {"/Answer": 42}),
        ("indirect_reference", b"12 0 R", "IndirectObject", {"idnum": 12, "generation": 0}),
    ]
    correctness = []
    for name, token, expected_type, expected_value in tokens:
        for prefix_name, prefix in [("no_comments", b""), ("one_comment", b"% c\n \t"),
                                    ("mixed_line_endings", b"% a\r% b\r\n% c\n \t")]:
            result = observe(prefix + token + b" tail")
            require(result.get("type") == expected_type and result.get("value") == expected_value
                    and result.get("remaining_hex") == b" tail".hex(),
                    f"Correctness mismatch: {label}/{name}/{prefix_name}: {result}")
            correctness.append({"case": name, "prefix": prefix_name, **result})

    # The 1000-comment budget resets for the next read_object invocation.
    reset = None
    if label != "parent":
        block = b"% c\n" * 1000
        stream = io.BytesIO(block + b"42 " + block + b"43 tail")
        first = read_object(stream, reader)
        separator = stream.read(1)  # read_object expects the caller at the next token.
        second = read_object(stream, reader)
        tail = stream.read()
        require(int(first) == 42 and int(second) == 43 and separator == b" " and tail == b" tail",
                "Comment limit failed to reset for a separate object read")
        reset = {"comments_before_each_object": 1000, "values": [int(first), int(second)],
                 "remaining_hex": tail.hex()}

    return {"label": label, "commit": COMMITS[label], "environment": environment(),
            "socket_audit_self_test": socket_audit_self_test(),
            "snapshot": verified[0], "package_version_metadata": pypdf.__version__,
            "import_path": Path(pypdf.__file__).relative_to(ROOT).as_posix(),
            "boundary": boundary, "guarded_1001st_comment": guarded,
            "no_comment_call_budget": {"elements": len(array), "python_calls": calls,
                "budget_strictly_below": 900, "passes": calls < 900,
                "array_input_sha256": digest(array_input),
                "counter": "upstream count_function_calls, original AST source segment",
                "entry": "ArrayObject.read_from_stream"},
            "eof": eof, "representative_correctness": correctness,
            "separate_object_limit_reset": reset, "status": "PASS"}


def execute(args):
    manifest, verified = verify_sources()
    workers = []
    for label in COMMITS:
        proc = subprocess.run([sys.executable, "-I", "-B", "-S", "-X", "utf8", str(ROOT / "run.py"),
                               "--worker", label], capture_output=True, encoding="utf-8", timeout=120)
        require(proc.returncode == 0, f"Worker {label} failed ({proc.returncode}):\n{proc.stderr}\n{proc.stdout}")
        result = json.loads(proc.stdout)
        result["stderr"] = proc.stderr
        require(not proc.stderr, f"Unexpected worker stderr: {label}")
        workers.append(result)
    # EOF behavior is inherited, not a newly promised recovery policy.
    signatures = [[{k: v for k, v in item.items() if k != "message"} for item in row["eof"]] for row in workers]
    require(signatures[0] == signatures[1] == signatures[2], "EOF behavior changed between revisions")
    result = {
        "schema": 1, "status": "PASS", "environment": environment(),
        "test_requested": args.test, "socket_audit_self_test": socket_audit_self_test(),
        "integrity": {"provenance_sha256": PROVENANCE_SHA256, "snapshots": verified,
                      "individual_file_hashes": manifest},
        "demo_run_py_sha256": digest((ROOT / "run.py").read_bytes()),
        "workers": workers,
        "scope": "Object-token parsing with real pypdf packages; not complete PDFs, the full upstream test suite, a CVE assessment, or a wall-clock benchmark.",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = Path(args.output).resolve()
        # Output must not overwrite a source/provenance file or create files in vendor.
        require(not target.is_relative_to(ROOT / "vendor"), "Output cannot be written inside vendor")
        protected = [ROOT / p for p in ("run.py", "provenance.json", "LICENSE", "README.md", ".gitattributes")]
        require(target not in protected, "Output cannot overwrite demo sources")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    if args.json:
        print(text, end="")
    else:
        for row in workers:
            budget = row["no_comment_call_budget"]
            print(f"{row['label']:12} {row['commit'][:12]}  calls={budget['python_calls']}  "
                  f"calls<900={budget['passes']}  boundary={len(row['boundary'])}  "
                  f"correctness={len(row['representative_correctness'])}")
        print("PASS: 3 real snapshots; file hashes, boundaries, guarded reads, EOF and call budgets verified.")
        print("Old RecursionError positions are observations, not a fixed pypdf threshold.")
        if args.output:
            print("JSON:", args.output)


def main():
    require(sys.version_info >= (3, 11), "Python >= 3.11 is required for a standard-library-only run")
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        # -I also ignores PYTHONPATH/user packages. -S excludes site-packages entirely.
        proc = subprocess.run([sys.executable, "-I", "-B", "-S", "-X", "utf8",
                               str(ROOT / "run.py"), *sys.argv[1:]])
        raise SystemExit(proc.returncode)
    sys.addaudithook(deny_network)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="explicitly request all regression checks (also checked by default)")
    parser.add_argument("--json", action="store_true", help="emit only the full JSON report on stdout")
    parser.add_argument("--output", metavar="PATH", help="save the full JSON report to PATH")
    parser.add_argument("--worker", choices=list(COMMITS), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker), ensure_ascii=False))
    else:
        execute(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, VerificationError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
