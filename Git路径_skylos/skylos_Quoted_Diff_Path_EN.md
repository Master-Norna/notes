# Git quoted the path, and the file dropped out of review

A change that deletes `@login_required` can pass straight through a skylos PR review: the file is in the changed list, the review is posted, and the comments contain no security regression.

The same `git diff` is parsed in two places inside skylos. [`get_changed_line_ranges`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L299) picks the lines the change touches, and the findings the scanner turns up are filtered against them; [`_get_per_file_diffs`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L427) splits the diff by file and hands each piece to [`detect_security_regressions`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/rules/quality/regression.py#L193), which looks at whether a control such as `@login_required` was deleted. `get_changed_line_ranges` resolves paths through `_new_diff_header_path`; `_get_per_file_diffs` slices `line[6:]` directly. The second one is the one that misreads.

So the changed ranges are right, ordinary findings are there, and only the security branch gets no input. That column in the report is empty, and empty and clean are indistinguishable in the output.

`skylos cicd review` goes through this reading on every PR. In 5.4.0 (2026-11-02) it is still `text=True` plus `line[6:]`; the fix shows up in the [5.5.0](https://github.com/duriantaco/skylos/releases/tag/v5.5.0) release notes (2026-11-10).

## `text=True` and `line[6:]`

In `skylos/cicd/review.py` at parent commit `7cf919a1`, `_get_per_file_diffs` runs one `git diff` and splits the output by line:

```python
result = subprocess.run(diff_cmd, ..., text=True)
for line in result.stdout.splitlines():
    if line.startswith("diff --git"):
        ...
    elif line.startswith("+++ b/"):
        current_file = line[6:]
```

Two assumptions. After `+++` there is always `b/`, and the path starts at the sixth character; and the stdout that `text=True` hands back always decodes in the current locale ([it decodes with `locale.getpreferredencoding()`](https://docs.python.org/3/library/subprocess.html#subprocess.run)), while `subprocess` reads with [universal newlines](https://docs.python.org/3/library/io.html#io.TextIOWrapper), so `\r`, `\n` and `\r\n` all end a line.

[`_parse_unified_diff`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L373) in the merged version of the same file makes neither assumption. Its [`_new_diff_header_path`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L410) handles Git's C-style quoting, the TAB suffix and `/dev/null`; `get_changed_line_ranges` also reads bytes and decodes explicitly. One diff format, two readings, side by side.

## The diff is read twice

In a single `skylos cicd review`, [`run_pr_review`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L48) reads the diff once, `get_changed_line_ranges(diff_base, cwd=review_root, ...)`. The ranges that come back filter the findings the scanner produced over the whole tree — only those on changed lines stay, through [`filter_findings_to_diff`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L529). The second read is for security regressions, `_detect_regressions_from_diff(diff_base, ...)`: it needs each file's own diff text to see that a control such as `@login_required` was deleted, and `_get_per_file_diffs` is what serves that step. The two commands do not even share a `--unified` value: `get_changed_line_ranges` passes `--unified=0`, since it only wants line numbers; `_get_per_file_diffs` passes `--unified=3`, since it needs the context to see a decorator go.

Both chains end up in one comment: the second read misreads, so security regressions get no input; the first does not, so ordinary findings arrive as usual.

## Five shapes

In Git's diff output the `+++` line is not always `+++ b/path`. Change the filename a few ways and `git diff --unified=3 HEAD~1...HEAD` gives these raw bytes (Git 2.55, one temporary repository per case):

| filename | `core.quotePath=true` (default) | `core.quotePath=false` |
| --- | --- | --- |
| `cafe.py` | `+++ b/src/cafe.py` | same as left |
| `café.py` | `+++ "b/src/caf\303\251.py"` | `+++ b/src/café.py` |
| `中文名.py` | `+++ "b/src/\344\270\255\346\226\207\345\220\215.py"` | `+++ b/src/中文名.py` |
| `my views.py` | `+++ b/src/my views.py` `<TAB>` | same as left |

The last row ends with a real 0x09 byte. Turning off [`core.quotePath`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corequotePath) only removes the quotes and octal escapes around non-ASCII names; the TAB after a path with a space stays, because it is not an escape — it is the boundary Git draws for a name containing spaces. So changing the config is not a fix: that half cannot be changed, and neither can a fake file header inside a hunk nor a bare CR.

The PR lists four; with the decode failure there are five. The project in `Git路径_skylos/git_diff_paths_demo/` builds each one in a real Git repository and runs both versions of the functions verbatim.

`_detect_regressions_from_diff` iterates `file_diffs.items()` and calls `detect_security_regressions(diff_text, file_path)` once per file's diff text. If the dictionary has no entry for a file, no later step touches it.

### Non-ASCII bytes in the path

[`core.quotePath`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corequotePath) is on by default, and Git wraps a non-ASCII path in quotes with the bytes written in octal:

```text
+++ "b/src/vues_caf\303\251.py"
```

`line.startswith("+++ b/")` is false, and the file's diff is skipped whole. `get_changed_line_ranges` reads the same header through `_new_diff_header_path` and gets `src/vues_café.py`. The file is in the changed list and absent from the review.

### A space in the filename

After an unquoted path Git appends a TAB:

```text
+++ b/src/my views.py\t
```

`line[6:]` carries the TAB into the key. `file_diffs` gets `src/my views.py\t`, which no longer matches the PR's diff; and if a finding here is posted as an inline comment, the comment lands outside the diff.

### A hunk line that looks like a file header

A new JS template string contains:

```text
++ b/victim.js
```

which renders into the diff as `+++ b/victim.js`, one character away from a real file header. The old scan has no notion of being inside a hunk: it sees `+++ b/` and takes it for a new file. The whole hunk is filed under `victim.js`, and the change to `src/evil.js` disappears.

### A bare CR in the source

A test file has:

```python
note = "a\rdiff --git a/zz/zz b/zz/zz"
```

`\r` is an ordinary character in Python source; universal newlines under `text=True` treat it as a line boundary. In the diff Git emits, the line is split in two, and the second half starts at column zero:

```text
diff --git a/zz/zz b/zz/zz
```

The scanner sees a `diff --git` at column zero and believes a new file begins. The original file's hunk ends there, the deleted `@login_required` below falls into the "new file", and `src/app.py`'s diff is incomplete.

### Source bytes that are not UTF-8

A latin-1 source file puts `0xE9` into the diff. `text=True` decodes as the local locale (UTF-8) and fails on `0xE9`. The exception is not raised inside `run()` — reading happens on another thread, `result.stdout` becomes `None`, and the next line reports:

```text
AttributeError: 'NoneType' object has no attribute 'splitlines'
```

This time `skylos cicd review` stops before finishing.

## Three changes

Merge commit `380b2a3e` changes `review.py` by +18/−4, and it changes three things:

- No more `text=True`; the bytes come back and are decoded explicitly with `decode("utf-8", errors="replace")`. Bytes that are not UTF-8 become replacement characters, and the file's key and hunk survive.
- The `+++` handling goes through `_new_diff_header_path`. Quotes, TAB and `/dev/null` are already in the function, so none of it is written a second time.
- `in_hunk` is new: set on `@@`, cleared on `diff --git`. A `+++` inside a hunk is source code.

`_new_diff_header_path` is short, three rules written one after another:

```python
# Git appends a TAB after an unquoted name containing spaces. Literal
# filename tabs, newlines and quotes use Git's C-style quoted form.
path = raw.partition("\t")[0]
if path.startswith('"'):
    if len(path) < 2 or not path.endswith('"'):
        raise ValueError("Cannot compare changes: malformed quoted Git path")
    path = _unquote_c_style(path[1:-1])
if path == "/dev/null":
    return None
if not path.startswith("b/"):
    raise ValueError("Cannot compare changes: unsupported Git path header")
return path[2:]
```

The call site passes `line[4:]`, everything after `+++ `, and the function strips the `b/` itself. The TAB split comes first and the unquoting second, and the two forms exclude each other: a path with spaces is not quoted and ends with a TAB; a path with a TAB, a newline or a double quote is quoted, with everything inside escaped. `_unquote_c_style` lives in [`skylos/done/base.py`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/done/base.py); the single-character escapes `\t`, `\"`, `\\`, `\n` and the three-digit octal escapes each resolve on their own, and what comes out is bytes that are then decoded, so `"b/src/caf\303\251.py"` lands as `src/café.py`.

`text=True` also takes `errors="replace"`, but decoding is only one of the two problems: universal newlines remain, and a bare CR still conjures a fake header. Reading bytes and decoding them yourself splits lines on `\n` alone, settling both at once. The comment in the merge says `like get_changed_line_ranges` — the fix is to make this spot behave like that one.

`_new_diff_header_path` does not guess at shapes it does not know: a path that does not start with `b/`, a quote that does not close, both `raise ValueError`. The exception leaves the loop in `_get_per_file_diffs` and is caught by `run_pr_review`'s `except ValueError`, which prints `Skylos PR review unavailable` and exits 2. The review stops, but it does not finish with a report that is missing one file.

The PR's precision section says it "restores silently dropped findings and removes one malformed comment path".

## What the five scenarios return

The project lifts the four functions out of both versions of `review.py` verbatim and runs five scenarios in a real Git repository. The merge's [`test/test_cicd_review_diff_paths.py`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/test/test_cicd_review_diff_paths.py) has four cases, one for each of the first four shapes. `--test` output:

| scenario | parent `_get_per_file_diffs` | merged |
| --- | --- | --- |
| `vues_café.py` | `{}` | `src/vues_café.py` |
| `my views.py` | `src/my views.py\t` | `src/my views.py` |
| `++ b/victim.js` in a hunk | `victim.js` | `src/evil.js` |
| bare CR | `src/app.py` (hunk truncated) | `src/app.py` (complete) |
| latin-1 source bytes | `AttributeError` | `src/latin1.py` |

The first two rows are the wrong key, the third files the whole change under the wrong name, the fourth cuts the diff short, and the fifth takes the review down.

And the deleted decorator:

| scenario | parent sees `-@login_required` | merged |
| --- | --- | --- |
| `vues_café.py` | no (no diff at all) | yes |
| bare CR | no (hunk truncated) | yes |
| latin-1 source bytes | no (exception) | yes |

`get_changed_line_ranges` is right in all five — it goes through the other parser. The problem is not Git, and not the rule.

Run it without `--test` and the output is two dictionaries per scenario. Two of them:

```console
$ python -B Git路径_skylos/git_diff_paths_demo/run.py
## quoted_non_ascii_path (vues_café.py)
parent: {'files': [], 'removed': {}, 'complete': False}
merged: {'files': ['src/vues_café.py'], 'removed': {'src/vues_café.py': ['-@login_required']}, 'complete': True}

## unquoted_path_with_space (my views.py)
parent: {'files': ['src/my views.py\t'], 'removed': {'src/my views.py\t': ['-@login_required']}, 'complete': True}
merged: {'files': ['src/my views.py'], 'removed': {'src/my views.py': ['-@login_required']}, 'complete': True}
```

`complete` is the script's own criterion: whether the deleted lines contain `@login_required`.

The first dictionary is the cleanest sample of this bug. The parent has `files` empty and `removed` empty, so `detect_security_regressions` is never called even once; and the file itself is inside `get_changed_line_ranges`' changed ranges, so the ordinary findings the scanner turns up on it are reported as usual. One file, a conclusion on one side and none on the other.

The second dictionary is the opposite case: the parent sees the file and sees the deleted decorator, and the key just carries one extra TAB. The finding is still there; the path is what is wrong — the next consumer takes it to GitHub's diff to find a position and finds nothing.

## The comment lands outside the diff

All three key errors end in the same place: `_post_pr_review` looks up the position in the diff by path — [GitHub's comments API](https://docs.github.com/en/rest/pulls/comments) wants `path` and `position`, and both have to match a file in the diff. With a key of `src/my views.py\t` or `victim.js`, GitHub's diff has no such path, and the comment goes out carrying a position outside the diff. The PR body calls this class "posted as a comment path outside the diff".

Worse than a misplaced comment is no comment at all. A file with a non-ASCII path sits in the changed list, and the conclusion is "nothing wrong"; a file with a bare CR is reviewed halfway, and the rest of the hunk is discarded as a new file. When a tool like this does not fail, nobody goes to look at whether that column is empty or right.

## Which repositories hit this

Having skylos installed is not enough. `skylos .` scans the working tree, and in the whole package `_get_per_file_diffs` is defined in one place and called in one place, both in `review.py`; `skylos done` has its own diff reading, and `_unquote_c_style` was borrowed from it in the first place. What walks this chain is `skylos cicd review`, the PR gate that [`skylos cicd init`](https://github.com/duriantaco/skylos/blob/v5.6.0/docs/first-gated-pr.md) writes into `.github/workflows`.

Two commands show whether your own repository can hit it:

```console
$ git -c core.quotePath=false ls-files | LC_ALL=C grep '[^ -~]'   # non-ASCII paths
$ git ls-files | grep ' '                                        # paths with a space
```

The first needs `-c core.quotePath=false`; otherwise `ls-files` turns Chinese names into octal escapes itself and grep never matches. Both only cover the first two shapes: a hit means the repository has such a path, and it gets hit the time that path enters a PR's change. The last three — a line in a hunk that looks like a file header, a bare CR, source bytes that are not UTF-8 — cannot be found this way; that takes reading the source.

On versions, the line falls at 5.5.0 (version numbers and dates from [PyPI](https://pypi.org/project/skylos/#history) and the repository's releases):

| date | commit or version | the `get_changed_line_ranges` side | the `_get_per_file_diffs` side |
| --- | --- | --- | --- |
| 2026-11-02 | 5.4.0 | `+++ b/` plus `line[6:]` | `+++ b/` plus `line[6:]` |
| 2026-11-05 | `07265f6e` (#1172) | `_new_diff_header_path`, plus `in_hunk` | still `line[6:]` |
| 2026-11-09 | `380b2a3e` (#1196) | as on the left | `_new_diff_header_path` |
| 2026-11-10 | 5.5.0 | as above | as above |

The two readings have not always been like this. `_new_diff_header_path` came in with #1172, and that commit fixed `_parse_unified_diff` whole — bytes, `in_hunk`, the new function — while `_get_per_file_diffs` stayed where it was. Four days later #1196 fills in that one spot. 5.4.0 shipped before #1172, so in that version both chains are still `line[6:]`; only from 5.5.0 do they agree.

The matching line in the 5.5.0 release notes is `cicd: read the PR diff as bytes and parse Git's quoted paths (#1196)`. Which version you have, and what the copy you installed actually does, two commands will tell you:

```console
$ python -c "import skylos; print(skylos.__version__)"
$ python -c "import skylos, os; print(os.path.join(os.path.dirname(skylos.__file__), 'cicd', 'review.py'))"
```

Open the `review.py` it prints; if `_get_per_file_diffs` still has `text=True` and `line[6:]`, that copy is unfixed.

## Two parsers back into one

The five shapes look like five things to `if` on: unquote, strip the TAB, track hunk state, change how bytes are read. The first two are already written out in `_new_diff_header_path`, down to `/dev/null` (the `+++` of a deleted file) and malformed quotes; hunk state in `_parse_unified_diff` is that `in_hunk`. The parsing logic itself does not need to move; what has to move is `_get_per_file_diffs` back onto the same set.

One line from the PR:

> `get_changed_line_ranges` parsed the same diff correctly, so the file looked reviewed.

The file looked reviewed. The fix did not touch the report; it touched the few lines that read the diff.

Upstream added four tests for this behaviour, and the latin-1 case is not one of them. That one is fixed by `errors="replace"`, but the comment explains why bytes are read — universal newlines turn a bare CR into a fake header — and says nothing about the decode failure. The fifth shape can be built in the demo and has no matching line upstream.

The four tests assert `list(diffs)` to concrete paths first, and talk about findings second. Assert on findings alone and the test still passes on an empty result, with not one file split out. Same for your own checks: when a column is empty, first see whether it says which files it looked at; if it cannot say that, the pass only counts as not having checked.

## Reproducing

```console
$ python -B Git路径_skylos/git_diff_paths_demo/run.py --test
ALL PASS
```

The project needs Python 3.11+ and Git. Both versions of the functions are under `git_diff_paths_demo/vendor/`, with the source and line numbers in the file header and the Apache-2.0 licence alongside. The full comparison output and the upstream snapshot stay in the notes repository's check records.

Upstream: `duriantaco/skylos`, [#1196](https://github.com/duriantaco/skylos/pull/1196), parent commit [`7cf919a1`](https://github.com/duriantaco/skylos/commit/7cf919a103a416982d0a1fd7c79008424f47d274), merge commit [`380b2a3e`](https://github.com/duriantaco/skylos/commit/380b2a3e315ca05f5546139c691b678114e38dc4).
