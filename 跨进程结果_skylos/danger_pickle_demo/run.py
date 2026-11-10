"""Show why a skylos danger worker result cannot cross the process boundary.

The two vendored revisions differ only in the pickle protocol of
``_CallableIndex``: the parent revision keeps its flow caches (which contain a
local ``outer`` closure) in ``__dict__``; the merged revision serializes only
the module and rebuilds the caches lazily.

Run:  python run.py [--test]
"""

from __future__ import annotations

import argparse
import ast
import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))

from parent import callable_bindings as parent_cb  # noqa: E402
from merged import callable_bindings as merged_cb  # noqa: E402

SOURCE = """import os
import random

def run(cmd):
    os.system(cmd)

def weak():
    return random.random()

def helper(x):
    return x + 1
"""


def set_parents(node: ast.AST, parent: ast.AST | None = None) -> None:
    for child in ast.iter_child_nodes(node):
        child.parent = node
        set_parents(child, node)


def build(module_cls):
    module = ast.parse(SOURCE)
    set_parents(module)
    index = module_cls._CallableIndex(module)
    func = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    flow = index.flow(func)
    call = next(node for node in ast.walk(func) if isinstance(node, ast.Call))
    names = index.names(call, "os.system", "fixture.py", None)
    return module, index, flow, names


def try_pickle(index) -> dict:
    try:
        data = pickle.dumps(index)
    except Exception as exc:  # noqa: BLE001 - the failure is the observation
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "bytes": len(data)}


def roundtrip(index) -> dict:
    data = pickle.dumps(index)
    restored = pickle.loads(data)
    module = restored.module
    func = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    before = {
        "ready": getattr(restored, "_ready", None),
        "has_flows": hasattr(restored, "flows"),
    }
    # the first lookup rebuilds the id-keyed caches from the restored module
    restored.scope(func)
    flow = restored.flow(func)
    after = {"ready": getattr(restored, "_ready", None), "flows": len(restored.flows)}
    call = next(node for node in ast.walk(func) if isinstance(node, ast.Call))
    names = restored.names(call, "os.system", "fixture.py", None)
    return {
        "bytes": len(data),
        "before_first_use": before,
        "after_first_use": after,
        "flow_is_none": flow is None,
        "names": list(names),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    module, parent_index, parent_flow, parent_names = build(parent_cb)
    module2, merged_index, merged_flow, merged_names = build(merged_cb)

    report = {
        "parent": {
            "flow_is_none": parent_flow is None,
            "names": list(parent_names),
            "pickle": try_pickle(parent_index),
        },
        "merged": {
            "flow_is_none": merged_flow is None,
            "names": list(merged_names),
            "pickle": try_pickle(merged_index),
            "roundtrip": roundtrip(merged_index),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.test:
        assert report["parent"]["flow_is_none"] is False
        assert report["merged"]["flow_is_none"] is False
        assert report["parent"]["pickle"]["ok"] is False
        assert "_CallableIndex.flow.<locals>.outer" in report["parent"]["pickle"]["error"]
        assert report["merged"]["pickle"]["ok"] is True
        assert report["merged"]["roundtrip"]["before_first_use"]["has_flows"] is False
        assert report["merged"]["roundtrip"]["after_first_use"]["flows"] > 0
        assert report["merged"]["roundtrip"]["names"] == ["os.system"]
        print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
