"""skylos #1228: the text prefilter that decides whether the Python security
scan runs at all, and the Cypher rule it is supposed to gate.

Every case is a whole source file.  `vendor/parent` and `vendor/merged` hold
`skylos/rules/danger/python_security_gaps.py` and the two modules it imports,
copied from the two commits.  The two prefilter functions are copied verbatim
from `danger.py` at those commits; only the Cypher literals changed there.

    python -B run.py --test                 assertions + tables
    python -B run.py --measure <directory>  file counts on a Python source tree
"""

from __future__ import annotations

import argparse
import ast
import importlib
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"

PARENT = "311cfdf30ce4f92983a8a880fdc5fea88e056047"
MERGED = "017365e64b19109199fc9d037c80b7f795e2087b"


def _load(tag: str):
    """Import the vendored `python_security_gaps` module for one commit."""
    for name in [n for n in sys.modules if n == "skylos" or n.startswith("skylos.")]:
        del sys.modules[name]
    root = str(VENDOR / tag)
    sys.path.insert(0, root)
    try:
        return importlib.import_module("skylos.rules.danger.python_security_gaps")
    finally:
        sys.path.remove(root)


# --- danger.py:625-626 and :658-681 at PARENT, verbatim ---------------------
def _has_any(source: str, tokens: tuple[str, ...]) -> bool:
    return any(token in source for token in tokens)


def parent_prefilter(source: str | None) -> bool:
    if source is None or _has_any(
        source.lower(),
        (
            "jinja",
            "requests",
            "httpx",
            "urllib",
            "importlib",
            "__import__",
            "gradio",
            "/tmp/",
            "makedirs",
            "mkdir",
            "url_for",
            "subprocess",
            "shlex",
            "match (",
            "merge (",
            "create (",
        ),
    ):
        return True
    return False


# --- danger.py:658-681 at MERGED, verbatim ---------------------------------
def merged_prefilter(source: str | None, mentions_graph_query) -> bool:
    if (
        source is None
        or _has_any(
            source.lower(),
            (
                "jinja",
                "requests",
                "httpx",
                "urllib",
                "importlib",
                "__import__",
                "gradio",
                "/tmp/",
                "makedirs",
                "mkdir",
                "url_for",
                "subprocess",
                "shlex",
            ),
        )
        or mentions_graph_query(source)
    ):
        return True
    return False


CASES: dict[str, str] = {
    "standard": r"""
def find(graph, name):
    return graph.query(f"MATCH (p:Person {{name: '{name}'}}) RETURN p")
""",
    "no-space": r"""
def find(graph, name):
    return graph.query(f"MATCH(p:Person {{name: '{name}'}}) RETURN p")
""",
    "two-spaces": r"""
def find(graph, name):
    return graph.query(f"MATCH  (p:Person {{name: '{name}'}}) RETURN p")
""",
    "line-break": r'''
def find(graph, name):
    return graph.query(f"""MATCH
(p:Person {{name: '{name}'}}) RETURN p""")
''',
    "optional-match": r"""
def find(graph, name):
    return graph.query(f"OPTIONAL MATCH(p:Person {{name: '{name}'}}) RETURN p")
""",
    "merge": r"""
def add(graph, node):
    graph.query(f"MERGE(n:Entity {{id: '{node}'}}) RETURN n")
""",
    "create": r"""
def add(graph, node):
    graph.query(f"CREATE(n:Entity {{id: '{node}'}}) RETURN n")
""",
    "triple-quoted": r'''
def find(graph, name):
    return graph.query(f"""MATCH(n {{id: '{name}'}}) RETURN n""")
''',
    "quote-next-line": r'''
def find(graph, name):
    return graph.query(f"""
MATCH(n:Person)
WHERE n.name = '{name}'
RETURN n
""")
''',
    "leading-clause": r'''
def find(graph, name):
    return graph.query(f"""
WITH 1 AS one
MATCH(n:Person)
WHERE n.name = '{name}'
RETURN n
""")
''',
    "escaped-newline": r"""
def find(graph, name):
    return graph.query(f"WITH 1 AS one\nMATCH(n {{id: '{name}'}}) RETURN n")
""",
}

LOOKALIKES: dict[str, str] = {
    "re.match (name, pattern)": "re.match (name, pattern)",
    "re.match(name, pattern)": "re.match(name, pattern)",
    "db.create(obj)": "db.create(obj)",
    "def create (name):": "def create (name):\n    return name",
    "def create(name):": "def create(name):\n    return name",
}


def d211_lines(module, source: str) -> list[int]:
    findings: list[dict] = []
    module.scan(ast.parse(source), "case.py", findings)
    return [f["line"] for f in findings if f["rule_id"] == "SKY-D211"]


def _best_ms(fn, source: str, repeat: int = 3) -> float:
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        fn(source)
        best = min(best, (time.perf_counter() - started) * 1000)
    return best


