# Why a threshold of 0 did not turn the filter off

`find_similar(similarity_threshold=0)` — the docstring calls the threshold a percentage for attribute comparison, so writing 0 should switch attribute filtering off. On this page the first link has no attributes and the second carries `class="sale"`:

```python
page = Selector('<div><a>Alpha</a><a href="/beta" class="sale">Beta</a></div>')
reference = page.css("a")[0]
reference.find_similar(similarity_threshold=0)   # []
```

It returns nothing. Beta shares the tag, the depth and the parent with Alpha; the structural pass had already selected it; attribute filtering at 0 was supposed to let it through, and that is exactly where it was dropped.

## Structure runs first, attributes are the last step

`find_similar` works in two stages. The first is a structural prefilter: an XPath finds elements with the same tag, the same depth and the same parent/grandparent tag ([lines 1025-1084](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/scrapling/parser.py#L1025-L1084)). The second is `__are_alike`, which scores attribute values and compares the score with the threshold.

A threshold of 0 switches off the second stage. The first stage has already decided that these are same-level, same-shape candidates; the second has no reason to empty the list.

## `checks` is a denominator with three sources

`__are_alike` adds each comparison's similarity into `score` and counts `checks` as the denominator. Where `checks` comes from depends on whether the reference element has attributes:

| Reference attributes | Candidate attributes | `checks` | `score` | Old result |
| --- | --- | --- | --- | --- |
| present | any | `max(len(original), len(candidate))` | sum of per-attribute similarity | compared with the threshold |
| none | none | 1 | 1 | 100%, passes |
| none | present | 0 | 0 | `False`, whatever the threshold |

The first two rows have a score to compute. The third has none: without attributes on the reference there is no "key" to compare against the candidate's `class="sale"`, and `checks` stays at 0.

The old code ended at [lines 1020-1022](https://github.com/D4Vinci/Scrapling/blob/49eaff11da8de7c8067cf048a5dc3e0f95b53715/scrapling/parser.py#L1020-L1022):

```python
if checks:
    return round(score / checks, 2) >= similarity_threshold
return False
```

**`checks == 0` does not mean "not alike". It means "there is no attribute to compare".** The old code turned that into a verdict and skipped the threshold. Under a zero threshold the result was a strange split: a candidate with attributes and zero similarity passed (score 0, and `0 >= 0` is true), while a candidate with nothing to compare could not. That is not the semantics of a threshold, it is the semantics of a sentinel value.

## Earlier: the `max` fixed the other direction

The denominator had been changed once before. In June 2026, [#322](https://github.com/D4Vinci/Scrapling/issues/322) reported the opposite problem: the denominator used `len(candidate_attributes)`, so when the candidate had fewer attributes than the reference the denominator shrank and the score was inflated. The maintainer answered in the issue:

> using `len(candidate_attributes)` is intentional. It penalizes candidates who have extra attributes not present in the original element, making them less "alike". ... when the candidate has fewer attributes than the original, the score gets inflated instead of penalized ... The correct fix ... is: `checks += max(len(original_attributes), len(candidate_attributes))`

[`9c0c857`](https://github.com/D4Vinci/Scrapling/commit/9c0c857245726352a8502b1e4822a444ade96543) landed that. `max` protects both directions at once: an extra attribute on the candidate makes the denominator larger and pushes the score down; a missing attribute no longer shrinks the denominator, so the score cannot inflate.

But `max` only runs when `original_attributes` is non-empty. With no attributes on the reference, the code takes the `else` branch and never reaches `max`. **`max` fixed a denominator that was too small; it never touched a denominator of zero.** #539 fills that one cell.

## The fix: let the threshold decide a score of 0

[\#539](https://github.com/D4Vinci/Scrapling/pull/539) is one line: `return False` becomes `return 0 >= similarity_threshold`.

It is not `return True`, because a positive threshold still has to exclude these candidates: no attributes on the reference and a `class` on the candidate is a similarity of 0, and at 0.2, `0 >= 0.2` is false, so Beta should not appear. Only a zero threshold lets it through. "No comparable attributes" thus becomes a score (0) instead of an early verdict, and the threshold still does the judging it was written for.

The docstring also says that two attribute-free elements are a 100% match. That is the cell with a denominator — `score += 1; checks += 1`. This patch covers its reverse: when the denominator cannot be counted, the score is 0, not "no result". Together the two sentences make the attribute stage total.

## When you actually hit this

Four conditions have to hold at once:

- The threshold really is 0. `find_similar` defaults to `0.2`; the only call inside the library is the documentation example in the Scrapy integration ([`integrations/scrapy.py:69`](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/scrapling/integrations/scrapy.py#L69)), and it uses the default, so it never reaches this branch. Whoever hits it passed 0 explicitly.
- The reference element has no comparable attributes. `ignore_attributes` defaults to `("href", "src")`, so `<a href="/alpha">Alpha</a>` also counts as attribute-free — its only attribute is ignored.
- The candidate does have attributes. The candidate is filtered through the same ignore list first, so it needs something like `class` or `id` left over.
- `match_text` is the default `False`. With text comparison on, `checks` gains at least 1 and the `if checks` branch is never skipped.

A page that satisfies all four is not exotic: in a navigation bar every link except the current one has only `href`, which is ignored by default. Take the first link as the reference and look for its kin: the current item carries `class="active"`, 0.2 will miss it, and to get "every sibling link, no exceptions" you write the threshold as 0. The docstring itself, in [the `similarity_threshold` paragraph](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/scrapling/parser.py#L1041-L1046), says the prefiltered elements are "99% likely to be correct" and attribute comparison is only the last gate — 0 is how you say "I trust the structure".

## Fourteen rows

The demo runs the same set of pages through the `parser.py` of both fixed commits: 7 cases, two thresholds each, 14 rows. Every page is `<div class="list"><a ref>Alpha</a><a cand>Beta</a></div>`, and the first link is the reference for `find_similar`.

| Case | Threshold | Before | After |
| --- | ---: | --- | --- |
| reference has no attributes, candidate `class="sale"` | 0 | `[]` | `['Beta']` |
| same | 0.2 | `[]` | `[]` |
| reference has only `href` (ignored by default), candidate adds `class` | 0 | `[]` | `['Beta']` |
| same | 0.2 | `[]` | `[]` |
| neither has attributes | 0 | `['Beta']` | `['Beta']` |
| same | 0.2 | `['Beta']` | `['Beta']` |
| same class name `class="product"` | 0 | `['Beta']` | `['Beta']` |
| same | 0.2 | `['Beta']` | `['Beta']` |
| reference `class="product"`, candidate adds `id="x"` | 0.5 | `['Beta']` | `['Beta']` |
| same | 0.6 | `[]` | `[]` |
| different class names `product` / `deal` | 0 | `['Beta']` | `['Beta']` |
| same | 0.2 | `[]` | `[]` |
| `ignore_attributes=()`, so `href` is compared | 0 | `['Beta']` | `['Beta']` |
| same | 0.2 | `[]` | `[]` |

Run it:

```powershell
.venv/Scripts/python run.py --test
```

The last three lines:

```text
rows: 14
before: 2 mismatches
after:  0 mismatches
```

Two rows disagree with the contract before the fix and none after it.

## Only two rows moved

Of the 14 rows, just two differ between the versions: `no attrs vs class` and `href only vs class` go from `[]` to `['Beta']` at threshold 0. The other 12 are byte-for-byte identical.

The row that looks most alike did not move either: `class="product"` against `class="deal"` scores 0 with a denominator of 1, and `0 >= 0` already held in the old code, so it returned `['Beta']` before the fix too. **What the old code dropped was not "a score of 0" but "a score of 0 with no denominator"** — which also explains why the bug stayed hidden: the overwhelming majority of zero-score paths were already right.

The last two rows are the mirror image: pass `ignore_attributes=()`, let `href` be compared, and `"aaa"` against `"zzz"` also scores 0 — but with a denominator, so both versions get it right. The same "score of 0" lands on two different sides depending on whether a denominator exists.

## What upstream's test looks like

The test in the PR is parametrized; two decorators lay two reference elements and two thresholds out into four cases ([`tests/parser/test_find_similar_advanced.py`, lines 35-37](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/tests/parser/test_find_similar_advanced.py#L35-L37)):

```python
@pytest.mark.parametrize("reference_attributes", ["", 'href="/alpha"'])
@pytest.mark.parametrize("threshold, expected", [(0, ["Beta"]), (0.2, [])])
def test_find_similar_zero_threshold_without_reference_attributes(
    self, reference_attributes: str, threshold: float, expected: list[str]
) -> None:
    """A zero threshold disables attribute filtering even without scored attributes."""
```

The docstring is the maintainer's statement of the contract: a zero threshold turns attribute filtering off, and "no attributes to score" counts as part of it. The two reference elements are exactly the first two rows of the table above — truly no attributes, and only `href`.

Zero is not "a lower bar", it is "this step is off". With the step off, the only judgement left is the structural prefilter — the one the docstring itself calls 99% reliable. The old code made that decision once more at the last step, on the strength of a sentinel value: if the denominator cannot be counted, call it not alike.

The full page construction, the provenance of the two snapshots and how to run it are in `threshold_demo/README.md`; the complete output of this run is in `.yan/scrapling-threshold/runs/scrapling-demo-publish-20261103.txt`.
