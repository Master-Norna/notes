"""Offline reproduction using unmodified PDM source snapshots (see README)."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
COMMITS = {"before": "7aaeb992092d827dee173e60e82cfffa0a5b9676", "after": "f01b85810baacec4c8a22168da3f9e54550adb14"}


def deny_network(event, args):
    if event.startswith("socket.") and event != "socket.gethostname":
        raise RuntimeError(f"Offline execution: forbidden audit event {event}")


def make_zip(path):
    # Stable bytes, independent of temp paths and wall clock. One ZIP for both versions.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for directory, name in [("", "parent"), ("src/child/", "child"), ("src/a&b/", "child"), ("src/a/", "decoy")]:
            data = f'[project]\nname = "{name}"\nversion = "1.0"\ndependencies = ["{name}-dep"]\nrequires-python = ">=3.10"\n'
            archive.writestr(zipfile.ZipInfo("bundle/" + directory + "pyproject.toml", (2020, 1, 1, 0, 0, 0)), data)


def verify_environment():
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use Python 3.12 and the fixed dependency environment (see README).")
    errors = []
    for line in (HERE / "requirements.lock").read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        name, expected = line.split("==", 1)
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        if actual != expected:
            errors.append(f"{name}: expected {expected}, found {actual}")
    if errors:
        raise SystemExit("Prepare the fixed dependencies first (see README); run.py never installs them:\n" + "\n".join(errors))


def verify_sources():
    manifest = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    for item in manifest:
        assert item["commit"] == COMMITS[item["label"]]
        for filename, expected in item["files"].items():
            path = HERE / "vendor" / item["label"] / filename
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"Modified upstream snapshot: {path}"


def worker(label, work):
    sys.addaudithook(deny_network)
    sys.path.insert(0, str(HERE / "vendor" / label / "src"))
    # findpython runs isolated probes (-Ic ignores PYTHONUTF8); force their stdout to UTF-8.
    # This is environment plumbing only: no converter/reader/candidate/finder code is replaced.
    import findpython.python as finder
    from types import SimpleNamespace
    original_run = subprocess.run
    def utf8_run(command, *args, **kwargs):
        if len(command) >= 2 and command[1] == "-Ic":
            command = [command[0], "-X", "utf8", *command[1:]]
        return original_run(command, *args, **kwargs)
    finder.subprocess = SimpleNamespace(
        run=utf8_run, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL,
        CalledProcessError=subprocess.CalledProcessError, TimeoutExpired=subprocess.TimeoutExpired,
    )

    import tomlkit
    import tomllib
    from pdm.core import Core
    from pdm.project import Project
    from pdm.environments import BareEnvironment
    from pdm.formats.requirements import convert as import_requirements
    from pdm.formats.pylock import PyLockConverter
    from pdm.models.candidates import Candidate, PreparedCandidate
    from pdm.models.requirements import parse_line
    from pdm.models.repositories.lock import LockedRepository, Package
    from pdm.utils import cd

    import socket
    try:
        socket.socket()
    except RuntimeError:
        pass
    else:
        raise AssertionError("socket guard failed")

    core = Core()
    core.state.enable_cache = False
    root = work / label
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="demo-host"\nversion="1.0"\nrequires-python=">=3.10"\ndependencies=[]\n', encoding="utf-8")
    project = Project(core, root, global_config=root / "global-config.toml")
    project.global_config["cache_dir"] = str(root / "cache")
    project.project_config["pypi.url"] = "https://index.invalid/simple"
    environment = BareEnvironment(project)
    # A local HTTPX transport serves the exact same ZIP bytes for the URL-only
    # branch. No HTTP server/socket, redirects, or package-index traffic is used.
    import httpx2
    transport_requests = []
    archive_url = "https://archives.invalid/bundle-1.0.zip"
    def serve_archive(request):
        assert str(request.url).split("#", 1)[0] == archive_url, f"Unexpected fixture request: {request.url}"
        transport_requests.append(str(request.url))
        return httpx2.Response(200, content=(work / "bundle-1.0.zip").read_bytes(), headers={"Content-Type": "application/zip"})
    environment.__dict__["session"] = environment._build_session(mounts={"https://archives.invalid/": httpx2.MockTransport(serve_archive)})
    project._environment = environment
    archive = work / "bundle-1.0.zip"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    rows = []
    decoy_control = None
    unpack_calls = []
    def observe_unpack(frame, event, arg):
        if event == "call" and frame.f_code.co_name == "_unpack" and frame.f_globals.get("__name__") == "pdm.models.candidates":
            unpack_calls.append({"validate_hashes": frame.f_locals["validate_hashes"], "url": frame.f_locals["self"].link.url})
    sys.setprofile(observe_unpack)
    try:
        for source in ("url", "path"):
            for selector in (None, "src/child", "src/a&b"):
                from urllib.parse import quote
                name = "child" if selector else "parent"
                url = archive_url if source == "url" else archive.as_uri()
                req_text = f"{name} @ {url}"
                if selector:
                    req_text += "#subdirectory=" + quote(selector)
                req_file = root / "requirements.txt"
                req_file.write_text(req_text + "\n", encoding="utf-8")
                imported, _ = import_requirements(project, req_file, argparse.Namespace(dev=False, group=None))
                imported_line = str(imported["dependencies"][0])
                with cd(root):
                    req = parse_line(imported_line)
                assert req.subdirectory == selector
                candidate = Candidate(req)
                PreparedCandidate._build_dir_cache.clear()
                before_metadata = candidate.prepare(environment).metadata
                assert before_metadata.metadata["Name"] == name
                assert before_metadata.requires == [f"{name}-dep"]
                candidate.hashes = [{"url": url, "file": archive.name, "hash": f"sha256:{digest}"}]
                normal_entry = candidate.as_lockfile_entry(root)
                assert normal_entry.get("subdirectory") == selector
                # Construct a repository, not a resolver: placeholder dependencies are
                # deliberately metadata observations, never fetched or installed.
                repository = LockedRepository({}, [], environment)
                repository.add_package(Package(candidate, before_metadata.requires))
                repository.targets = [environment.spec]
                converter = PyLockConverter(project, repository)
                exported = converter.convert(all_groups=["default"])
                serialized = tomlkit.dumps(exported)
                exported_doc = tomllib.loads(serialized)
                assert exported_doc["lock-version"] == "1.0"
                package = exported_doc["packages"][0]
                assert package["name"] == name
                assert package["archive"]["hashes"] == {"sha256": digest}
                assert package["archive"]["url"] == url
                expected_subdir = selector if label == "after" else None
                assert package["archive"].get("subdirectory") == expected_subdir
                assert ("subdirectory" in package["archive"]) == bool(expected_subdir)
                assert ("path" in package["archive"]) == (source == "path")
                suffix = selector.replace("/", "_").replace("&", "and") if selector else "root"
                (root / f"{source}-{suffix}.toml").write_text(serialized, encoding="utf-8")
                # Reader mutates input (pop name), so use a fresh parse, not shared data.
                fresh_repository = LockedRepository(tomllib.loads(serialized), [], environment)
                fresh = next(iter(fresh_repository.packages.values())).candidate
                assert fresh is not candidate and fresh.prepared is None
                PreparedCandidate._build_dir_cache.clear()
                prepared = fresh.prepare(environment)
                metadata = prepared.metadata
                selected = selector if label == "after" else None
                expected = "child" if selected else "parent"
                assert metadata.metadata["Name"] == expected
                assert metadata.requires == [f"{expected}-dep"]
                assert fresh.name == name and fresh.req.key == name
                assert fresh.req.subdirectory == selected
                assert fresh.hashes[0]["hash"] == f"sha256:{digest}"
                assert prepared._unpacked_dir is not None and prepared._source_dir is not None
                relative = prepared._unpacked_dir.relative_to(prepared._source_dir).as_posix()
                rows.append({
                    "source": source, "selector": selector, "imported_line": imported_line,
                    "initial_metadata": {"name": before_metadata.metadata["Name"], "requires": before_metadata.requires},
                    "normal_pdm_lock_entry": normal_entry,
                    "lock_version": exported_doc["lock-version"], "metadata_validate_hashes": False,
                    "pylock_toml": serialized, "exported_name": package["name"], "archive": package["archive"],
                    "read_subdirectory": fresh.req.subdirectory, "read_hashes": fresh.hashes,
                    "fresh_candidate_name": fresh.name,
                    "metadata_name": metadata.metadata["Name"], "metadata_requires": metadata.requires,
                    "unpacked_relative": relative,
                })
        # Positive control: the truncation decoy really has different metadata.
        with cd(root):
            decoy = Candidate(parse_line(f"decoy @ {archive.as_uri()}#subdirectory=src/a"))
        PreparedCandidate._build_dir_cache.clear()
        decoy_metadata = decoy.prepare(environment).metadata
        assert decoy_metadata.metadata["Name"] == "decoy"
        assert decoy_metadata.requires == ["decoy-dep"]
        decoy_control = {"name": decoy_metadata.metadata["Name"], "requires": decoy_metadata.requires}
        assert len(unpack_calls) == 13 and all(call["validate_hashes"] is False for call in unpack_calls)
        assert len(transport_requests) == 6, "Every URL case must fetch initial and fresh metadata"
    finally:
        sys.setprofile(None)
        core.exit_stack.close()
    return {
        "label": label, "commit": COMMITS[label],
        "pdm_module": str(Path(sys.modules["pdm.formats.pylock"].__file__).relative_to(HERE)),
        "unpack_calls": unpack_calls, "decoy_control": decoy_control, "transport_requests": transport_requests,
        "dependencies": {n: importlib.metadata.version(n) for n in ["pdm", "unearth", "hishel", "httpx2", "dep-logic", "findpython", "tomlkit"]},
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="assert all invariants (also asserted in normal mode)")
    parser.add_argument("--json", type=Path, help="write full evidence JSON")
    parser.add_argument("--worker", choices=COMMITS, help=argparse.SUPPRESS)
    parser.add_argument("--work", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not __debug__:
        raise SystemExit("Do not use -O: this reproduction relies on assertions.")
    if args.worker:
        result = worker(args.worker, args.work)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    sys.addaudithook(deny_network)
    verify_environment()
    verify_sources()
    with tempfile.TemporaryDirectory(prefix="pdm-subdirectory-") as tmp:
        work = Path(tmp)
        make_zip(work / "bundle-1.0.zip")
        results = []
        for label in COMMITS:
            output = work / (label + ".json")
            command = [sys.executable, "-B", "-X", "utf8", str(HERE / "run.py"), "--worker", label, "--work", str(work), "--json", str(output)]
            result = subprocess.run(command, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PDM_CHECK_UPDATE": "false", "PDM_IGNORE_ACTIVE_VENV": "1"})
            if result.returncode:
                raise SystemExit(f"{label}: worker failed; prepare fixed dependencies first (see README).")
            results.append(json.loads(output.read_text(encoding="utf-8")))
        for before, after in zip(results[0]["rows"], results[1]["rows"], strict=True):
            a, b = dict(before["archive"]), dict(after["archive"])
            a.pop("subdirectory", None)
            b.pop("subdirectory", None)
            assert a == b, "URL/path/hash must not change"
            assert before["exported_name"] == after["exported_name"]
        report = {"python": sys.version, "zip_sha256": hashlib.sha256((work / "bundle-1.0.zip").read_bytes()).hexdigest(), "network": "socket creation, DNS resolution and network operations denied (gethostname allowed); URL fixture uses in-process MockTransport", "results": results}
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("source selector       exported  before metadata      after metadata")
        for a, b in zip(results[0]["rows"], results[1]["rows"], strict=True):
            print(f"{a['source']:6} {str(a['selector']):14} {a['exported_name']:9} {a['metadata_name']+'/'+a['metadata_requires'][0]:20} {b['metadata_name']+'/'+b['metadata_requires'][0]}")
        print("pylock lock-version: 1.0; prepare_metadata calls _unpack(validate_hashes=False).")
        print(f"ZIP SHA-256: {report['zip_sha256']}")
        print("PASS: 12 fresh-read metadata cases + 2 decoy controls; URL/path/hash unchanged; no installation performed.")


if __name__ == "__main__":
    main()
