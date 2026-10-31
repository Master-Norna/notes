# I installed an accelerator, and the same rule stopped matching

`SECRET` should match. The result was `False`.

There was nothing wrong with the rule. The expression was `^secret$`, explicitly compiled to ignore case:

```python
import re
from pathspec import PathSpec, RegexPattern

pattern = RegexPattern(re.compile('^secret$', re.I), include=True)
spec = PathSpec([pattern])
print(spec.match_file('SECRET'))
```

In the pre-fix Pathspec code, forcing Python's `simple` backend produced `True`. With an importable RE2 installation, the default backend became RE2, and the answer became `False`. Explicitly selecting Hyperscan missed the match too.

Installing an optional accelerator had changed the answer, not just the execution path.

That was the problem I fixed in [python-pathspec #151](https://github.com/cpburnz/python-pathspec/pull/151). My first draft restored the answer by falling back to Python when it encountered flags like these. The maintainer asked for a different approach: if the native engine could represent the flags, why give up on it?

## 1. A compiled regex crosses the boundary as text

Pathspec compiles a collection of rules into a matcher that determines which paths match. Python's regex engine is not its only execution path: it also supports native RE2 and Hyperscan backends. Before the fix, the [default selection logic](https://github.com/cpburnz/python-pathspec/blob/88a9b711e0120a1eb16d5627fb68d15e3187c6ad/pathspec/_backends/agg.py#L39-L49) was straightforward: use RE2 if available, otherwise try Hyperscan, then fall back to simple.

For ordinary rules, that is convenient. Install an optional library and switch backends without changing every call site. But the input is not always a string waiting to be compiled. `RegexPattern` also [accepts an already compiled regex object](https://github.com/cpburnz/python-pathspec/blob/88a9b711e0120a1eb16d5627fb68d15e3187c6ad/pathspec/pattern.py#L138-L142).

The object in the opening example carries two pieces of information:

```python
regex = re.compile('^secret$', re.I)
regex.pattern       # '^secret$'
bool(regex.flags & re.I)  # True
```

The expression text says nothing about ignoring case. That requirement lives in `.flags`. Take only `.pattern` and compile it again, and the new regex is case-sensitive.

The simple backend [calls `regex.search(file)` on the original object](https://github.com/cpburnz/python-pathspec/blob/88a9b711e0120a1eb16d5627fb68d15e3187c6ad/pathspec/pattern.py#L214-L218), so the flags survive. The pre-fix RE2 backend instead [extracts `pattern.regex.pattern`](https://github.com/cpburnz/python-pathspec/blob/88a9b711e0120a1eb16d5627fb68d15e3187c6ad/pathspec/_backends/re2/pathspec.py#L134-L152) and hands it to another engine to compile. Hyperscan's [corresponding path](https://github.com/cpburnz/python-pathspec/blob/88a9b711e0120a1eb16d5627fb68d15e3187c6ad/pathspec/_backends/hyperscan/pathspec.py#L150-L165) did the same thing.

**The expression survived; the requirements used to compile it did not.**

Case sensitivity is only one consequence. `re.M` makes `^` and `$` recognize line boundaries; `re.S` lets a dot match a newline. Leave those requirements out of the handoff, and the same text means something different in the new engine.

## 2. The first draft fixed the answer by avoiding native execution

My initial strategy was conservative: if a flag was not expressed in the pattern text, the native backend should not take over.

The [detection function, `has_regex_flags()`](https://github.com/cpburnz/python-pathspec/blob/21e4342c73fd02be6458b9b2353e9f63fa1824a0/pathspec/_backends/_utils.py#L22-L56), compiled `.pattern` again with Python and compared the new object's flags with the original object's. For example, `(?i)^secret$` already encodes case-insensitive matching in its text; the presence of `re.I` alone should not force a fallback. With `re.compile('^secret$', re.I)`, however, the flag is external to the text, so the comparison detects a difference.

The draft then took one of two paths:

- With automatic `best` selection, use simple for the entire rule set.
- With an explicit `re2` or `hyperscan` request, raise `ValueError` and suggest simple.

That restored the correct result for the default call in the opening example, without pretending the native engines could preserve every flag. But even ordinary case-insensitive matching fell back to Python, despite both native engines being able to express it.

The maintainer pointed this out in a [comment](https://github.com/cpburnz/python-pathspec/pull/151#issuecomment-6098537091):

> I don't think `has_regex_flags()` is the right approach.

The request was not to add more branches to the detector. Instead of recompiling to detect flags and then backing out, the fix should translate `.flags` into global inline flags understood by the native engines. For example, `re.I | re.S` could become a `(?is)` prefix.

That changed the direction of the patch. The draft answered “How do we avoid losing flags?” The final version also had to answer “Which flags can we carry into native execution?”

## 3. Python's flag names are not a translation table

Case-insensitive matching can be written as `(?i)`, multiline matching as `(?m)`, and dot-all matching as `(?s)`. The final patch [maps these three flags to an `ims` prefix](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/pathspec/_backends/_utils.py#L33-L113) and applies it where the native backend rebuilds the expression:

```python
regex = translate_regex_flags(
    translate_end_anchor(pattern.regex.pattern),
    get_regex_flags(pattern.regex),
)
```

This excerpt comes from the [merged RE2 path](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/pathspec/_backends/re2/pathspec.py#L144-L149). For the opening example, the native engine now receives `(?i)^secret$`, not just `^secret$`.

But copying every Python flag name into a prefix would be wrong. Python's `re.UNICODE`, for instance, cannot simply become `(?U)`: in [RE2's syntax table](https://github.com/google/re2/blob/927f5d53caf8111721e734cf24724686bb745f55/doc/syntax.txt#L64-L69), `U` means ungreedy mode, something entirely different. Python's str regexes normally carry `re.UNICODE` implicitly; the final implementation adds no prefix for it. Nor does that make the native engines' existing Unicode character classes or case-folding behavior identical to Python's.

`VERBOSE` makes the boundary clearer. In Python, this regex ignores the whitespace in the expression:

```python
re.compile('^S E C R E T$', re.X)
```

It should therefore match `SECRET`. But RE2 has no `(?x)`. Hyperscan supports some related syntax, but cannot accept every Python VERBOSE expression unchanged either. My [revision reply](https://github.com/cpburnz/python-pathspec/pull/151#issuecomment-6103540982) records the API checks for both engines. Rather than maintain two VERBOSE translators in this patch, the final version uses the same fallback-or-error policy for both native backends.

The final [support check](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/pathspec/_backends/_utils.py#L68-L86) also rejects `LOCALE`, unknown flag bits, and the combination `ASCII | IGNORECASE`. `UNICODE` and `DEBUG` add no prefix; `ASCII` alone relies on the current native engines' character-class behavior. Only the translatable flags form the `(?ims)` prefix. This patch repairs the handoff of compilation flags. It is not a compiler that losslessly translates Python regexes into other regex languages.

**The final version keeps fallback, but reserves it for flags it cannot preserve.**

For `re.compile('^secret$', re.I)` matched against `SECRET`, the three strategies are:

| Revision | What crosses the boundary | Automatic selection and result |
|---|---|---|
| Before the fix | Only `.pattern`: `^secret$` | RE2, `False` |
| First draft | Detect flags external to the text | Fall back to simple, `True` |
| Merged fix | Translate `.pattern` and `.flags`: `(?i)^secret$` | Keep RE2, `True` |

Here, `i` is a flag the native engines can express. For unsupported flags such as `VERBOSE`, the merged version falls back to simple for the entire spec under `best`, or raises `ValueError` for an explicit `re2` or `hyperscan` request.

## 4. Another patch landed while the PR was still open

During the revision, a small piece of code disappeared from the diff.

Besides handling flags, the draft had [hardened `PathSpec.__iadd__`](https://github.com/cpburnz/python-pathspec/blob/21e4342c73fd02be6458b9b2353e9f63fa1824a0/pathspec/pathspec.py#L142-L154). When combining rules with `+=`, it built the new pattern list and backend first, then replaced the object's state only after both succeeded.

The connection to this bug was backend construction: it can fail. If the pattern list is written back to the object before the matcher is built, an exception can leave the object holding new rules but still using its old matcher. Once the draft introduced errors for explicit native-backend requests, that failure boundary also needed attention.

While #151 was still open, however, another contributor, Larry-Labs, fixed that state-consistency problem in [#159](https://github.com/cpburnz/python-pathspec/pull/159), which reached the main branch first, on October 10. In my revision reply, I explicitly noted that #159 had landed and removed the overlapping `+=` changes.

This was not a separate PR spun out of the flags fix, nor the removal of the `+=` feature. Two fixes had met at the same failure boundary. Once one patch put the state updates in the right order, the other no longer needed to carry the same hardening through to merge.

What remained in #151 was flag translation, backend selection, and the corresponding regression tests. The maintainer subsequently [accepted the revision](https://github.com/cpburnz/python-pathspec/pull/151#issuecomment-6104819335), and the PR was merged on October 11, 2026.

## 5. A `True` result does not distinguish the two fixes

Reproducing this fix requires more than checking whether the final match becomes `True`.

The draft's default call returned `True` too, but used simple. The final version should retain a native backend for flags it can express. The [offline reproduction project](flags_demo/README.md) therefore runs three pinned source snapshots in separate processes, actually loads RE2 and Hyperscan, and records both the match result and the selected backend.

For the opening case-insensitive example:

| Backend request | Before the fix | First draft | Merged fix |
|---|---|---|---|
| simple | True, simple | True, simple | True, simple |
| Automatic best | False, RE2 | True, simple | True, RE2 |
| Explicit RE2 | False | ValueError | True |
| Explicit Hyperscan | False | ValueError | True |

The automatic choices here come from the reproduction environment: Windows x64 / Python 3.12, with both pinned native dependencies importable, so best prefers RE2. The string matrix covers 16 scenarios across two spec classes, five backend requests, and three source snapshots: 480 construction-and-behavior checks, including expected rejection paths. The table above is one scenario from that matrix.

The draft is an actual commit recovered from before a force-push. The pre-fix baseline is the merge commit's first parent. These snapshots compare three strategies; they are not three released versions.

Switch to `VERBOSE`, and the merged version automatically selects simple and matches correctly. Explicitly request either native backend, and it raises `ValueError` suggesting simple. That differs from the case-insensitive example precisely because it is the distinction the patch is meant to preserve.

The [selector](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/pathspec/_backends/agg.py#L87-L106) makes the fallback decision while constructing the entire spec; it does not quietly switch one rule to a different engine. For an explicit request, the [native constructor](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/pathspec/_backends/re2/pathspec.py#L67-L71) reports that it cannot preserve the flags instead of overriding the caller's choice.

The patch also has to cover two easily missed handoff paths. A bytes expression needs a bytes prefix. And GitIgnoreSpec's directory-marker handling splits a pattern into multiple expressions; carrying the flags into only one of them is not enough. The merged [regression tests](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/tests/test_08_regex_flags.py#L167-L259) check bytes prefixes, directory precedence, and ordinary patterns continuing to use native backends. The split expressions each receive their flags [inside the loop](https://github.com/cpburnz/python-pathspec/blob/157bccfbc24777aed9330223a546487b0f3d7f1b/pathspec/_backends/re2/gitignore.py#L90-L127).

## 6. “Best” has to ask more than what is installed

From the opening example alone, this looks like a small missing-argument fix: carry the flags alongside the expression.

Following the PR reveals two decisions that shaped the result. First, the maintainer redirected “back out whenever flags live outside the text” toward “keep native execution for flags we can express.” Second, once another patch had handled the overlapping state update, this PR dropped that part. The final solution neither stopped at the most conservative answer nor grew indefinitely to support every mode.

**Automatic backend selection must consider not only which engine is available, but whether it can preserve the flags carried by this input.**

Otherwise, the same rule and the same call can change from a match to a miss merely because another library is installed. An accelerator should change how the work is done, not silently discard requirements the caller has already specified.

---

### Source and reproduction

- Main fix: [python-pathspec #151](https://github.com/cpburnz/python-pathspec/pull/151); overlapping `+=` hardening: [#159](https://github.com/cpburnz/python-pathspec/pull/159).
- Before: [`88a9b71`](https://github.com/cpburnz/python-pathspec/tree/88a9b711e0120a1eb16d5627fb68d15e3187c6ad); draft: [`21e4342`](https://github.com/cpburnz/python-pathspec/tree/21e4342c73fd02be6458b9b2353e9f63fa1824a0); merged: [`157bccf`](https://github.com/cpburnz/python-pathspec/tree/157bccfbc24777aed9330223a546487b0f3d7f1b).
- [flags_demo: three real source snapshots, one-time preparation, and offline execution](flags_demo/README.md). Native dependencies are pinned to `google-re2==1.1.20251105` and `hyperscan==0.9.1`. This article makes no performance comparison.
