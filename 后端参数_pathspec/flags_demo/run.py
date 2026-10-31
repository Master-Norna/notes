"""Real three-revision Pathspec #151 experiment. No downloads, no silent skips."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
COMMITS = {
    'before': '88a9b711e0120a1eb16d5627fb68d15e3187c6ad',
    'draft': '21e4342c73fd02be6458b9b2353e9f63fa1824a0',
    'after': '157bccfbc24777aed9330223a546487b0f3d7f1b',
}
PINNED = {'google-re2': '1.1.20251105', 'hyperscan': '0.9.1'}
REQUESTS = ('simple', 're2', 'hyperscan', 'best', None)


def require(condition, message):
    # Do not turn off checks under python -O.
    if not condition:
        raise AssertionError(message)


def network_guard():
    """Python-level guard, not an OS firewall for arbitrary native code."""
    original = socket.socket
    blocked = []

    def deny(*args, **kwargs):
        raise RuntimeError('network disabled by flags_demo')

    def audit(event, args):
        if (event.startswith('socket.') and event != 'socket.gethostname') or event in {'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
            raise RuntimeError(f'network/process escape disabled by flags_demo: {event}')

    sys.addaudithook(audit)
    socket.socket = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny
    for name, call in (
        ('socket.socket', lambda: socket.socket()),
        ('socket.create_connection', lambda: socket.create_connection(('127.0.0.1', 9))),
        ('socket.getaddrinfo', lambda: socket.getaddrinfo('example.invalid', 80)),
        ('original socket via audit', lambda: original()),
    ):
        try:
            call()
        except RuntimeError:
            blocked.append(name)
        else:
            raise AssertionError(f'Network guard failed: {name}')
    return {'scope': 'Python socket patch + socket audit; workers also deny process spawn',
            'selftests_blocked': blocked, 'not_os_firewall': True}


def verify_sources(version):
    manifest = json.loads((HERE / 'provenance.json').read_text(encoding='utf-8'))
    info = manifest['versions'][version]
    require(info['commit'] == COMMITS[version], 'Unexpected provenance commit')
    root = HERE / 'vendor' / version
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual == set(info['files']), f'{version}: unexpected/missing source files')
    for rel, digest in info['files'].items():
        require(hashlib.sha256((root / rel).read_bytes()).hexdigest() == digest,
                f'{version}: SHA256 mismatch: {rel}')
    return root, len(actual)


def native_environment():
    import re2
    import hyperscan
    versions = {name: md.version(name) for name in PINNED}
    require(versions == PINNED, f'Native dependency version mismatch: {versions!r}')
    binaries = []
    for name in PINNED:
        dist = md.distribution(name)
        for rel in dist.files or []:
            if str(rel).lower().endswith(('.pyd', '.so', '.dll')):
                path = dist.locate_file(rel).resolve()
                binaries.append({'distribution': name, 'file': str(path),
                                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    for name in PINNED:
        require(any(b['distribution'] == name for b in binaries), f'No native binary for {name}')
    return {'python': sys.version, 'executable': sys.executable,
            'implementation': platform.python_implementation(), 'platform': platform.platform(),
            'machine': platform.machine(), 'processor': platform.processor(),
            'native_versions': versions, 'native_binaries': binaries,
            'module_files': {'re2': re2.__file__, 'hyperscan': hyperscan.__file__}}


def scenarios():
    import re
    # expected_before_native is deliberately literal, not a substitute matcher.
    cases = [
        ('plain', '^secret$', 0, ['secret', 'SECRET'], [True, False], False, False),
        ('IGNORECASE', '^secret$', re.I, ['SECRET', 'public'], [False, False], True, False),
        ('MULTILINE', '^secret$', re.M, ['x\nsecret\ny', 'xsecret'], [False, False], True, False),
        ('DOTALL', '^a.b$', re.S, ['a\nb', 'aXbY'], [False, False], True, False),
        ('IMS', '^secret.*end$', re.I | re.M | re.S,
         ['x\nSECRET\nEND\ny', 'xsecret'], [False, False], True, False),
        ('VERBOSE', '^S E C R E T$', re.X, ['SECRET', 'public'], [False, False], True, True),
        ('ASCII-IGNORECASE', '^[a-z]+$', re.A | re.I,
         ['SECRET', '123'], [False, False], True, True),
        ('inline-I', '(?i)^secret$', 0, ['SECRET', 'public'], [True, False], False, False),
        ('inline-M', '(?m)^secret$', 0, ['x\nsecret\ny', 'xsecret'], [True, False], False, False),
        ('inline-S', '(?s)^a.b$', 0, ['a\nb', 'aXbY'], [True, False], False, False),
        ('inline-IMS', '(?ims)^secret.*end$', 0,
         ['x\nSECRET\nEND\ny', 'xsecret'], [True, False], False, False),
        ('inline-I-external-M', '(?i)^secret$', re.M,
         ['x\nSECRET\ny', 'xsecret'], [False, False], True, False),
        ('ASCII', '^\\w+$', re.A, ['secret_9', '!'], [True, False], True, False),
    ]
    result = []
    for name, expression, flags, samples, before, external, unsupported in cases:
        result.append(dict(name=name, kind='regex', expression=expression, flags=int(flags),
                           samples=samples, correct=[True, False], before=before,
                           external=external, unsupported=unsupported))
    for name, line, samples in (
        ('directory-required-I', 'logs/', ['LOGS/', 'LOGS/child', 'public']),
        ('directory-optional-I', 'logs', ['LOGS', 'LOGS/child', 'public']),
    ):
        result.append(dict(name=name, kind='directory', line=line, flags=int(re.I),
                           samples=samples, correct=[True, True, False], before=[False, False, False],
                           external=True, unsupported=False))
    result.append(dict(name='mixed-whole-spec-VERBOSE', kind='mixed', flags=int(re.X),
                       samples=['plain', 'SECRET', 'public'], correct=[True, True, False],
                       before=[True, False, False], external=True, unsupported=True))
    return result


def bytes_scenarios():
    import re
    return [
        dict(name=name, kind='bytes', expression=expression, flags=int(flags),
             samples=samples, correct=[True, False], before=before,
             external=external, unsupported=False)
        for name, expression, flags, samples, before, external in (
            ('bytes-plain', b'^secret$', 0, ['secret', 'SECRET'], [True, False], False),
            ('bytes-I', b'^secret$', re.I, ['SECRET', 'public'], [False, False], True),
            ('bytes-IMS', b'^secret.*end$', re.I | re.M | re.S,
             ['x\nSECRET\nEND\ny', 'xsecret'], [False, False], True),
            ('bytes-inline-I', b'(?i)^secret$', 0, ['SECRET', 'public'], [True, False], False),
        )
    ]


def make_patterns(case):
    import re
    from pathspec import RegexPattern
    from pathspec.patterns.gitignore.spec import GitIgnoreSpecPattern
    if case['kind'] == 'directory':
        pattern = GitIgnoreSpecPattern(case['line'])
        return [GitIgnoreSpecPattern(re.compile(pattern.regex.pattern, case['flags']), pattern.include)]
    if case['kind'] == 'mixed':
        return [RegexPattern(re.compile('^plain$'), include=True),
                RegexPattern(re.compile('^S E C R E T$', re.X), include=True)]
    return [RegexPattern(re.compile(case['expression'], case['flags']), include=True)]


def expected_policy(version, case, requested):
    automatic = requested in ('best', None)
    blocked = (version == 'draft' and case['external']) or (version == 'after' and case['unsupported'])
    if requested == 'simple' or (automatic and blocked):
        return 'simple', case['correct']
    if blocked:
        return 'ValueError', None
    selected = 're2' if automatic else requested
    return selected, case['before'] if version == 'before' else case['correct']


def backend_identity(spec, expected, suffix):
    import re2
    import hyperscan
    cls = type(spec._backend)
    prefix = {'simple': 'Simple', 're2': 'Re2', 'hyperscan': 'Hyperscan'}[expected]
    require(cls.__name__ == f'{prefix}{suffix}Backend', f'Unexpected backend class: {cls!r}')
    require(cls.__module__ == f'pathspec._backends.{expected}.' + ('pathspec' if suffix == 'Ps' else 'gitignore'),
            f'Unexpected backend module: {cls.__module__}')
    result = {'class': cls.__name__, 'module': cls.__module__}
    if expected == 're2':
        obj = spec._backend._set
        require(isinstance(obj, re2.Set), f'Not a real re2.Set: {obj!r}')
        result['native_object'] = f'{type(obj).__module__}.{type(obj).__name__}'
    elif expected == 'hyperscan':
        obj = spec._backend._db
        require(isinstance(obj, hyperscan.Database), f'Not a real hyperscan.Database: {obj!r}')
        result['native_object'] = f'{type(obj).__module__}.{type(obj).__name__}'
    return result


def run_worker(version):
    guard = network_guard()
    root, count = verify_sources(version)
    env = native_environment()  # Import/version/load failures must fail, not skip.
    sys.path.insert(0, str(root))
    import pathspec
    from pathspec import PathSpec, GitIgnoreSpec
    from pathspec._backends import agg
    require(Path(pathspec.__file__).resolve() == root / 'pathspec/__init__.py', 'Wrong pathspec imported')
    require(agg._BEST_BACKEND == 're2', 'Both native libraries are required; best must be re2')
    rows = []
    for case in scenarios() + bytes_scenarios():
        for spec_class, suffix in ((PathSpec, 'Ps'), (GitIgnoreSpec, 'Gi')):
            for requested in REQUESTS:
                selected, expected_matches = expected_policy(version, case, requested)
                row = {'case': case['name'], 'domain': 'bytes-pattern' if case['kind'] == 'bytes' else 'str-pattern',
                       'spec': spec_class.__name__,
                       'requested': requested if requested is not None else 'default',
                       'pattern_expressions': [], 'samples': case['samples'],
                       'expected_backend': selected}
                patterns = make_patterns(case)
                row['pattern_expressions'] = [
                    {'expression': p.regex.pattern.decode('ascii') if isinstance(p.regex.pattern, bytes) else p.regex.pattern,
                     'expression_type': type(p.regex.pattern).__name__,
                     'compile_flags': p.regex.flags, 'include': p.include}
                    for p in patterns]
                try:
                    spec = spec_class(patterns, backend=requested)
                except Exception as exc:
                    row.update(error=type(exc).__name__, message=str(exc))
                    row['ok'] = (selected == 'ValueError' and type(exc) is ValueError
                                 and "backend='simple'" in str(exc))
                else:
                    try:
                        require(selected != 'ValueError', 'Explicit native backend should have rejected flags')
                        row['backend'] = backend_identity(spec, selected, suffix)
                        matches = []
                        for index, sample in enumerate(case['samples']):
                            if case['kind'] == 'bytes' and selected == 'simple':
                                # Public API takes str paths; Python bytes regex cannot search str.
                                # This is an asserted boundary, not a skipped backend.
                                errors = []
                                for method in (spec.check_file, spec.match_file):
                                    try:
                                        method(sample)
                                    except TypeError as exc:
                                        errors.append({'method': method.__name__, 'error': 'TypeError', 'message': str(exc)})
                                    else:
                                        raise AssertionError('Expected TypeError for simple bytes regex / str path')
                                matches.append({'input': sample, 'expected_public_boundary': errors})
                                continue
                            result = spec.check_file(sample)
                            matched = spec.match_file(sample)
                            expect = expected_matches[index]
                            expected_index = (index if case['kind'] == 'mixed' else 0) if expect else None
                            require(matched is expect, f'{sample!r}: expected {expect}, got {matched}')
                            require((result.include, result.index) == ((True, expected_index) if expect else (None, None)),
                                    f'{sample!r}: unexpected include/index: {result!r}')
                            matches.append({'input': sample, 'matched': matched,
                                            'include': result.include, 'index': result.index})
                        row['results'] = matches
                        row['ok'] = True
                    except Exception as exc:
                        row.update(ok=False, assertion=type(exc).__name__, message=str(exc))
                rows.append(row)
    return {'version': version, 'commit': COMMITS[version], 'environment': env,
            'pathspec_file': pathspec.__file__, 'source_files_verified': count,
            'network_guard': guard, 'best_available': agg._BEST_BACKEND,
            'rows': rows, 'ok': all(row['ok'] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test', action='store_true', help='Run full asserted matrix (also the default)')
    parser.add_argument('--offline', action='store_true', help='Explicit spelling; run is always offline')
    parser.add_argument('--json', type=Path, help='Write complete evidence JSON')
    parser.add_argument('--worker', choices=COMMITS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            result = run_worker(args.worker)
        except Exception as exc:
            result = {'version': args.worker, 'ok': False, 'fatal': type(exc).__name__,
                      'message': str(exc), 'traceback': traceback.format_exc()}
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result['ok'] else 1
    result = {'experiment': 'Pathspec #151 real native three-revision flags/selection',
              'schema': 1, 'versions': {}, 'ok': True}
    # Parent only launches this script, once per revision; workers deny spawning.
    def deny(*args, **kwargs):
        raise RuntimeError('network disabled by flags_demo parent')
    socket.socket = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny
    for version in COMMITS:
        proc = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--worker', version],
                              capture_output=True, text=True, encoding='utf-8')
        try:
            data = json.loads(proc.stdout)
        except (ValueError, TypeError):
            data = {'ok': False, 'fatal': 'WorkerOutputError', 'stdout': proc.stdout}
        data['worker_returncode'] = proc.returncode
        if proc.stderr:
            data['worker_stderr'] = proc.stderr
        result['versions'][version] = data
        result['ok'] = result['ok'] and proc.returncode == 0 and data.get('ok', False)
    rows = [row for data in result['versions'].values() for row in data.get('rows', [])]
    def summarize(selected_rows, scenario_count):
        return {
            'scenario_definitions': scenario_count, 'revision_workers': len(COMMITS),
            'construction_rows': len(selected_rows), 'passed_rows': sum(r['ok'] for r in selected_rows),
            'expected_rejections': sum(r.get('error') == 'ValueError' and r['ok'] for r in selected_rows),
            'constructed_specs': sum('backend' in r for r in selected_rows),
            'sample_checks': sum('matched' in item for r in selected_rows for item in r.get('results', [])),
            'public_typeerror_sample_pairs': sum('expected_public_boundary' in item
                for r in selected_rows for item in r.get('results', [])),
            'selected_classes': dict(Counter(r['backend']['class'] for r in selected_rows if 'backend' in r)),
        }
    result['summary'] = summarize([r for r in rows if r['domain'] == 'str-pattern'], len(scenarios()))
    result['bytes_summary'] = summarize([r for r in rows if r['domain'] == 'bytes-pattern'], len(bytes_scenarios()))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': result['ok'], 'summary': result['summary'], 'bytes_summary': result['bytes_summary']}, indent=2))
    if not result['ok']:
        for name, data in result['versions'].items():
            if 'fatal' in data:
                print(f'{name}: {data["fatal"]}: {data.get("message", data)}', file=sys.stderr)
            for row in data.get('rows', []):
                if not row['ok']:
                    print(f'{name}: {row}', file=sys.stderr)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
