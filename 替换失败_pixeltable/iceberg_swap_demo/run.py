"""Replay pixeltable #1889: a failed catalog swap must not delete the export.

Two versions of one module are vendored:

  vendor/base/iceberg.py   pixeltable @ 2eca8e44  (parent of the fix)
  vendor/merge/iceberg.py  pixeltable @ b7661983  (merge of PR #1889)

Everything else comes from an installed pixeltable 0.7.24, whose
`pixeltable/io/iceberg.py` is byte-identical to the parent snapshot.

The scenarios replace the target table through a catalog wrapper that fails at
one step of the swap: after `drop_table` took effect, inside `rename_table`,
before `drop_table` took effect, or while `table_exists` is being asked.

Usage:
  python -B run.py --test      # run both snapshots, exit 1 on a mismatch
  python -B run.py             # same, with the per-case table
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDORS = {"base": HERE / "vendor" / "base" / "iceberg.py", "merge": HERE / "vendor" / "merge" / "iceberg.py"}
TARGET = "demo.t"
TMP_TAG = "__pxt_tmp_"

CASES = {
    "rename-fails/no-target": {"target": False, "rename": True},
    "drop-applied-then-raises": {"target": True, "drop": "after"},
    "drop-fails-before-effect": {"target": True, "drop": "before"},
    "target-check-fails": {"target": True, "drop": "after", "exists": True},
    "replace-succeeds": {"target": True},
}

# What the merged snapshot should leave behind. The parent is measured, not
# asserted: losing the only copy is the point of the replay.
EXPECT_MERGE = {
    "rename-fails/no-target": {"temp_tables": 1, "temp_rows": 3, "target": "missing", "target_rows": 0},
    "drop-applied-then-raises": {"temp_tables": 1, "temp_rows": 3, "target": "missing", "target_rows": 0},
    "drop-fails-before-effect": {"temp_tables": 0, "temp_rows": 0, "target": "present", "target_rows": 1},
    "target-check-fails": {"temp_tables": 1, "temp_rows": 3, "target": "missing", "target_rows": 0},
    "replace-succeeds": {"temp_tables": 0, "temp_rows": 0, "target": "present", "target_rows": 3},
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _pg_bin() -> Path:
    import pixeltable_pgserver

    return Path(pixeltable_pgserver.__file__).resolve().parent / "pginstall" / "bin"


def _psql(bin_dir: Path, port: int, database: str, sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(bin_dir / "psql.exe"), "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-d", database,
         "-tAc", sql],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )


def preseed(home: Path) -> None:
    """Create a cluster whose system databases are UTF-8.

    The bundled initdb cannot initialize a UTF-8 cluster on this host (the
    Chinese system locale leaks a non-UTF-8 byte into post-bootstrap). It can
    create an SQL_ASCII cluster, so the two databases pixeltable talks to are
    rebuilt from template0 as UTF-8 afterwards.
    """
    data = home / "pgdata"
    if (data / "PG_VERSION").exists():
        return
    home.mkdir(parents=True, exist_ok=True)
    bin_dir = _pg_bin()
    subprocess.run(
        [str(bin_dir / "initdb.exe"), "--auth=trust", "--auth-local=trust", "--encoding=SQL_ASCII", "--locale=C",
         "-U", "postgres", "-D", str(data)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    port = _free_port()
    proc = subprocess.Popen(
        [str(bin_dir / "postgres.exe"), "-D", str(data), "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            if _psql(bin_dir, port, "template1", "SELECT 1").returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("postgres did not become ready")
            time.sleep(0.2)
        for database in ("postgres", "pixeltable"):
            if database == "postgres":
                _psql(bin_dir, port, "template1", "DROP DATABASE postgres")
            created = _psql(
                bin_dir, port, "template1",
                f"CREATE DATABASE {database} TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'",
            )
            if created.returncode != 0:
                raise RuntimeError(created.stderr.decode("utf-8", "replace"))
    finally:
        subprocess.run([str(bin_dir / "pg_ctl.exe"), "-D", str(data), "stop", "-m", "fast"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _load_vendored(path: Path) -> None:
    import pixeltable as pxt

    spec = importlib.util.spec_from_file_location("pixeltable.io.iceberg_vendored", str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pxt.io.export_iceberg = module.export_iceberg


class FailingCatalog:
    def __init__(self, inner, *, drop: str | None = None, rename: bool = False, exists: bool = False) -> None:
        self._inner = inner
        self._drop = drop
        self._rename = rename
        self._exists = exists

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def drop_table(self, identifier, *args, **kwargs):
        if self._drop == "before" and identifier == TARGET:
            raise PermissionError("synthetic failure before dropping the target")
        result = self._inner.drop_table(identifier, *args, **kwargs)
        if self._drop == "after" and identifier == TARGET:
            raise OSError("synthetic failure after dropping the target")
        return result

    def rename_table(self, *args, **kwargs):
        if self._rename:
            raise OSError("synthetic rename failure")
        return self._inner.rename_table(*args, **kwargs)

    def table_exists(self, identifier):
        if self._exists:
            raise OSError("synthetic target lookup failure")
        return self._inner.table_exists(identifier)


def _case(case: str, spec: dict, work: Path) -> dict:
    import pixeltable as pxt
    from pyiceberg.catalog.sql import SqlCatalog
    from pyiceberg.exceptions import NoSuchTableError

    table_name = "swap_" + case.replace("-", "_").replace("/", "_")
    table = pxt.create_table(table_name, {"c_int": pxt.Int, "c_string": pxt.String})
    rows = [{"c_int": i, "c_string": f"row_{i}"} for i in range(3)]
    table.insert(rows)

    catalog = SqlCatalog(
        "demo",
        uri=f"sqlite:///{work / (table_name + '.db')}",
        warehouse=str(work / (table_name + '_warehouse')),
    )
    if spec.get("target"):
        pxt.io.export_iceberg(table.where(table.c_int == 0), catalog, TARGET)
        assert catalog.load_table(TARGET).scan().to_arrow().num_rows == 1

    failing = FailingCatalog(catalog, drop=spec.get("drop"), rename=spec.get("rename", False),
                             exists=spec.get("exists", False))
    try:
        pxt.io.export_iceberg(table, failing, TARGET, if_exists="replace")
        error = None
    except Exception as exc:  # noqa: BLE001 - the message is part of the result
        error = str(exc)

    try:
        target_rows = sorted(catalog.load_table(TARGET).scan().to_arrow().to_pylist(), key=lambda r: r["c_int"])
        target = "present"
    except NoSuchTableError:
        target_rows, target = [], "missing"
    temp_names = [name for _, name in catalog.list_tables("demo") if TMP_TAG in name]
    temp_rows = []
    if temp_names:
        temp_rows = sorted(catalog.load_table(f"demo.{temp_names[0]}").scan().to_arrow().to_pylist(),
                           key=lambda r: r["c_int"])
    return {
        "temp_tables": len(temp_names),
        "temp_rows": len(temp_rows),
        "target": target,
        "target_rows": len(target_rows),
        "temp_named_in_error": bool(temp_names) and temp_names[0] in (error or ""),
        "error": (error or "").replace("\n", " ")[:160],
    }


def _worker(vendor: str) -> None:
    home = Path(tempfile.mkdtemp(prefix=f"pxt-swap-{vendor}-"))
    os.environ["PIXELTABLE_HOME"] = str(home)
    preseed(home)
    _load_vendored(VENDORS[vendor])

    work = home / "iceberg"
    work.mkdir()
    results = {}
    for case, spec in CASES.items():
        results[case] = _case(case, spec, work)
    print(json.dumps(results, ensure_ascii=False))

    # Stop the embedded Postgres this worker started before deleting its data dir.
    try:
        from pixeltable.env import Env

        server = getattr(Env.get(), "_db_server", None)
        if server is not None:
            server.stop()
    except Exception:  # noqa: BLE001 - cleanup must not hide the result
        pass
    shutil.rmtree(home, ignore_errors=True)


def _measure(vendor: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()), "--worker", vendor],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _short(result: dict) -> str:
    return (
        f"temp={result['temp_tables']} rows={result['temp_rows']} "
        f"target={result['target']}({result['target_rows']}) named={result['temp_named_in_error']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", metavar="VENDOR")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.worker:
        _worker(args.worker)
        return 0

    base = _measure("base")
    merge = _measure("merge")
    print(f"{'case':<30} {'parent 2eca8e44':<52} {'merged b7661983'}")
    print("-" * 120)
    failures = 0
    lost = 0
    for case in CASES:
        b, m = base[case], merge[case]
        if b["temp_tables"] == 0 and b["target"] == "missing":
            lost += 1
        good = all(m[key] == value for key, value in EXPECT_MERGE[case].items())
        if not good:
            failures += 1
        print(f"{case:<30} {_short(b):<52} {_short(m)}{'' if good else '   <-- MISMATCH'}")
    print()
    print(f"parent left no copy after {lost}/{len(CASES)} failed swaps; merged failed {failures}/{len(CASES)} expectations")
    if args.test:
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