def backtracking() -> list[tuple[int, float, float]]:
    """`label = '<N spaces>'`: the first hint shape vs the merged one."""
    merged = _load("merged")
    keywords = merged._CYPHER_KEYWORDS
    early = re.compile(
        rf"""["']{{1,3}}\s*[^"'\n]*\b(?:{keywords})\s*\(""", re.IGNORECASE
    )
    rows = []
    for n in (500, 1000, 2000, 4000, 8000):
        source = "label = '" + " " * n + "'"
        rows.append(
            (
                n,
                _best_ms(early.search, source),
                _best_ms(merged.mentions_graph_query, source),
            )
        )
    return rows


def measure(directory: Path) -> None:
    merged = _load("merged")
    keywords = merged._CYPHER_KEYWORDS
    wide = re.compile(rf"\b(?:{keywords})\s*\(", re.IGNORECASE)
    literal = re.compile(r"(?:match|merge|create) \(")
    files = sorted(p for p in directory.rglob("*.py") if p.is_file())
    counts = {"files": len(files), "merged hint": 0, "wide \\b hint": 0, "parent literals": 0}
    extra = []
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hint = merged.mentions_graph_query(source)
        counts["merged hint"] += hint
        if wide.search(source):
            counts["wide \\b hint"] += 1
            if not hint:
                extra.append(path)
        counts["parent literals"] += bool(literal.search(source))
    print(f"directory: {directory}")
    for name, value in counts.items():
        print(f"  {name:16} {value}")
    print(f"  wide-hint-only files: {len(extra)}")
    for path in extra[:10]:
        print(f"    {path.relative_to(directory)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--measure", type=Path)
    args = parser.parse_args()
    if args.measure:
        measure(args.measure)
        return 0
    if not args.test:
        parser.print_help()
        return 2

    parent = _load("parent")
    merged = _load("merged")
    early = re.compile(
        rf"""["']{{1,3}}\s*[^"'\n]*\b(?:{merged._CYPHER_KEYWORDS})\s*\(""", re.IGNORECASE
    )

    print("== prefilter vs rule (each case is a whole source file) ==")
    print(f"{'case':16} {'parent':7} {'pr-first':9} {'merged':7} D211")
    failures: list[str] = []
    for name, source in CASES.items():
        parent_ok = parent_prefilter(source)
        early_ok = early.search(source) is not None
        merged_ok = merged_prefilter(source, merged.mentions_graph_query)
        lines = d211_lines(parent, source)
        print(f"{name:16} {str(parent_ok):7} {str(early_ok):9} {str(merged_ok):7} {len(lines)}")
        expected_parent = name == "standard"
        if parent_ok != expected_parent:
            failures.append(f"{name}: parent prefilter {parent_ok}, expected {expected_parent}")
        if not merged_ok:
            failures.append(f"{name}: merged prefilter skipped the file")
        if len(lines) != 1:
            failures.append(f"{name}: the rule reported {len(lines)} D211 findings")

    print()
    print("== a file that also mentions requests ==")
    with_requests = "import requests\n" + CASES["no-space"]
    print(f"parent={parent_prefilter(with_requests)} merged={merged_prefilter(with_requests, merged.mentions_graph_query)}")
    if not parent_prefilter(with_requests):
        failures.append("an unrelated trigger word no longer lets the parent scan")

    print()
    print("== lookalikes (no Cypher query in them) ==")
    print(f"{'source':26} {'parent':7} {'merged':7}")
    for label, source in LOOKALIKES.items():
        print(f"{label:26} {str(parent_prefilter(source)):7} {str(merged_prefilter(source, merged.mentions_graph_query)):7}")
    for label in ("re.match (name, pattern)", "def create (name):"):
        if not parent_prefilter(LOOKALIKES[label]):
            failures.append(f"{label}: expected the parent literal to fire")
        if merged_prefilter(LOOKALIKES[label], merged.mentions_graph_query):
            failures.append(f"{label}: merged hint fired on a lookalike")
    for label in ("re.match(name, pattern)", "db.create(obj)", "def create(name):"):
        if merged_prefilter(LOOKALIKES[label], merged.mentions_graph_query):
            failures.append(f"{label}: merged hint fired on a lookalike")

    print()
    print("== backtracking on \"label = '<N spaces>'\" ==")
    print(f"{'N':6} {'pr-first ms':12} {'merged ms':10}")
    rows = backtracking()
    for n, early_ms, merged_ms in rows:
        print(f"{n:6} {early_ms:12.2f} {merged_ms:10.3f}")
    if rows[-1][2] > 2.0:
        failures.append(f"merged hint took {rows[-1][2]:.2f} ms on 8000 spaces")
    growth = rows[-1][1] / rows[-2][1]
    if growth < 3.0:
        failures.append(f"pr-first hint grew {growth:.1f}x from 4000 to 8000 spaces; expected ~4x")

    print()
    if failures:
        for line in failures:
            print(f"FAIL {line}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
