# The error says −257. The file says −256.

Change the `startxref` at the end of a PDF to `-256`, and pypdf raises:

```text
ValueError: negative seek value -257
```

The file says −256. The message says −257. That missing 1 is not a typo; it points at the line that touches the value first.

The number after `startxref` is a byte offset to the xref table. The sample used below is 431 bytes: the xref table starts at 256, and the `startxref` keyword itself sits at 411. pypdf does not seek straight to that offset. It steps back one byte first, to see whether the table is preceded by whitespace. 256 becomes 255, still inside the file. −256 becomes −257, which is 257 bytes before the first byte.

![Two landing points for the same read, and the three places the one value flows to](assets/startxref-map.png)

## One value, three destinations

`read()` stores what `_find_startxref_pos()` returns in `self._startxref`, and three places consume it:

- [`_get_xref_issues()`](https://github.com/py-pdf/pypdf/blob/b78c2aa5301ee4fb1ee024b9838923945ab357b6/pypdf/_reader.py#L1310-L1313) runs `stream.seek(startxref - 1)` to look for leading whitespace;
- [`_read_xref_tables_and_trailers()`](https://github.com/py-pdf/pypdf/blob/b78c2aa5301ee4fb1ee024b9838923945ab357b6/pypdf/_reader.py#L1090) runs `stream.seek(startxref)` to actually read the table;
- the writer, on an incremental update, writes `self._startxref` out as [`/Prev`](https://github.com/py-pdf/pypdf/blob/b78c2aa5301ee4fb1ee024b9838923945ab357b6/pypdf/_writer.py#L1520).

`int(b"-256")` is perfectly valid. `seek(-256)` is a valid Python call too — it just puts the position outside the file. So the first `seek()` raises `ValueError` at −257; bypass it and the second raises the same error at −256; the writer, meanwhile, would copy the negative number into `/Prev` as is.

## The 2025 guard checked for zero

On 24 February 2025, [#3151](https://github.com/py-pdf/pypdf/issues/3151) reported a PDF with two xref tables, where `PdfReader` raised `ValueError: negative seek value -1`. The report said:

> It would be nice if this file was parsed, but IMO at least if it can't be parsed, it should return a malformed error.

That file had a `startxref` of 0, and zero minus one is −1. Two days later [#3157](https://github.com/py-pdf/pypdf/pull/3157) landed four lines in `_get_xref_issues()`:

```python
if startxref == 0:
    return 4
```

Zero was stopped. Negative numbers were not. `return 4` means "this xref is broken", and the caller rebuilds the table — which is why a zero pointer still yields one page.

**That gate sits at one of the three destinations, and it recognises one value.**

## Fixed at the exit

\#4144 changes `read()`, right after `_find_startxref_pos()`:

```python
startxref = self._find_startxref_pos(stream)
if startxref < 0:
    # A negative offset cannot point into the file. Treat it like the
    # zero case (#3157) so the xref table is repaired instead of
    # leaking a ValueError from a negative seek.
    logger_warning(
        "Negative startxref pointer (%(startxref)d), treating it as zero.",
        source=__name__,
        startxref=startxref,
    )
    startxref = 0
self._startxref = startxref
```

The merged version is [`read()` at `91a73b5`](https://github.com/py-pdf/pypdf/blob/91a73b5e8e9701efdad26b865964c2a53cb110b3/pypdf/_reader.py#L713-L738).

Why not widen the old gate to `< 1`? Because that fixes one call site out of three. `_read_xref_tables_and_trailers()` would still receive a negative number and seek to it, and `self._startxref` would still be negative.

Normalised at the exit, a negative number takes the zero path #3157 already paved: `_get_xref_issues()` returns 4, non-strict mode logs a warning and calls `_rebuild_xref_table()`, strict mode raises `PdfReadError("Broken xref table")`. The recovery code is the same one, unchanged.

## The same file, both versions

The reproduction keeps two complete pypdf source trees side by side, generates a one-page PDF with the same `PdfWriter`, and rewrites only the digits after `startxref`. This sample's offset is 256, so the negative pointer is −256.

| Input | Before, `b78c2aa` | Merged, `91a73b5` |
|---|---|---|
| ordinary `256` | one page, no warnings | one page, no warnings |
| `0` | one page; `incorrect startxref pointer(4)`, `parsing for Object Streams` | same |
| `-256`, non-strict | `ValueError: negative seek value -257` | one page; `Negative startxref pointer (-256), treating it as zero.`, `incorrect startxref pointer(4)`, `parsing for Object Streams` |
| `-256`, strict | `ValueError: negative seek value -257` | `PdfReadError: Broken xref table`, after the negative-pointer warning |
| `0`, strict | `PdfReadError: Broken xref table`, no warning | same |

The `0` rows are the control group: they show the pre-fix tree already contains #3157, so the failure is specific to negative numbers. The two strict rows behave identically — a broken file still fails, but it fails with pypdf's own exception, the same one a zero pointer gets.

All five cases rerun in one go: `negative_startxref_demo/` holds the `b78c2aa` and `91a73b5` trees and a `run.py` that drives both.

The patch drew exactly one substantive review comment: stefan6419846 asked why the test didn't assert the full warning messages. The author tightened the assertions, forgot to push them, and was asked `Did you forget to push these changes?`, answered `Yes..`, and pushed. The merged test at [`tests/test_reader.py#L2098`](https://github.com/py-pdf/pypdf/blob/91a73b5e8e9701efdad26b865964c2a53cb110b3/tests/test_reader.py#L2098) checks the three warnings in order, plus one more case: a healthy file produces none.
