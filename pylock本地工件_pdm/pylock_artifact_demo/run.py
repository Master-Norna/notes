"""Offline reproduction for PDM #3975: pylock local artifact paths and explicit names.

The lock reader used to ignore ``path`` and only keep ``url``; even when a
local file was reached, unearth derived the artifact name from the physical
basename. Two unmodified PDM source snapshots live under vendor/before and
vendor/after. Every case runs in its own isolated interpreter and every socket
call is refused by an audit hook.

    python run.py --test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMITS = {
    "before": "dc1f476a53043ec36c83df104a73a6e86a4d4e64",
    "after": "a4965a8f116dc51d961cdd6b1e0d55aabb0abd2e",
}
WHEEL = "first-2.0.2-py2.py3-none-any.whl"
SDIST = "demo-0.0.1.tar.gz"

WORKER = r"""
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import types
from pathlib import Path

vendor, label, payload_json = sys.argv[1], sys.argv[2], sys.argv[3]
payload = json.loads(payload_json)
sys.path.insert(0, vendor)

# findpython invokes the interpreter with -Ic; on a UTF-8 host locale the child
# prints in the OEM code page and decoding fails. Run with -X utf8 instead.
import findpython.python as _fp


def _run_script_utf8(executable, script, timeout=None):
    return subprocess.run(
        [str(executable), "-I", "-X", "utf8", "-c", script],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
        check=True, text=True, encoding="utf-8",
    ).stdout


_fp._run_script = _run_script_utf8


def deny_network(event, args):
    if event.startswith("socket.") and event != "socket.gethostname":
        raise RuntimeError(f"offline: forbidden audit event {event}")


sys.addaudithook(deny_network)

from pdm.core import Core
from pdm.environments import PythonEnvironment
from pdm.models.markers import EnvSpec
from pdm.models.repositories.lock import LockedRepository

work = Path(payload["work"])
tmp = work / f"project-{label}"
tmp.mkdir()
home = tmp / ".pdm-home"
home.mkdir()
(home / "config.toml").write_text(
    f'[global_project]\npath = "{(home / "global-project").as_posix()}"\n', encoding="utf-8"
)
core = Core()
project = core.create_project(tmp, global_config=str(home / "config.toml"))
for key, value in {
    "python.install_root": str(tmp / "pythons"),
    "venv.location": str(tmp / "venvs"),
    "cache_dir": str(tmp / "caches"),
    "log_dir": str(tmp / "logs"),
}.items():
    project.global_config[key] = value
project._saved_python = sys.executable
(tmp / "caches").mkdir()

lockfile = tomllib.loads((work / "locks" / "pylock.toml").read_text(encoding="utf-8"))
project.set_lockfile(work / "locks" / "pylock.toml")
env = PythonEnvironment(project, python=sys.executable, prefix=str(tmp / "env"))
project._environment = env

out = {"hashes": None, "link": None, "filename": None, "file_path": None,
       "obtain": None, "error": None, "unpacked": None}
try:
    repo = LockedRepository(lockfile, [], env, env_spec=EnvSpec.current())
    candidate = next(iter(repo.packages.values())).candidate
    out["hashes"] = candidate.hashes
    prepared = candidate.prepare(env)
    prepared._obtain(allow_all=False)
    out["obtain"] = "ok"
    link = prepared.link
    out["link"] = link.url if link is not None else None
    out["filename"] = link.filename if link is not None else None
    out["file_path"] = str(link.file_path) if link is not None else None
    if prepared._unpacked_dir is not None:
        out["unpacked"] = sorted(p.name for p in Path(prepared._unpacked_dir).iterdir())[:8]
