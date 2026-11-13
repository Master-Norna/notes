"""Replay skylos #1224: the npm mirror identity cache that was never written.

Two trimmed snapshots of the package are vendored:

  vendor/base   duriantaco/skylos @ 3f47e36  (parent of the fix)
  vendor/merge  duriantaco/skylos @ 89b8873  (merge of PR #1224)

Only the modules on the import path of `skylos.rules.sca.npm_mirrors` are
kept. `skylos.commands.hook_locked_packages` (the internal-package check) is
replaced by a stub that always answers "not internal"; it has nothing to do
with the cache and drags in every lockfile parser.

Usage:
  python -B run.py --test      # compare both snapshots, exit 1 on mismatch
  python -B run.py             # same, with the per-case table
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "base"
MERGE = "merge"
MIRROR = "https://mirror.example/npm"


def _install_stub() -> None:
    stub = types.ModuleType("skylos.commands.hook_locked_packages")
    stub.is_internal = lambda *_args, **_kwargs: False  # type: ignore[attr-defined]
    sys.modules["skylos.commands.hook_locked_packages"] = stub


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def iter_content(self, chunk_size: int | None = None):
        yield self.body

    def close(self) -> None:
        pass


class _Transport:
    def __init__(self, mapping: dict[str, bytes]) -> None:
        self.mapping = mapping
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.urls.append(url)
        return _Response(self.mapping.get(url, b""))


class _Candidate:
    def __init__(self, name: str, version: str, integrity: str) -> None:
        self.dependency = {
            "name": name,
            "version": version,
            "file": "/tmp/project/package-lock.json",
            "lockfile_version": 3,
            "source_type": "external",
            "integrity": integrity,
        }
        self.source_url = f"{MIRROR}/{name}/-/{name}-{version}.tgz"
        self.proof_key = f"npm:{name}@{version}"
        self.not_checked = {"name": name, "reason": "non_registry_source", "source_type": "url"}


class _Inventory:
    def __init__(self, candidates) -> None:
        self._npm_mirror_candidates = list(candidates)


class _Policy:
    npm_registry_mirrors = (MIRROR,)
    internal_packages = ()


def _integrity() -> str:
    import base64
    import hashlib

    return "sha512-" + base64.b64encode(hashlib.sha512(b"artifact").digest()).decode()


def _metadata(name: str, version: str, integrity: str) -> bytes:
    return json.dumps({"name": name, "version": version, "dist": {"integrity": integrity}}).encode()


def _scan(cache_root: Path, project: Path, transport: _Transport):
    from skylos.rules.sca.npm_mirrors import verify_npm_mirrors

    integrity = _integrity()
    candidate = _Candidate("left-pad", "1.3.0", integrity)
    inventory = _Inventory([candidate])
    policy = _Policy()
    os.environ["XDG_CACHE_HOME"] = str(cache_root)
    first = verify_npm_mirrors(project, inventory, policy, transport)
    second = verify_npm_mirrors(project, inventory, policy, transport)
    return first, second, integrity, cache_root / "skylos" / "npm-mirror-identities.json"


def _run_worker(vendor: str) -> None:
    root = HERE / "vendor" / vendor
    sys.path.insert(0, str(root))
    _install_stub()

    import skylos.rules.sca.npm_mirrors as mirrors

    if Path(mirrors.__file__).resolve().parent != (root / "skylos/rules/sca").resolve():
        raise SystemExit(f"imported {mirrors.__file__}, expected the vendored snapshot")

    tmp = Path(tempfile.mkdtemp(prefix=f"skylos-cache-{vendor}-"))
    cache_root = tmp / "cache"
    project = tmp / "project"
    project.mkdir()
    integrity = _integrity()
    transport = _Transport(
        {f"https://registry.npmjs.org/left-pad/1.3.0": _metadata("left-pad", "1.3.0", integrity)}
    )

    first, second, integrity, cache_file = _scan(cache_root, project, transport)
    after_two = {
        "first": {k: first.receipt[k] for k in ("status", "metadata_requests", "cache_hits", "verified_occurrences")},
        "second": {k: second.receipt[k] for k in ("status", "metadata_requests", "cache_hits", "verified_occurrences")},
        "requests_seen": len(transport.urls),
        "cache_path_kind": "file" if cache_file.is_file() else ("directory" if cache_file.is_dir() else "missing"),
        "cache_entries": (
            len(json.loads(cache_file.read_text(encoding="utf-8"))["entries"]) if cache_file.is_file() else 0
        ),
    }

    # What the lock path is while held: the data file name, or a sibling .lock.
    from contextlib import contextmanager

    from skylos.rules.sca.npm_mirrors import PublicNpmIdentity

    lock_dir = tmp / "lockprobe"
    lock_dir.mkdir()
    seen: list[dict] = []
    original_lock = mirrors.project_cache_lock

    @contextmanager
    def spy(root, lock_path, **kwargs):
        with original_lock(root, lock_path, **kwargs) as owned:
            target = Path(root) / Path(lock_path)
            data = Path(root) / mirrors.CACHE_FILE
            seen.append(
                {
                    "passed_to_lock": Path(lock_path).name,
                    "lock_is_dir": target.is_dir(),
                    "data_kind_while_held": "file" if data.is_file() else ("dir" if data.is_dir() else "missing"),
                }
            )
            yield owned

    mirrors.project_cache_lock = spy
    try:
        mirrors._save_cache(
            lock_dir, [PublicNpmIdentity("left-pad", "1.3.0", integrity, int(__import__("time").time()))]
        )
    finally:
        mirrors.project_cache_lock = original_lock
    lock_state = {
        "calls": seen,
        "data_file_after": (lock_dir / mirrors.CACHE_FILE).is_file(),
        "data_is_dir_after": (lock_dir / mirrors.CACHE_FILE).is_dir(),
    }

    # A host without a home directory: Path.home() raises RuntimeError.
    os.environ.pop("XDG_CACHE_HOME", None)
    original_home = Path.home
    try:
        def _no_home(cls):
            raise RuntimeError("Could not determine home directory.")

        Path.home = classmethod(_no_home)
        try:
            home_result = {"returned": str(mirrors._cache_directory(project))}
        except Exception as exc:  # noqa: BLE001 - the exception is the observation
            home_result = {"raised": f"{type(exc).__name__}: {exc}"}
    finally:
        Path.home = original_home

    print(
        json.dumps(
            {"two_scans": after_two, "lock_state": lock_state, "without_home": home_result},
            ensure_ascii=False,
        )
    )


def _measure(vendor: str) -> dict:
    env = dict(os.environ)
    env.pop("XDG_CACHE_HOME", None)
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--worker", vendor],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", metavar="VENDOR")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.worker:
        _run_worker(args.worker)
        return 0

    base = _measure(BASE)
    merge = _measure(MERGE)

    def line(label: str, value) -> None:
        print(f"  {label:<28} {json.dumps(value, ensure_ascii=False)}")

    for name, data in (("parent 3f47e36", base), ("merged 89b8873", merge)):
        print(f"== {name} ==")
        line("run 1", data["two_scans"]["first"])
        line("run 2", data["two_scans"]["second"])
        line("HTTP requests seen", data["two_scans"]["requests_seen"])
        line("cache path after run 2", data["two_scans"]["cache_path_kind"])
        line("cache entries", data["two_scans"]["cache_entries"])
        line("lock holds", data["lock_state"])
        line("no home", data["without_home"])
        print()

    checks = {
        "parent: second scan still asks": base["two_scans"]["second"]["metadata_requests"] == 1,
        "parent: no cache file": base["two_scans"]["cache_path_kind"] == "missing",
        "parent: no home raises": "raised" in base["without_home"],
        "merged: second scan hits cache": merge["two_scans"]["second"]["cache_hits"] == 1,
        "merged: file with one entry": merge["two_scans"]["cache_path_kind"] == "file"
        and merge["two_scans"]["cache_entries"] == 1,
        "merged: no home disables cache": merge["without_home"].get("returned") == "None",
    }
    for label, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    failures = sum(not ok for ok in checks.values())
    print(f"\n{failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
