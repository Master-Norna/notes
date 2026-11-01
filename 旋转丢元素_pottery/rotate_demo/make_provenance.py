#!/usr/bin/env python3
"""Regenerate provenance.json for the pottery rotate demo."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVES = Path(r"E:\项目\Note\.yan\选题-20261031\pottery\snapshots")
VERSIONS = {
    "parent": {
        "sha": "f6e59b0127f3375278fd473450fff1152548f7c7",
        "role": "first parent of the #857 merge (pre-fix)",
        "archive": "parent-f6e59b0127f3375278fd473450fff1152548f7c7.tar.gz",
    },
    "merge": {
        "sha": "4e98b44cb888f08660c5f6f943fac4f62c95b3e5",
        "role": "#857 merge",
        "archive": "merge-4e98b44cb888f08660c5f6f943fac4f62c95b3e5.tar.gz",
    },
}
SITE = {
    "fakeredis": {"version": "2.38.0", "license": "BSD-3-Clause"},
    "redis": {"version": "8.1.0", "license": "MIT"},
    "sortedcontainers": {"version": "2.4.0", "license": "Apache-2.0"},
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    out = {
        "upstream": "brainix/pottery",
        "license": "Apache-2.0",
        "backend": "fakeredis in-process emulator",
        "versions": {},
        "site_packages": SITE,
    }
    for label, meta in VERSIONS.items():
        package = ROOT / "vendor" / label / "pottery"
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
            "codeload": f"https://codeload.github.com/brainix/pottery/tar.gz/{meta['sha']}",
            "archive": meta["archive"],
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": sha256(archive),
            "package_files": len(files),
            "files": files,
        }
    site = ROOT / "vendor" / "site"
    out["site_files"] = {
        str(p.relative_to(ROOT)).replace("\\", "/"): {
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
        }
        for p in sorted(site.rglob("*"))
        if p.is_file()
    }
    (ROOT / "provenance.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote provenance.json: {sum(v['package_files'] for v in out['versions'].values())} "
        f"pottery files, {len(out['site_files'])} vendored dependency files"
    )


if __name__ == "__main__":
    main()
