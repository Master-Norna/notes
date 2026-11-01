#!/usr/bin/env python3
"""Regenerate provenance.json for the tomlkit local-time demo."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVES = Path(r"E:\项目\Note\.yan\tomlkit-local-time")
VERSIONS = {
    "parent": {
        "sha": "763bd661bfed068209c03510ae94493eb2db12b5",
        "role": "first parent of the #613 merge (pre-fix)",
        "archive": "parent-763bd661.tar.gz",
    },
    "merge": {
        "sha": "ce8f8ee982411c4afef5cfb90df7313cc5f7d779",
        "role": "#613 merge",
        "archive": "merge-ce8f8ee9.tar.gz",
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
        "upstream": "python-poetry/tomlkit",
        "license": "MIT",
        "release": {
            "version": "0.15.2",
            "contains": "#613",
            "source": "https://github.com/python-poetry/tomlkit/releases/tag/0.15.2",
        },
        "versions": {},
    }
    for label, meta in VERSIONS.items():
        package = ROOT / "vendor" / label / "tomlkit"
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
            "codeload": f"https://codeload.github.com/python-poetry/tomlkit/tar.gz/{meta['sha']}",
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
