# `http://foo.bar/\n` passes jsonschema's format check, and `urllib` reads it as a different URL

`jsonschema.Draft202012Validator.FORMAT_CHECKER.conforms("http://foo.bar/\n", "uri")` returns `True`. Hand the same string to `urllib.parse.urlsplit` and the newline is quietly dropped, leaving `http://foo.bar/`; hand it to `http.client` and a request line containing the newline raises `InvalidURL`.

Three components, three opinions. And it is not only URI: `date-time`, `time`, `uri`, `uri-reference`, `iri`, `iri-reference` and `hostname` — seven formats — all accept one extra newline (U+000A) at the end. 4.26.0 (the current PyPI release) and `main` (2026-11-25) both give this result.

In JSON Schema, `format` is an annotation by default; these checks only run when a `format_checker` is handed to the validator. Everything below assumes format checking is already on.

## The official test suite already calls these values invalid

Between August and September 2026, [JSON-Schema-Test-Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite) added a "trailing newline is invalid" case to each of the seven formats: date-time [#959](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/959) (August 3), hostname [#1023](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1023) (August 4), iri [#1067](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1067) (August 13), uri-reference [#1083](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1083) and iri-reference [#1144](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1144) (August 24), time [#1135](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1135) (August 25), uri [#1169](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1169) (September 3). In October, hostname got one more case for whitespace ([#1226](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1226)). These PRs are one sweep: before them, the suite had no format case whose `data` contained a newline, and the shape that "looks right, isn't" — one extra newline at the end — had never been asserted.

The cases are short. The URI one is `"http://foo.bar/\n"` with `valid: false`; the date-time one is `"1985-04-12T23:20:50Z\n"` with `valid: false`. In the same file, the value without the newline is still `valid: true`. The problem the suite names is exactly the trailing `\n`, nothing else.

Hand those cases to `Draft202012Validator.FORMAT_CHECKER` in [jsonschema 4.26.0](https://pypi.org/project/jsonschema/4.26.0/) and this comes back:

| format | value in the suite | suite says | 4.26.0 says |
| --- | --- | --- | --- |
| `date-time` | `"1985-04-12T23:20:50Z\n"` | invalid | valid |
| `time` | `"08:30:06Z\n"` | invalid | valid |
| `hostname` | `"example.com\n"` | invalid | valid |
| `uri` | `"http://foo.bar/\n"` | invalid | valid |
| `uri-reference` | `"/p\n"` | invalid | valid |
| `iri` | `"http://ƒøø.ßår/\n"` | invalid | valid |
| `iri-reference` | `"/âππ\n"` | invalid | valid |

All seven come back valid — the opposite of the suite. On `main`, the last change to `_format.py` is `84bae0ea` on 2026-10-04; as of 2026-11-25 that is still the file on `main`, with no guard for the trailing newline.

## Three delegation chains, all ending in `$`

jsonschema does not write the grammar for any of these formats. `date-time` goes to `rfc3339-validator`; `time` prefixes the value with `1970-01-01T` and reuses the same chain; the four URI and IRI formats go to `rfc3987`; `hostname` goes to `fqdn`.

Three endings, one line each:

- `rfc3339_validator.py:32`, the last character of `RFC3339_REGEX` is `$`;
- `rfc3987.py:424`, `get_compiled_pattern('^%%(%s)s$' % rule).match(string)`;
- `fqdn/__init__.py:30`, `PREFERRED_NAME_SYNTAX_REGEXSTR` ends with `[.]?$`.

Three packages, three periods of time, one and the same shape. Nobody copied anybody; the reason is what `$` means in Python's regular expressions.

![`$` stops before the newline; `\Z` demands the real end](assets/dollar-vs-Z.png)

## `$` is not the end of the string

In [Python's `re`](https://docs.python.org/3/library/re.html#regular-expression-syntax), `$` matches "the end of the string, or just before a newline at the end of the string". So:

```python
import re
re.match(r"^1985-04-12T23:20:50Z$",  "1985-04-12T23:20:50Z\n")  # match
re.match(r"^1985-04-12T23:20:50Z\Z", "1985-04-12T23:20:50Z\n")  # None
re.fullmatch(r"1985-04-12T23:20:50Z", "1985-04-12T23:20:50Z\n") # None
```

The `$` anchor lands between `Z` and `\n`; the regex succeeds once it has eaten `Z`, and the newline stays outside the match. `\Z` accepts only the real end of the string, and the newline has not been consumed, so the match fails.

That explains two details that are easy to miss. First, a value ending in `\r\n` is rejected: `$` knows only about `\n`, the `\r` sits in front of the anchor and the regex cannot eat it. Second, one extra space in front is also rejected, because `^` is immediately followed by a four-digit year. The only shape let through is exactly one `\n` at the very end — an asymmetric one.

Under `re.MULTILINE`, `$` also matches every line end, which is wider still. None of the three chains sets `MULTILINE`, so only the final newline leaks through.

Starting with Python 3.14 the standard library has [`\z`](https://docs.python.org/3/library/re.html#regular-expression-syntax), documented as matching only at the end of the string, with `\Z` kept as a compatibility alias. The `$` written in these three packages is the old spelling, and its meaning on 3.14 has not changed — it still stops before a trailing newline.

## Counterexamples in the same library

Not every format in jsonschema behaves this way. Inside the same `_format.py`:

`date` uses `_RE_DATE.fullmatch` and then hands the string to `date.fromisoformat`; `uuid` parses with `UUID()` and then checks the positions of the four hyphens; `duration` goes to `isoduration.parse_duration` and finally requires the value to end in one of `D`, `M`, `Y`, `W`, `H`, `S`. All three reject the trailing newline in the matrix above.

`duration` is worth a look: it blocks the newline not by checking for a newline, but because "the last character must be a unit letter" rules `\n` out. In one library, ending with `fullmatch`, delegating to a real parser, or adding one final condition all give a different result; the three chains ending in `$` all let it through.

`email` goes the other way: jsonschema's `is_email` only checks that the string contains an `@`, which is wider than `$` — the suite's `"test@iana.org\n"` case is invalid there too, jsonschema accepts it, and it accepts a great deal more than that one.

## What the downstream sees

Values like these are rarely typed by hand. Reading a file line by line, `readline()` brings the `\n` back with the line; output captured from `subprocess`, a log field split by lines, a config value copied from somewhere — all can arrive as "value plus newline". Once the validator has passed them, the components that actually consume them are not so forgiving:

| Consumer | Input | Result |
| --- | --- | --- |
| jsonschema `format: uri` | `http://foo.bar/\n` | passes |
| `urllib.parse.urlsplit` | same | `path` is `/`, `geturl()` is `http://foo.bar/` (newline deleted) |
| `http.client.putrequest` | request target `/\n` | `InvalidURL: URL can't contain control characters` |
| `http.client.putheader` | header value `example.com\n` | `ValueError: Invalid header value` |
| `datetime.fromisoformat` | `1985-04-12T23:20:50Z\n` | `ValueError: Invalid isoformat string` |
| `json.dumps` | any value with a trailing newline | escaped to `\\n`, invisible in logs |

The `urlsplit` row is the one worth keeping: before parsing it deletes three bytes — `\t`, `\r`, `\n` ([`_UNSAFE_URL_BYTES_TO_REMOVE`](https://github.com/python/cpython/blob/main/Lib/urllib/parse.py), there to match browser tolerance). So `"http://foo.bar/a\nb"` parses as `http://foo.bar/ab` — **what follows the slash has changed**. Not an error: it quietly becomes another URL. The validator sees A, the downstream gets B.

The `json.dumps` row explains why values like this are hard to spot in logs: the newline is escaped into the two characters `\n`, and the log line is one complete JSON document.

## Check your own setup

To see whether this road exists in your service, the direct way is to run all seven formats with the bare value and with the newline:

```python
from jsonschema import Draft202012Validator

FC = Draft202012Validator.FORMAT_CHECKER
CASES = {
    "date-time": "1985-04-12T23:20:50Z",
    "time": "08:30:06Z",
    "hostname": "example.com",
    "uri": "http://foo.bar/",
    "uri-reference": "/p",
    "iri": "http://ƒøø.ßår/",
    "iri-reference": "/âππ",
}
for fmt, value in CASES.items():
    v = Draft202012Validator({"format": fmt}, format_checker=FC)
    print(fmt, v.is_valid(value), v.is_valid(value + "\n"))
```

On the current release, the second column is `True` on all seven rows. The same 14 cases live in this repository under `格式尾随换行_jsonschema/trailing_newline_demo/`; `run.py --test` prints the "as released" and "with a one-line guard" results side by side.

One detail that trips people up: `FormatChecker()` and `Draft202012Validator.FORMAT_CHECKER` are not the same set. The former copies the class-level registry, where a later registration of the same name wins, so `time` lands on draft3's `%H:%M:%S` parsing; the latter registers per draft, so `time` is the RFC 3339 chain. Use the latter for a check like this, or a validator that already has a `format_checker`.

## How to fix it

There are two granularities. One is to change the ending from `$` to `\Z` (or `fullmatch`) in each of the three packages; the other is one shape guard in `jsonschema/_format.py` in front of the delegation, shared by all seven formats. The second is more contained, because the three packages move on different schedules, while the suite has already tightened ahead of them.

Changing `$` to `\Z` is the smallest edit: `rfc3987` builds its pattern as `'^%%(%s)s$'`, so it is one character at the end; `fqdn` has two patterns (one allowing underscores), and both need it. `fullmatch` is more thorough but also requires dropping the leading `^`, which is more work for a composed pattern. The shape guard leaves the upstream packages alone and adds one `endswith` check beforehand — at the cost of remembering it at every delegation point.

The release cadence of the three packages also decides which side to fix on: [rfc3987](https://pypi.org/project/rfc3987/)'s last release, 1.3.8, is from 2018; [rfc3339-validator](https://pypi.org/project/rfc3339-validator/)'s 0.1.4 is from 2021; [fqdn](https://pypi.org/project/fqdn/)'s 1.6.0 came out in September 2026. Asking two packages that have not moved in years to cut a release for this edge is not realistic.

Inside `trailing_newline_demo/run.py --test` the two sets look like this:

- as released, all 14 cases — each bare value and the same value plus a newline, across seven formats — are accepted;
- with one `value.endswith("\n")` in front of each delegation, the seven bare values are still accepted and the seven with a newline are all rejected.

When both hold, it prints `ALL PASS`. The project vendors the released files of the three packages (rfc3339-validator 0.1.4, rfc3987 1.3.8, fqdn 1.6.0) with their licences; the same 14 cases run through the real jsonschema 4.26.0 give the same verdict, row for row.

Upstream: `python-jsonschema/jsonschema`, [#1588](https://github.com/python-jsonschema/jsonschema/issues/1588) (opened 2026-10-14; still unfixed in 4.26.0 and on `main`).
