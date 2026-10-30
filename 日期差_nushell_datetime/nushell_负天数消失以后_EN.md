# The Negative Days Were Gone. Then Review Found Another Problem.

How far is January 31 from March 1?

Nushell's `dt datetime-diff` once broke it down like this:

```text
2023-01-31 → 2023-03-01
1 month −2 days
```

The inputs were not reversed. The start came before the end, yet the result contained a negative day count. If we add a month to January 31, clamping to February 28, and then subtract two days, we do not even get back to March 1.

That was the bug I worked on in [Nushell #19109](https://github.com/nushell/nushell/pull/19109). But the turning point was not getting rid of the minus sign. It came afterward, when review brought up another pair of dates:

**January 31 to February 28 used to be 28 days. Why was it now one month?**

## 1. The Previous Patch Had Borrowed from the Right Month

`datetime-diff` does not just return a total number of seconds. It splits the difference between two instants into years, months, days, and smaller units, all the way down to nanoseconds. Months vary in length, so dividing by a fixed number of seconds will not do.

The old implementation took a straightforward approach: subtract the fields, borrowing from the next larger unit when necessary. Not enough days? Borrow a month. Not enough hours? Borrow a day. The difficult part was deciding how many days a borrowed month supplied.

That had just been fixed. In [#19064](https://github.com/nushell/nushell/pull/19064), another contributor corrected which month to borrow from. Between January 15 and March 1, the month to borrow was February, not March with its 31 days. The code after that fix is the “before” version used in this article.

In a non-leap year, subtracting the day numbers gives `1 − 15 = −14`. Adding February's 28 days produces a result of 1 month and 14 days. For that example, the problem was solved.

But move the start from the 15th to the 31st, and the arithmetic becomes:

```text
Subtract day numbers:  1 − 31 = −30
Borrow February:     −30 + 28 = −2
```

The [borrowing code at the pinned parent commit](https://github.com/nushell/nushell/blob/c3b7a5aebea0119d88bba4608bc6a3f81bb54a45/crates/nu-std/std/dt/mod.nu#L20-L41) really does borrow only once: add the number of days in the intervening month, decrement the month count, and return. It chose the right month, but that month was too short to cover the deficit.

This is an easy place to investigate the wrong thing. A negative day count suggests checking whether February was selected incorrectly, or whether the leap-year calculation was wrong. But February really did have 28 days here. What needed replacing was the method of subtracting day numbers and then adding one month's worth of days.

## 2. An Answer That Looked Solid

The [implementation I submitted for review](https://github.com/nushell/nushell/blob/ca90358650f1afa85a5bfb05645e87e04f52baaf/crates/nu-std/std/dt/mod.nu#L193-L210) used an actual date as a reference point. I will call that version the draft.

First, calculate the difference in months and advance the start by that many months. If the target month does not have the original day number, clamp it to the last day of that month. January 31 plus one month, for example, becomes February 28. That landing date is the anchor.

Then check whether the anchor is past the end. If so, count one fewer month. Measure the remaining days directly from the anchor to the end.

For the original counterexample, this worked neatly:

- January 31 plus two months lands on March 31, past March 1.
- Reduce the month count to one, landing on February 28.
- Add one more day to reach March 1.

The answer became “1 month 1 day.” It had no negative components, and adding it back reconstructed the end. The new regression test caught the original bug.

But reviewer fdncred did not stop at the broken example. He checked inputs that had not been broken, and pointed out the issue [in review](https://github.com/nushell/nushell/pull/19109#discussion_r4230030631):

> “Clamp semantics is a reasonable choice … but this is a user-visible change.”

January 31 plus a month clamps to February 28. Under my draft, the anchor had already reached the end, so it counted as a whole month. The old implementation, however, returned 28 days for that pair.

The draft had not turned a sensible answer into nonsense. It had replaced one defensible convention with another. That was harder to spot than a minus sign.

All four inputs raised in review showed the same issue:

| Start → end | Before | Draft | Merged version |
|---|---|---|---|
| 2023-01-31 → 2023-02-28 | 28 days | 1 month | 28 days |
| 2023-03-31 → 2023-04-30 | 30 days | 1 month | 30 days |
| 2024-02-29 → 2025-02-28 | 11 months 30 days | 1 year | 11 months 30 days |
| 2023-01-31 12:00 → 2023-02-28 13:00 | 28 days 1 hour | 1 month 1 hour | 28 days 1 hour |

All dates and times in the table are UTC; zero-valued fields are omitted. The reproduction project linked below runs all three versions side by side.

The task was to fix negative days, not redefine “one month.” **Reconstructing the end proves that a decomposition is internally consistent. It does not prove that it preserves existing behavior.**

## 3. Two Decisions, Not One

The final approach kept the anchor, but stopped asking it to decide everything.

There were really two separate questions:

1. How many whole months should count? Keep the existing rule based on the original day numbers.
2. Where do those months actually land? Calculate that using a clamped date.

Start with the year difference multiplied by 12, plus the month difference. If the end's original day number is smaller than the start's, subtract one month. If the day numbers are equal, compare the times of day as well, subtracting a month if the end's time is earlier. Only after choosing the whole-month count do we build the clamped anchor and calculate the remaining days.

The key part of the [final code](https://github.com/nushell/nushell/blob/996de1f9a48520c8679e6d791f3260b722d5116e/crates/nu-std/std/dt/mod.nu#L131-L153) is:

```nushell
mut total_months = (($from_expanded.year - $to_expanded.year) * 12) + ($from_expanded.month - $to_expanded.month)
if ($from_expanded.day < $to_expanded.day) or (($from_expanded.day == $to_expanded.day) and ($to_time_ns > $from_time_ns)) {
    $total_months = $total_months - 1
}
let anchor = (add-months-clamp $to_expanded.year $to_expanded.month $to_expanded.day $total_months)
```

Here, `from_expanded` is the end and `to_expanded` is the start. Both have already been converted to UTC.

| Start → end | Choose the month count using original day numbers | Build the clamped anchor | Remaining days |
|---|---|---|---|
| January 31 → February 28 | `28 < 31`: reduce 1 month to 0 | January 31 | 28 |
| January 31 → March 1 | `1 < 31`: reduce 2 months to 1 | February 28 | 1 |

For January 31 to February 28, the candidate month count falls to zero. The anchor stays at January 31, leaving 28 days.

For January 31 to March 1, the candidate count falls from two months to one. The anchor lands on February 28, leaving one day.

The same clamping function is still there. It just no longer treats “where this month lands” as an answer to “whether a whole month has elapsed.”

Time of day also matters at two distinct levels. From noon on January 31 to 06:00 on February 28, the calculation first finds 28 calendar days, then borrows a day because the clock is six hours short. The output is 27 days and 18 hours. That is borrowing from days to cover the hour deficit; it is not the same as the condition above that compares times only when the original day numbers are equal. Midnight-to-midnight tests alone miss these boundaries.

## 4. Fixing the Rule Also Made More Code Removable

The review went beyond the month-count condition.

To measure the days from the anchor to the end, the draft included a general date-to-ordinal algorithm: convert each Gregorian date to a continuous day count, then subtract. It could handle dates very far apart. But these particular dates could never be that far apart.

The whole-month count is reduced by at most one. That places the anchor either in the end's month or in the immediately preceding month. As [review pointed out](https://github.com/nushell/nushell/pull/19109#discussion_r4230030659), only two cases are needed:

```nushell
$result.day = if $anchor.month == $from_expanded.month {
    $from_expanded.day - $anchor.day
} else {
    (days-in-month $anchor.month $anchor.year) - $anchor.day + $from_expanded.day
}
```

Within the same month, subtract the day numbers. Across a month boundary, take the days left in the anchor's month and add the end's day number. Crossing a year boundary needs no additional day-count conversion: the month before January is the previous December, and the anchor already carries its year.

The old month-borrowing chain could go too.

The whole-month selection now ensures that the anchor is no later than the end. If the anchor and the end fall on the same date, that selection also ensures that the end's time of day is no earlier than the start's. Borrowing a day to cover a time deficit is therefore only necessary when some calendar days remain. The hour, minute, and second borrowing still works, but it can no longer drive the day count below zero and propagate into the month field.

That is why [this review comment](https://github.com/nushell/nushell/pull/19109#discussion_r4230030646) recommended removing the now-unreachable `borrow-month` and `borrow-year`, together with parameters passed down the chain solely for their benefit. The final patch did not wrap another safeguard around the old month-borrowing logic. It removed the path that was no longer reachable.

## 5. Wider Tests Found a Different Problem

Checking this change meant asking more than “Are there any negative numbers?”

- If we add the clamped years and months to the start, then add the days and smaller units, do we recover the end?
- For inputs where the old implementation already reconstructed the end without negative components, did the decomposition change?
- Does the rule still hold with times of day, across year boundaries, and for dates such as January 29, which is not month-end but still needs clamping in February?

Those questions took testing beyond January 31. The [regression cases in the merged repository](https://github.com/nushell/nushell/blob/996de1f9a48520c8679e6d791f3260b722d5116e/crates/nu-std/tests/test_dt.nu#L73-L156) retain those boundaries too.

During the broader testing at the time, another symptom appeared, outside this subtraction logic: for some leap years on century boundaries, the string parser had already changed February 29 to February 28 before the value reached `datetime-diff`. I [reported it in the original discussion](https://github.com/nushell/nushell/pull/19109#discussion_r4235740052) and left it outside this patch.

The maintainer's [reply](https://github.com/nushell/nushell/pull/19109#discussion_r4237714473) kept that separate as well: a suitable replacement parser could be considered, but not in this PR.

While preparing this article, the same issue interrupted the reproduction. The first scan reached `2000-02-29T00:00:00Z`, which the default parser in official Nu 0.116.1 parsed with a day number of 28. The reproduction program checks the parsed UTC fields before validating the algorithms, so its checks stopped there rather than counting the altered date as an algorithm test. A [standalone parser probe](datetime_demo/parser_probe.nu) preserves that observation, alongside a 2024 leap-day case that parses correctly.

The final three-version comparison explicitly parses RFC3339 inputs with `into datetime --format '%+'`. It checks every UTC field, then passes the datetime values to the original modules. This separates input parsing from date-difference calculation; it does not quietly patch any of the three algorithms.

It would be tempting to describe this detour as “fixing another bug along the way.” That is not what happened. The input changed during parsing, so the date-difference algorithm never received the original date. Parsing and choosing the year/month/day split are different stages of the same input flow. Adding a parser replacement would only have expanded a fix whose scope had just been narrowed.

## 6. Keep the Rejected Draft, Too

This article's [datetime_demo](datetime_demo/) includes not just the before and after versions, but also the draft addressed by review.

It runs the three modules from pinned commits directly in Nushell, with Python collecting the output and checking the results. These two rows are the most useful comparison:

| Start → end | Before | Draft | Merged version |
|---|---|---|---|
| 2023-01-31 → 2023-03-01 | 1 month −2 days | 1 month 1 day | 1 month 1 day |
| 2023-01-31 → 2023-02-28 | 28 days | 1 month | 28 days |

The first row shows why the old implementation needed to change. The second shows why the draft still needed to change. With only before and after columns, the most valuable turn in the story disappears.

This reproduction also ran 6,580 non-reversed inputs in a single Nu 0.116.1 process, covering dates at the beginning, middle, and end of months in selected years, with three time-of-day combinations. The draft had no negative components and reconstructed every end, yet 32 outputs differed from the decomposition convention ultimately retained. The merged version had zero failures on all three checks. It also preserved every old output in the sample that was nonnegative, within the checked unit ranges, and able to reconstruct the end. The [demo README](datetime_demo/README.md) documents the sampling rules and output format; both the named regressions and the batch scan can be rerun offline.

[#19109](https://github.com/nushell/nushell/pull/19109) was merged on October 10, 2026. Looking back, what settled the approach was not finding an answer that looked more plausible. It was separating “repair a bad answer” from “choose a different convention.”

**This patch had to protect two sets of dates: one that showed the old code really was wrong, and another that reminded me not every old answer needed replacing.**

---

### Source and Reproduction

- Upstream: [Nushell #19109](https://github.com/nushell/nushell/pull/19109); preceding fix [#19064](https://github.com/nushell/nushell/pull/19064).
- Before: [`c3b7a5a`](https://github.com/nushell/nushell/tree/c3b7a5aebea0119d88bba4608bc6a3f81bb54a45); reviewed draft: [`ca90358`](https://github.com/nushell/nushell/tree/ca90358650f1afa85a5bfb05645e87e04f52baaf); merged version: [`996de1f`](https://github.com/nushell/nushell/tree/996de1f9a48520c8679e6d791f3260b722d5116e).
- Requirements, pinned source files, and integrity checks are in the [demo README](datetime_demo/README.md). The tables and scan counts in this article come from fresh runs of the three modules. The default parser's leap-day behavior was checked with a separate probe; the original discussion records the historical investigation and the decision to keep it outside this fix.
