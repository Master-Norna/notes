"""Offline reproduction for python-benedict #604: an empty query value (``a=``) was dropped.

Two unmodified benedict snapshots are vendored under vendor/before and
vendor/after; each case runs in an isolated interpreter with one snapshot
first on sys.path.

    python run.py --test
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMITS = {
    "before": "c36e48c6a6b6ef60c6dbf4e0572d23efcb545ab5",
    "after": "5cb4922f285baddf9c9ee1612a67a0ef1d370efb",
}

WORKER = r"""
import json
import sys

sys.path.insert(0, sys.argv[1])
from benedict import benedict

action = sys.argv[2]
payload = json.loads(sys.argv[3])
try:
    if action == "decode":
        value = benedict.from_query_string(payload["query"])
        out = {"ok": True, "dict": dict(value)}
    elif action == "roundtrip":
        value = benedict(payload["data"])
        encoded = value.to_query_string()
        decoded = benedict.from_query_string(encoded)
        out = {"ok": True, "encoded": encoded, "decoded": dict(decoded)}
    else:
        raise AssertionError(action)
except Exception as exc:  # noqa: BLE001 - the failure type is part of the observation
    lines = [line for line in str(exc).splitlines() if line.strip()]
    out = {"ok": False, "error": type(exc).__name__, "message": lines[-1] if lines else ""}
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
"""

CASES = [
    ("empty_and_value", "decode", {"query": "a=&b=2"}),
    ("single_empty", "decode", {"query": "a="}),
    ("trailing_empty", "decode", {"query": "a=1&b="}),
    ("roundtrip_empty", "roundtrip", {"data": {"a": ""}}),
    ("roundtrip_mixed", "roundtrip", {"data": {"a": "", "b": "2"}}),
    ("encoded_space", "decode", {"query": "a=%20&b=+"}),
    ("bracket_empty", "decode", {"query": "a[b]=&a[c]=2"}),
    ("missing_equals", "decode", {"query": "a&b=2"}),
]


def run_case(version: str, action: str, payload: dict) -> dict:
    cmd = [
        sys.executable, "-I", "-B", "-X", "utf8", "-c",
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        f"exec(compile({WORKER!r}, '<worker>', 'exec'))\n",
        str(HERE / "vendor" / version), action, json.dumps(payload),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"worker failed for {version}/{action}:\n{proc.stderr}")
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    results = {}
    for name, action, payload in CASES:
        results[name] = {v: run_case(v, action, payload) for v in ("before", "after")}

    for name, pair in results.items():
        print(f"== {name}")
        for version in ("before", "after"):
            print(f"  {version:6} {json.dumps(pair[version], ensure_ascii=False, sort_keys=True)}")
        print()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"commits": COMMITS, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.test:
        failures = []
        if results["empty_and_value"]["before"].get("dict") != {"b": "2"}:
            failures.append("before/empty_and_value should drop 'a'")
        if results["empty_and_value"]["after"].get("dict") != {"a": "", "b": "2"}:
            failures.append("after/empty_and_value did not keep 'a'")
        if results["single_empty"]["before"].get("dict") != {}:
            failures.append("before/single_empty should decode to an empty dict")
        if results["single_empty"]["after"].get("dict") != {"a": ""}:
            failures.append("after/single_empty did not keep 'a'")
        if results["trailing_empty"]["before"].get("dict") != {"a": "1"}:
            failures.append("before/trailing_empty should drop 'b'")
        if results["trailing_empty"]["after"].get("dict") != {"a": "1", "b": ""}:
            failures.append("after/trailing_empty did not keep 'b'")
        rt = results["roundtrip_empty"]
        if rt["before"].get("decoded") != {}:
            failures.append("before/roundtrip_empty should lose the key")
        if rt["after"].get("encoded") != "a=" or rt["after"].get("decoded") != {"a": ""}:
            failures.append("after/roundtrip_empty is not stable")
        if results["bracket_empty"]["after"].get("dict") != {"a": {"b": "", "c": "2"}}:
            failures.append("after/bracket_empty did not keep the nested empty value")
        if results["missing_equals"]["before"].get("ok") or results["missing_equals"]["after"].get("ok"):
            failures.append("missing_equals should stay invalid in both versions")
        if results["encoded_space"]["before"] != results["encoded_space"]["after"]:
            failures.append("encoded_space changed between versions")
        if failures:
            print("FAIL")
            for item in failures:
                print(" -", item)
            return 1
        print("PASS: 8 cases; only the empty-value cases differ between the two snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
