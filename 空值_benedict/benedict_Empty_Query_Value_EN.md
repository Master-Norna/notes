# `a=` and no `a` differ by one empty string

One query-string round trip:

```python
from benedict import benedict

benedict({"a": ""}).to_query_string()   # 'a='
benedict.from_query_string("a=")        # {}   ← before the fix
```

The encoding side writes `{"a": ""}` as `a=`; the decoding side reads `a=` as "there is no such key". Same library, two directions, two opinions about an empty value.

It shows up more often mixed into a longer string:

```python
benedict.from_query_string("a=&b=2")    # {'b': '2'}            ← before the fix
benedict.from_query_string("a=&b=2")    # {'a': '', 'b': '2'}   ← after the fix
```

[python-benedict #604](https://github.com/fabiocaccamo/python-benedict/pull/604), one line changed: `parse_qs` now gets `keep_blank_values=True` — the parameter defaults to `False`.

## `a` and `a=` are two different things

In a query string, `a` is a bare key name with no equals sign, and benedict rejects it outright (that is the `missing_equals` case below); `a=` has a key, has the equals sign, and its value is the empty string. An optional form field left blank, a search box cleared but still submitted — what goes out is the second kind. `urlencode({"a": ""})` also emits `a=`, rather than dropping the key.

benedict's encoder is `urlencode`:

```python
data = urlencode(d, **kwargs)
```

The outgoing side has no ambiguity. The whole problem is on the way back.

The standard library hands the choice to the caller. The `parse_qs` docs say it plainly: with `keep_blank_values` true, blank values in a percent-encoded query are kept as empty strings; with it false (the default), blank values are ignored as if the key were not present. Python does not decide which semantics is right — it asks you to pick a side before reading.

## The validator lets it through, the parser drops it

`QueryStringSerializer.decode` does the work in two steps (`benedict/serializers/query_string.py:59`). The first validates the string piece by piece with a regex:

```python
pair_re = re.compile(r"^[^\s=&]+=[^\s&]*$")
pairs = s.split("&")
if pairs and not pairs[-1]:
    pairs = pairs[:-1]
if all(pair_re.match(pair) for pair in pairs):
    data = parse_qs(s)          # the parent commit; the merge has keep_blank_values=True here
    return self._parse_bracket_notation(data)
raise ValueError(f"Invalid query string: {s}")
```

The `*` after `=` allows zero characters, so `a=` gets through. The comment above the regex says a value only has to avoid whitespace and `&`, with no minimum length. The intent on this side is to keep. The same block also lets `pairs[:-1]` wave through a stray trailing `&` — `a=1&` has always counted as valid.

The second step calls `parse_qs(s)` with the library default. `keep_blank_values=False`, so keys with empty values never reach the result.

The same input: the first step calls it valid, the second throws it away.

So `a=` yields `{}`. Nested forms behave the same way: `a[b]=&a[c]=2` leaves only `{'a': {'c': '2'}}`.

## The fix lands on the second call

The merged version changes one line (`:76`), with a comment above it noting that `pair_re` already accepts empty values and keeping them is what makes the two steps agree:

```python
data = parse_qs(s, keep_blank_values=True)
```

`parse_qs` now parses `a=` as `{'a': ['']}`, and `_parse_bracket_notation` takes `values[0]` for a plain key:

```python
else:
    result[key] = values[0]
```

Which gives `''`. Nested keys take the other branch, so `a[b]=` becomes `{'a': {'b': ''}}`. That function did not change by a line, and the docstring line saying a plain key always returns a scalar string still holds.

There is another way to line the two up: make `pair_re` reject empty values, siding with `parse_qs`'s default. The cost is that `a=` then counts as an invalid query string, while `benedict({"a": ""}).to_query_string()` produces exactly that — the encoder's output, refused by the decoder. This PR went the other way: the parser follows the validator.

## Eight inputs

```text
== empty_and_value     before {'b': '2'}            after {'a': '', 'b': '2'}
== single_empty        before {}                    after {'a': ''}
== trailing_empty      before {'a': '1'}            after {'a': '1', 'b': ''}
== roundtrip_empty     before decoded {}            after decoded {'a': ''}
== roundtrip_mixed     before decoded {'b': '2'}    after decoded {'a': '', 'b': '2'}
== encoded_space       before {'a': ' ', 'b': ' '}  after {'a': ' ', 'b': ' '}
== bracket_empty       before {'a': {'c': '2'}}     after {'a': {'b': '', 'c': '2'}}
== missing_equals      before ValueError            after ValueError
```

`encoded_space` is `a=%20&b=+`; both versions decode to spaces, since `keep_blank_values` does not touch percent-decoding. `missing_equals` is `a&b=2`; both versions raise `ValueError` — the fix did not relax the rule that every key needs an equals sign. `roundtrip_empty` is the most direct acceptance check: `{'a': ''}` encodes to `a=` and decodes back to `{'a': ''}`. `bracket_empty` shows empty values inside brackets are kept too.

The genuinely surprising case is the same key appearing twice. `a=&a=1` gives `{'a': '1'}` before the fix and `{'a': ''}` after. `_parse_bracket_notation` has always taken `values[0]`: before the fix the first value was the empty string that `parse_qs` dropped, so the later `1` moved up; after the fix the first value survives. Order starts to matter for the first time.

Array syntax is outside this change. `a[]=` is `{}` before and `{'a': ['']}` after — a list, not a string, taking `_parse_bracket_notation`'s array branch. That is existing behaviour, untouched here and not asserted in `--test`. That case and `a=1&` (trailing empty segment; `{'a': '1'}` in both versions) come from separate probes rather than from the eight above.

`--test` asserts case by case, against these same JSON values. The `missing_equals` case only asserts that both versions fail (`ok` is false); the message, `Invalid query string: a&b=2` in both, was checked by eye and is not part of the assertion.

## The blast radius is one path

benedict has two entry points for reading a query string:

```python
benedict.from_query_string("a=&b=2")          # the static method
benedict("a=&b=2", format="query_string")     # the constructor
```

The second one delegates to the first (`from_query_string` in `io_dict.py` is `cls(s, format="query_string")`), so one fix covers both. The JSON, YAML, TOML and XML serializers do not go through this code, and empty strings never had a "treated as missing" rule in them anyway.

Code that relied on the old behaviour will see extra keys. Before the fix, empty-value semantics meant preprocessing by hand — swap `a=` for a placeholder, read, swap back, or skip benedict and call `parse_qs(s, keep_blank_values=True)` directly. After the fix that detour is unnecessary, at the cost of `a=&b=2` going from `{'b': '2'}` to `{'a': '', 'b': '2'}`. A deliberate behaviour change.

On a concrete call, what differs is this line: `d.get("a", "default")`. Before the fix it returns `'default'`, `"a" in d` is `False`, and the dict has length 1; after, it returns `''`, `"a" in d` is `True`, and the length is 2. A default value and an empty string are two different branches in any API where "the parameter was not supplied" and "the parameter was supplied empty" need separate handling.

## All three steps return normally

`a=` arrives, the regex passes, `parse_qs` returns `{}`, `_parse_bracket_notation` returns an empty dict for an empty dict, and `decode` returns. No exception, no warning, not a single log line.

Each component is reasonable on its own: the author of `pair_re` wanted to keep empty values, the default of `parse_qs` filters them out; put both in one function and neither is wrong. The break is in the round trip — what the encoder writes, the decoder cannot read back. That kind of error does not announce itself unless a test happens to cover the empty-value cell.

The PR's Related issue field says None: the inconsistency was found by reading code, not reported as a bug. The regression test added is `test_from_query_string_with_empty_values`, placed right after the existing `test_from_query_string_with_trailing_ampersand` — first "a trailing `&` is also valid", then "an empty value is also a value", which lines up nicely. The test asserts three things: the static method reads `{'a': '', 'b': '2'}`; the constructor `benedict("a=&b=2", format="query_string")` does the same; and `to_query_string()` on the result is still `a=&b=2`.

There is also an API that is easy to reach for by mistake: `parse_qsl`. It returns a list of pairs, drops blank values by default too, and takes the same `keep_blank_values` parameter. This change only touched the `parse_qs` call; if someone later swaps the implementation for `parse_qsl`, the parameter has to travel with it, or the same bug comes back in a different spot.

The patch adds 19 lines including tests; the production change is one line.

## Reproducing

The project lives in `空值_benedict/query_blank_demo/`, with the `benedict/` package from parent `c36e48c6` and merge `5cb4922f` sitting untouched in `vendor/before` and `vendor/after`. Every case starts a subprocess whose `sys.path` points at exactly one version; input goes in as JSON and results come back as JSON, then both versions are compared key by key. `--json` writes this run's results and both commit hashes to a file for the record:

```text
python run.py --test
```

Running needs benedict's runtime dependencies (`python-slugify`, `typing_extensions`, plus `openpyxl`, `xlrd`, `PyYAML`, `tomli-w`, `ftfy` and friends, which get pulled in when the serializers are imported — see the project README). `--test` asserts: the four empty-value inputs lose their key before the fix and keep it after; `encoded_space` matches in both; `missing_equals` raises in both; nested empty values survive.

## References

- python-benedict PR [#604](https://github.com/fabiocaccamo/python-benedict/pull/604); parent commit [`c36e48c6`](https://github.com/fabiocaccamo/python-benedict/commit/c36e48c6a6b6ef60c6dbf4e0572d23efcb545ab5), merge commit [`5cb4922f`](https://github.com/fabiocaccamo/python-benedict/commit/5cb4922f285baddf9c9ee1612a67a0ef1d370efb).
- Changed files: [`benedict/serializers/query_string.py`](https://github.com/fabiocaccamo/python-benedict/blob/5cb4922f285baddf9c9ee1612a67a0ef1d370efb/benedict/serializers/query_string.py), [`tests/dicts/io/test_io_dict_query_string.py`](https://github.com/fabiocaccamo/python-benedict/blob/5cb4922f285baddf9c9ee1612a67a0ef1d370efb/tests/dicts/io/test_io_dict_query_string.py).
- The standard library: [`urllib.parse.parse_qs`](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.parse_qs), [`urllib.parse.urlencode`](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlencode).
