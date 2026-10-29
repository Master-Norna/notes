"""Run the same real-TCP probe against both pinned upstream source trees."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
REVISIONS = {
    "before": ("633965bad02a857574b3dbad03d1ef9f35e9caa4",
               "409e953a965b44426b75e52dc37a9fc040360e7f754b8435f50b420103a39008"),
    "after": ("6219807568bd7c32f2c08f923c7d93f95c836127",
              "8502570afae1bffed2918135b9057ec59255033832ed97ce3846120efd846d05"),
}


def find_source(directory):
    candidates = list(directory.glob("src/anyio/_backends/_asyncio.py"))
    candidates += list(directory.glob("*/src/anyio/_backends/_asyncio.py"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one AnyIO source tree in {directory}")
    return candidates[0].parents[2]  # .../src


def source_for(label, source_root, offline):
    sha, expected_hash = REVISIONS[label]
    if source_root is not None:
        src = find_source(source_root / label)
    else:
        cache = HERE / ".sources"
        directory = cache / sha
        if not directory.exists():
            cache.mkdir(exist_ok=True)
            archive = cache / f"{sha}.zip"
            if not archive.exists():
                if offline:
                    raise RuntimeError(f"Offline cache miss: {archive}")
                url = f"https://codeload.github.com/agronholm/anyio/zip/{sha}"
                print(f"Downloading {url}", flush=True)
                temporary = archive.with_suffix(".download")
                try:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        temporary.write_bytes(response.read())
                    temporary.replace(archive)
                finally:
                    temporary.unlink(missing_ok=True)
            with zipfile.ZipFile(archive) as zipped:
                # Only trusted GitHub archives are expected; reject path escapes.
                for name in zipped.namelist():
                    if not (directory / name).resolve().is_relative_to(directory.resolve()):
                        raise RuntimeError(f"Unsafe zip path: {name}")
                zipped.extractall(directory)
        src = find_source(directory)
    backend = src / "anyio" / "_backends" / "_asyncio.py"
    actual_hash = hashlib.sha256(backend.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise RuntimeError(f"Unexpected {label} backend SHA256: {backend}: {actual_hash}")
    return src.resolve()


def child(command, env):
    completed = subprocess.run(
        [sys.executable, *command], cwd=HERE, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=90,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"Child exited with {completed.returncode}: {' '.join(command)}")
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path,
                        help="Existing root with before/*/src and after/*/src; never download")
    parser.add_argument("--offline", action="store_true", help="Forbid all downloads")
    parser.add_argument("--loop", choices=("default", "selector"), default="default")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--test", action="store_true", help="Also run the 3 unittest cases per source")
    parser.add_argument("--output", type=Path, help="Optionally write the complete results as JSON")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if sys.version_info < (3, 12):
        parser.error("This demo requires Python 3.12+")
    sources = {label: source_for(label, args.source_root, args.offline) for label in REVISIONS}
    results = []
    for label, src in sources.items():
        env = dict(os.environ, PYTHONPATH=str(src), PYTHONUTF8="1",
                   PYTHONDONTWRITEBYTECODE="1", BACKPRESSURE_REVISION=label,
                   BACKPRESSURE_LOOP=args.loop)
        if args.test:
            completed = child(["-m", "unittest", "-v", "test_probe"], env)
            print(f"\n[{label}] unittest", flush=True)
            print(completed.stdout + completed.stderr, end="", flush=True)
        for index in range(1, args.repeat + 1):
            completed = child(["probe.py", "--revision", label, "--loop", args.loop], env)
            result = json.loads(completed.stdout)
            if Path(result["anyio_file"]).resolve() != src / "anyio" / "__init__.py":
                raise RuntimeError(f"Wrong import: {result['anyio_file']}")
            result.update(sha=REVISIONS[label][0], repeat=index)
            results.append(result)
            bp = result["backpressure"]
            print(
                f"{label:6} #{index} {result['loop']} "
                f"already_reading={result['already_cancelled']['is_reading']} "
                f"blocked_reading={result['blocked_receive']['is_reading']} "
                f"queue={bp['queue_bytes']} B/{bp['window_seconds']:.1f}s "
                f"sender_done={bp['sender_done_at_snapshot']} "
                f"received={bp['received_bytes']} B intact={bp['content_equal']} "
                f"reused={bp['connection_reused_both_directions']}", flush=True,
            )
    print("PASS: expected before/after states, cancellation, full payload and bidirectional reuse")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Full results: {args.output}")


if __name__ == "__main__":
    main()
