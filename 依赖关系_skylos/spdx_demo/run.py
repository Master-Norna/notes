"""Compare skylos' SPDX relationships before and after merge bf6215f.

The two vendor trees are the upstream ``skylos`` package at the merge's parent
(4481fea7) and at the merge (bf6215f0). Only the modules the SPDX export
imports are kept; everything else is unchanged upstream source.

Cases come from one Yarn Berry workspace, ``app -> parent -> child``:

* ``transitive_child``  child is only reachable through parent
* ``also_direct``       app also declares child in its own dependencies
* ``incomplete_graph``  same as the first, with the recorded graph marked
                        incomplete, so package-to-package edges are dropped

    python run.py            # table
    python run.py --json     # machine-readable results
    python run.py --test     # assertions, exit 1 on failure
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = {"before": "4481fea7", "after": "bf6215f0"}
CASES = (
    ("transitive_child", False, True),
    ("also_direct", True, True),
    ("incomplete_graph", False, False),
)

WORKER = """
import json, sys
from pathlib import Path

vendor, root = Path(sys.argv[1]), Path(sys.argv[2])
child_is_direct, complete = sys.argv[3] == "1", sys.argv[4] == "1"
sys.path.insert(0, str(vendor))

from skylos.reporting.spdx import spdx_document
from skylos.rules.sca.licenses import LicenseInventory
from skylos.rules.sca.yarn_lockfile import parse_yarn_lock


class Inventory:
    def __init__(self, dependencies):
        self.dependencies = dependencies
        self.receipt = {"complete": complete}
        self.manifest_gaps = []
        self.lockfile_projects = set()

    def __iter__(self):
        return iter(self.dependencies)


lock = parse_yarn_lock(root / "yarn.lock")
kind = {dep["name"]: dep["dependency_kind"] for dep in lock.dependencies}
roots = {dep["name"]: dep["dependency_roots"] for dep in lock.dependencies}
document = spdx_document(Inventory(lock.dependencies), root, LicenseInventory())

names = {"SPDXRef-DOCUMENT": "document"}
for package in document["packages"]:
    names[package["SPDXID"]] = (
        "root" if package["SPDXID"] == "SPDXRef-RootPackage" else package["name"]
    )
edges, other = [], []
for item in document["relationships"]:
    pair = [names[item["spdxElementId"]], names[item["relatedSpdxElement"]]]
    if item["relationshipType"] == "DEPENDS_ON":
        edges.append(pair)
    elif item["relationshipType"] == "OTHER":
        other.append(pair)
print(json.dumps(
    {"kind": kind, "roots": roots, "edges": sorted(edges), "other": sorted(other)},
    sort_keys=True,
))
"""

BERRY = {
    "__metadata": {"version": 8},
    "app@workspace:.": {
        "version": "0.0.0-use.local",
        "resolution": "app@workspace:.",
        "linkType": "soft",
        "dependencies": {"parent": "npm:^1"},
    },
    "parent@npm:^1": {
        "version": "1.0.0",
        "resolution": "parent@npm:1.0.0",
        "linkType": "hard",
        "dependencies": {"child": "npm:^2"},
        "dependenciesMeta": {"child": {"optional": True}},
    },
    "child@npm:^2": {
        "version": "2.0.0",
        "resolution": "child@npm:2.0.0",
        "linkType": "hard",
        "conditions": "os=linux & cpu=x64",
    },
}


def fixture(child_is_direct: bool) -> str:
    """Yarn Berry workspace: app -> parent -> child, optionally app -> child."""
    data = json.loads(json.dumps(BERRY))
    if child_is_direct:
        data["app@workspace:."]["dependencies"]["child"] = "npm:^2"
    return json.dumps(data, indent=2)


def run_case(version: str, child_is_direct: bool, complete: bool) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "app"
        root.mkdir()
        (root / "yarn.lock").write_text(fixture(child_is_direct), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                "-c",
                WORKER,
                str(HERE / "vendor" / version),
                str(root),
                "1" if child_is_direct else "0",
                "1" if complete else "0",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1])
    return json.loads(proc.stdout)


def describe(data: dict) -> str:
    parts = []
    for source, target in data["edges"]:
        parts.append(f"{source} -> {target}")
    for source, target in data["other"]:
        parts.append(f"{source} .. {target} (OTHER)")
    return ", ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    results = {}
    for name, child_is_direct, complete in CASES:
        results[name] = {
            version: run_case(version, child_is_direct, complete) for version in VERSIONS
        }

    for name, _, _ in CASES:
        print(f"== {name}")
        for version in VERSIONS:
            print(f"  {version:6} {describe(results[name][version])}")
        print()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"commits": VERSIONS, "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    if args.test:
        failures = []
        reachable = results["transitive_child"]
        for version in VERSIONS:
            if reachable[version]["kind"]["child"] != "transitive":
                failures.append(f"{version}/transitive_child child is not recorded transitive")
            if reachable[version]["roots"]["child"] != [""]:
                failures.append(f"{version}/transitive_child child has no recorded root")
            if ["parent", "child"] not in reachable[version]["edges"]:
                failures.append(f"{version}/transitive_child lost the parent -> child edge")
        if ["root", "child"] not in reachable["before"]["edges"]:
            failures.append("before/transitive_child should add root -> child")
        if ["root", "child"] in reachable["after"]["edges"]:
            failures.append("after/transitive_child still adds root -> child")
        if ["root", "parent"] not in reachable["after"]["edges"]:
            failures.append("after/transitive_child lost the direct parent edge")

        both = results["also_direct"]
        for version in VERSIONS:
            if ["root", "child"] not in both[version]["edges"]:
                failures.append(f"{version}/also_direct lost the declared root -> child edge")
        if both["before"]["edges"] != both["after"]["edges"]:
            failures.append("also_direct should be identical in both versions")

        partial = results["incomplete_graph"]
        if ["root", "child"] not in partial["before"]["edges"]:
            failures.append("before/incomplete_graph should add root -> child")
        if ["root", "child"] in partial["after"]["edges"]:
            failures.append("after/incomplete_graph still adds root -> child")
        if ["root", "child"] not in partial["after"]["other"]:
            failures.append("after/incomplete_graph should record the package as OTHER")

        if failures:
            print("FAIL")
            for item in failures:
                print(" -", item)
            return 1
        print("PASS: 3 cases; the reachable-only child loses its invented root edge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