except Exception as exc:  # noqa: BLE001 - the failure type is the observation
    out["obtain"] = "failed"
    out["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_case(name: str, root: Path) -> Path:
    """Create work/locks/{pylock.toml,local artifacts/...} for one case."""
    work = root / name
    locks = work / "locks"
    artifacts = locks / "local artifacts"
    artifacts.mkdir(parents=True)

    if name == "path_only_wheel":
        data = artifacts / "0123456789abcdef"
        shutil.copyfile(HERE / "fixtures" / WHEEL, data)
        artifact = {"name": WHEEL, "path": "local artifacts/0123456789abcdef",
                    "hashes": {"sha256": sha256(data)}}
    elif name == "path_and_url_wheel":
        data = artifacts / "0123456789abcdef"
        shutil.copyfile(HERE / "fixtures" / WHEEL, data)
        artifact = {"name": WHEEL, "path": "local artifacts/0123456789abcdef",
                    "url": f"https://example.invalid/{WHEEL}",
                    "hashes": {"sha256": sha256(data)}}
    elif name == "named_local_wheel":
        data = artifacts / "0123456789abcdef"
        shutil.copyfile(HERE / "fixtures" / WHEEL, data)
        artifact = {"name": WHEEL, "path": "local artifacts/0123456789abcdef",
                    "url": data.as_uri(), "hashes": {"sha256": sha256(data)}}
    elif name == "named_local_sdist":
        data = artifacts / "wrong.tar.bz2"
        shutil.copyfile(HERE / "fixtures" / SDIST, data)
        artifact = {"name": SDIST, "path": "local artifacts/wrong.tar.bz2",
                    "url": data.as_uri(), "hashes": {"sha256": sha256(data)}}
    else:
        raise AssertionError(name)

    lockfile = {
        "lock-version": "1.0",
        "created-by": "reproduction",
        "packages": [
            {
                "name": "first" if "wheel" in name else "demo",
                "version": "2.0.2" if "wheel" in name else "0.0.1",
                "wheels" if "wheel" in name else "sdist": [artifact] if "wheel" in name else artifact,
            }
        ],
    }
    import tomllib  # noqa: F401  (only for the format hint below)
    (locks / "pylock.toml").write_text(render_toml(lockfile), encoding="utf-8")
    return work


def render_toml(lockfile: dict) -> str:
    lines = ['lock-version = "1.0"', 'created-by = "reproduction"', ""]
    package = lockfile["packages"][0]
    lines.append("[[packages]]")
    lines.append(f'name = "{package["name"]}"')
    lines.append(f'version = "{package["version"]}"')
    lines.append("")
    if "wheels" in package:
        artifact = package["wheels"][0]
        lines.append("[[packages.wheels]]")
        table = "packages.wheels"
    else:
        artifact = package["sdist"]
        lines.append("[packages.sdist]")
        table = "packages.sdist"
    for key in ("name", "path", "url"):
        if key in artifact:
            value = artifact[key].replace("\\", "/")
            lines.append(f'{key} = "{value}"')
    lines.append(f"[{table}.hashes]")
    lines.append(f'sha256 = "{artifact["hashes"]["sha256"]}"')
    lines.append("")
    return "\n".join(lines)


CASES = ["path_only_wheel", "path_and_url_wheel", "named_local_wheel", "named_local_sdist"]


def run_case(version: str, work: Path) -> dict:
    cmd = [
        sys.executable, "-I", "-B", "-X", "utf8", "-c",
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        f"exec(compile({WORKER!r}, '<worker>', 'exec'))\n",
        str(HERE / "vendor" / version), version, json.dumps({"work": str(work)}),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        return {"obtain": "crashed", "error": proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no stderr"}
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="pdm-artifact-"))
    results = {}
    for case in CASES:
        work = make_case(case, root)
        results[case] = {v: run_case(v, work) for v in ("before", "after")}

    for case, pair in results.items():
        print(f"== {case}")
        for version in ("before", "after"):
            item = pair[version]
            print(f"  {version}: obtain={item.get('obtain')} filename={item.get('filename')!r}")
            if item.get("error"):
                print(f"          error={item['error']}")
        print()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"commits": COMMITS, "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    if args.test:
        failures = []
        # before: no file url at all; after: the local path wins.
        if "url" in json.dumps(results["path_only_wheel"]["before"].get("hashes") or []):
            failures.append("before/path_only_wheel unexpectedly kept a url")
        if not any("file:" in str(h.get("url", "")) for h in (results["path_only_wheel"]["after"].get("hashes") or [])):
            failures.append("after/path_only_wheel did not turn the path into a file url")
        for case in CASES:
            if results[case]["after"].get("obtain") != "ok":
                failures.append(f"after/{case} failed: {results[case]['after'].get('error')}")
        if results["named_local_wheel"]["after"].get("filename") != WHEEL:
            failures.append("after/named_local_wheel lost the logical filename")
        if results["named_local_sdist"]["after"].get("unpacked") is None:
            failures.append("after/named_local_sdist did not unpack")
        # The pre-fix reader must not succeed by reading the local bytes it ignored.
        for case in ("path_only_wheel", "path_and_url_wheel"):
            if results[case]["before"].get("obtain") == "ok":
                failures.append(f"before/{case} should not succeed offline")
        if failures:
            print("FAIL")
            for item in failures:
                print(" -", item)
            return 1
        print("PASS: 4 cases; before ignores path (and the explicit name), after honours both")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

