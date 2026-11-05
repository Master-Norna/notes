# tomlkit Wrote 07:32:00+02:00. Why Couldn't It Read It Back?

Writing a tz-aware time from an API or a database into a config file is the most ordinary step in code like this:

```python
from datetime import time, timedelta, timezone
from tomlkit import dumps, item, parse

t = time(7, 32, tzinfo=timezone(timedelta(hours=2)))
parse(dumps({"t": item(t)}))
# InvalidTimeError: Invalid time at line 1 col 18
```

The line it writes is `t = 07:32:00+02:00`, which its own parser rejects. Nobody typed that line by hand: the library rendered it from the Python `time` object, and carried it from 0.1.0 (2018-07-10) through 0.15.1 (2026-07-17); 0.15.2 (2026-10-16) fixed it.

What follows traces that error message: why the six characters have nowhere to go, which two call sites write them, what the patch chose and left alone, which bytes change on upgrade, and what to do with a file already broken.

## Six characters with nowhere to go

[TOML 1.0](https://toml.io/en/v1.0.0#local-time) defines Local Time like this:

> If you include only the time portion of an RFC 3339 formatted date-time, it will represent that time of day without any relation to a specific day or any offset or timezone.

The spec's example is `lt1 = 07:32:00`.

![One time object with five fields; TOML's Local Time has a slot for the first four only](assets/local-time-slots.png)

`07:32:00` is a Local Time. **The six characters `+02:00` have no slot in that grammar.**

TOML can express an offset, but then it is one of four date-time types, and the offset belongs to the first:

| Type | Example | What it allows |
|---|---|---|
| [Offset Date-Time](https://toml.io/en/v1.0.0#offset-date-time) | `1979-05-27T07:32:00Z` | date + time + offset |
| [Local Date-Time](https://toml.io/en/v1.0.0#local-date-time) | `1979-05-27T07:32:00` | date + time |
| [Local Date](https://toml.io/en/v1.0.0#local-date) | `1979-05-27` | date |
| [Local Time](https://toml.io/en/v1.0.0#local-time) | `07:32:00` | time |

To carry `+02:00`, you have to fall back to the type that has a date; a bare time has nothing to hang it on. That is not just tomlkit's reading either: the standard library's [`tomllib`](https://docs.python.org/3/library/tomllib.html) parses `t = 07:32:00` as a naive `datetime.time(7, 32)`, and on `t = 07:32:00+02:00` it fails with `Expected newline or end of document after a statement`. RFC 3339 itself keeps the instant and the offset in two segments ([§5.6](https://datatracker.ietf.org/doc/html/rfc3339#section-5.6)); TOML simply does not attach the second segment to the "time only" cell.

## `raw` is not a copy of `isoformat()`

The `Time` item stores two things at once: the Python value and the literal destined for the TOML text. The constructor arguments split in two:

| Field | What it is | Written to TOML? |
|---|---|---|
| `hour` `minute` `second` | time of day | yes |
| `microsecond` | microseconds | yes, padded to six digits and stripped of trailing zeros when non-zero |
| `tzinfo` | the zone on the Python side | no |
| `fold` | marks the second occurrence of a wall time when DST falls back | no |
| `raw` | the characters that go straight into the text | it *is* the text |

The trouble is that `raw` was treated as a copy of `isoformat()`. Before the fix, `item()` built `Time` like this:

```python
Time(
    ...,
    value.tzinfo,           # stays on the object, no problem
    Trivia(),
    value.isoformat(),      # -> '07:32:00+02:00'
    fold=value.fold,
)
```

`isoformat()` is Python's format. [Its documentation](https://docs.python.org/3/library/datetime.html#datetime.time.isoformat) says an offset is appended whenever `tzinfo` is not `None` — exactly the segment a TOML Local Time does not have. A few lines above in `item()`, the `datetime` branch writes `value.isoformat().replace("+00:00", "Z")`; the `time` branch is plain `value.isoformat()`, because it had no offset to replace.

There is a second site: `Time._new()`, which `replace()` goes through, where `raw` is likewise `result.isoformat()`.

## One line, eight years

Several places write the same `isoformat()`, and they did not go in on the same day:

| Date | Commit | Site | Expression |
|---|---|---|---|
| 2018-07-08 | [`4a09449`](https://github.com/python-poetry/tomlkit/commit/4a094491aae8fd0de32e8a19296fb4bb6b32bbc8) | `item()` in `tomllib/api.py` | `value.isoformat()` |
| 2018-07-18 | [`d02e9ec`](https://github.com/python-poetry/tomlkit/commit/d02e9ec2ef7543ad775b19f27f021be6f187d14a) | `item()` in `tomlkit/items.py` | carried over as it stood |
| 2022-04-16 | [`5118514`](https://github.com/python-poetry/tomlkit/commit/5118514fa1f193ff92c3d26b4d4da2f0a94f70e2) ([#189](https://github.com/python-poetry/tomlkit/pull/189)) | `Time._new()` | `raw = result.isoformat()` |
| 2026-09-30 | [`ce8f8ee`](https://github.com/python-poetry/tomlkit/commit/ce8f8ee982411c4afef5cfb90df7313cc5f7d779) | both sites switch to `_format_time()` | no longer reads `tzinfo` |

The first commit is two days older than 0.1.0 (PyPI dates 0.1.0 to 2018-07-10), so the first release on PyPI already carried it; the last to carry it was 0.15.1 (2026-07-17). Opening the wheels at both ends: 0.1.0's `tomlkit/api.py` line 162 is `return time(value.isoformat())`, and 0.15.1's `tomlkit/items.py` line 208 is still `value.isoformat()` — eight years changed the package name, the file name and the line number, not the expression.

The day it was first written, the package was still called `tomllib`: the `datetime` branch already carried `.replace("+00:00", "Z")`, and the `time` branch was plain `value.isoformat()`. Ten days later the dispatch moved into `tomlkit/items.py` and the code was carried over as it stood. The second site came three years later, when `Time` gained `replace()` and `_new()`, and the same `raw = result.isoformat()` was written once more.

Both times the same function was picked, because on the Python side it is the default answer to "turn a time into a string". Only the TOML side disagrees. From July 2018 to September 2026 that code changed package name, file and constructor; only this one line stayed.

It is hard to notice because the everyday path never goes through either site: a `Time` that came out of `parse()` carries the `raw` from the source text, and `dumps()` hands it back unchanged. Only `item()` on a Python `time` object, or a `replace()` that changes a field, renders on the spot.

## Only the writing end changed

[#613](https://github.com/python-poetry/tomlkit/pull/613) adds a `_format_time()`:

```python
def _format_time(value: time) -> str:
    # TOML local times carry no offset or timezone (the spec's examples
    # are plain ``07:32:00``); keeping the offset in the rendered raw
    # value would produce a literal this library's own parser rejects.
    # Built from the fields (not ``isoformat``/``replace``) so it stays
    # correct even when called on a ``Time`` from ``Time._new``.
    s = f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    if value.microsecond:
        s += f".{value.microsecond:06d}".rstrip("0")
    return s
```

The comment's line "the spec's examples are plain 07:32:00" is the reasoning: do not guess what `isoformat()` will print, build the string from the characters the spec allows.

Both `item()` and `Time._new()` now call it, one line each:

```diff
-    value.isoformat(),
+    _format_time(value),
```

```diff
-    raw = result.isoformat()
+    raw = _format_time(result)
```

The merged version is [`items.py` at `ce8f8ee`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L209) and [`_format_time()`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L237-L246).

It reads hours, minutes, seconds and microseconds; it never reads `tzinfo`. A non-zero microsecond is padded to six digits and stripped of trailing zeros: `123450` prints as `.12345`, `0` prints no decimal point at all.

![The same time, three writing paths: the first two rebuild `raw`, the third copies the text it read](assets/three-paths.png)

Only the first two of those paths render `raw` on the spot; a `Time` from `parse()` carries the source text and `dumps()` copies it. So the patch only has to touch the first two, and the third appears in the tests only to confirm it was not touched.

The parser was left alone. `parse("t = 07:32:00+02:00")` raises `InvalidTimeError` before and after — that syntax does not exist in TOML, and the library should not invent one. Round-tripping means "what was read is what is written"; these two sites are not round-tripping, they are inventing text from a Python object, so only the inventing end needed fixing.

## Why not just drop the offset?

There are at least four ways to make that line legal, and they cost different things:

| Approach | What gets written | Where it gets stuck |
|---|---|---|
| Slice the offset off the result of `isoformat()` | `07:32:00` | You first have to find where the offset starts. `+00:00`, `-05:00`, an offset after microseconds — all of them need handling, which amounts to re-implementing Python's formatting rules and following them as they change |
| Raise whenever `tzinfo` is not `None` | no text | `item()` fails at construction, blocking even uses that never dump to a file; TOML cannot represent an offset, but that does not mean a Python object cannot carry one |
| Convert to UTC first | `07:32:00+00:00` | UTC is an offset too, and a Local Time still will not take it; converting to naive changes the value silently |
| Invent a date and write an Offset Date-Time | `1970-01-01T07:32:00+02:00` | The date is made up, and the type silently changes from `time` to `datetime` |

The patch took a narrower route: instead of editing the output of `isoformat()`, it builds the string from the fields TOML allows. The input is four integers; the output has one shape; nothing depends on how Python chooses to format a time in a given version or with a given `timespec`.

The price is that the offset really is dropped. That has consequences, which get their own section below.

## What changes, what doesn't

What changed is "build a `Time` from a Python object", so inputs that can reach it and inputs that cannot need separating. The table has four blocks: rows one to four are `time`'s own rendering, row five is `fold`, rows six to eight are `datetime`, row nine is an array element, and the last two rows are the read-then-write path. Every cell comes from an actual run of `local_time_demo/run.py`:

| Input | Before, `763bd66` | Merged, `ce8f8ee` | Why |
|---|---|---|---|
| `time(7, 32, tzinfo=utc)` | `07:32:00+00:00` | `07:32:00` | a UTC offset is still an offset |
| microsecond `100000`, tz-aware | `07:32:00.100000+02:00` | `07:32:00.1` | padded to six, then trailing zeros stripped |
| microsecond `1`, tz-aware | `07:32:00.000001+02:00` | `07:32:00.000001` | leading zeros stay |
| microsecond `123450`, naive | `07:32:00.123450` | `07:32:00.12345` | naive times lose trailing zeros too; value unchanged |
| `time(7, 32, fold=1)` | `07:32:00` | `07:32:00` | `fold` never reaches the text |
| tz-aware `datetime` | `2026-11-04T07:32:00+02:00` | same | an Offset Date-Time is legal |
| UTC `datetime` | `2026-11-04T07:32:00Z` | same | `item()` writes `+00:00` as `Z` |
| `datetime.replace(hour=13)` | `2026-11-04T13:32:00+00:00` | same | `_new()` does not switch to `Z`, in either version |
| tz-aware `time` in an array | `a = [07:32:00+02:00]` | `a = [07:32:00]` | array elements render on the spot too |
| `parse()` then `dumps()` unchanged | `t = 07:32:00.123450` | same | text read in is kept verbatim |
| `parse()` then `replace(minute=33)` | `t = 07:33:00.123450` | `t = 07:33:00.12345` | changing a field re-renders |

The PR description's line "Naive times are byte-for-byte unchanged" holds for whole seconds; a naive time with microseconds ending in zero comes out a few characters shorter — it still reads back as the same `time(7, 32, 0, 123450)`. That cell is measured, and the PR's summary line does not mention it.

The `datetime` column is all "same", because an Offset Date-Time accepts an offset and there is no error to fix there. The one difference that survives between the versions is cosmetic: `item()` writes UTC as `Z`, `replace()` writes `+00:00`; both are legal, and both versions do it.

## Run it

```powershell
python -B -S 本地时间_tomlkit/local_time_demo/run.py --test
```

Both complete source trees are in the project (`vendor/parent`, `vendor/merge`); tomlkit is not installed and there is no network, subprocesses run with `-I -B -S` and reject `socket.*`. On Windows, Python 3.12.14 and PowerShell 7, the last line should be `PASS` and the exit code 0:

```text
Python 3.12.14  (two complete tomlkit snapshots, no install)
case                         parent 763bd66                   merge ce8f8ee
----------------------------------------------------------------------------------------------
aware.as_string()            07:32:00+02:00                   07:32:00
micro.as_string()            07:32:00.123450+02:00            07:32:00.12345
aware.replace(hour=13)       13:32:00+02:00                   13:32:00
dumps()                      t = 07:32:00+02:00               t = 07:32:00
parse(dumps())               InvalidTimeError                 ok
naive.as_string()            07:32:00                         07:32:00

PASS: parent writes 07:32:00+02:00 and cannot parse its own output; merge writes 07:32:00, parses it back, leaves whole-second naive times unchanged, and touches neither datetime nor parsed text.
```

The assertions map to each line of that output, not merely to "did it raise": before the fix it must write the offset and fail to read it back; after, it must read back exactly; whole-second naive times must stay byte-for-byte; and both `datetime` paths plus the parsed-then-dumped text must not move a single character.

The same output has a `boundary cases` section after it, which is the table above. `--json` prints the full report, `--output PATH` saves one, and `--emit DIR` has each version write a TOML file, with an extra legal sample from the merged version — the next section uses it.

## Who hits it

People who write a tz-aware time from an API or a database into a config file. A nightly job that runs at 23:30 UTC, say:

```python
from datetime import time, timezone
from tomlkit import dumps, item

start = time(23, 30, tzinfo=timezone.utc)
open("schedule.toml", "w", encoding="utf-8").write(dumps({"start": item(start)}))
```

Before the fix it writes `start = 23:30:00+00:00`; the merged version writes `start = 23:30:00` (both run from the source snapshots). **The first failure is not at write time but at the next read**: `tomllib` reports `Expected newline or end of document after a statement (at line 1, column 17)`, and tomlkit raises `InvalidTimeError`. The writer saw a config saved successfully; the reader gets a syntax error — and the exception points at the document, not at the library.

A naive `time(23, 30)` is written as `start = 23:30:00` by both versions, byte for byte. The same goes for `fold`: [its meaning](https://docs.python.org/3/library/datetime.html#datetime.time.fold) is the second occurrence of a wall time when daylight saving falls back, a property of the Python object, and neither version writes it into the text.

## Two things to know before upgrading

The first is bytes. Take the "microsecond `123450`, naive" row: before, `07:32:00.123450`; after, `07:32:00.12345`, two characters shorter. It still reads back as `time(7, 32, 0, 123450)`, so the value is unchanged; but if your tests compare text snapshots, or something downstream compares bytes, the upgrade will show a diff.

The second is meaning. `+02:00` no longer reaches the file, and the `Time` that `parse()` returns has `tzinfo = None`. If the offset was merely something the object happened to carry, nothing is lost. If it was part of the value — 23:30 meaning 23:30 UTC, say — a Local Time cannot hold it. That case wants an Offset Date-Time with a date, or a UTC timestamp stored as a number or string and converted on read. **The patch fixes syntax, not that semantic problem.**

No flag switches the old rendering back. Staying on 0.15.1 means not handing a tz-aware `time` to `item()` or `replace()`: convert it to naive yourself, or store a string.

## Is this your file?

Check the version first:

```powershell
python -c "import tomlkit; print(tomlkit.__version__)"
```

0.15.2 and later need no code change; only files written by 0.15.1 and earlier need the next step.

What the pre-fix version wrote looks like this:

```toml
[schedule]
start = 07:32:00+02:00
```

Any line of that shape was most likely written by tomlkit ≤0.15.1 from a tz-aware `time`; a hand-written file can be wrong in the same shape. `scan_local_times.py` scans a directory of `*.toml` for exactly that shape:

```powershell
python -B -S 本地时间_tomlkit/local_time_demo/run.py --emit emitted
python -B -S 本地时间_tomlkit/local_time_demo/scan_local_times.py emitted
```

```text
emitted/legal.toml: clean
emitted/merge.toml: clean
emitted/parent.toml:2:9  07:32:00+02:00
emitted/parent.toml: tomllib rejects this file: TOMLDecodeError: Expected newline or end of document after a statement (at line 2, column 17)
--- 3 file(s) scanned, 1 hit(s), 1 rejected by tomllib
```

`legal.toml` contains two easily-mistaken forms and neither is reported: `note = "07:32:00+02:00"` is a string, and `stamp = 1979-05-27T07:32:00+02:00` is a legal Offset Date-Time. The scanner reports `file:line:column` and exits with 1 on a hit or when `tomllib` rejects a file.

**The upgrade only guarantees that what is written from now on is right. A file already broken is not read back by 0.15.2 either** — the parser's attitude to `t = 07:32:00+02:00` is the same in both versions, `InvalidTimeError`. Those six characters have to be deleted by hand, at the position the scanner gives. If the TOML is generated by a program, the cheaper route is to upgrade and re-run the generator; the scanner is there to tell you which files a person still has to look at.

## The conflict came from next door

Before #613 merged, the maintainer left one line: "Please resolve the conflict".

The conflict came from [#620](https://github.com/python-poetry/tomlkit/pull/620), which added the standard library's `fold` argument to `Time` and `DateTime` and edited exactly the neighbourhood of `Time._new()`; it started from [#619](https://github.com/python-poetry/tomlkit/issues/619). The two PRs merged on the same day, #620 three and a half hours earlier. After rebasing onto the latest master, the author had `fold=result.fold` and `_format_time(result)` in the same constructor:

```python
def _new(self, result: time) -> Time:
    raw = _format_time(result)
    return Time(
        ...,
        raw,
        fold=result.fold,
    )
```

`fold` describes the second occurrence of a local time when daylight saving falls back; it is a property of the Python `time` object itself. `_format_time()` decides how that object is written into TOML. Two concerns, one constructor, no interaction.

## What comes back

```python
parse(dumps({"t": item(t)}))["t"]     # 07:32:00
```

It reads back now. What comes back is `07:32:00`, and its `tzinfo` is `None` — that line of text never carried the information.

The [0.15.2 release notes](https://github.com/python-poetry/tomlkit/releases/tag/0.15.2) list #613 explicitly, and the [CHANGELOG](https://github.com/python-poetry/tomlkit/blob/0.15.2/CHANGELOG.md) entry reads "Fix a tz-aware `datetime.time` rendering with a UTC offset …; it now renders as a local time". Re-running against the published wheel `tomlkit-0.15.2-py3-none-any.whl` (unpacked and put on `sys.path`) gives output identical to the merged tree: `version: 0.15.2`, `as_string: 07:32:00`, `document: t = 07:32:00`, `parsed: 07:32:00`.

The test upstream added for this behaviour is at [`tests/test_items.py` line 847](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tests/test_items.py#L847): `item()` gives `07:32:00`, which `parse` returns as `time(7, 32)`; `replace(hour=13)` gives `13:32:00`, which reads back as `time(13, 32)`. It covers those two exits.

So this is not a fix that deletes legal information. A TOML Local Time never had room for an offset; the library used to force it in. Now the extra part stays on the Python object and does not reach the file. To carry a zone, you write an Offset Date-Time with a date — a different type.

The commits, PRs, spec, Python docs and release notes in this piece were checked against the links above; the release dates come from PyPI's [`tomlkit` JSON API](https://pypi.org/pypi/tomlkit/json) (queried 2026-11-05; latest 0.15.2, requires Python 3.9+).
