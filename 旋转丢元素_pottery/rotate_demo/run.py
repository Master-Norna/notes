#!/usr/bin/env python3
"""Pottery #857: RedisDeque.rotate() loses elements when abs(n) > len(d).

Two complete, fixed pottery snapshots are loaded from vendor/ and driven
against an in-process fakeredis emulator.  The emulator is not a Redis server;
it is used only to observe the commands the unmodified rotate() sends and to
read the resulting list back.

Run from the repository root:

    python -B -S 旋转丢元素_pottery/rotate_demo/run.py --test
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
        "sha": "f6e59b0127f3375278fd473450fff1152548f7c7",
        "role": "first parent of the #857 merge (pre-fix)",
    },
    "merge": {
        "sha": "4e98b44cb888f08660c5f6f943fac4f62c95b3e5",
        "role": "#857 merge",
    },
}
CASES = (4, -4, 6, -6, 7, -7)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CHILD = r"""
import collections, importlib, json, sys, types, warnings

def deny_socket(event, args):
    if event.startswith("socket."):
        raise RuntimeError("offline demo: socket event blocked: " + event)

sys.addaudithook(deny_socket)
site, vendor = sys.argv[1], sys.argv[2]
sys.path.insert(0, site)

# Import only the original pottery.deque module.  pottery/__init__.py also
# imports BloomFilter/HyperLogLog, which need the optional mmh3 extension;
# those classes are unrelated to RedisDeque and are not used here.
package = types.ModuleType("pottery")
package.__path__ = [vendor]
sys.modules["pottery"] = package
from pottery.deque import RedisDeque

import fakeredis
import redis
import importlib.metadata as metadata
import warnings
warnings.simplefilter("ignore")

def trace_client(client):
    calls = []
    original = client.pipeline
    def traced_pipeline(*args, **kwargs):
        pipeline = original(*args, **kwargs)
        execute = pipeline.execute_command
        def traced(*command_args, **command_kwargs):
            calls.append(list(command_args))
            return execute(*command_args, **command_kwargs)
        pipeline.execute_command = traced
        return pipeline
    client.pipeline = traced_pipeline
    return calls

def mutations(calls):
    return [
        [str(part) for part in command]
        for command in calls
        if str(command[0]).upper() in ("LPUSH", "RPUSH", "LTRIM")
    ]

rows = []
for length in range(9):
    for n in range(-20, 21):
        client = fakeredis.FakeRedis()
        queue = RedisDeque(range(1, length + 1), redis=client, key="case")
        calls = trace_client(client)
        queue.rotate(n)
        expected = collections.deque(range(1, length + 1))
        expected.rotate(n)
        actual = [json.loads(value) for value in client.lrange(queue.key, 0, -1)]
        rows.append({
            "length": length,
            "n": n,
            "expected": list(expected),
            "actual": actual,
            "match": actual == list(expected),
            "mutations": mutations(calls),
        })
        client.delete(queue.key)

selected = [row for row in rows if row["length"] == 3 and row["n"] in (4, -4, 6, -6, 7, -7)]

# The 10-element rotate(-2) case from the PR body: bare modulo would turn it
# into +8 and push eight values; the merged normalization keeps it at -2.
client = fakeredis.FakeRedis()
queue = RedisDeque(range(10), redis=client, key="cost")
calls = trace_client(client)
queue.rotate(-2)
cost = {
    "length": 10,
    "n": -2,
    "bare_modulo": -2 % 10,
    "actual": [json.loads(value) for value in client.lrange(queue.key, 0, -1)],
    "mutations": mutations(calls),
}
client.delete(queue.key)

# Empty deque: both versions should be a no-op with no push/trim.
client = fakeredis.FakeRedis()
empty = RedisDeque([], redis=client, key="empty")
calls = trace_client(client)
empty.rotate(4)
empty_case = {"actual": [], "mutations": mutations(calls)}
client.delete(empty.key)

invalid = []
for bad in (None, "a", 0.5):
    client = fakeredis.FakeRedis()
    queue = RedisDeque([1, 2, 3], redis=client, key="invalid")
    try:
        queue.rotate(bad)
    except TypeError:
        invalid.append({"value": repr(bad), "type": "TypeError"})
    else:
        invalid.append({"value": repr(bad), "type": "accepted"})
    client.delete(queue.key)

