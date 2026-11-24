# `[]string` in a plan, and ralphex treats the line as done

ralphex runs tasks from a plan file: tasks are written as `### Task N:` with `- [ ]` items underneath; it hands each one to Claude, Codex or a custom executor, and after every round it comes back to the plan. Only when everything is ticked does it move on to code review.

A plan with a single task, still open:

```markdown
### Task 1: Convert types

- [ ] convert []string to []T in the callers
```

After the first round ralphex prints `all tasks completed, starting code review...` and goes into code review. The `- [ ]` stays exactly where it was.

The brackets in `[]string` are the problem. In [v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0) (released 2026-09-07, still the latest) any task line whose text carries an empty bracket pair drops out of the completion check, and `s[x]` or `mark all tasks [x]` does the same. If the plan has not run yet, scan it first:

```console
$ grep -rnE '^[[:space:]]*-[[:space:]]+\[ \].*\[\]' docs/plans
```

Every hit is a task the completion gate will let through early.

## The check reads the text for brackets

[`pkg/plan/parse.go`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L51) carries a regex meant to recognise checkboxes whose text quotes a format example:

```go
// formatInText matches [ ] or [x] in checkbox text — description/example, not actionable for completion check.
formatInText = regexp.MustCompile(`\[\s*[ xX]?\s*\]`)
```

The comment says it matches `[ ]` or `[x]`. The character class `[ xX]` is followed by a question mark, so the class may be absent altogether and a bare `[]` matches too. The decision lands in `Checkbox.IsActionable()` (v1.7.0, `:250`):

```go
func (cb Checkbox) IsActionable() bool {
	return !formatInText.MatchString(cb.Text)
}
```

A match returns false, and the line is filed as "this is only describing the format, not a task". The person writing the plan sees `- [ ]` untouched; ralphex sees a task with nothing to execute.

## Why the exemption exists

