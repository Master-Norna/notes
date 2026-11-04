#!/usr/bin/env python3
"""tomlkit #613: a tz-aware time is rendered as a local time without offset.

Two complete, fixed tomlkit snapshots are imported from vendor/.  No tomlkit
installation is needed.  Run from the repository root:

    python -B -S 本地时间_tomlkit/local_time_demo/run.py --test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSIONS = {
    "parent": {
        "sha": "763bd661bfed068209c03510ae94493eb2db12b5",
        "role": "first parent of the #613 merge (pre-fix)",
    },
    "merge": {
        "sha": "ce8f8ee982411c4afef5cfb90df7313cc5f7d779",
        "role": "#613 merge",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CHILD = r"""
import json, sys
from datetime import datetime, time, timedelta, timezone

def deny_socket(event, args):
    if event.startswith("socket."):
        raise RuntimeError("offline demo: socket event blocked: " + event)

sys.addaudithook(deny_socket)
sys.path.insert(0, sys.argv[1])
import tomlkit
from tomlkit import dumps, item, parse

TZ = timezone(timedelta(hours=2))
aware = time(7, 32, tzinfo=TZ)
naive = time(7, 32)
micro = time(7, 32, 0, 123450, tzinfo=TZ)

def render(value):
    rendered = item(value)
    return {"as_string": rendered.as_string()}

