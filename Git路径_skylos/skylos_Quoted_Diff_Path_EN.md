# Git quoted the path, and the file dropped out of review

A change that deletes `@login_required` can pass straight through a skylos PR review: the file is in the changed list, the review is posted, and the comments contain no security regression.

The same `git diff` is parsed in two places. [`get_changed_line_ranges`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L299) picks the lines the change touches, and findings from the scanner are filtered against them; [`_get_per_file_diffs`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L427) splits the diff by file and hands each piece to [`detect_security_regressions`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L500), which looks for a deleted `@login_required` or a similar control. The first resolves paths through `_new_diff_header_path`; the second slices `line[6:]`. The second is the one that misreads.

So the changed ranges are right, ordinary findings are there, and only the security branch gets no input. Its column in the report is empty, and empty and clean are indistinguishable in the output.

## `text=True` and `line[6:]`

In `skylos/cicd/review.py` at parent commit `7cf919a1`, `_get_per_file_diffs` reads the diff in the direct way:

```python
result = subprocess.run(
    diff_cmd,
    cwd=cwd,
    capture_output=True,
    text=True,
    env=read_only_git_environment(),
)
...
for line in result.stdout.splitlines():
    if line.startswith("diff --git"):
        ...
    elif line.startswith("+++ b/"):
        current_file = line[6:]
        current_lines.append(line)
```

Two assumptions. After `+++` there is always `b/`, and the path starts at character six. And with `text=True`, stdout always decodes in the current locale, read with universal newlines, so `\r`, `\n` and `\r\n` all end a line.

[`_parse_unified_diff`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L373) in the same file makes neither assumption. Its [`_new_diff_header_path`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L410) handles Git's C-style quoting, the TAB suffix and `/dev/null`; `get_changed_line_ranges` also reads bytes and decodes explicitly. One diff format, two readings, side by side.

## The diff is read twice

In a single `skylos cicd review`, [`run_pr_review`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L48) reads the diff once:

```python
changed_ranges = get_changed_line_ranges(
    diff_base,
    cwd=review_root,
    raise_on_error=True,
    include_deletion_anchors=False,
)
```

Those ranges filter the findings the scanner produced over the whole tree; only those on changed lines survive, through [`filter_findings_to_diff`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L529). The second read is for security regressions:

```python
regression_findings = _detect_regressions_from_diff(
    diff_base, cwd=review_root, raise_on_error=True
)
```

It needs each file's own diff text to see a deleted `@login_required`. `_get_per_file_diffs` serves that step. The two commands do not even share a `--unified` value: `get_changed_line_ranges` passes `--unified=0` because it only wants line numbers, while `_get_per_file_diffs` passes `--unified=3` because context is needed to see a decorator go.

Both results end up in the same comment. The second read misreads, so security regressions get no input; the first does not, so ordinary findings arrive as usual.

## Five shapes

The PR lists four; with the decode failure there are five. The project in `Git路径_skylos/git_diff_paths_demo/` builds each one in a real Git repository and runs both versions of the functions verbatim.

`_detect_regressions_from_diff` iterates `file_diffs.items()` and calls `detect_security_regressions(diff_text, file_path)` once per file. If the dictionary has no entry for a file, no later step touches it.

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

`line[6:]` carries the TAB into the key. `file_diffs` gets `src/my views.py\t`, which no longer matches the PR's diff; if a finding here is posted as an inline comment, the comment lands outside the diff.

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

The scanner sees a `diff --git` at column zero and believes a new file begins. The original file's hunk ends there, and the deleted `@login_required` below falls into the "new file": `src/app.py`'s diff is incomplete.

### Source bytes that are not UTF-8

A latin-1 source file puts `0xE9` into the diff. `text=True` decodes as the local locale (UTF-8) and fails on `0xE9`. The exception is not raised in `run()` — reading happens on another thread, `result.stdout` becomes `None`, and the next line reports:

```text
AttributeError: 'NoneType' object has no attribute 'splitlines'
```

