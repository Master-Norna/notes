# `[]string` in a plan, and ralphex treats the line as done

The completion check in ralphex [v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0) skips any plan line whose task text carries an empty bracket pair: the `- [ ]` was never ticked, and ralphex still counts that line as done.

It advances through a Markdown plan file: `### Task N:` with a few `- [ ]` items underneath, each handed to Claude, Codex or a custom executor, and only when everything is ticked does it move on to code review. A plan with a single task, still open:

```markdown
### Task 1: Convert types

- [ ] convert []string to []T in the callers
```

After the first round ralphex prints `all tasks completed, starting code review...` and goes into code review. The `- [ ]` stays exactly where it was.

One task line holds two sets of brackets. The `- [ ]` at the start is the checkbox that decides whether the step was done; the text after it is the task description, and whoever writes it often copies a signature straight out of the code — that is how `[]string` gets in. To decide whether a box is quoting a format example, ralphex reads the task text for brackets, and its regex takes an empty `[]` for an example as well.

Go's `[]string` and Python argparse's `default=[]` both hit. The same regex recognises `[x]` too — the marker of a ticked item — so `mark all tasks [x]` in the task text turns the whole box into an example, and so does an index like `s[x]`. v1.7.0 (2026-09-07) is the latest release and all of this is in it; the fix on main waits for the next version.

If the plan has not run yet, scan for the empty-bracket kind first:

```console
$ grep -rnE '^[[:space:]]*-[[:space:]]+\[ \].*\[\]' docs/plans
```

Every hit is a task the completion gate will let through early. The `[x]` and `s[x]` forms are not in that command; the mechanism is the same, and there is a table for them further down.

## One regex, two bracket positions read as one

[`pkg/plan/parse.go`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L51) carries one regex, and its comment says what it recognises:

```go
// formatInText matches [ ] or [x] in checkbox text — description/example, not actionable for completion check.
formatInText = regexp.MustCompile(`\[\s*[ xX]?\s*\]`)
```

The comment says it matches `[ ]` or `[x]`. The character class `[ xX]` is followed by a question mark, so the class may be absent altogether and a bare `[]` matches too. The decision lands in `Checkbox.IsActionable()` (v1.7.0, `:250`), which reads the text only and never the tick state:

```go
func (cb Checkbox) IsActionable() bool {
	return !formatInText.MatchString(cb.Text)
}
```

A match returns false, and the box is filed as "this only describes the format, not a task". The person writing the plan sees `- [ ]` untouched; ralphex sees a task with nothing to execute.

The gate asks that question in two places. When a task section parses, it walks the boxes of every task ([`Task.HasUncompletedActionableWork`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L256)); when not a single task section parses, it falls back to scanning the file line by line ([`FileHasUncompletedCheckbox`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L157)). The two never run together, and both ask the same `!cb.Checked && cb.IsActionable()` — which is why even a malformed plan with zero task sections leaks through the same door.

![Two paths through the completion gate: with task sections it walks the boxes inside each task, with none it scans the file line by line. The two never run together, and both end at the same actionable check, where the question mark lets an empty bracket pair match](assets/two-paths.png)

## Why the exemption exists

