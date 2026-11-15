"""Measure the private bytes Pillow adds for one decoded mode, in a fresh process.

Called by run.py --mem.  Pillow allocates the pixel buffer in C, so neither
tracemalloc nor sys.getsizeof() sees it; the process's private byte count
does.  One mode per process keeps the allocator from reusing another mode's
block.
"""

from __future__ import annotations

import json
import sys

import psutil
from PIL import Image


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    mode = sys.argv[1]
    edge = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    size = (edge, edge)
    process = psutil.Process()
    baseline = process.memory_info().private
    image = Image.new(mode, size)
    image.load()
    allocated = process.memory_info().private - baseline
    print(
        json.dumps(
            {
                "mode": mode,
                "size": list(size),
                "allocated": allocated,
                "bytes_per_pixel": allocated / (size[0] * size[1]),
            }
        )
    )
    del image
    return 0


if __name__ == "__main__":
    sys.exit(main())
