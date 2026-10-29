# One Pass Through isort, Two F401s Are Back

Take one import line with a trailing `# noqa: F401` — a note to flake8 that these two names are deliberately left unused. Run it through [isort](https://github.com/PyCQA/isort) with `force_grid_wrap=2` (everything else at its default), and the output is:

```text
input:  from ugly import a, b  # noqa: F401
output: from ugly import (a, b)
```

The code is valid, the names are alphabetically sorted, and a second run changes nothing. Everything looks fine — except the comment is gone. The very next flake8 run reports two F401s: `'ugly.a' imported but unused` and `'ugly.b' imported but unused`.

A formatter silently dropping the very comment that suppresses a lint, bringing the warning back to life. That is what I fixed in [isort #2675](https://github.com/PyCQA/isort/pull/2675), merged on October 18, 2026 — six lines added and one removed in production code. This post follows the comment along its path through isort's internals, to the exit it falls out of.

## 1. Comments arrive as arguments

When isort produces an import line, it does not copy the original. It disassembles the line and reassembles it: the name list goes one way, and the trailing comment is peeled off during parsing and stored in a list of its own. At the end, the wrap mode you configured rebuilds the whole line.

Wrap modes are a set of functions, and [`grid()` is one of them](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/isort/wrap_modes.py#L46-L57). Its signature explicitly takes a `comments` argument:

```python
def grid(
    statement: str,
    imports: list[str],
    ...
    comments: Sequence[str],
    comment_prefix: str,
    ...
) -> str:
```

Whether the comment survives depends on whether these mode functions put it back. The call chain goes: `output.py` decides a block needs re-flowing ([`output.py` L432-L446](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/isort/output.py#L432-L446)), then `wrap.import_statement()` hands everything to the mode function.

## 2. Two paths through grid(), and only one picks up the comments

Here is [`grid()` as it was before the fix](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/wrap_modes.py#L46-L91) (parent commit `1745766e`, excerpted):

```python
statement += "(" + imports.pop(0)
while imports:
    next_import = imports.pop(0)
    next_statement = isort.comments.add_to_line(
        comments,
        statement + ", " + next_import,
        removed=remove_comments,
        comment_prefix=comment_prefix,
    )
    if len(next_statement.split(line_separator)[-1]) + 1 > line_length:
        # folding branch: attach the comments at the fold, then clear them
        statement = isort.comments.add_to_line(...) + f"{line_separator}{next_import}"
        comments = []
    else:
        statement += ", " + next_import
return f"{statement}{',' if include_trailing_comma else ''})"
```

Each iteration probes first: would adding the next name exceed the line width? If yes, the folding branch runs — [`add_to_line()`](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/comments.py#L16-L43) attaches the comments at the fold, `comments` is cleared, job done.

But what if the statement never gets that wide? The loop runs the `else` branch every time, `comments` stays untouched, and the final `return` just appends the closing parenthesis. **The comments were taken in, yet no path ever takes them out.** The same input forks at this exit depending on the version:

| Path through `grid()` | Before `1745766e` | After `3415efa` |
| --- | --- | --- |
| Statement exceeds `line_length` → folding branch | comments joined at the fold | unchanged |
| Statement fits → straight to the `return` | comments reach the exit un-consumed, then dropped | `return` routes through `add_to_line()`, comments back on the tail |

The other modes in the same file each have their own way of picking comments up:

- [`vertical`](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/wrap_modes.py#L110-L123) attaches them via `add_to_line` as soon as it takes the first name;
- [`vertical_hanging_indent`](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/wrap_modes.py#L211-L222) computes the commented line right at function entry;
- [`_vertical_grid_common`](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/wrap_modes.py#L241-L251) attaches them the moment the opening parenthesis is written;
- [`hanging_indent`](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/wrap_modes.py#L176-L195) has a dedicated `if comments:` branch as a safety net at the end;
- the [`noqa` mode](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/wrap_modes.py#L364-L376) makes comments the very body of its output.

`grid` was the only one consuming comments solely through its folding branch. In the PR I compressed the consequence into one sentence:

> The `# noqa: F401` is lost, re-activating the lint it was suppressing — with no error or warning, and the output stays valid and idempotent, so it's easy to miss.
> —— [isort #2675 description](https://github.com/PyCQA/isort/pull/2675)

## 3. Why the default configuration never hits it

This bug stayed hidden for a reason rooted in isort's defaults. [`multi_line_output` defaults to GRID](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/isort/settings.py#L150), but [`force_grid_wrap` defaults to 0](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/isort/settings.py#L183).

With `force_grid_wrap=0`, a statement that fits the line never enters the re-flow path at all — the call chain from section 2 never fires, the comment is glued back verbatim by the output layer, and nothing is lost. I ran the same input under the default configuration: the output came back unchanged, comment intact.

So four conditions have to line up before a comment gets dropped:

1. the wrap mode is GRID (the default, in fact);
2. `force_grid_wrap` is explicitly set greater than 0;
3. the `from` import carries at least that many names;
4. the statement fits within `line_length` — it enters grid layout, yet never folds.

Condition 2 is something the user wrote into their own config. Condition 4 sounds self-contradictory — how can a statement re-enter formatting without being too wide — but that is exactly what `force_grid_wrap` means: "once the name count reaches the threshold, force the grid layout regardless of line width." Users who set it get parenthesized grid output even for short statements.

One misconception worth clearing up: the popular [pycharm profile](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/isort/profiles.py#L20-L24) does set `force_grid_wrap: 2`, but its `multi_line_output` is VERTICAL — one of the modes from section 2 that attach comments at entry. It is unaffected. The loss only happens under GRID.

## 4. The seven-line fix sits at the exit

The fix touches one place: [`grid()`'s exit](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/isort/wrap_modes.py#L88-L96) now returns through `add_to_line()`:

```python
return isort.comments.add_to_line(
    comments,
    f"{statement}{',' if include_trailing_comma else ''})",
    removed=remove_comments,
    comment_prefix=comment_prefix,
)
```

This landing spot works because [`add_to_line()`](https://github.com/PyCQA/isort/blob/1745766e5cc705eec7179c1122fcdf5b5b6e7546/isort/comments.py#L16-L43) measures each case carefully:

- no comments left: returns the statement untouched — normal output unchanged to the last character;
- `remove_comments` enabled: returns the statement stripped of comments, preserving the `--ignore-comments` semantics;
- unconsumed comments present: deduplicates them, joins with `; `, attaches them to the tail per `comment_prefix`.

The folding branch was not touched by a single character. When a statement genuinely overflows, the comments still land at the fold — that is the existing behavior `noqa`-style trailing comments depend on, **and the fix must not disturb it**. Upstream added [two regression tests](https://github.com/PyCQA/isort/blob/3415efa3668f5514c57dfa4291d83021a575b56f/tests/unit/test_wrap_modes.py#L210-L324) for exactly this: one pins the four non-folding cases (kept, unchanged without comments, trailing comma, multiple comments merged), the other pins the comment's position when folding, so the fix cannot break the folding branch in turn.

The review itself was uneventful: [DanielNoord](https://github.com/DanielNoord) asked for a rebase and type annotations on the tests, and [approved](https://github.com/PyCQA/isort/pull/2675#pullrequestreview-5563642587) once those landed. The [10.0.0b1 pre-release](https://github.com/PyCQA/isort/releases/tag/10.0.0b1) tagged four hours after the merge already contains the fix (verified by comparing tag contents); the latest stable release, 9.0.2 (September 28), does not.

## 5. Before and after, side by side

I put the `isort` package sources of parent commit `1745766e` and merge commit `3415efa` verbatim into [isort_demo](isort_demo/), and fed the same input to both snapshots. No network needed:

```bash
pip install mypy_extensions      # hard dependency of the snapshots' settings.py
pip install flake8               # optional: joins the lint comparison
python run.py
```

Both snapshots verify, after loading, that the module really came from the snapshot directory (isort's `__version__` goes through importlib.metadata and would misread a same-named installed distribution, so versions are identified by git SHA throughout). This run produced:

| Observation | Before `1745766e` | After `3415efa` |
| --- | --- | --- |
| `# noqa: F401` in the output | 0 (lost) | 1 (kept at the tail) |
| `flake8 --select=F401` | 2 findings, exit code 1 | none, exit code 0 |
| Idempotent on a second run | yes | yes |
| Folding case (19 names) | comments land at the fold | byte-identical to before |
| Input without comments | normal output | byte-identical to before |

The broken output deserves a second look: syntactically valid, idempotent, and the two F401s flake8 reports point at imports that genuinely exist in the code. Every single step looks "correct" in isolation — **the loss happens on the semantic layer alone**. The only thing that stops matching is the comment the user wrote at the end of the line.

The demo runs on Windows / Python 3.12.14 with 9 assertions (2 of them flake8); `python run.py --test` passes all of them, and `--offline` skips the lint comparison.

## Closing

A formatter's output has to pass three gates: syntactically valid, idempotent under a second run, and semantically faithful to the input. The first two have long been covered by isort's own tests. Within the third, comments are the easiest thing to treat as decoration — they take no part in parsing, and losing them raises no error.

But `# noqa` is not decoration. It is an instruction written for the tools downstream. This fix does a seven-line job: letting grid carry out what the user handed in.

The change is merged into isort's mainline ([`3415efa`](https://github.com/PyCQA/isort/commit/3415efa3668f5514c57dfa4291d83021a575b56f)). If your config mentions `force_grid_wrap`, it is worth checking whether you stand in the intersection of those four conditions.
