# The time it wrote, it could not read back

tomlkit's selling point is round-tripping: a document read in comes out the same. The last line of this snippet raises.

```python
from datetime import time, timedelta, timezone
from tomlkit import dumps, item, parse

t = time(7, 32, tzinfo=timezone(timedelta(hours=2)))
parse(dumps({"t": item(t)}))
# InvalidTimeError: Invalid time at line 1 col 18
```

The line it wrote was `t = 07:32:00+02:00`, which its own parser rejects. Nobody typed that line by hand: tomlkit rendered it from the Python `time` object, from July 2018 until September 2026.

## Six characters with nowhere to go

[TOML 1.0](https://toml.io/en/v1.0.0#local-time) defines Local Time like this:

> If you include only the time portion of an RFC 3339 formatted date-time, it will represent that time of day without any relation to a specific day or any offset or timezone.

The spec's example is `lt1 = 07:32:00`.

![One time object with five fields; TOML's Local Time has a slot for the first four only](assets/local-time-slots.png)

`07:32:00` is a Local Time. **The six characters `+02:00` have no slot in that grammar.**

TOML can express an offset, but then it is an [Offset Date-Time](https://toml.io/en/v1.0.0#offset-date-time) and must carry a date: `1979-05-27T07:32:00+02:00`. A bare time has nothing to hang it on. That is not just tomlkit's reading either: the standard library's `tomllib` parses `t = 07:32:00` as a naive `datetime.time(7, 32)`, and on `t = 07:32:00+02:00` it fails with `Expected newline or end of document after a statement`.

## `raw` is not a copy of `isoformat()`

The `Time` item stores two things at once: the Python `tzinfo`, and the `raw` literal destined for the TOML text.

Keeping `tzinfo` on the Python object is fine — `datetime.time` is allowed to carry a zone. The trouble is that `raw` was treated as a copy of `isoformat()`. Before the fix, `item()` built `Time` like this:

```python
Time(
    value.hour,
    value.minute,
    value.second,
    value.microsecond,
    value.tzinfo,
    Trivia(),
    value.isoformat(),      # -> '07:32:00+02:00'
    fold=value.fold,
)
```

A few lines above in `item()`, the `datetime` branch writes `value.isoformat().replace("+00:00", "Z")`; the `time` branch writes `value.isoformat()` unmodified.

`isoformat()` is Python's format. [Its documentation](https://docs.python.org/3/library/datetime.html#datetime.time.isoformat) says an offset is appended whenever `tzinfo` is not `None` — exactly the segment a TOML Local Time does not have.

There is a second site: `Time._new()`, which `replace()` goes through, where `raw` is likewise `result.isoformat()`.

## One line, eight years

Several places write the same `isoformat()`, and they did not go in on the same day.

The earliest is [`4a09449`](https://github.com/python-poetry/tomlkit/commit/4a094491aae8fd0de32e8a19296fb4bb6b32bbc8) on 8 July 2018. The package was still called `tomllib`; `item()` in `api.py` dispatched on type, and the `datetime` branch already carried `.replace("+00:00", "Z")` while the `time` branch was plain `value.isoformat()`. Ten days later [`d02e9ec`](https://github.com/python-poetry/tomlkit/commit/d02e9ec2ef7543ad775b19f27f021be6f187d14a) moved that dispatch into `tomlkit/items.py` and carried the code over as it stood. The second site is [`5118514`](https://github.com/python-poetry/tomlkit/commit/5118514fa1f193ff92c3d26b4d4da2f0a94f70e2) in April 2022 (#189): adding `replace()` and `_new()` to `Time`, it wrote the same `raw = result.isoformat()` once more.

Three years apart, and the same function was picked, because on the Python side it is the default answer to "turn a time into a string". Only the TOML side disagrees. From July 2018 to September 2026 that code changed package name, file and constructor; only this one line stayed.

It is hard to notice because the everyday path never goes through either site: a `Time` that came out of `parse()` carries the `raw` from the source text, and `dumps()` hands it back unchanged. Only `item()` on a Python `time` object, or a `replace()` that changes a field, renders on the spot. The people who hit it are those writing a tz-aware time from an API or a database into a config file — and when they first hit it, what they see is `InvalidTimeError` on the next read of that file, pointing at the document, not at the library.

So it is not one version either: from that 2018 commit on, any program that handed a tz-aware `time` to `item()` wrote those six characters into the file. What was fixed is 0.15.2.

## Only the writing end changed

[#613](https://github.com/python-poetry/tomlkit/pull/613) adds a `_format_time()`:

```python
def _format_time(value: time) -> str:
    # TOML local times carry no offset or timezone ...
    s = f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    if value.microsecond:
        s += f".{value.microsecond:06d}".rstrip("0")
    return s
```

Both `item()` and `Time._new()` now call it. The merged version is [`items.py` at `ce8f8ee`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L209) and [`_format_time()`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L237-L246).

It reads hours, minutes, seconds and microseconds; it never reads `tzinfo`. A non-zero microsecond is padded to six digits and stripped of trailing zeros: `123450` prints as `.12345`, `0` prints no decimal point at all.

The parser was left alone. `parse("t = 07:32:00+02:00")` raises `InvalidTimeError` before and after — that syntax does not exist in TOML, and the library should not invent one.

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

Both complete source trees are in the project (`vendor/parent`, `vendor/merge`); tomlkit is not installed and there is no network, subprocesses run with `-I -B -S` and reject `socket.*`:

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

The same output has a `boundary cases` section after it, which is the table above. `--json` prints the full report, `--output PATH` saves one, and `--emit DIR` has each version write a TOML file, with an extra legal sample from the merged version — the next section uses it.

## Is this your file?

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

The [0.15.2 release notes](https://github.com/python-poetry/tomlkit/releases/tag/0.15.2) list #613 explicitly, and the [CHANGELOG](https://github.com/python-poetry/tomlkit/blob/0.15.2/CHANGELOG.md) entry reads "Fix a tz-aware `datetime.time` rendering with a UTC offset …; it now renders as a local time". Re-running against the published wheel `tomlkit-0.15.2-py3-none-any.whl` gives output identical to the merged tree: `07:32:00`, and it reads back.

The test upstream added for this behaviour is at [`tests/test_items.py` line 847](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tests/test_items.py#L847): `item()` gives `07:32:00`, which `parse` returns as `time(7, 32)`; `replace(hour=13)` gives `13:32:00`, which reads back as `time(13, 32)`. It covers those two exits.

So this is not a fix that throws information away. A TOML Local Time never had room for an offset; the library used to force it in. Now the extra part stays on the Python object and does not reach the file. To carry a zone, you write an Offset Date-Time with a date — a different type.