print(json.dumps({
    "fakeredis": metadata.version("fakeredis"),
    "redis": redis.__version__,
    "total": len(rows),
    "mismatches": sum(not row["match"] for row in rows),
    "rows": rows,
    "selected": selected,
    "cost": cost,
    "empty": empty_case,
    "invalid": invalid,
}))
"""


def run_child(label: str) -> dict:
    vendor = ROOT / "vendor" / label / "pottery"
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            "-c",
            CHILD,
            str(ROOT / "vendor" / "site"),
            str(vendor),
        ],
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


def mutation_text(rows):
    return "; ".join(" ".join(str(part) for part in row) for row in rows) or "(none)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="run all assertions")
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--output", type=Path, help="also write the JSON report here")
    parser.add_argument(
        "--matrix",
        type=Path,
        help="write one match/mismatch cell per (len, n) for the figures",
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

    results = {}
    for label in ("parent", "merge"):
        results[label] = run_child(label)
        results[label]["source_sha"] = VERSIONS[label]["sha"]
        results[label]["source_role"] = VERSIONS[label]["role"]
        results[label]["source_sha256"] = {
            str(path.relative_to(ROOT)): sha256(path)
            for path in sorted((ROOT / "vendor" / label).rglob("*"))
            if path.is_file()
        }

    parent = results["parent"]
    merge = results["merge"]
    failures = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(parent["total"] == 369 and merge["total"] == 369, "expected 369 cases per version")
    check(parent["mismatches"] == 204, f"parent: expected 204 mismatches, got {parent['mismatches']}")
    check(merge["mismatches"] == 0, f"merge: expected 0 mismatches, got {merge['mismatches']}")

    expected_parent = {
        4: ([1, 2, 3], [["LPUSH", "case", "3", "2", "1"], ["LTRIM", "case", "0", "2"]]),
        -4: ([2, 3], [["RPUSH", "case", "1", "2", "3"], ["LTRIM", "case", "4", "6"]]),
        6: ([1, 2, 3], [["LPUSH", "case", "3", "2", "1"], ["LTRIM", "case", "0", "2"]]),
        -6: ([], [["RPUSH", "case", "1", "2", "3"], ["LTRIM", "case", "6", "8"]]),
        7: ([1, 2, 3], [["LPUSH", "case", "3", "2", "1"], ["LTRIM", "case", "0", "2"]]),
        -7: ([], [["RPUSH", "case", "1", "2", "3"], ["LTRIM", "case", "7", "9"]]),
    }
    expected_merge = {
        4: ([3, 1, 2], [["LPUSH", "case", "3"], ["LTRIM", "case", "0", "2"]]),
        -4: ([2, 3, 1], [["RPUSH", "case", "1"], ["LTRIM", "case", "1", "3"]]),
        6: ([1, 2, 3], []),
        -6: ([1, 2, 3], []),
        7: ([3, 1, 2], [["LPUSH", "case", "3"], ["LTRIM", "case", "0", "2"]]),
        -7: ([2, 3, 1], [["RPUSH", "case", "1"], ["LTRIM", "case", "1", "3"]]),
    }
    for row in parent["selected"]:
        expected, commands = expected_parent[row["n"]]
        check(row["actual"] == expected, f"parent n={row['n']}: actual {row['actual']}")
        check(row["mutations"] == commands, f"parent n={row['n']}: commands {row['mutations']}")
    for row in merge["selected"]:
        expected, commands = expected_merge[row["n"]]
        check(row["actual"] == expected, f"merge n={row['n']}: actual {row['actual']}")
        check(row["mutations"] == commands, f"merge n={row['n']}: commands {row['mutations']}")

    for label, data in results.items():
        check(
            data["cost"]["actual"] == [2, 3, 4, 5, 6, 7, 8, 9, 0, 1],
            f"{label}: cost case actual {data['cost']['actual']}",
        )
        check(
            data["cost"]["mutations"]
            == [["RPUSH", "cost", "0", "1"], ["LTRIM", "cost", "2", "11"]],
            f"{label}: cost case commands {data['cost']['mutations']}",
        )
        check(data["empty"]["mutations"] == [], f"{label}: empty rotate should not mutate")
        check(
            all(item["type"] == "TypeError" for item in data["invalid"]),
            f"{label}: invalid inputs {data['invalid']}",
        )

    report = {
        "demo": "pottery-rotate-overflow",
        "backend": "fakeredis (in-process emulator), NOT a Redis server",
        "python": sys.version.split()[0],
        "versions": {
            label: {
                "pottery_sha": data["source_sha"],
                "role": data["source_role"],
                "fakeredis": data["fakeredis"],
                "redis": data["redis"],
            }
            for label, data in results.items()
        },
        "cases": {
            label: {
                "total": data["total"],
                "mismatches": data["mismatches"],
                "selected": data["selected"],
                "cost": data["cost"],
                "empty": data["empty"],
                "invalid": data["invalid"],
            }
            for label, data in results.items()
        },
        "assertions": {"passed": not failures, "failures": failures},
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.matrix:
        args.matrix.parent.mkdir(parents=True, exist_ok=True)
        args.matrix.write_text(
            json.dumps(
                {
                    label: [
                        {"length": row["length"], "n": row["n"], "match": row["match"]}
                        for row in results[label]["rows"]
                    ]
                    for label in ("parent", "merge")
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Python {report['python']}  backend: {report['backend']}")
        print(f"parent {parent['source_sha'][:12]}: {parent['total']} cases, {parent['mismatches']} mismatches")
        print(f"merge  {merge['source_sha'][:12]}: {merge['total']} cases, {merge['mismatches']} mismatches")
        print()
        print("length=3  n   stdlib/merge        parent              parent commands")
        print("-" * 94)
        by_n = {row["n"]: row for row in merge["selected"]}
        by_parent = {row["n"]: row for row in parent["selected"]}
        for n in CASES:
            print(
                f"{n:>9}  {str(by_n[n]['actual']):20} {str(by_parent[n]['actual']):20} "
                f"{mutation_text(by_parent[n]['mutations'])}"
            )
        print()
        print(f"10-element rotate(-2): actual {merge['cost']['actual']}")
        print(f"  commands: {mutation_text(merge['cost']['mutations'])}")
        print(f"  bare modulo would be {merge['cost']['bare_modulo']}, pushing 8 values")
        if failures:
            print("\nFAIL")
            for failure in failures:
                print(" -", failure)
        else:
            print("\nPASS: all 369 cases match collections.deque after the fix; the pre-fix version loses elements at the boundary.")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
