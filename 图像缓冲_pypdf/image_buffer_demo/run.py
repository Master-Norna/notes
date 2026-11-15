"""One question, two pypdf builds: how many bytes does a pixel take?

The parent build (`5a936f9`) estimates the buffer Pillow will allocate as
`len(mode)` bytes per pixel.  The merge commit (`1cd993b`, PR #4374) asks
Pillow how many bands the mode has and keeps a nine-key table only for
single-band modes.

    python -B run.py --test      # deterministic checks, allocates nothing big
    python -B run.py --mem       # private-byte measurement, needs psutil
    python -B run.py --emit DIR  # also write the two probe payloads

Both vendored trees report version 7.0.0: the merge commit did not bump it, so
the import path is the only thing that decides which build answers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
LIMIT = 75_000_000

VENDORS = {
    "parent": HERE / "vendor" / "pypdf-parent",
    "merged": HERE / "vendor" / "pypdf-merged",
}

# ImagingNewPrologueSubtype() in Pillow's src/libImaging/Storage.c, read at both
# 8.0.0 and 12.3.0: every mode with two or more bands takes a four-byte pixel,
# the 16-bit family two, and "1"/"L"/"P" one.  Image.MODES reports exactly
# these twenty modes.
PILLOW_BYTES = {
    "1": 1,
    "L": 1,
    "P": 1,
    "I;16": 2,
    "I;16B": 2,
    "I;16L": 2,
    "I;16N": 2,
    "I": 4,
    "F": 4,
    "LA": 4,
    "La": 4,
    "PA": 4,
    "RGB": 4,
    "RGBA": 4,
    "RGBa": 4,
    "RGBX": 4,
    "CMYK": 4,
    "YCbCr": 4,
    "LAB": 4,
    "HSV": 4,
}

# (mode, width, height) -> (parent verdict, merged verdict)
EXPECTED_VALIDATE = {
    ("I", 5000, 5000): ("accept", "reject"),
    ("F", 5000, 5000): ("accept", "reject"),
    ("RGB", 5000, 5000): ("accept", "reject"),
    ("LA", 6000, 5000): ("accept", "reject"),
    ("YCbCr", 4000, 4000): ("reject", "accept"),
    ("I;16", 5000, 4000): ("reject", "accept"),
}

# case name -> (parent verdict, merged verdict)
EXPECTED_E2E = {
    "16-bit PNG": ("reject", "accept"),
    "32-bit TIFF / I": ("accept", "reject"),
    "32-bit TIFF / F": ("accept", "reject"),
}

MEM_MODES = ["1", "L", "P", "I;16", "I", "F", "LA", "PA", "RGB", "YCbCr", "LAB", "HSV"]


def run_probe(vendor: Path) -> dict:
    completed = subprocess.run(
        [PYTHON, "-I", "-B", str(HERE / "probe.py"), str(vendor)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


def run_mem(mode: str, edge: int = 8000) -> dict:
    completed = subprocess.run(
        [PYTHON, "-I", "-B", str(HERE / "measure_mem.py"), mode, str(edge)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


def show_modes(builds: dict, errors: list[str]) -> None:
    print("== bytes per pixel, by mode ==")
    print(f"{'mode':<7}{'len(mode)':>10}{'parent':>8}{'merged':>8}{'Pillow':>8}")
    low = high = wrong = 0
    for entry in builds["merged"]["modes"]:
        mode = entry["mode"]
        parent = next(m for m in builds["parent"]["modes"] if m["mode"] == mode)
        expected = PILLOW_BYTES[mode]
        print(
            f"{mode:<7}{entry['name_length']:>10}{parent['bytes_per_pixel']:>8}"
            f"{entry['bytes_per_pixel']:>8}{expected:>8}"
        )
        if parent["bytes_per_pixel"] < expected:
            low += 1
        elif parent["bytes_per_pixel"] > expected:
            high += 1
        if entry["bytes_per_pixel"] != expected:
            errors.append(f"merged counts {mode} as {entry['bytes_per_pixel']}, Pillow allocates {expected}")
    wrong = low + high
    print()
    print(f"parent differs from Pillow on {wrong} of {len(PILLOW_BYTES)} modes: {low} low, {high} high")
    print("merged differs from Pillow on 0 modes" if not errors else "merged table has mismatches")


def show_validate(builds: dict, errors: list[str]) -> None:
    print()
    print(f"== _validate_image_size, default limit {LIMIT:,} ==")
    print(f"{'mode':<7}{'pixels':>12}{'parent':>24}{'merged':>24}")
    for parent, merged in zip(builds["parent"]["validate"], builds["merged"]["validate"], strict=True):
        assert parent["mode"] == merged["mode"]
        key = (parent["mode"], parent["size"][0], parent["size"][1])
        want = EXPECTED_VALIDATE[key]
        got = (parent["verdict"], merged["verdict"])
        print(
            f"{parent['mode']:<7}{parent['pixel_count']:>12,}"
            f"{parent['verdict']:>8} {parent['required']:>14,}"
            f"{merged['verdict']:>8} {merged['required']:>14,}"
        )
        if got != want:
            errors.append(f"{key}: expected {want}, got {got}")


def show_e2e(builds: dict, errors: list[str]) -> None:
    print()
    print("== _create_image_from_buffer on a real file ==")
    print(f"{'case':<18}{'file bytes':>12}{'limit':>12}{'parent':>22}{'merged':>22}")
    for parent, merged in zip(builds["parent"]["e2e"], builds["merged"]["e2e"], strict=True):
        assert parent["name"] == merged["name"]
        want = EXPECTED_E2E[parent["name"]]
        got = (parent["verdict"], merged["verdict"])
        print(
            f"{parent['name']:<18}{parent['file_bytes']:>12,}{parent['limit']:>12,}"
            f"{parent['verdict']:>8} {parent['required']:>12,}"
            f"{merged['verdict']:>8} {merged['required']:>12,}"
        )
        if got != want:
            errors.append(f"{parent['name']}: expected {want}, got {got}")


def show_mem(errors: list[str]) -> None:
    print()
    print("== private bytes Pillow adds for one 8000x8000 image ==")
    print(f"{'mode':<7}{'allocated':>14}{'bytes/px':>10}{'Pillow table':>14}")
    for mode in MEM_MODES:
        row = run_mem(mode)
        expected = PILLOW_BYTES[mode]
        print(f"{mode:<7}{row['allocated']:>14,}{row['bytes_per_pixel']:>10.3f}{expected:>14}")
        if round(row["bytes_per_pixel"]) != expected:
            errors.append(f"{mode}: measured {row['bytes_per_pixel']:.3f} bytes/px, table says {expected}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="run the deterministic checks")
    parser.add_argument("--mem", action="store_true", help="measure private bytes with psutil")
    parser.add_argument("--emit", type=Path, help="directory for the raw probe payloads")
    args = parser.parse_args()
    if not (args.test or args.mem or args.emit):
        parser.print_help()
        return 2

    errors: list[str] = []
    builds = {name: run_probe(vendor) for name, vendor in VENDORS.items()}

    for name, build in builds.items():
        expected_root = (VENDORS[name] / "pypdf").resolve()
        if not Path(build["pypdf_file"]).resolve().is_relative_to(expected_root):
            errors.append(f"{name}: imported {build['pypdf_file']}, not the vendored tree")
        print(f"{name:<7} {build['pypdf_version']}  {build['pypdf_file']}")
    print(f"Pillow  {builds['merged']['pillow_version']}")
    print()

    show_modes(builds, errors)
    show_validate(builds, errors)
    show_e2e(builds, errors)
    if args.mem:
        show_mem(errors)

    if args.emit:
        args.emit.mkdir(parents=True, exist_ok=True)
        for name, build in builds.items():
            (args.emit / f"{name}.json").write_text(
                json.dumps(build, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    print()
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
