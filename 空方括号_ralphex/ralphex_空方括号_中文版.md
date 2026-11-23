# 计划里还留着 `- [ ]`，ralphex 已经开始 code review

ralphex 是一个按计划文件跑任务的 agent 运行器：计划里写 `### Task N:`，每个任务下面是若干 `- [ ]`；它把任务交给 Claude、Codex 或自定义 executor，跑完一轮回来检查计划，直到所有任务勾完，再进入 code review。

计划文件里只有一项：

```markdown
### Task 1: Convert types

- [ ] convert []string to []T in the callers
```

这一项还没有勾。按 [`pkg/processor/phase/task.go`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L106-L112) 的完成判定，ralphex 会在第一轮之后打印 `all tasks completed, starting code review...`，然后进入 code review。计划里的 `- [ ]` 原样留在那里。

问题出在 `[]string` 的方括号上。`pkg/plan/parse.go` 有一条正则，本来用来认出「任务文字里引用了格式示例」的复选框：

```go
// formatInText matches [ ] or [x] in checkbox text — description/example, not actionable for completion check.
formatInText = regexp.MustCompile(`\[\s*[ xX]?\s*\]`)
```

注释说它匹配 `[ ]` 或 `[x]`。字符类 `[ xX]?` 后面带着问号，空 `[]` 也匹配。`Checkbox.IsActionable()` 用这条正则判断一个框是不是真正的任务：命中就返回 false，把它当作格式示例。

## 这条豁免是为什么加的