def round_trip(value):
    document = dumps({"t": item(value)})
    try:
        parsed = parse(document)
        return {
            "document": document,
            "ok": True,
            "parsed": parsed["t"].as_string(),
            "parsed_type": type(parsed["t"]).__name__,
        }
    except Exception as exc:
        return {
            "document": document,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

result = {
    "version": tomlkit.__version__,
    "aware": render(aware),
    "naive": render(naive),
    "micro": render(micro),
    "aware_replace": item(aware).replace(hour=13).as_string(),
    "aware_round_trip": round_trip(aware),
    "naive_round_trip": round_trip(naive),
    "literal_offset": None,
}
try:
    parse("t = 07:32:00+02:00")
    result["literal_offset"] = {"ok": True}
except Exception as exc:
    result["literal_offset"] = {
        "ok": False,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
result["boundary"] = {
    "time_utc": render(time(7, 32, tzinfo=timezone.utc))["as_string"],
    "micro_100000": render(time(7, 32, 0, 100000, tzinfo=TZ))["as_string"],
    "micro_one": render(time(7, 32, 0, 1, tzinfo=TZ))["as_string"],
    "micro_naive": render(time(7, 32, 0, 123450))["as_string"],
    "fold_one": render(time(7, 32, fold=1))["as_string"],
    "datetime_aware": item(datetime(2026, 11, 4, 7, 32, tzinfo=TZ)).as_string(),
    "datetime_utc": item(datetime(2026, 11, 4, 7, 32, tzinfo=timezone.utc)).as_string(),
    "datetime_replace": item(
        datetime(2026, 11, 4, 7, 32, tzinfo=timezone.utc)
    ).replace(hour=13).as_string(),
    "array": dumps({"a": [item(aware)]}).strip(),
    "parsed_text": dumps(parse("t = 07:32:00.123450")).strip(),
    "parsed_replace": dumps(
        {"t": parse("t = 07:32:00.123450")["t"].replace(minute=33)}
    ).strip(),
}
print(json.dumps(result, ensure_ascii=False))
"""


EMIT = r"""
import sys
from datetime import datetime, time, timedelta, timezone
sys.path.insert(0, sys.argv[1])
from tomlkit import dumps, item

folder, label = sys.argv[2], sys.argv[3]
zone = timezone(timedelta(hours=2))
with open(f"{folder}/{label}.toml", "w", encoding="utf-8", newline="\n") as handle:
    handle.write(dumps({"schedule": {"start": item(time(7, 32, tzinfo=zone))}}))

if label == "merge":
    legal = dumps(
        {
            "note": item("07:32:00+02:00"),
            "stamp": item(datetime(1979, 5, 27, 7, 32, tzinfo=zone)),
        }
    )
    with open(f"{folder}/legal.toml", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(legal)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="run all assertions")
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--output", type=Path, help="also write the JSON report here")
    parser.add_argument(
        "--emit",
        type=Path,
        metavar="DIR",
        help="write DIR/parent.toml and DIR/merge.toml as each snapshot dumps them",
    )
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

    if args.emit:
        args.emit.mkdir(parents=True, exist_ok=True)
        for label in ("parent", "merge"):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-S",
                    "-c",
                    EMIT,
                    str(ROOT / "vendor" / label),
                    str(args.emit),
                    label,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONPATH": ""},
            )
            if proc.returncode != 0:
                raise SystemExit(f"emit {label} failed: {proc.stderr}")
            print(f"wrote {args.emit / (label + '.toml')}")

    results = {}
    for label in ("parent", "merge"):
        results[label] = run_child(label)
        results[label]["source_sha"] = VERSIONS[label]["sha"]
        results[label]["source_role"] = VERSIONS[label]["role"]
        results[label]["source_sha256"] = {
            str(path.relative_to(ROOT)): sha256(path)
            for path in sorted((ROOT / "vendor" / label / "tomlkit").rglob("*"))
            if path.is_file()
        }

    parent = results["parent"]
    merge = results["merge"]
    failures = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    for label, data in results.items():
        check(data["version"] == "0.15.1", f"{label}: expected 0.15.1, got {data['version']}")
        check(data["naive"]["as_string"] == "07:32:00", f"{label}: naive time")
        check(data["naive_round_trip"]["ok"], f"{label}: naive round trip")
        check(data["literal_offset"]["ok"] is False, f"{label}: parser should reject offset")
        check(
            data["literal_offset"]["error_type"] == "InvalidTimeError",
            f"{label}: literal offset error type {data['literal_offset']}",
        )

    check(
        parent["aware"]["as_string"] == "07:32:00+02:00",
        f"parent: aware as_string {parent['aware']['as_string']}",
    )
    check(
        parent["micro"]["as_string"] == "07:32:00.123450+02:00",
        f"parent: micro as_string {parent['micro']['as_string']}",
    )
    check(
        parent["aware_replace"] == "13:32:00+02:00",
        f"parent: replace {parent['aware_replace']}",
    )
    check(
        parent["aware_round_trip"]["ok"] is False
        and parent["aware_round_trip"]["error_type"] == "InvalidTimeError",
        f"parent: round trip should fail, got {parent['aware_round_trip']}",
    )
    check(
        parent["aware_round_trip"]["document"] == "t = 07:32:00+02:00\n",
        f"parent: document {parent['aware_round_trip']['document']!r}",
    )

    check(
        merge["aware"]["as_string"] == "07:32:00",
        f"merge: aware as_string {merge['aware']['as_string']}",
    )
    check(
        merge["micro"]["as_string"] == "07:32:00.12345",
        f"merge: micro as_string {merge['micro']['as_string']}",
    )
    check(merge["aware_replace"] == "13:32:00", f"merge: replace {merge['aware_replace']}")
    check(merge["aware_round_trip"]["ok"], f"merge: round trip {merge['aware_round_trip']}")
    check(
        merge["aware_round_trip"]["document"] == "t = 07:32:00\n",
        f"merge: document {merge['aware_round_trip']['document']!r}",
    )
    check(
        merge["aware_round_trip"]["parsed"] == "07:32:00",
        f"merge: parsed {merge['aware_round_trip']['parsed']}",
    )
    check(
        merge["naive"] == parent["naive"],
        "merge: naive output must be byte-for-byte unchanged",
    )

    # Boundary cases: what the #613 rendering does and does not touch.
    boundary = {label: data["boundary"] for label, data in results.items()}
    for label, data in boundary.items():
        check(
            data["datetime_aware"] == "2026-11-04T07:32:00+02:00",
            f"{label}: aware datetime {data['datetime_aware']}",
        )
        check(
            data["datetime_utc"] == "2026-11-04T07:32:00Z",
            f"{label}: utc datetime {data['datetime_utc']}",
        )
        check(
            data["datetime_replace"] == "2026-11-04T13:32:00+00:00",
            f"{label}: datetime replace {data['datetime_replace']}",
        )
        check(
            data["parsed_text"] == "t = 07:32:00.123450",
            f"{label}: parsed text must survive a round trip: {data['parsed_text']}",
        )
        check(data["fold_one"] == "07:32:00", f"{label}: fold {data['fold_one']}")

    check(boundary["parent"]["time_utc"] == "07:32:00+00:00", "parent: utc offset")
    check(
        boundary["parent"]["micro_100000"] == "07:32:00.100000+02:00",
        "parent: micro 100000",
    )
    check(
        boundary["parent"]["micro_naive"] == "07:32:00.123450",
        "parent: naive microseconds keep their trailing zero",
    )
    check(
        boundary["parent"]["parsed_replace"] == "t = 07:33:00.123450",
        "parent: replace on a parsed value",
    )
    check(boundary["parent"]["array"] == "a = [07:32:00+02:00]", "parent: array element")

    check(boundary["merge"]["time_utc"] == "07:32:00", "merge: utc offset dropped")
    check(boundary["merge"]["micro_100000"] == "07:32:00.1", "merge: micro 100000")
    check(boundary["merge"]["micro_one"] == "07:32:00.000001", "merge: micro 1")
    check(
        boundary["merge"]["micro_naive"] == "07:32:00.12345",
        "merge: naive microseconds also lose the trailing zero",
    )
    check(
        boundary["merge"]["parsed_replace"] == "t = 07:33:00.12345",
        "merge: replace on a parsed value",
    )
    check(boundary["merge"]["array"] == "a = [07:32:00]", "merge: array element")

    report = {
        "demo": "tomlkit-local-time",
        "python": sys.version.split()[0],
        "versions": {
            label: {
                "tomlkit": data["version"],
                "sha": data["source_sha"],
                "role": data["source_role"],
            }
            for label, data in results.items()
        },
        "cases": {
            label: {
                key: data[key]
                for key in (
                    "aware",
                    "naive",
                    "micro",
                    "aware_replace",
                    "aware_round_trip",
                    "naive_round_trip",
                    "literal_offset",
                )
            }
            for label, data in results.items()
        },
        "boundary": boundary,
        "assertions": {"passed": not failures, "failures": failures},
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Python {report['python']}  (two complete tomlkit snapshots, no install)")
        print(f"{'case':28} {'parent 763bd66':32} {'merge ce8f8ee':32}")
        print("-" * 94)
        rows = [
            ("aware.as_string()", parent["aware"]["as_string"], merge["aware"]["as_string"]),
            ("micro.as_string()", parent["micro"]["as_string"], merge["micro"]["as_string"]),
            ("aware.replace(hour=13)", parent["aware_replace"], merge["aware_replace"]),
            (
                "dumps()",
                parent["aware_round_trip"]["document"].strip(),
                merge["aware_round_trip"]["document"].strip(),
            ),
            (
                "parse(dumps())",
                "InvalidTimeError" if not parent["aware_round_trip"]["ok"] else "ok",
                "ok" if merge["aware_round_trip"]["ok"] else "error",
            ),
            (
                "naive.as_string()",
                parent["naive"]["as_string"],
                merge["naive"]["as_string"],
            ),
        ]
        for name, before, after in rows:
            print(f"{name:28} {before:32} {after:32}")

        print()
        print("boundary cases")
        print(f"{'case':28} {'parent 763bd66':32} {'merge ce8f8ee':32}")
        print("-" * 94)
        boundary_rows = [
            ("time(tzinfo=utc)", "time_utc"),
            ("micro 100000 (aware)", "micro_100000"),
            ("micro 1 (aware)", "micro_one"),
            ("micro 123450 (naive)", "micro_naive"),
            ("fold=1 (naive)", "fold_one"),
            ("datetime (aware)", "datetime_aware"),
            ("datetime (utc)", "datetime_utc"),
            ("datetime.replace(hour=13)", "datetime_replace"),
            ("dumps(array)", "array"),
            ("parse().dumps()", "parsed_text"),
            ("parse().replace(minute=33)", "parsed_replace"),
        ]
        for name, key in boundary_rows:
            print(f"{name:28} {boundary['parent'][key]:32} {boundary['merge'][key]:32}")

        if failures:
            print("\nFAIL")
            for failure in failures:
                print(" -", failure)
        else:
            print(
                "\nPASS: parent writes 07:32:00+02:00 and cannot parse its own output; "
                "merge writes 07:32:00, parses it back, leaves whole-second naive times "
                "unchanged, and touches neither datetime nor parsed text."
            )

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
