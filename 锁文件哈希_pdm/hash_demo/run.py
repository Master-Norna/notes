#!/usr/bin/env python3
"""Offline comparison using verbatim PDM functions; Python 3.11+, stdlib only."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from support import (
    HERE, PdmUsageError, export_pylock_package, export_requirements, read_lock,
)

FILENAME = "demo-1.0-py3-none-any.whl"
URL = f"https://example.invalid/{FILENAME}"


def wheel_bytes():
    """Deterministic tiny wheel, generated locally; never downloaded/installed."""
    files = {
        "demo.py": b'"""Offline fixture; intentionally contains no executable statements."""\n',
        "demo-1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n\n",
        "demo-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: hash-demo\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n",
    }
    records = io.StringIO(newline="")
    writer = csv.writer(records, lineterminator="\n")
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, f"sha256={digest}", len(data)])
    writer.writerow(["demo-1.0.dist-info/RECORD", "", ""])
    files["demo-1.0.dist-info/RECORD"] = records.getvalue().encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


WHEEL = wheel_bytes()
HASHES = {name: hashlib.new(name, WHEEL).hexdigest() for name in ("sha256", "sha512")}


def lock_for(source="url", multiple=False, missing=False, empty=False, wheels=False, sdist=False):
    hashes = dict(HASHES) if multiple else {"sha256": HASHES["sha256"]}
    package = {"name": "demo", "version": "1.0"}
    if wheels or sdist:
        artifact = {"name": FILENAME, "url": URL, "hashes": hashes}
        if sdist:
            artifact.update(name="demo-1.0.tar.gz", url="https://example.invalid/demo-1.0.tar.gz")
            package["sdist"] = artifact
        else:
            package["wheels"] = [artifact]
    else:
        archive = {"url": URL + "#subdirectory=src"} if source == "url" else {"path": FILENAME}
        if not missing:
            archive["hashes"] = {} if empty else hashes
        package["archive"] = archive
    return {"lock-version": "1.0", "created-by": "hash-demo", "packages": [package]}


def observe(label, lock, root):
    repo = read_lock(label, lock, root)
    package, = repo.packages.values()
    candidate = package.candidate
    try:
        requirements = {"ok": True, "text": export_requirements(candidate)}
    except PdmUsageError as error:
        requirements = {"ok": False, "error": str(error)}
    return {"candidate_hashes": candidate.hashes, "requirements": requirements,
            "pylock_package": export_pylock_package(package),
            "no_hashes_requirements": export_requirements(candidate, hashes=False)}


def verify_provenance():
    provenance = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    for item in provenance["extracts"]:
        actual = hashlib.sha256((HERE / item["file"]).read_bytes()).hexdigest()
        if actual != item["sha256"]:
            raise AssertionError(f"Extract integrity mismatch: {item['file']}")
    assert hashlib.sha256((HERE / "LICENSE").read_bytes()).hexdigest() == provenance["license_sha256"]
    return provenance


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdm-hash-demo-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / FILENAME).write_bytes(WHEEL)

    def test_archive_url_and_local_single_and_multiple_hashes(self):
        for source in ("url", "path"):
            for multiple in (False, True):
                with self.subTest(source=source, multiple=multiple):
                    lock = lock_for(source, multiple)
                    before, after = (observe(label, lock, self.root) for label in ("before", "after"))
                    expected = dict(HASHES) if multiple else {"sha256": HASHES["sha256"]}
                    self.assertEqual(before["candidate_hashes"], [])
                    self.assertFalse(before["requirements"]["ok"])
                    self.assertIn("Hash is not available", before["requirements"]["error"])
                    self.assertNotIn("hashes", before["pylock_package"]["archive"])
                    expected_url = URL if source == "url" else (self.root / FILENAME).as_uri()
                    self.assertEqual(after["candidate_hashes"], [
                        {"url": expected_url, "file": FILENAME, "hash": f"{algo}:{value}"}
                        for algo, value in expected.items()])
                    self.assertTrue(after["requirements"]["ok"])
                    for algo, value in expected.items():
                        self.assertIn(f"--hash={algo}:{value}", after["requirements"]["text"])
                    self.assertEqual(after["pylock_package"]["archive"]["hashes"], expected)
                    self.assertNotIn("--hash=", before["no_hashes_requirements"])
                    self.assertEqual(lock["packages"][0]["name"], "demo")  # Reader got a deepcopy.
                    # Re-read only the source-location/hash fields: subdirectory
                    # round trips are explicitly outside PR #3956's scope.
                    next_lock = {"lock-version": "1.0", "packages": [after["pylock_package"]]}
                    roundtrip = observe("after", next_lock, self.root)
                    self.assertEqual(roundtrip["candidate_hashes"], after["candidate_hashes"])

    def test_named_wheels_and_sdist_compatibility(self):
        for kind in ("wheels", "sdist"):
            for multiple in (False, True):
                with self.subTest(kind=kind, multiple=multiple):
                    lock = lock_for(multiple=multiple, **{kind: True})
                    before, after = (observe(label, lock, self.root) for label in ("before", "after"))
                    self.assertEqual(before, after)
                    self.assertTrue(after["requirements"]["ok"])
                    self.assertEqual(len(after["candidate_hashes"]), 1)
                    # Existing wheels/sdist branch selects the first algorithm;
                    # do not attribute multi-hash support there to this patch.
                    self.assertEqual(after["candidate_hashes"][0]["hash"], "sha256:" + HASHES["sha256"])

    def test_missing_and_empty_archive_hashes_stay_negative(self):
        for source in ("url", "path"):
            for missing in (False, True):
                with self.subTest(source=source, missing=missing):
                    lock = lock_for(source, missing=missing, empty=not missing)
                    before, after = (observe(label, lock, self.root) for label in ("before", "after"))
                    self.assertEqual(before, after)
                    self.assertEqual(after["candidate_hashes"], [])
                    self.assertFalse(after["requirements"]["ok"])
                    self.assertNotIn("hashes", after["pylock_package"]["archive"])
                    self.assertNotIn("--hash=", after["no_hashes_requirements"])

    def test_extract_integrity(self):
        verify_provenance()

    def test_wheel_fixture_hashes_are_of_actual_bytes(self):
        self.assertEqual(WHEEL, wheel_bytes())
        with zipfile.ZipFile(io.BytesIO(WHEEL)) as wheel:
            self.assertIsNone(wheel.testzip())
            self.assertIn("demo-1.0.dist-info/RECORD", wheel.namelist())
        self.assertEqual(HASHES["sha256"], hashlib.sha256((self.root / FILENAME).read_bytes()).hexdigest())


def comparison():
    provenance = verify_provenance()
    result = {"before_sha": provenance["before"], "after_sha": provenance["after"],
              "fixture": {"filename": FILENAME, "bytes": len(WHEEL), "hashes": HASHES}, "cases": []}
    with tempfile.TemporaryDirectory(prefix="pdm-hash-demo-") as temp:
        root = Path(temp).resolve()
        (root / FILENAME).write_bytes(WHEEL)
        cases = [(f"archive-{source}-{'multi' if multiple else 'single'}", lock_for(source, multiple))
                 for source in ("url", "path") for multiple in (False, True)]
        cases += [("named-wheels", lock_for(wheels=True)), ("named-sdist", lock_for(sdist=True)),
                  ("archive-missing-hashes", lock_for(missing=True)), ("archive-empty-hashes", lock_for(empty=True))]
        for name, lock in cases:
            result["cases"].append({"name": name, "input_lock": lock,
                                    "before": observe("before", lock, root), "after": observe("after", lock, root)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="run regression assertions (no third-party packages)")
    args = parser.parse_args()
    # Enforce no sockets even if a future edit accidentally adds network access.
    with patch.object(socket, "socket", side_effect=AssertionError("Offline demo: sockets forbidden")):
        if args.test:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(RegressionTests)
            outcome = unittest.TextTestRunner(verbosity=2).run(suite)
            if outcome.wasSuccessful():
                print("PASS: 4 archive-positive + 4 wheel/sdist-compatibility + 4 true-negative scenarios; 5 test methods")
            return 0 if outcome.wasSuccessful() else 1
        print(json.dumps(comparison(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