`formatInText` 是 [#222](https://github.com/umputun/ralphex/pull/222) 在 2026-03-17 引入的。在那之前，完成检查只做一件事：按行读计划文件，看到 `- [ ]` 就认为还有未完成的工作。计划模板里除了 `### Task N:` 段，还有 `## Success criteria`、`## Overview`、`## Context` 这些段，里面也会出现复选框。它们不是可执行的任务，agent 不会去勾，完成信号于是每次都被拒绝，运行一直循环到迭代上限。

那一笔把完成检查改成先解析计划，只看 `### Task N:` 与 `### Iteration N:` 段里的框；遇到 `##` 段标题就关闭当前任务，免得把下面的框挂到上一个任务上。没有任务节的畸形计划仍有兜底：`FileHasUncompletedCheckbox()` 按行扫文件，看到未勾选的框就返回 true。

同一笔改动里还有一条规则：文字里出现 `[ ]` 或 `[x]` 的框不算可执行项。模板里有这样一行——

```markdown
- [ ] use this format for [ ] unchecked items
```

它只是在说明格式，不该拦住完成信号。这条规则落成了 `formatInText`，并在 review 里被收进 [`Checkbox.IsActionable()`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/plan/parse.go#L250-L252)；文件兜底也调用同一个方法，两处判断保持一致。

规则本身没有错，错在字符类是可选的。`[ ]` 和 `[x]` 是计划格式定义的两种标记，`[]` 不是；但 `[ xX]?` 允许字符类整个不出现，`[]` 于是被归进了「格式示例」。

## 完成门怎么走

[`TaskPhase.Run`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L56-L134) 是一个最多跑 `MaxIterations` 轮的循环。每一轮把计划交给 executor，收到 `ALL_TASKS_DONE` 之后，它只问一件事：计划里还有没有未完成的可执行项。

[`HasUncompletedTasks()`](https://github.com/umputun/ralphex/blob/904f23025dd7390528585841fc3c1543b23c559e/pkg/processor/phase/task.go#L150-L178) 先遍历解析出来的任务，任一任务里存在「未勾选且 `IsActionable()` 为真」的框，就打印 `warning: completion signal received but plan still has [ ] items, continuing...`，继续下一轮。只有计划解析出零个任务节时，它才退到 `FileHasUncompletedCheckbox()`，按行扫文件找 `- [ ]`。而这条兜底同样调用 `IsActionable()`。

所以有任务节的计划，兜底根本不会跑。`[]string` 那一项被判成示例，任务里没有「未完成的可执行项」，完成门放行。零任务节的计划走兜底，也一样漏。

![完成门的两条路：有任务节时遍历任务里的框，零任务节时逐行扫文件；两条路不会同时走，但每个框都要过同一个 `!cb.Checked && cb.IsActionable()`，最后都落在 `Checkbox.IsActionable()` 上，而它用的 `formatInText` 把 `[]string` 读成格式示例](assets/two-paths.png)

这条检查本来是 #222 用来堵死循环的：没有它，`## Success criteria` 里一个不打算勾的框就能把运行拖到迭代上限。`[]` 混进来之后，它反过来把真正的任务当成了不打算勾的框。

## 16 行真实任务

这不是构造出来的形状。ralphex 仓库自己的 [`docs/plans/`](https://github.com/umputun/ralphex/tree/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans) 里，任务文字带 `[]` 的复选框有 16 行，分布在 7 个文件里，时间从 2026-01 到 2026-05。几个例子：

```text
- [x] Add `ClaudeErrorPatterns []string` to `Values` struct
- [x] define `-E/--env` flag with `action="append"`, `default=[]`
- [x] extract `buildPendingSectionEvents(name, phase, ts) []Event` ...
```

`[]string` 是 Go 的切片类型，`[]Event` 是项目自己的事件类型，`default=[]` 是 Python argparse 的写法。它们和计划格式没有关系，只是任务文字在描述代码。最早的一行在 [`2026-01-25-interactive-plan-creation.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/2026-01-25-interactive-plan-creation.md#L138)，是给 `AskQuestion` 加 `options []string` 参数；最晚的一行在 `20260529-refactor-smells-and-duplication.md`，要提取的函数返回 `[]Event`。

这 16 行现在都在 `docs/plans/completed/` 里，勾成了 `[x]`；计划执行时，它们是 `- [ ]`。把每一行单独放回未勾选，交给修复前后的两版解析器：

| 版本 | 判成格式示例 | 完成门放行 |
| --- | --- | --- |
| 父提交 `cd1ca6b1` | 16 / 16 | 16 / 16 |
| 合并 `904f2302` | 0 / 16 | 0 / 16 |

## 一个字符改了哪几格

修法是把问号去掉：

```go
formatInText = regexp.MustCompile(`\[\s*[ xX]\s*\]`)
```

字符类必须出现，`[]` 不再命中。其余几格：

| 任务文字里的片段 | 父版 `cd1ca6b1` | 合并 `904f2302` |
| --- | --- | --- |
| `[]string`、`default=[]` | 命中，判成示例 | 不命中，算任务 |
| `[` + tab + `]` | 命中 | 不命中 |
| `[ ]`、`[x]`、`[  ]` | 命中 | 命中 |
| `s[x]`、`mark all tasks [x]` | 命中 | 命中 |
| `["CLAUDE.md"]`、`a[0]`、`[=true]` | 不命中 | 不命中 |

`[ ]`、`[x]`、`[  ]` 仍然被当作格式示例，因为 `\s*` 会吸收掉方括号里的空格；`s[x]` 和 `mark all tasks [x]` 也仍然命中，这是 #484 没有覆盖的一格。方括号里放一个真实的 tab 字符也一样：父版的 `[ xX]?` 允许字符类空着，`\s*` 把 tab 吃掉就匹配了；合并版要求字符类必须出现，而 `[ xX]` 只认空格或 `x`，方括号里只有一个 tab 时没有字符给它。

这一笔新增的测试只覆盖了 `[]string` 那一行：断言 `IsActionable()` 为真、`HasUncompletedActionableWork()` 为真。相邻的两个用例仍然守着旧行为——`- [ ] use this format for [ ] unchecked items` 不算可执行项，`- [ ] use [ ] for format example` 旁边的真任务仍然算数。

## 同一天晚上的第二刀

[#484](https://github.com/umputun/ralphex/pull/484) 合并于 2026-11-22 18:14:59Z。41 分 22 秒之后，维护者自己的 [#486](https://github.com/umputun/ralphex/pull/486) 合了进来，合并提交是 [`50843f0`](https://github.com/umputun/ralphex/commit/50843f0801609b08446b379e4d9f7ecc02d68f1c)。

它把 `formatInText` 和 `Checkbox.IsActionable` 整个删掉，`HasUncompletedActionableWork` 改名 `HasUncompletedCheckbox`：所有未勾选的框都算未完成。`pkg/plan/parse.go` 这一笔是 +40/−46，`task.go` 是 +4/−4。PR 里的理由是：

> [#484](https://github.com/umputun/ralphex/pull/484) narrowed that to `[x]`, but the rule still hid real work: "mark all tasks `[x]`" or an index like `s[x]` counted as done, so a run could accept `ALL_TASKS_DONE` with those tasks open.

`mark all tasks [x]` 和 `s[x]` 就是没有被 #484 覆盖的那两格。仓库自己的计划里另有 4 行任务文字带 `[ ]` 或 `[x]`，比如 [`20260424-watch-mode-reactivate-tailing.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260424-watch-mode-reactivate-tailing.md#L294) 里的「mark all tasks `[x]`」，以及 [`20260512-resolve-renamed-plan.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260512-resolve-renamed-plan.md#L137) 里那句「file present + has `[ ]` → true」。它们在 #484 之后仍然会被吞。

真正的格式示例怎么办？`task.txt` 已经让 agent 把无法完成的框勾上（[#228](https://github.com/umputun/ralphex/pull/228)），一行示例最多多跑一轮，不再有理由把它藏起来。同一笔还收紧了围栏代码块的识别：opener 可以任意缩进，closer 最多比 opener 深 3 格，tab 按 4 列算。豁免拿掉之后，围栏里那些示例框会不会被当成任务，就取决于这条边界。`HasUncompletedTasks` 里那句 `warning` 的文案没变，仍然写着「plan still has [ ] items」，尽管现在它数的是所有未勾选的框。

## 版本

[v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0)（2026-09-07）是当前最新的发行版，里面的 `pkg/plan/parse.go` 还是带问号的写法，`formatInText` 在 `:51`，`IsActionable` 在 `:250`。#484 与 #486 都在 main 上，v1.7.0 之后没有新的 release，两笔修复都还没有发行。

也就是说，读者手上的 v1.7.0 同时有这两层问题：`[]string` 被判成示例；`s[x]`、`mark all tasks [x]` 也被判成示例。下一版带上的是 #486 的整块删除，而不是 #484 的一个字符。

自查可以看源码里还有没有 `formatInText`：

```console
$ grep -n 'formatInText' pkg/plan/parse.go
$ go test ./pkg/plan
```

## 复现

两版 `pkg/plan/parse.go` 原样放在 `空方括号_ralphex/plan_bracket_demo/before/` 与 `after/`，完成门按 `pkg/processor/phase/task.go` 的 `HasUncompletedTasks` 逐行复刻。`go run .` 跑 13 个合成用例与 16 行真实任务：合成用例覆盖 `[]string`、真实的 tab、两空格、`[x]`、`s[x]`、`[=true]`、无任务节的兜底；真实任务逐行放回未勾选。`go test ./...` 断言结果，零依赖，Go 1.24+。

上游：`umputun/ralphex`，[#484](https://github.com/umputun/ralphex/pull/484)，父提交 [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a)，合并提交 [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e)。
