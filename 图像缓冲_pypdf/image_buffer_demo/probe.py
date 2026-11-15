"""Run one vendored pypdf build over a fixed set of images, print JSON.

Called by run.py, not meant to be run by hand.  The import path is the only
thing that decides which build answers: both trees report 7.0.0, because the
merge commit did not bump the version.
"""

from __future__ import annotations

import io
import json
import sys


def main() -> int:
    vendor = sys.argv[1]
    sys.path.insert(0, vendor)
    sys.stdout.reconfigure(encoding="utf-8")

    from PIL import Image
    import pypdf
    from pypdf._configuration import apply_configuration
    from pypdf.errors import LimitReachedError
    from pypdf.generic._image_xobject import (
        _create_image_from_buffer,
        _validate_image_size,
    )

    result = {
        "pypdf_file": str(pypdf.__file__),
        "pypdf_version": pypdf.__version__,
        "pillow_version": Image.__version__,
        "modes": [],
        "validate": [],
        "e2e": [],
    }

    # The number the build multiplies by the pixel count, for every mode Pillow
    # reports.  A 1x1 image keeps the limit check out of the way.
    for mode in Image.MODES:
        pixel_count, required = _validate_image_size(mode=mode, size=(1, 1))
        assert pixel_count == 1
        result["modes"].append(
            {"mode": mode, "name_length": len(mode), "bytes_per_pixel": required}
        )

    # Default image_maximum_buffer_size is 75_000_000 bytes.
    for mode, size in VALIDATE_CASES:
        pixel_count = size[0] * size[1]
        _, bytes_per_pixel = _validate_image_size(mode=mode, size=(1, 1))
        try:
            _validate_image_size(mode=mode, size=size)
            verdict = "accept"
            message = None
        except LimitReachedError as exc:
            verdict = "reject"
            message = str(exc)
        result["validate"].append(
            {
                "mode": mode,
                "size": list(size),
                "pixel_count": pixel_count,
                "verdict": verdict,
                "required": pixel_count * bytes_per_pixel,
                "message": message,
            }
        )

    # A real container image, through the same entry point the reader uses.
    for name, mode, fmt, size, limit in E2E_CASES:
        buffer = io.BytesIO()
        Image.new(mode, size).save(buffer, format=fmt)
        buffer.seek(0)
        file_size = len(buffer.getvalue())
        _, bytes_per_pixel = _validate_image_size(mode=mode, size=(1, 1))
        required = size[0] * size[1] * bytes_per_pixel
        with apply_configuration(image_maximum_buffer_size=limit):
            try:
                image = _create_image_from_buffer(buf=buffer, formats=(fmt,))
                result["e2e"].append(
                    {
                        "name": name,
                        "format": fmt,
                        "size": list(size),
                        "file_bytes": file_size,
                        "limit": limit,
                        "required": required,
                        "verdict": "accept",
                        "decoded_mode": image.mode,
                        "message": None,
                    }
                )
            except LimitReachedError as exc:
                result["e2e"].append(
                    {
                        "name": name,
                        "format": fmt,
                        "size": list(size),
                        "file_bytes": file_size,
                        "limit": limit,
                        "required": required,
                        "verdict": "reject",
                        "decoded_mode": None,
                        "message": str(exc),
                    }
                )

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


VALIDATE_CASES = [
    ("I", (5000, 5000)),
    ("F", (5000, 5000)),
    ("RGB", (5000, 5000)),
    ("LA", (6000, 5000)),
    ("YCbCr", (4000, 4000)),
    ("I;16", (5000, 4000)),
]

E2E_CASES = [
    ("16-bit PNG", "I;16", "PNG", (1000, 1000), 3_000_000),
    ("32-bit TIFF / I", "I", "TIFF", (1000, 1000), 3_000_000),
    ("32-bit TIFF / F", "F", "TIFF", (1000, 1000), 3_000_000),
]


if __name__ == "__main__":
    sys.exit(main())