This time `skylos cicd review` stops without finishing.

## Three changes

Merge commit `380b2a3e` changes `review.py` by +22/−4:

```python
result = subprocess.run(
    diff_cmd,
    cwd=cwd,
    capture_output=True,
    env=read_only_git_environment(),
)
...
diff_output = result.stdout
if isinstance(diff_output, bytes):
    diff_output = diff_output.decode("utf-8", errors="replace")
...
elif line.startswith("+++ ") and not in_hunk:
    current_file = _new_diff_header_path(line[4:])
```

- No `text=True`; read bytes back and `decode("utf-8", errors="replace")`. Bytes that are not UTF-8 become replacement characters, and the file's key and hunk survive.
- `+++` goes through `_new_diff_header_path`. Quotes, TAB and `/dev/null` are already there, and none of it is rewritten.
- `in_hunk` is set on `@@` and cleared on `diff --git`. Inside a hunk, `+++` is source.

`text=True` also takes `errors="replace"`, but decoding is only one of the two problems: universal newlines remain, and a bare CR still conjures a fake header. Reading bytes and decoding them yourself splits lines on `\n` alone, settling both at once. The comment in the merge says `like get_changed_line_ranges` — the fix is to make this spot behave like that one.

`_new_diff_header_path` does not guess at shapes it does not know: a path that does not start with `b/`, a quote that does not close, both `raise ValueError`. The exception leaves the loop in `_get_per_file_diffs` and is caught by `run_pr_review`'s `except ValueError`, which prints `Skylos PR review unavailable` and exits 2. The review stops, but it does not finish with a report missing one file.

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

`get_changed_line_ranges` is right in all five — it always went through the other parser. The problem is not Git, and not the rule.

## The comment lands outside the diff

All three key errors end in the same place: `_post_pr_review` looks up the position in the diff by path. With a key of `src/my views.py\t` or `victim.js`, GitHub's diff has no such path, and the comment goes out with a position outside the diff. The PR describes this class as "posted as a comment path outside the diff".

Worse than a misplaced comment is no comment. A file with a non-ASCII path sits in the changed list, and the conclusion is "nothing wrong"; a file with a bare CR is reviewed halfway, the rest of the hunk discarded as a new file. When a tool like this does not fail, nobody goes to check whether that column is empty or right.

## Two parsers back into one

The five shapes look like five `if`s: unquote, strip the TAB, track hunk state, change how bytes are read. `_new_diff_header_path` already does all of it, including `/dev/null` (the `+++` of a deletion) and malformed quotes; `_parse_unified_diff` already has `in_hunk`. The parsing logic does not need to move; what has to move is `_get_per_file_diffs` back onto the same function.

One line from the PR:

> `get_changed_line_ranges` parsed the same diff correctly, so the file looked reviewed.

That is where this fix starts: in the output of a review, "no findings" and "file never read" look the same. Both read as a pass.

Upstream added four tests for this behaviour; the latin-1 case is not one of them. That one is fixed by `errors="replace"`, but the comment explains why bytes are read — universal newlines turn a bare CR into a fake header — and says nothing about the decode failure. The fifth shape is reproducible in the demo and has no matching line upstream.

## Reproducing

```console
$ python -B Git路径_skylos/git_diff_paths_demo/run.py --test
ALL PASS
```

The project needs Python 3.11+ and Git. Both versions of the functions are under `git_diff_paths_demo/vendor/`, with the source and line numbers in the file header and the Apache-2.0 licence alongside. The full comparison output and the upstream snapshot stay in the notes repository's check records.

Upstream: `duriantaco/skylos`, [#1196](https://github.com/duriantaco/skylos/pull/1196), parent commit [`7cf919a1`](https://github.com/duriantaco/skylos/commit/7cf919a103a416982d0a1fd7c79008424f47d274), merge commit [`380b2a3e`](https://github.com/duriantaco/skylos/commit/380b2a3e315ca05f5546139c691b678114e38dc4).
