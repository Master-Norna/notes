#!/usr/bin/env python3
"""Offline real-Nu comparison; stdlib Python is a driver and independent oracle.

No Python implementation of before/draft/after is used as the measured result.
All three result records come from runner.nu and unchanged upstream snapshots.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
VERSIONS = ('before', 'draft', 'after')
UNITS = ('year', 'month', 'day', 'hour', 'minute', 'second', 'millisecond', 'microsecond', 'nanosecond')
NS = 1_000_000_000
DAY = 86400 * NS
EPOCH = date(1970, 1, 1)
ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})')


@dataclass(frozen=True)
class Instant:
    day: date
    time: int  # nanoseconds after midnight, UTC

    @property
    def ns(self):
        return (self.day - EPOCH).days * DAY + self.time

    def record(self):
        rest = self.time
        values = [self.day.year, self.day.month, self.day.day]
        for scale in (3600 * NS, 60 * NS, NS, 1_000_000, 1_000, 1):
            value, rest = divmod(rest, scale)
            values.append(value)
        return dict(zip(UNITS, values))


def parse_iso(text):
    """Strict RFC3339 subset, retaining all nine subsecond digits, not floats."""
    match = ISO.fullmatch(text)
    if not match:
        raise ValueError(text)
    y, m, d, h, minute, second = map(int, match.groups()[:6])
    if h > 23 or minute > 59 or second > 59:
        raise ValueError(text)
    fractional = int((match[7] or '').ljust(9, '0'))
    offset = 0
    if match[8] != 'Z':
        zone = match[8]
        offset = (int(zone[1:3]) * 60 + int(zone[4:6])) * 60 * NS
        if zone[0] == '-':
            offset = -offset
    total = (date(y, m, d) - EPOCH).days * DAY + ((h * 3600 + minute * 60 + second) * NS) + fractional - offset
    days, tod = divmod(total, DAY)
    return Instant(EPOCH + timedelta(days=days), tod)


def month_anchor(start, months):
    """One direct calendar-month shift, NOT repeated one-month additions."""
    index = start.day.year * 12 + start.day.month - 1 + months
    year, month0 = divmod(index, 12)
    target = date(year, month0 + 1, min(start.day.day, calendar.monthrange(year, month0 + 1)[1]))
    return Instant(target, start.time)


def semantic_oracle(earlier, later):
    """Final contract, independently expressed with Python's Gregorian calendar.

    Raw day/time selects whole months. A clamped anchor is used only for the
    remainder, measured as an exact integer-nanosecond distance.
    """
    if earlier.ns > later.ns:
        raise ValueError('reversed interval')
    months = (later.day.year - earlier.day.year) * 12 + later.day.month - earlier.day.month
    if (later.day.day, later.time) < (earlier.day.day, earlier.time):
        months -= 1
    anchor = month_anchor(earlier, months)
    rest = later.ns - anchor.ns
    assert rest >= 0
    values = list(divmod(months, 12))
    for scale in (DAY, 3600 * NS, 60 * NS, NS, 1_000_000, 1_000, 1):
        value, rest = divmod(rest, scale)
        values.append(value)
    return dict(zip(UNITS, values))


def reconstruct(earlier, result):
    anchor = month_anchor(earlier, result['year'] * 12 + result['month'])
    rest = sum(result[key] * scale for key, scale in zip(UNITS[2:], (DAY, 3600 * NS, 60 * NS, NS, 1_000_000, 1_000, 1)))
    return anchor.ns + rest


def record(*values):
    return dict(zip(UNITS, (*values, *([0] * (len(UNITS) - len(values))))))


def examples():
    """Hand-specified expectations, separate from the semantic oracle."""
    specs = [
        ('jan15-mar1', '2023-01-15', '2023-03-01', record(0, 1, 14)),
        ('jan31-mar1', '2023-01-31', '2023-03-01', record(0, 1, 1)),
        ('jan31-feb28', '2023-01-31', '2023-02-28', record(0, 0, 28)),
        ('mar31-apr30', '2023-03-31', '2023-04-30', record(0, 0, 30)),
        ('leap-anniversary', '2024-02-29', '2025-02-28', record(0, 11, 30)),
        ('later-clock', '2023-01-31T12:00:00Z', '2023-02-28T13:00:00Z', record(0, 0, 28, 1)),
        ('earlier-clock', '2023-01-31T12:00:00Z', '2023-02-28T06:00:00Z', record(0, 0, 27, 18)),
        ('cross-year', '2022-12-31', '2023-03-01', record(0, 2, 1)),
        ('jan29-mar1', '2023-01-29', '2023-03-01', record(0, 1, 1)),
        ('jan30-mar1', '2023-01-30', '2023-03-01', record(0, 1, 1)),
        ('leap-jan31-mar1', '2024-01-31', '2024-03-01', record(0, 1, 1)),
        ('may31-jul1', '2023-05-31', '2023-07-01', record(0, 1, 1)),
        ('same-dom-one-month-clock-borrow', '2023-01-15T12:00:00Z', '2023-02-15T06:00:00Z', record(0, 0, 30, 18)),
        ('same-dom-clock-borrow', '2023-01-15T12:00:00Z', '2023-03-15T06:00:00Z', record(0, 1, 27, 18)),
        ('same-dom-clamped-anchor', '2023-01-31T12:00:00Z', '2023-03-31T06:00:00Z', record(0, 1, 30, 18)),
        ('nanosecond-borrow-chain', '2023-01-31T23:59:59.999999999Z', '2023-03-01', record(0, 1, 0, 0, 0, 0, 0, 0, 1)),
        ('equal', '2023-01-31', '2023-01-31', record(0)),
        ('timezone-same-instant', '2023-01-31T23:00:00-01:00', '2023-02-01T12:00:00+12:00', record(0)),
        ('timezone-calendar-boundary', '2023-02-01T01:00:00+02:00', '2023-03-01T00:00:00Z', record(0, 1, 0, 1)),
        ('upstream-example', '2019-05-10T09:59:12.967486456-07:00', '2023-05-07T04:08:45.582926123+12:00', record(3, 11, 25, 23, 9, 32, 615, 439, 667)),
    ]
    for year in (1900, 2000, 2100, 2400):
        leap_days = calendar.monthrange(year, 2)[1]
        specs.append((f'century-{year}-feb28', f'{year}-02-28', f'{year}-03-01', record(0, 0, leap_days - 27)))
        specs.append((f'century-{year}-jan31', f'{year}-01-31', f'{year}-03-01', record(0, 1, 1)))
        if leap_days == 29:
            specs.append((f'century-{year}-feb29', f'{year}-02-29', f'{year}-03-01', record(0, 0, 1)))
    cases, expected = [], {}
    for name, earlier, later, wanted in specs:
        normalize = lambda text: text if 'T' in text else text + 'T00:00:00Z'
        cases.append(dict(id=name, earlier=normalize(earlier), later=normalize(later)))
        expected[name] = wanted
    cases.append(dict(id='reversed', earlier='2023-03-01T00:00:00Z', later='2023-01-31T00:00:00Z'))
    return cases, expected


def scan_cases():
    """Bounded, deterministic grid; no unbounded/random stress or benchmark."""
    result = []
    for year in (1999, 2000, 2023, 2024):
        for month in range(1, 13):
            for dom in (1, 15, 28, 29, 30, 31):
                if dom > calendar.monthrange(year, month)[1]:
                    continue
                start = date(year, month, dom)
                for delta in (0, 1, 27, 28, 29, 30, 31, 59, 366):
                    end = start + timedelta(days=delta)
                    for first, last in (('00:00:00', '00:00:00'), ('12:00:00', '06:00:00'), ('23:59:59.999999999', '00:00:00')):
                        if delta == 0 and first > last:
                            continue
                        result.append(dict(id=f'grid-{len(result):05}', earlier=f'{start}T{first}Z', later=f'{end}T{last}Z'))
    return result


def verify_sources():
    provenance = json.loads((HERE / 'provenance.json').read_text(encoding='utf-8'))
    for source in provenance['files']:
        data = (HERE / source['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            raise RuntimeError(f"Snapshot hash mismatch: {source['path']}")
    return len(provenance['files'])


def find_nu(argument):
    if argument:
        candidate = Path(argument).resolve()
    elif shutil.which('nu'):
        candidate = Path(shutil.which('nu')).resolve()
    else:
        candidate = HERE.parents[1] / '.yan' / 'datetime' / 'tools' / 'nu-0.116.1' / 'nu.exe'
    if not candidate.is_file():
        raise RuntimeError('Nu not found. Install the official portable Nu (README), or pass --nu PATH. No Python fallback is used.')
    return candidate


def call_nu(nu, cases, output):
    with tempfile.TemporaryDirectory(prefix='nu-datetime-') as tmp:
        inputs = Path(tmp) / 'cases.json'
        inputs.write_text(json.dumps(cases), encoding='utf-8')
        command = [str(nu), '--no-config-file', '--no-std-lib', str(HERE / 'runner.nu'), str(inputs)]
        proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=300)
        if output:
            (output / 'nu-command.json').write_text(json.dumps(command, indent=2), encoding='utf-8')
            (output / 'nu-stdout.json').write_text(proc.stdout, encoding='utf-8')
            (output / 'nu-stderr.txt').write_text(proc.stderr, encoding='utf-8')
            (output / 'inputs.json').write_text(json.dumps(cases, indent=2), encoding='utf-8')
        if proc.returncode:
            raise RuntimeError(f'Nu exited {proc.returncode}: {proc.stderr}')
        return json.loads(proc.stdout)


def analyse(cases, outputs, expected):
    assert len(cases) == len(outputs)
    stat_keys = ('valid_intervals', 'negative_component', 'unit_range_failure', 'reconstruction_failure', 'final_policy_mismatch', 'reversed_rejected')
    stats = {version: Counter({key: 0 for key in stat_keys}) for version in VERSIONS}
    witnesses = {version: {} for version in VERSIONS}
    table = []
    compatibility = Counter(preserved_before_valid_count=0, compatible_changes_failures=0, draft_changes_on_before_valid_count=0)
    for case, output in zip(cases, outputs):
        assert case['id'] == output['id']
        earlier, later = parse_iso(case['earlier']), parse_iso(case['later'])
        # Do not conflate a date-parser issue with the date-difference algorithm.
        for key, instant in (('earlier_utc', earlier), ('later_utc', later)):
            actual = {unit: output[key][unit] for unit in UNITS}
            assert actual == instant.record(), ('Nu parser mismatch', case, key, actual, instant.record())
        if earlier.ns > later.ns:
            for version in VERSIONS:
                assert not output[version]['ok'], (case, version)
                assert 'Incompatible arguments' in output[version]['error'], (case, version)
                stats[version]['reversed_rejected'] += 1
            continue
        wanted = semantic_oracle(earlier, later)
        if case['id'] in expected:
            assert wanted == expected[case['id']], ('independent oracle vs hand expectation', case, wanted)
        row = {'id': case['id'], 'earlier': case['earlier'], 'later': case['later']}
        before_contract_ok = False
        for version in VERSIONS:
            answer = output[version]
            assert answer['ok'], (case, version, answer)
            result = answer['result']
            assert set(result) == set(UNITS)
            assert all(type(v) is int for v in result.values())
            stats[version]['valid_intervals'] += 1
            failures = []
            if any(v < 0 for v in result.values()):
                failures.append('negative_component')
            if not (0 <= result['month'] < 12 and 0 <= result['hour'] < 24 and 0 <= result['minute'] < 60 and 0 <= result['second'] < 60 and all(0 <= result[k] < 1000 for k in UNITS[6:])):
                failures.append('unit_range_failure')
            if reconstruct(earlier, result) != later.ns:
                failures.append('reconstruction_failure')
            if result != wanted:
                failures.append('final_policy_mismatch')
            for failure in failures:
                stats[version][failure] += 1
                witnesses[version].setdefault(failure, {'case': case, 'result': result, 'final_policy': wanted})
            if version == 'before':
                before_contract_ok = not any(key in failures for key in ('negative_component', 'unit_range_failure', 'reconstruction_failure'))
            if version == 'after':
                assert not failures, ('final implementation violated contract', case, result, failures)
            row[version] = result
        if before_contract_ok:
            unchanged = row['before'] == row['after']
            compatibility['preserved_before_valid_count'] += int(unchanged)
            compatibility['compatible_changes_failures'] += int(not unchanged)
            compatibility['draft_changes_on_before_valid_count'] += int(row['before'] != row['draft'])
            assert unchanged, ('previously reconstructable, nonnegative result changed', case, row)
        if case['id'] in expected:
            table.append(row)
    by_id = {row['id']: row for row in table}
    # Pin the observed bug and the review's compatibility counterexamples.
    assert by_id['jan31-mar1']['before'] == record(0, 1, -2)
    assert by_id['jan31-feb28']['before'] == record(0, 0, 28)
    assert by_id['jan31-feb28']['draft'] == record(0, 1, 0)
    assert by_id['mar31-apr30']['draft'] == record(0, 1, 0)
    assert by_id['leap-anniversary']['draft'] == record(1, 0, 0)
    assert by_id['jan29-mar1']['before'] == record(0, 1, 0)
    assert stats['before']['negative_component'] > 0
    assert stats['draft']['final_policy_mismatch'] > 0
    # In this finite sample the initial clamped-month policy reconstructs too:
    # reconstruction alone does NOT enforce the old month-counting convention.
    assert stats['draft']['negative_component'] == 0
    assert stats['draft']['reconstruction_failure'] == 0
    return {version: dict(count) for version, count in stats.items()}, witnesses, table, dict(compatibility)


def compact(result):
    suffixes = ('y', 'mo', 'd', 'h', 'min', 's', 'ms', 'us', 'ns')
    parts = [f'{result[k]}{suffix}' for k, suffix in zip(UNITS, suffixes) if result[k] != 0]
    return ' '.join(parts) or '0'


def parser_probe(nu, output):
    """Report the known input-parser mismatch without calling it a PR failure."""
    command = [str(nu), '--no-config-file', '--no-std-lib', str(HERE / 'parser_probe.nu')]
    proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    if output:
        (output / 'nu-command.json').write_text(json.dumps(command, indent=2), encoding='utf-8')
        (output / 'nu-stdout.json').write_text(proc.stdout, encoding='utf-8')
        (output / 'nu-stderr.txt').write_text(proc.stderr, encoding='utf-8')
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    observations = json.loads(proc.stdout)
    for observation in observations:
        expected = parse_iso(observation['input']).record()
        assert {k: observation['expected_utc'][k] for k in UNITS} == expected
        assert observation['explicit_matches_expected'], observation
        assert {k: observation['explicit_rfc3339_actual_utc'][k] for k in UNITS} == expected
    summary = dict(nu_version=subprocess.check_output([str(nu), '--version'], text=True).strip(),
                   nu_executable_sha256=hashlib.sha256(nu.read_bytes()).hexdigest(),
                   probes=len(observations),
                   known_default_parser_mismatches=sum(not row['default_matches_expected'] for row in observations),
                   explicit_rfc3339_mismatches=sum(not row['explicit_matches_expected'] for row in observations),
                   scope='Input conversion only, not datetime-diff or parser root-cause investigation.')
    if output:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(observations, indent=2))
    print(json.dumps(summary, indent=2))
    print('OBSERVED: known default-parser mismatches are reported, not treated as #19109 failures.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nu', help='path to real nu executable; otherwise PATH/local prepared binary')
    parser.add_argument('--test', action='store_true', help='named regression cases (also run by default)')
    parser.add_argument('--scan', action='store_true', help='also run bounded calendar/time property grid')
    parser.add_argument('--parser-probe', action='store_true', help='only report the independent known input-parser boundary')
    parser.add_argument('--output', type=Path, help='write raw inputs, Nu stdout, summary and table to this directory')
    args = parser.parse_args()
    if args.parser_probe and (args.scan or args.test):
        parser.error('--parser-probe is separate from --test/--scan')
    verified = verify_sources()
    nu = find_nu(args.nu)
    output = args.output.resolve() if args.output else None
    if output:
        output.mkdir(parents=True, exist_ok=True)
    if args.parser_probe:
        parser_probe(nu, output)
        return
    version = subprocess.check_output([str(nu), '--version'], text=True, encoding='utf-8').strip()
    cases, expected = examples()
    named_count = len(cases)
    if args.scan:
        cases.extend(scan_cases())
    results = call_nu(nu, cases, output)
    stats, witnesses, table, compatibility = analyse(cases, results, expected)
    summary = dict(nu_version=version, nu_executable_sha256=hashlib.sha256(nu.read_bytes()).hexdigest(),
                   python_version=os.sys.version, source_entries_verified=verified,
                   driver_sha256={name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ('run.py', 'runner.nu')},
                   input_parse_mode="Explicit RFC3339: into datetime --format '%+'; every UTC field independently verified; default-parser issue isolated in --parser-probe.",
                   **compatibility,
                   named_cases_including_reverse=named_count, grid_cases=len(cases) - named_count,
                   total_input_pairs=len(cases), actual_nu_algorithm_calls=len(cases) * 3,
                   stats=stats, first_witnesses=witnesses,
                   scope='Finite deterministic UTC calendar grid plus explicit offsets, nanoseconds, centuries; not exhaustive and not a benchmark.')
    lines = ['| Case | before | draft | after |', '|---|---|---|---|']
    lines += [f"| {row['id']} | {compact(row['before'])} | {compact(row['draft'])} | {compact(row['after'])} |" for row in table]
    markdown = '\n'.join(lines) + '\n'
    if output:
        (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output / 'table.json').write_text(json.dumps(table, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output / 'table.md').write_text(markdown, encoding='utf-8')
    print(markdown)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print('PASS: real Nu snapshots; hashes, parser fidelity, hand expectations, final policy, nonnegative units, reconstruction, reverse rejection.')


if __name__ == '__main__':
    main()