Before [#222](https://github.com/umputun/ralphex/pull/222) (merged 2026-03-17, +275/−20) the completion check did one thing: read the plan line by line and, on seeing `- [ ]`, conclude there was work left. Plan templates also carry checkboxes in `## Success criteria`, `## Overview` and `## Context` sections. Nothing will ever tick those, so the completion signal was rejected every time and the run looped until the iteration cap.

#222 turned the check into a parse first, looking only at boxes inside `### Task N:` and `### Iteration N:` sections, and closing the current task when a `##` heading shows up so the boxes below are not attached to the task above. The same change exempted boxes whose text contains `[ ]` or `[x]` — the template has a line like

```markdown
- [ ] use this format for [ ] unchecked items
```

which only describes the format and should not hold the completion signal back. The exemption became `formatInText`, and both paths of the gate call it, so the judgement stays consistent.

The rule itself was not wrong. `[ ]` and `[x]` are the two markers the plan format defines; `[]` is not. What went wrong is that the character class is optional.

## Sixteen real task lines

This is not a constructed shape. In ralphex's own [`docs/plans/`](https://github.com/umputun/ralphex/tree/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans), 16 checkboxes whose task text contains `[]` are spread over 7 files, the earliest written 2026-01-25 and the latest 2026-05-29:

```text
- [x] Add `ClaudeErrorPatterns []string` to `Values` struct
- [x] define `-E/--env` flag with `action="append"`, `default=[]`
- [x] extract `buildPendingSectionEvents(name, phase, ts) []Event` ...
```

`[]string` is a Go slice type, `[]Event` the project's own event type, `default=[]` Python argparse. None of it has anything to do with the plan format; the text is describing code. The earliest line sits in [`2026-01-25-interactive-plan-creation.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/2026-01-25-interactive-plan-creation.md#L138), adding an `options []string` parameter to `AskQuestion`.

All 16 sit in `docs/plans/completed/` today, ticked as `[x]`; while a plan runs they are `- [ ]`. Fourteen of them were written before #222, when there was no exemption yet and `[]string` could not affect the decision. The other two, from plans dated 2026-05-14 and 2026-05-29, came after v0.24.0, so the question mark was already in a release. Put any one of the 16 back to unchecked today and the result is the same.

## One character, and the `[x]` it does not cover

The fix drops the question mark; `pkg/plan/parse.go` changes by +1/−1:

```go
formatInText = regexp.MustCompile(`\[\s*[ xX]\s*\]`)
```

The character class has to be present, so `[]` no longer matches. Put the 16 lines above back to unchecked one at a time and hand them to the parser on either side of this commit: on the parent [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a) all 16 read as examples and the gate opens for all 16, on the merge [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e) none.

This commit only touched the empty-bracket kind. What the other forms do on either side only lines up once they share one table:

| fragment in task text | parent `cd1ca6b1` | merge `904f2302` |
| --- | --- | --- |
| `[]string`, `default=[]` | matches, read as example | no match, counts as task |
| a single tab between the brackets | matches | no match |
| `[ ]`, `[x]`, two spaces between the brackets | matches | matches |
| `s[x]`, `mark all tasks [x]` | matches | matches |
| `["CLAUDE.md"]`, `a[0]`, `[=true]` | no match | no match |

`[ ]`, `[x]` and the two-space form are the cell kept on purpose: those two markers are what the plan format defines, and they should match. `s[x]` and `mark all tasks [x]` are the cell it does not cover: written that way in task text, the whole box still reads as an example. The tab cell is only the shape of the regex — the parent let the class stand empty while `\s*` ate the tab, and the merge requires the class, which accepts only a space or an `x`, leaving no character for a lone tab.

The test this PR adds covers the `[]string` line only: it asserts `IsActionable()` is true and `HasUncompletedActionableWork()` is true. The two neighbouring cases still hold the old behaviour — `- [ ] use this format for [ ] unchecked items` stays not actionable, and the real task next to `- [ ] use [ ] for format example` still counts.

The patch was kept to the smallest change: make the character class mandatory and leave the exemption alone. As long as the exemption stands, the only way to tell which box is not a task is to read the text.

## Forty-one minutes later the exemption is gone

[#484](https://github.com/umputun/ralphex/pull/484) merged on 2026-11-22 18:14:59Z. Forty-one minutes and twenty-two seconds later the maintainer's own [#486](https://github.com/umputun/ralphex/pull/486) went in, merge commit [`50843f0`](https://github.com/umputun/ralphex/commit/50843f0801609b08446b379e4d9f7ecc02d68f1c).

It deletes `formatInText` and `Checkbox.IsActionable` outright and renames `HasUncompletedActionableWork` to `HasUncompletedCheckbox`: every unchecked box counts as unfinished. `pkg/plan/parse.go` changes by +40/−46, `task.go` by +4/−4. The reason given in the PR:

> [#484](https://github.com/umputun/ralphex/pull/484) narrowed that to `[x]`, but the rule still hid real work: "mark all tasks `[x]`" or an index like `s[x]` counted as done, so a run could accept `ALL_TASKS_DONE` with those tasks open.

`mark all tasks [x]` and `s[x]` are exactly the two cells the table above leaves unchanged. Four more lines in the repository's own plans are written that way, such as "mark all tasks `[x]`" in [`20260424-watch-mode-reactivate-tailing.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260424-watch-mode-reactivate-tailing.md#L294) and "file present + has `[ ]` → true" in [`20260512-resolve-renamed-plan.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260512-resolve-renamed-plan.md#L137). After #484 they would still be swallowed, and the gate would still open for them.

What about real format examples? `task.txt` already tells the agent to tick any box it cannot complete ([#228](https://github.com/umputun/ralphex/pull/228)), so a one-line example costs at most one extra round, and there is no longer a reason to hide it. The same commit tightens fence recognition: the opener may be indented at will, the closer at most 3 columns deeper than the opener, a tab counting as 4 columns. With the exemption gone, whether the example boxes inside a fence are taken for tasks hangs on that boundary.

The warning in `HasUncompletedTasks` still reads "plan still has [ ] items", even though it now counts every unchecked box.

The tests were rewritten along with it, +128/−45 in `parse_test.go` alone; the two source files together come to +44/−50.

## The v1.7.0 a reader is running

[v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0) (2026-09-07) is the latest release and its `pkg/plan/parse.go` still carries the question mark, with `formatInText` at `:51` and `IsActionable` at `:250`. #484 and #486 are both on main, no release has followed v1.7.0, and neither fix has shipped.

So both layers are still in place: `[]string` reads as an example, and so do `s[x]` and `mark all tasks [x]`. What ships next is #486's wholesale deletion, not #484's single character.

Task text in a plan often quotes a signature — Go's `[]string`, Python argparse's `default=[]`, shell's `a[0]`. On v1.7.0 the first two let the completion gate open early. For a plan that has not run, scan it with the grep from the top; a hit means either split the task so no bracket pair sits in its text, or wait for a release that carries #486. In ralphex's own repository that command hits 0 lines today, because the 16 are ticked `[x]` inside `completed/`; put any one of them back to `- [ ]` and it hits.

## Reproduction

Both versions of `pkg/plan/parse.go` sit verbatim in [`空方括号_ralphex/plan_bracket_demo`](https://github.com/Master-Norna/notes/tree/main/%E7%A9%BA%E6%96%B9%E6%8B%AC%E5%8F%B7_ralphex/plan_bracket_demo) under `before/` and `after/`, and the gate is a line-by-line model of `HasUncompletedTasks` from `pkg/processor/phase/task.go`, so ralphex itself is not needed. `go run .` walks 13 synthetic cases and the 16 real lines, printing both verdicts side by side:

```text
case               before                       after
slice-type         not actionable, completed    actionable, continuing
tab                not actionable, completed    actionable, continuing
index-x            not actionable, completed    not actionable, completed
no-task-slice      no task section, completed   no task section, continuing

real docs/plans rows: 16
  before: 16/16 rows end the gate as completed
  after:  0/16 rows end the gate as completed
```

`go test ./...` asserts these results. No dependencies, Go 1.24+.

The gate is really answering one question: is there a box that is unchecked *and* actually a task. `[]string` makes it answer "nothing left" early; #484 narrows the exemption by one character, #486 stops guessing from text altogether. Any runner that advances on Markdown checkboxes runs into the same split: brackets inside task text and brackets in list syntax are not the same thing.

Upstream: `umputun/ralphex`, [#484](https://github.com/umputun/ralphex/pull/484), parent commit [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a), merge commit [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e).
