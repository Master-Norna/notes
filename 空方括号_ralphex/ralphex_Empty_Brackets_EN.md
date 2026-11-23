# The plan still had `- [ ]` open, and ralphex had already started code review

ralphex is an agent runner driven by a plan file: tasks are written as `### Task N:` with `- [ ]` items underneath; it hands each one to Claude, Codex or a custom executor, and after every round it comes back to the plan. When nothing is left unchecked it moves on to code review.

A plan with a single item:

```markdown
### Task 1: Convert types

- [ ] convert []string to []T in the callers
```

The box is not checked. By the completion check in [`pkg/processor/phase/task.go`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L106-L112), ralphex prints `all tasks completed, starting code review...` after the first round and goes into code review, leaving the `- [ ]` exactly where it was.

The problem is the brackets in `[]string`. `pkg/plan/parse.go` carries a regex meant to recognise checkboxes whose text quotes a format example:

```go
// formatInText matches [ ] or [x] in checkbox text — description/example, not actionable for completion check.
formatInText = regexp.MustCompile(`\[\s*[ xX]?\s*\]`)
```

The comment says it matches `[ ]` or `[x]`. The question mark after the character class lets the class disappear, so an empty `[]` matches as well. `Checkbox.IsActionable()` uses the regex to decide whether a box is a real task: a match returns false, and the box is filed as an example.

## Why the exemption is there

