"""One explicit online download, then fresh offline installation; stdlib only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import urllib.request
import venv

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Allow online wheel download')
    parser.add_argument('--wheelhouse', type=Path, default=HERE / '.local/wheelhouse')
    parser.add_argument('--venv', type=Path, default=HERE / '.local/venv')
    args = parser.parse_args()
    if (sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 12)
            or sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'}):
        raise RuntimeError('This lock targets CPython 3.12 on Windows x86-64 only.')
    if args.venv.exists():
        raise FileExistsError(f'Refusing to reuse a venv: {args.venv}; choose a fresh path.')
    config = json.loads((HERE / 'wheels.json').read_text(encoding='utf-8'))
    args.wheelhouse.mkdir(parents=True, exist_ok=True)
    verified = []
    for wheel in config['wheels']:
        path = args.wheelhouse / wheel['filename']
        if not path.exists():
            if not args.download:
                raise FileNotFoundError(f'{path}; run once with --download while online.')
            with urllib.request.urlopen(wheel['url'], timeout=120) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != wheel['sha256']:
                raise ValueError(f'Download SHA256 mismatch: {path.name}')
            path.write_bytes(payload)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != wheel['sha256']:
            raise ValueError(f'SHA256 mismatch: {path.name}')
        verified.append({'filename': path.name, 'sha256': digest, 'bytes': path.stat().st_size})
    print(json.dumps({'target': config['target'], 'verified_wheels': verified}, indent=2), flush=True)
    # The parent and pip child are offline during installation. No source builds.
    import socket
    def forbidden(*args, **kwargs):
        raise RuntimeError('Network disabled during offline preparation')
    socket.socket = forbidden
    socket.create_connection = forbidden
    socket.getaddrinfo = forbidden
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(args.venv)
    python = args.venv.resolve() / 'Scripts/python.exe'
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PIP_')}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    subprocess.run([
        str(python), '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
        'install', '--no-index', '--find-links', str(args.wheelhouse.resolve()),
        '--only-binary=:all:', '--require-hashes', '--no-deps',
        '-r', str(HERE / 'requirements.txt'),
    ], env=env, check=True)
    print(f'Fresh offline venv ready: {python}', flush=True)


if __name__ == '__main__':
    main()