Before [#222](https://github.com/umputun/ralphex/pull/222) (merged 2026-03-17, +275/−20) the completion check did one thing: read the plan line by line and, on seeing `- [ ]`, conclude there was work left. Plan templates also carry checkboxes in `## Success criteria`, `## Overview` and `## Context` sections. Nothing will ever tick those, so the completion signal was rejected every time and the run looped until the iteration cap.

#222 turned the check into a parse first, looking only at boxes inside `### Task N:` and `### Iteration N:` sections, and closing the current task when a `##` heading shows up so the boxes below are not attached to the task above. The same change exempted boxes whose text contains `[ ]` or `[x]` — the template has a line like

```markdown
- [ ] use this format for [ ] unchecked items
```

which only describes the format and should not hold the completion signal back. The exemption became `formatInText`, and the file fallback calls the same method, so both paths agree.

The rule itself was not wrong. `[ ]` and `[x]` are the two markers the plan format defines; `[]` is not. What went wrong is that the character class is optional.

## Both paths pass the same check

[`TaskPhase.Run`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L56-L134) is a loop of at most `MaxIterations` rounds. Each round hands the plan to the executor, and after `ALL_TASKS_DONE` it asks one question: is anything actionable left unchecked?

[`HasUncompletedTasks()`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L150-L178) walks the parsed tasks; if any task holds a box that is unchecked and `IsActionable()`, it prints `warning: completion signal received but plan still has [ ] items, continuing...` and goes around again. Only when the plan parsed into zero task sections does it fall back to `FileHasUncompletedCheckbox()` and scan the raw lines for `- [ ]`, and that fallback calls `IsActionable()` as well:

```go
func (t *Task) HasUncompletedActionableWork() bool {
	for _, cb := range t.Checkboxes {
		if !cb.Checked && cb.IsActionable() {
			return true
		}
	}
	return false
}
```

A plan with task sections never reaches the fallback. The `[]string` item reads as an example, no task holds an uncompleted actionable box, and the gate opens. A malformed plan with no task section takes the fallback and misses through the same door: both paths end at that one judgement.

![Two paths through the completion gate: with task sections it walks the boxes inside each task, with none it scans the file line by line. The two never run together, and both end at the same actionable check, which reads an empty bracket pair as a format example](assets/two-paths.png)

The check was #222's way out of an endless loop. Without it, a single box in `## Success criteria` that nobody means to tick could drag a run to the iteration cap. Once `[]` was among the matches, it turned around and read real tasks as boxes nobody meant to tick.

## Sixteen real task lines

This is not a constructed shape. In ralphex's own [`docs/plans/`](https://github.com/umputun/ralphex/tree/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans), 16 checkboxes whose task text contains `[]` are spread over 7 files, the earliest written 2026-01-25 and the latest 2026-05-29:

```text
- [x] Add `ClaudeErrorPatterns []string` to `Values` struct
- [x] define `-E/--env` flag with `action="append"`, `default=[]`
- [x] extract `buildPendingSectionEvents(name, phase, ts) []Event` ...
```

`[]string` is a Go slice type, `[]Event` the project's own event type, `default=[]` Python argparse. None of it has anything to do with the plan format; the text is describing code. The earliest line sits in [`2026-01-25-interactive-plan-creation.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/2026-01-25-interactive-plan-creation.md#L138), adding an `options []string` parameter to `AskQuestion`.

All 16 sit in `docs/plans/completed/` today, ticked as `[x]`; while a plan runs they are `- [ ]`. Put each line back to unchecked on its own and hand it to both parsers:

| version | read as a format example | gate opens early |
| --- | --- | --- |
| parent `cd1ca6b1` | 16 / 16 | 16 / 16 |
| merge `904f2302` | 0 / 16 | 0 / 16 |

Fourteen of them were written before #222, when there was no exemption yet and `[]string` could not affect the decision. The other two, from plans dated 2026-05-14 and 2026-05-29, came after v0.24.0, so the question mark was already in a release.

## One character, and the cells it leaves

The fix drops the question mark; `pkg/plan/parse.go` changes by +1/−1:

```go
formatInText = regexp.MustCompile(`\[\s*[ xX]\s*\]`)
```

The character class has to be present, so `[]` no longer matches. The rest of the grid:

| fragment in task text | parent `cd1ca6b1` | merge `904f2302` |
| --- | --- | --- |
| `[]string`, `default=[]` | matches, read as example | no match, counts as task |
| a single tab between the brackets | matches | no match |
| `[ ]`, `[x]`, two spaces between the brackets | matches | matches |
| `s[x]`, `mark all tasks [x]` | matches | matches |
| `["CLAUDE.md"]`, `a[0]`, `[=true]` | no match | no match |

`[ ]`, `[x]` and the two-space form are still examples: `\s*` soaks up the spaces inside the brackets, and `[ xX]` holds the one character that `[x]` needs. A real tab inside the brackets behaves the same way; the parent let the class stand empty while `\s*` ate the tab, and the merge requires the class, which accepts only a space or an `x`, leaving no character for a lone tab.

The test this PR adds covers the `[]string` line only: it asserts `IsActionable()` is true and `HasUncompletedActionableWork()` is true. The two neighbouring cases still hold the old behaviour — `- [ ] use this format for [ ] unchecked items` stays not actionable, and the real task next to `- [ ] use [ ] for format example` still counts.

The patch was kept to the smallest change: make the character class mandatory and leave the exemption alone. As long as the exemption stands, the only way to tell which box is not a task is to read the text.

## Forty-one minutes later the exemption is gone

[#484](https://github.com/umputun/ralphex/pull/484) merged on 2026-11-22 18:14:59Z. Forty-one minutes and twenty-two seconds later the maintainer's own [#486](https://github.com/umputun/ralphex/pull/486) went in, merge commit [`50843f0`](https://github.com/umputun/ralphex/commit/50843f0801609b08446b379e4d9f7ecc02d68f1c).

It deletes `formatInText` and `Checkbox.IsActionable` outright and renames `HasUncompletedActionableWork` to `HasUncompletedCheckbox`: every unchecked box counts as unfinished. `pkg/plan/parse.go` changes by +40/−46, `task.go` by +4/−4. The reason given in the PR:

> [#484](https://github.com/umputun/ralphex/pull/484) narrowed that to `[x]`, but the rule still hid real work: "mark all tasks `[x]`" or an index like `s[x]` counted as done, so a run could accept `ALL_TASKS_DONE` with those tasks open.

`mark all tasks [x]` and `s[x]` are exactly the two cells the table above leaves unchanged. Four more lines in the repository's own plans are written that way, such as "mark all tasks `[x]`" in [`20260424-watch-mode-reactivate-tailing.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260424-watch-mode-reactivate-tailing.md#L294) and "file present + has `[ ]` → true" in [`20260512-resolve-renamed-plan.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260512-resolve-renamed-plan.md#L137). They would still be swallowed after #484.

What about real format examples? `task.txt` already tells the agent to tick any box it cannot complete ([#228](https://github.com/umputun/ralphex/pull/228)), so a one-line example costs at most one extra round, and there is no longer a reason to hide it. The same commit tightens fence recognition: the opener may be indented at will, the closer at most 3 columns deeper than the opener, a tab counting as 4 columns. With the exemption gone, whether the example boxes inside a fence are taken for tasks hangs on that boundary. The warning in `HasUncompletedTasks` still reads "plan still has [ ] items", even though it now counts every unchecked box.

The tests were rewritten along with it, +128/−45 in `parse_test.go` alone; the two source files together come to +44/−50.

## Versions, and your own plan

[v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0) (2026-09-07) is the latest release and its `pkg/plan/parse.go` still carries the question mark, with `formatInText` at `:51` and `IsActionable` at `:250`. #484 and #486 are both on main, no release has followed v1.7.0, and neither fix has shipped.

So a reader on v1.7.0 has both layers at once: `[]string` reads as an example, and so do `s[x]` and `mark all tasks [x]`. What ships next is #486's wholesale deletion, not #484's single character.

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

The gate is really answering one question: is there a box that is unchecked *and* actually a task. `[]string` makes it read the second half wrong; #484 narrows the exemption by one character, #486 stops guessing from text altogether. Any runner that advances on Markdown checkboxes runs into the same split: brackets inside task text and brackets in list syntax are not the same thing.

Upstream: `umputun/ralphex`, [#484](https://github.com/umputun/ralphex/pull/484), parent commit [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a), merge commit [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e).
