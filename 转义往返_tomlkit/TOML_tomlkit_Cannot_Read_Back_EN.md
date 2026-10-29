# One Appended Quote, and tomlkit Cannot Read Back Its Own TOML

[tomlkit](https://github.com/python-poetry/tomlkit) introduces itself as a "style-preserving TOML library": comments, indentation, whitespace and element order survive a parse–edit–dump cycle, and the file comes back looking the way it went in. To keep that promise, every string value in memory has to be more than one thing.

First, the symptom. Three lines of code — append a quote to an existing string value:

```python
from tomlkit import item, parse

i = item("foo")
i += '"'

i == 'foo"'                   # True — the value is right
i.as_string()                 # '"foo""' — this is what gets serialized
parse(f'k = {i.as_string()}')
# UnexpectedCharError: Unexpected character: '"' at line 1 col 9
```

That trailing garbage is not a typo from some user — tomlkit itself serialized it, and the first parser to read it was tomlkit's own. That is what I fixed in [tomlkit #612](https://github.com/python-poetry/tomlkit/pull/612), merged on September 30, 2026 — seven lines added, one removed in production code. This post follows that extra quote to the exact step where a string's value and its spelling go separate ways.

## 1. One value, two texts

A `String` in tomlkit inherits from both `str` and `Item` ([items.py L2199-L2213](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/items.py#L2199-L2213)): the `str` body is the logical value, and construction stores a second copy, `_original` — the source text, the unquoted escaped form that ends up between the delimiters when the file is written. All `as_string()` does is wrap it back ([L2226-L2227](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/items.py#L2226-L2227)):

```python
def as_string(self) -> str:
    return f"{self._t.value}{decode(self._original)}{self._t.value}"
```

Why two copies: the same TOML value has many legal spellings. The value `foo` may be written `"foo"` or `'foo'`; the value `foo"` may be written `"foo\""` or `'foo"'`. A faithful round-trip — whatever spelling came in, the same spelling goes out — has to remember the spelling itself.

At **construction** the two copies agree. `item()` reaches `String.from_raw()` ([api.py L152-L153](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/api.py#L152-L153)), which escapes the content against the type's table and stores it in `_original` ([items.py L2251-L2271](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/items.py#L2251-L2271)): for basic strings (`"…"`) the table covers quotes, backslashes and control characters ([escaped_sequences, L256-L266](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/items.py#L256-L266), matching the escape set of the [TOML v1.0.0 spec](https://toml.io/en/v1.0.0#string)). Constructing `item('a"b')` yields: logical value `a"b`, source text `a\"b`, `as_string()` output `"a\"b"` — a spelling any TOML parser reads back.

The accident is not at construction. It is at **append**.

## 2. Half-fixed in 2022

String concatenation is taken over by `String.__add__`. As it was before the fix (parent commit [`7903965`](https://github.com/python-poetry/tomlkit/blob/79039653cbe5ff2a2e23042717455a2ac4875539/tomlkit/items.py#L2233-L2237)):

```python
def __add__(self, other: str) -> String:
    result = super().__add__(other)
    original = self._original + getattr(other, "_original", other)
    return self._new(result, original)
```

The first line is always right: `super().__add__` is `str.__add__`, and the logical value updates normally. The problem is entirely in how the second line splices the source text — and that line has a history.

In September 2022, [#231](https://github.com/python-poetry/tomlkit/issues/231) reported "escape characters lost after concatenation" — with a real AWS samconfig.toml case attached, where one lost escape let an inner quote tear the whole argument apart. Two weeks later [#235](https://github.com/python-poetry/tomlkit/pull/235) landed and wrote the line above: if the right operand is a `String`, `getattr` picks up its `_original` (an already-escaped source text) and appends it as is — right, because re-escaping would double-escape; if the right operand is a plain `str`, `getattr` falls to its default, and **the text is appended to the source text verbatim**.

That fix saved the left half: the left side's escapes survive concatenation, pinned by [test_string_add_preserve_escapes](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tests/test_items.py#L867-L873). But its append case was `" baz"` — not one special character anywhere, so the right half was exactly what it could not catch. The line then sat there for four years.

The same append feeds `"` into the logical value while the source text never sees it — the two representations fork on the spot. From the PR:

> String.__add__ spliced the appended text into the raw literal without escaping it, so appending a quote or backslash to a basic string produced a literal that is not valid TOML - including to this library's own parser.
> —— [#612 description](https://github.com/python-poetry/tomlkit/pull/612)

## 3. Seven lines at the concatenation

The fix (merge commit [`61941de`](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/items.py#L2233-L2243)) replaces that getattr with two explicit branches:

```python
def __add__(self, other: str) -> String:
    result = super().__add__(other)
    if isinstance(other, String):
        original = self._original + other._original
    else:
        escaped = self._t.escaped_sequences
        original = self._original + (
            escape_string(other, escaped) if escaped else other
        )
    return self._new(result, original)
```

Each branch carries a decision:

- The right side is already a `String`: append its `_original`, and the semantics #235 chose stay untouched — it was escaped by its own type already.
- The right side is a plain `str`: escape it with [`escape_string`](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/_utils.py#L128) against **the left string's own type**. The appended content will live inside `i`'s delimiters, so it escapes by `i`'s type (`self._t`), nothing else. Literal strings (`'…'`) have an empty escape table and take the `else` branch verbatim — TOML literals have no escaping at all (see section 4).

This is the same brush the construction path uses: `from_raw` calls `escape_string` too. What the change really pins down is one sentence: **the duty to keep the logical value and the source text in sync now extends from construction time to append time.** Upstream added a four-case regression test for it, [test_string_add_escapes_appended_content](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tests/test_items.py#L875-L902): append `"`, append `\`, right side a `String`, append plain text — each pinned in turn.

Mapped as the paths into `_original`, the fix's location is easy to see:

| Path into `_original` | Before `61941de` | After `61941de` |
| --- | --- | --- |
| Construction, `String.from_raw()` | escaped via `escape_string` against the type's table | unchanged |
| `+` with another `String` | the right side's already-escaped `_original` appended (#235) | unchanged |
| `+` with a plain `str` | appended verbatim — the hole | routed through `escape_string` against the left side's table |

Serialization, for contrast, never moved: `as_string()` wraps `_original` in delimiters and writes it out, byte-identical before and after.

## 4. What the fix does not cover

For honesty's sake, the corners the fix leaves open:

- **A literal string appending its own delimiter breaks in both versions.** `value("'foo'")` builds the literal `'foo'`; append a `'` and the output `'foo''` does not parse — identical before and after. Escaping cannot help, because literals have no escape mechanism at all; the rescue would be a different spelling (switch to a basic string and escape), which would be rewriting, not preserving — out of these seven lines' scope.
- **Construction validates, appending does not.** `from_raw` raises `InvalidStringError` on the spot when a literal contains a quote ([items.py L2257-L2259](https://github.com/python-poetry/tomlkit/blob/61941deb3c7155e88d5f038148b33a599c04a530/tomlkit/items.py#L2257-L2259)); `__add__` runs no such check. The two paths now share one escape brush, but validation still only stands at the construction end.
- Two parts of the comparison are **byte-identical across versions**: `String` + `String`, and appending plain text. The fix only closes the "plain str into a basic string" seam.

## 5. Before and after, side by side

I put the tomlkit package sources of parent commit `7903965` and merge commit `61941de` verbatim into [tomlkit_demo](tomlkit_demo/), and fed the same operations to both snapshots. Zero third-party dependencies, fully offline:

```bash
python 转义往返_tomlkit/tomlkit_demo/run.py          # comparison report
python 转义往返_tomlkit/tomlkit_demo/run.py --test   # assertion self-test
```

Both snapshots verify, after loading, that the module really came from the snapshot directory; versions are identified by git SHA throughout — both snapshots' `__init__.py` still read 0.15.1 (the release bump had not happened at merge time), so version strings are no help. This run (Windows / Python 3.12.14) produced:

| Appended | `as_string()` before | Read back before | `as_string()` after | Read back after |
| --- | --- | --- | --- | --- |
| `'"'` | `"foo""` | UnexpectedCharError | `"foo\""` | `'foo"'` |
| `"\\"` | `"foo\"` | InvalidControlChar | `"foo\\"` | `'foo\'` |
| `"\n"` | bare newline inside quotes | InvalidControlChar | `"foo\n"` | `'foo\n'` |
| `item('"')` | `"foo\""` | success | `"foo\""` (identical) | `'foo"'` |
| `" bar"` | `"foo bar"` | success | `"foo bar"` (identical) | `'foo bar'` |

The document-level round-trip is closest to real usage: `parse('k = "foo"')`, take out `k`, append a quote, `dumps`. Before the fix, the file comes out as `k = "foo""` and the next `load` rejects it on the spot; after, the file gets `k = "foo\""` and reads back `'foo"'`. **Writable but unreadable is the worst way to fail**: the broken file is already on disk, and the one who discovers it is the next tool that reads it.

The demo carries 17 assertions (the two boundaries from section 4 included); `--test` passes all of them with exit code 0; both snapshots ship under the upstream MIT license (`tomlkit_demo/LICENSE`). I also ran the after-snapshot's own test suite: release tarballs do not include the toml-test submodule, and the 383 runnable tests all pass (the full 1,059 in the PR description include that submodule).

The release status is checked too: 0.15.1 (July 17, 2026) does **not** contain the fix — the published `items.py` still has the old getattr spelling, compared byte-for-byte; 0.15.2 (October 16, 2026) **does** — the fix commit is its ancestor (verified via compare), and the published package has the new branch. If you edit TOML configs in place with tomlkit, it is worth a glance at the version in your hand.

## Closing

"Style-preserving" is a promise worth one extra copy in memory: the value and the spelling are both data. This fix introduces nothing new — the escape table, the escape function, the type check all existed in the library, and `from_raw` had been doing exactly this — it only extends an invariant that already held on the construction path to the concatenation path.

The hole stood open for four years, until someone appended a quote to `"foo"`. Round-trip invariants have one peculiar property: they break only in composition, while every single-step test still passes on its own. So the habit truly worth keeping after such a fix is leaving a place for "read back what you wrote" — that is where the demo's document-level round-trip case came from.

The change is merged into tomlkit's mainline ([`61941de`](https://github.com/python-poetry/tomlkit/commit/61941deb3c7155e88d5f038148b33a599c04a530)).
