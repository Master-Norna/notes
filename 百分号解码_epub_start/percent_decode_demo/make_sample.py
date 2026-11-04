"""Build the small EPUB used by the decode demo.

The archive only needs entry names, not valid XHTML: the demo reads the
central directory and compares names with the request path.  Entries are
stored uncompressed so the file stays readable and reproducible.
"""

from pathlib import Path
import zipfile

ENTRIES = [
    ("mimetype", b"application/epub+zip"),
    ("META-INF/container.xml", b"<?xml version=\"1.0\"?><container/>"),
    ("OEBPS/chapter.xhtml", b"<html><body>hello</body></html>"),
    ("OEBPS/\u56fe\u7247/\u5c01\u9762.png", b"\x89PNG\r\n\x1a\n"),
    ("OEBPS/cover v2.png", b"\x89PNG\r\n\x1a\n"),
    ("OEBPS/a#b.png", b"\x89PNG\r\n\x1a\n"),
    ("OEBPS/a?b.png", b"\x89PNG\r\n\x1a\n"),
    ("OEBPS/100%.png", b"\x89PNG\r\n\x1a\n"),
]


def main() -> None:
    target = Path(__file__).with_name("sample.epub")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        for name, data in ENTRIES:
            # fixed timestamp and mode: rebuilding the sample must not change a byte
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    print(f"wrote {target} ({target.stat().st_size} bytes, {len(ENTRIES)} entries)")
    for name, _ in ENTRIES:
        print(f"  {name}")


if __name__ == "__main__":
    main()
