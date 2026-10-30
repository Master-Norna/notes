#!/usr/bin/env python3
"""OPTIONAL ONLINE preparation for Windows x64; normal run.py never downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import urllib.request
import zipfile

VERSION = '0.116.1'
ASSET = f'nu-{VERSION}-x86_64-pc-windows-msvc.zip'
URL = f'https://github.com/nushell/nushell/releases/download/{VERSION}/{ASSET}'
ZIP_SHA256 = '6658c9e61fe42c88326c1caa99e8dc9ad99bec6c0bc353e6ecb7c5d3f79feed7'
EXE_SHA256 = 'e37dff301cf52a49eb82a90e8b4634328379fffa3b244b2172a1c307e03e5d69'
HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=HERE.parents[1] / '.yan' / 'datetime' / 'tools',
                        help='private tool cache (default: repository/.yan/datetime/tools)')
    args = parser.parse_args()
    if platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('This optional preparer is for Windows x64 only; use the matching official Nu 0.116.1 portable release on other systems.')
    folder = args.destination.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ASSET
    if not archive.exists():
        partial = archive.with_suffix('.zip.part')
        with urllib.request.urlopen(URL, timeout=120) as response, partial.open('wb') as out:
            shutil.copyfileobj(response, out)
        if digest(partial) != ZIP_SHA256:
            raise RuntimeError('Downloaded ZIP checksum mismatch; not extracting.')
        partial.replace(archive)
    if digest(archive) != ZIP_SHA256:
        raise RuntimeError('Cached ZIP checksum mismatch; not extracting.')
    exe = folder / f'nu-{VERSION}' / 'nu.exe'
    exe.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        matches = [name for name in zf.namelist() if name.rsplit('/', 1)[-1] == 'nu.exe']
        if len(matches) != 1:
            raise RuntimeError('Expected exactly one nu.exe in official portable archive.')
        # Copy only the executable, never arbitrary archive member paths.
        with zf.open(matches[0]) as src, exe.open('wb') as out:
            shutil.copyfileobj(src, out)
    if digest(exe) != EXE_SHA256:
        raise RuntimeError('Extracted nu.exe checksum mismatch.')
    manifest = dict(version=VERSION, archive_url=URL, archive_sha256=ZIP_SHA256,
                    executable_sha256=EXE_SHA256,
                    official_digest_source=f'https://api.github.com/repos/nushell/nushell/releases/tags/{VERSION}',
                    extraction='nu.exe only; no installer, PATH or system changes')
    (folder / 'runtime.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Ready: {exe}')
    print('Next run.py is offline; use --nu with the path above or its automatic local-cache discovery.')


if __name__ == '__main__':
    main()
