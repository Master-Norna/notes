"""Scan every case file with one vendored skylos version and print JSON.

Run by run.py in a separate process so that the three versions never share
an imported module tree.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

RULES = {"SKY-D340", "SKY-D327"}


def main() -> int:
    vendor = Path(sys.argv[1]).resolve()
    cases = Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(vendor))
    import skylos

    roots = {Path(p).resolve() for p in getattr(skylos, "__path__", [])}
    if vendor / "skylos" not in roots:
        raise SystemExit(f"skylos resolved outside the vendored tree: {roots}")
    from skylos.rules.config.cicd.github_actions import scan_github_actions

    out: dict[str, list[list[object]]] = {}
    for case in sorted(cases.glob("*.yml")):
        root = Path(tempfile.mkdtemp(prefix="skylos-case-"))
        try:
            workflow = root / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            shutil.copyfile(case, workflow)
            findings = scan_github_actions(root)
            out[case.stem] = [
                [f.get("rule_id"), f.get("line")]
                for f in findings
                if f.get("rule_id") in RULES
            ]
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
