# Fixing PDF comment recursion—and the extra call it left behind

There is only a `42` at the end. Put enough comments before it, and pypdf cannot even reach that number.

```python
from io import BytesIO
from pypdf.generic import read_object

stream = BytesIO(b"% padding\n" * 1000 + b"42 tail")
value = read_object(stream, None)
```

The pre-fix revision used in this article raises `RecursionError` here. Replacing recursion with a loop makes the number readable. Then, extracting that loop into a utility function at a reviewer's request breaks a call-count test that another PR has just added.

The merged patch keeps both the loop and its limit, while preserving the call budget on the comment-free parsing path. The interesting part is not that loops are better than recursion. It is how two reasonable changes meet in the same piece of code.

## 1. The comments were skipped; the stack frames were not

Under [PDF specification §7.2.3](https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf#page=21), comments outside strings and streams are treated as whitespace. In pypdf's [old implementation](https://github.com/py-pdf/pypdf/blob/a23cc36da7a8e86f2b551b7a6eed1d8798301c73/pypdf/generic/_data_structures.py#L1581-L1612), encountering `%` causes the parser to skip the line, skip whitespace, and call `read_object` again.

One line at a time, this looks natural. But the previous call has not returned when the next one encounters another `%`. Each comment disappears from the byte stream while leaving a Python call waiting to return.

The object itself need not be complicated. The trailing `42` has no nesting at all; enough leading comments will still exhaust the call stack. The [original issue, #4145](https://github.com/py-pdf/pypdf/issues/4145), uses this kind of small input rather than a large PDF that would be harder to inspect.

**Skipping content should not leave another parser call waiting on the stack.**

My [first draft](https://github.com/py-pdf/pypdf/blob/528c61de6b2e448634f899ee022eabdd1dce6041/pypdf/generic/_data_structures.py#L1551-L1579) for [#4150](https://github.com/py-pdf/pypdf/pull/4150) puts consecutive comments in a single loop and limits each object read to skipping 1,000 comments. It does not raise Python's recursion limit. It removes this work's dependence on the remaining stack depth.

That 1,000 is an implementation policy, not a comment count prescribed by the PDF format. In the [issue discussion](https://github.com/py-pdf/pypdf/issues/4145#issuecomment-5950264868), a maintainer suggests starting with a sufficiently large fixed value. Deeper object nesting is a separate problem.

## 2. The first draft fixed the bug; review asked for a better home

The initial loop lives directly in `read_object`. A maintainer then [asks](https://github.com/py-pdf/pypdf/pull/4150#discussion_r4207102313):

> Can we move this new logic to a dedicated utility function?

There is already something concrete to build on: pypdf has `skip_over_comment` for skipping a single comment, and the draft loop already calls it. What needs extracting is the repeated processing and the count limit around that single-comment utility.

The new `skip_over_comments` combines those two responsibilities, continuing to reuse the existing utility internally. The object parser calls it and then resumes identifying numbers, arrays, dictionaries, and other objects. The [extraction commit](https://github.com/py-pdf/pypdf/commit/e7dfa72a41d07a216647c5b7d32c51558e59ed74) records that change.

At this point, the recursion bug is still fixed, and the responsibilities are clearer. The next turn is not another example of a misread number. It is a new requirement that has arrived on the main branch for ordinary parsing.

## 3. Another PR left behind more than faster code

While this revision was in progress, MartinThoma's [#4148](https://github.com/py-pdf/pypdf/pull/4148) merged first. It optimizes the parsing of numbers, indirect references, and other objects, and leaves an unusual regression test: instead of measuring seconds, it counts Python function calls.

The input is an array containing repeated groups of `123`, `4.5`, and `12 0 R`. These exercise the integer, floating-point, and indirect-reference paths, for 300 elements in total. The [test's assertion](https://github.com/py-pdf/pypdf/blob/79423c1288cbbb4a16bf0601b3539797f6900bb3/tests/test_generic.py#L436-L450) is:

```python
assert calls < 3 * len(array)
```

This is not a definition of the correct parsing result. It is a cost budget left by that optimization: future changes must do more than read the same array correctly. They must also avoid casually adding back the calls that were just removed.

What does a comment utility extracted during review have to do with this budget? The answer lies in where it is called.

The [actual intermediate revision after merging the main branch](https://github.com/py-pdf/pypdf/blob/ad63551501ef8ad03ca91a8d1e5246a79319a048/pypdf/generic/_data_structures.py#L1587-L1598) calls `skip_over_comments` on every entry to `read_object`. With no comments in the input, the utility checks and returns without changing anything.

One empty check is small, but every ordinary element in the array pays for that extra Python function call. Across 300 elements, 300 additional calls turn 601 into 901. The test requires strictly fewer than 900.

**The utility for consecutive comments had also entered the path for objects with no comments at all.**

This connection is not inferred from the two PR numbers. The [fast-path correction's commit message](https://github.com/py-pdf/pypdf/commit/9f5a61b26e4a9734b1756eb7da26789b4fd42790) explicitly names #4148, that test, and the 901 calls for 300 elements.

I also reproduced the result using the fixed intermediate source and the upstream counting function. These are Python function calls, not elapsed time; 601 and 901 cannot be converted into a percentage slowdown.

## 4. Keep the utility; move its entry point

The final change is short: [look at the first byte, and enter the utility only when it is `%`](https://github.com/py-pdf/pypdf/blob/ccd8dc470e13915d384fb8b4c93a351cc1d79ae6/pypdf/generic/_data_structures.py#L1583-L1597).

```python
tok = stream.read(1)
stream.seek(-1, 1)  # reset to start
if tok == b"%":
    # Skip consecutive comments in a loop instead of recursing per comment.
    skip_over_comments(stream, limit=_MAX_LEADING_COMMENTS)
    tok = stream.read(1)
    stream.seek(-1, 1)  # reset to start
```

Without `%`, there are no consecutive comments to process. When a comment is present, the same bounded loop still handles it. The shared utility stays, while ordinary objects no longer take an extra Python call through it.

The final revision returns to 601 calls for the same array, meeting the original budget. The pre-fix revision also takes 601 calls in this test. This step preserves an existing cost, rather than making the final patch faster than the pre-fix code.

## 5. At the limit, where should the stream cursor stop?

There is another detail that “it no longer recurses” cannot settle: how many comments cause a failure, and how much input has been consumed when that happens?

The [final utility](https://github.com/py-pdf/pypdf/blob/ccd8dc470e13915d384fb8b4c93a351cc1d79ae6/pypdf/_utils.py#L288-L318) checks the next non-whitespace byte after skipping each comment. After exactly 1,000 comments, a following `42` can still be read as an object. If the next byte is another `%`, it raises `LimitReachedError`, leaving the stream positioned at that new comment's `%` without scanning its body.

“Positioned at `%`” does not mean that byte has never been read. The utility reads ahead to the next non-whitespace byte, then rewinds to just before it. A digit makes the utility return control to the object parser. Another `%` triggers the error at the start of the next loop iteration.

| After 1,000 comments have been skipped | Lookahead and rewind inside the utility | Cursor when the utility returns or raises | What happens next |
|---|---|---|---|
| Next object is `42 tail` | Read `4`, then rewind one byte | Immediately before `4` | Return to the object parser; it reads `42` and leaves ` tail` in the stream |
| Next input is `%` followed by the 1,001st comment's body | Read `%`, then rewind one byte | Immediately before `%` | Raise `LimitReachedError` at the next loop entry; the comment body has not been read |

The table distinguishes the utility's lookahead from the subsequent object parsing. Leaving ` tail` in the stream does not mean the number parser never read ahead into it; the unread-body guarantee concerns the rejected comment's body.

Review also [specifically questions the error wording](https://github.com/py-pdf/pypdf/pull/4150#discussion_r4207082471): the limit has been reached, not necessarily exceeded. The next comment is rejected; only 1,000 have actually been skipped.

Here is my comparison of the real source revisions under Python 3.12.14. Successful cases check both that the value is `42` and that ` tail` remains in the stream.

| Consecutive leading comments | Pre-fix | Intermediate: utility extracted, main branch integrated | Final merged revision |
|---|---|---|---|
| 0, 1 | Reads 42 | Reads 42 | Reads 42 |
| 999, 1,000 | `RecursionError` | Reads 42 | Reads 42 |
| 1,001, 2,000 | `RecursionError` | `LimitReachedError` | `LimitReachedError` |

The precise count at which the old code raises `RecursionError` depends on the available call stack; the table reports this run's observations. The new revisions' 1,000-comment limit comes from the implementation itself.

I also put a 100,000-byte body in the 1,001st comment. The final revision stops just before its `%`, without first reading through that body to decide that the limit has been reached. Separate checks with LF, CR, and CRLF line endings confirm that an object remains readable after 1,000 comments.

The boundary is specific: it limits consecutive leading comments skipped during one object read. It is not a document-wide comment count, nor a limit on the length of one comment. Object nesting has its own depth problem; this loop cannot provide a guarantee for that.

## 6. Two changes leave two kinds of regression constraint

This patch did not follow a straight line from a wrong first version to a correct second one. The first draft already solved recursion through consecutive comments. Extracting the utility made that logic reusable. A call budget left by another optimization then required the utility to stay off the unconditional hot path.

**The final code has to answer two questions: can it make bounded progress through comments, and can it preserve the original parsing cost when there are none?**

That is the value of reading related PRs together. #4148 is not just background to this story. Its test actually changes where #4150 ends up placing a function call. The reasons behind both changes survive in the code.

The [offline reproduction project](comments_demo/) keeps fixed source snapshots of the pre-fix, intermediate, and final revisions. It uses the upstream counting function and checks parsing results, stream positions, and the call budget separately. See the [project README](comments_demo/README.md) for commands, source SHAs, and scope. It parses object bytes directly in memory and needs no external PDF sample.

The final implementation discussed here was [merged with #4150](https://github.com/py-pdf/pypdf/commit/ccd8dc470e13915d384fb8b4c93a351cc1d79ae6). The call counts and comment boundaries above are my offline reproductions against those fixed sources.
