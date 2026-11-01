#!/usr/bin/env python3
"""Regenerate provenance.json for the pypdf negative-startxref demo."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVES = Path(r"E:\项目\Note\.yan\选题-20261031\pypdf\archives")
VERSIONS = {
    "parent": {
        "sha": "b78c2aa5301ee4fb1ee024b9838923945ab357b6",
        "role": "first parent of the #4144 merge (pre-fix)",
        "archive": "b78c2aa5301ee4fb1ee024b9838923945ab357b6.tar.gz",
    },
    "merge": {
        "sha": "91a73b5e8e9701efdad26b865964c2a53cb110b3",
        "role": "#4144 merge",
        "archive": "91a73b5e8e9701efdad26b865964c2a53cb110b3.tar.gz",
    },
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    out = {
        "upstream": "py-pdf/pypdf",
        "license": "BSD-3-Clause",
        "versions": {},
    }
    for label, meta in VERSIONS.items():
        package = ROOT / "vendor" / label / "pypdf"
        archive = ARCHIVES / meta["archive"]
        files = {
            str(p.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in sorted(package.rglob("*"))
            if p.is_file()
        }
        out["versions"][label] = {
            "commit": meta["sha"],
            "role": meta["role"],
            "codeload": f"https://codeload.github.com/py-pdf/pypdf/tar.gz/{meta['sha']}",
            "archive": meta["archive"],
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": sha256(archive),
            "package_files": len(files),
            "files": files,
        }
    (ROOT / "provenance.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote provenance.json: {sum(v['package_files'] for v in out['versions'].values())} files")


if __name__ == "__main__":
    main()