`formatInText` arrived with [#222](https://github.com/umputun/ralphex/pull/222) on 2026-03-17. Before that the completion check did one thing: read the plan line by line and, on seeing `- [ ]`, conclude there was work left. Plan templates carry `## Success criteria`, `## Overview` and `## Context` sections beside the `### Task N:` ones, and those hold checkboxes too. They are not tasks anything will execute or tick, so the completion signal was rejected every time and the run looped until the iteration cap.

That PR turned the check into a parse first, looking only at boxes inside `### Task N:` and `### Iteration N:` sections, and closing the current task when a `##` heading shows up so the boxes below are not attached to the task above. Malformed plans with no task section keep a fallback: `FileHasUncompletedCheckbox()` scans the file line by line and returns true on the first unchecked box.

One more rule landed in the same change: a box whose text contains `[ ]` or `[x]` is not actionable. The template has a line like

```markdown
- [ ] use this format for [ ] unchecked items
```

which only describes the format and should not hold the completion signal back. The rule became `formatInText`, tucked into [`Checkbox.IsActionable()`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/plan/parse.go#L250-L252) during review; the file fallback calls the same method, so both paths agree.

The rule is not wrong. What went wrong is that the character class is optional. `[ ]` and `[x]` are the two markers the plan format defines; `[]` is not one of them — but `[ xX]?` lets the class stay away entirely, so `[]` is read as a format example.

## How the completion gate runs

[`TaskPhase.Run`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L56-L134) is a loop of at most `MaxIterations` rounds. Each round hands the plan to the executor, and after `ALL_TASKS_DONE` it asks a single question: is anything executable left unchecked?

[`HasUncompletedTasks()`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L150-L178) walks the parsed tasks first; if any task holds a box that is both unchecked and `IsActionable()`, it prints `warning: completion signal received but plan still has [ ] items, continuing...` and goes around again. Only when the plan parsed into zero task sections does it fall back to `FileHasUncompletedCheckbox()` and scan the raw lines for `- [ ]`. The fallback calls `IsActionable()` as well.

So a plan with task sections never reaches the fallback. The `[]string` item reads as an example; no task holds an uncompleted actionable box, so the gate opens. A plan with no task section takes the fallback and misses the same item.

![Two paths through the completion gate: with task sections it walks the boxes inside each task, with none it scans the file line by line. The two paths never run together, but every box passes the same `!cb.Checked && cb.IsActionable()` and both end at `Checkbox.IsActionable()`, whose `formatInText` reads `[]string` as a format example](assets/two-paths.png)

The check was #222's way out of an endless loop: without it, one box in `## Success criteria` that nobody means to tick could drag a run to the iteration cap. With `[]` among the matches it turned around and read real tasks as boxes nobody meant to tick.

## Sixteen real task lines

This is not a constructed shape. In ralphex's own [`docs/plans/`](https://github.com/umputun/ralphex/tree/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans) there are 16 checkboxes whose task text contains `[]`, over 7 files, dated 2026-01 to 2026-05. A few of them:

```text
- [x] Add `ClaudeErrorPatterns []string` to `Values` struct
- [x] define `-E/--env` flag with `action="append"`, `default=[]`
- [x] extract `buildPendingSectionEvents(name, phase, ts) []Event` ...
```

`[]string` is a Go slice type, `[]Event` the project's own event type, and `default=[]` Python argparse. None of it has anything to do with the plan format; the task text simply describes code. The earliest line sits in [`2026-01-25-interactive-plan-creation.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/2026-01-25-interactive-plan-creation.md#L138), adding an `options []string` parameter to `AskQuestion`; the latest is in `20260529-refactor-smells-and-duplication.md`, extracting a function that returns `[]Event`.

All 16 are in `docs/plans/completed/` today, ticked as `[x]`; while a plan runs they are `- [ ]`. Putting each line back to unchecked and handing it to both parsers:

| version | read as a format example | gate opens |
| --- | --- | --- |
| parent `cd1ca6b1` | 16 / 16 | 16 / 16 |
| merge `904f2302` | 0 / 16 | 0 / 16 |

## What one character changed

The fix drops the question mark:

```go
formatInText = regexp.MustCompile(`\[\s*[ xX]\s*\]`)
```

The character class has to be present, so `[]` no longer matches. The rest of the grid:

| fragment in task text | parent `cd1ca6b1` | merge `904f2302` |
| --- | --- | --- |
| `[]string`, `default=[]` | matches, read as example | no match, counts as task |
| `[` + tab + `]` | matches | no match |
| `[ ]`, `[x]`, `[  ]` | matches | matches |
| `s[x]`, `mark all tasks [x]` | matches | matches |
| `["CLAUDE.md"]`, `a[0]`, `[=true]` | no match | no match |

`[ ]`, `[x]` and `[  ]` are still examples, because `\s*` soaks up the spaces inside the brackets; `s[x]` and `mark all tasks [x]` still match, which is the cell #484 left alone. A real tab character inside the brackets behaves the same way: the parent's `[ xX]?` lets the class stand empty while `\s*` eats the tab, and the merge requires the class, which accepts only a space or an `x` — with a lone tab there is no character for it.

The test this PR adds covers the `[]string` line only: it asserts `IsActionable()` is true and `HasUncompletedActionableWork()` is true. The two neighbouring cases still hold the old behaviour — `- [ ] use this format for [ ] unchecked items` stays not actionable, and the real task next to `- [ ] use [ ] for format example` still counts.

## The second cut, same evening

[#484](https://github.com/umputun/ralphex/pull/484) merged on 2026-11-22 18:14:59Z. Forty-one minutes and twenty-two seconds later the maintainer's own [#486](https://github.com/umputun/ralphex/pull/486) went in, merge commit [`50843f0`](https://github.com/umputun/ralphex/commit/50843f0801609b08446b379e4d9f7ecc02d68f1c).

It deletes `formatInText` and `Checkbox.IsActionable` outright and renames `HasUncompletedActionableWork` to `HasUncompletedCheckbox`: every unchecked box counts as unfinished. `pkg/plan/parse.go` is +40/−46 and `task.go` is +4/−4. The reason given in the PR:

> [#484](https://github.com/umputun/ralphex/pull/484) narrowed that to `[x]`, but the rule still hid real work: "mark all tasks `[x]`" or an index like `s[x]` counted as done, so a run could accept `ALL_TASKS_DONE` with those tasks open.

`mark all tasks [x]` and `s[x]` are exactly the two cells #484 did not cover. Four more lines in the repository's own plans carry `[ ]` or `[x]` in the task text, such as "mark all tasks `[x]`" in [`20260424-watch-mode-reactivate-tailing.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260424-watch-mode-reactivate-tailing.md#L294) and "file present + has `[ ]` → true" in [`20260512-resolve-renamed-plan.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260512-resolve-renamed-plan.md#L137). They would still be swallowed after #484.

What happens to real format examples? `prompts/task.txt` already tells the agent to tick any box it cannot complete ([#228](https://github.com/umputun/ralphex/pull/228)), so a one-line example costs at most one extra round, and there is no longer a reason to hide it. The same commit tightens fence recognition: the opener may be indented at will, the closer at most 3 columns deeper than the opener, a tab counting as 4 columns. With the exemption gone, whether the example boxes inside a fence are taken for tasks hangs on that boundary. The `warning` text in `HasUncompletedTasks` did not change and still says "plan still has [ ] items", even though it now counts every unchecked box.

## Versions

[v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0) (2026-09-07) is the latest release, and its `pkg/plan/parse.go` still carries the question mark, with `formatInText` at `:51` and `IsActionable` at `:250`. #484 and #486 are both on main, no release has followed v1.7.0, and neither fix has shipped.

So a reader on v1.7.0 has both layers at once: `[]string` reads as an example, and so do `s[x]` and `mark all tasks [x]`. What ships next is #486's wholesale deletion, not #484's single character.

To check a copy yourself, look for `formatInText`:

```console
$ grep -n 'formatInText' pkg/plan/parse.go
$ go test ./pkg/plan
```

## Reproduction

Both versions of `pkg/plan/parse.go` sit verbatim in `空方括号_ralphex/plan_bracket_demo/before/` and `after/`, and the gate is a line-by-line model of `HasUncompletedTasks` from `pkg/processor/phase/task.go`. `go run .` walks 13 synthetic cases and the 16 real lines: the synthetic ones cover `[]string`, a real tab, two spaces, `[x]`, `s[x]`, `[=true]` and the no-task-section fallback; each real line is put back to unchecked on its own. `go test ./...` asserts the results. No dependencies, Go 1.24+.

Upstream: `umputun/ralphex`, [#484](https://github.com/umputun/ralphex/pull/484), parent commit [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a), merge commit [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e).
