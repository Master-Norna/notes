# `[]string` 写在计划里，ralphex 把这行当成做完了

ralphex [v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0) 的完成判定会跳过任务文字里带一对空方括号的行：`- [ ]` 一步没做，它也认为这一行做完了。

它按 Markdown 计划文件推进任务：`### Task N:` 下面若干 `- [ ]`，逐条交给 Claude、Codex 或自定义 executor，全部勾完才进 code review。计划里只有一条任务，还没有勾：

```markdown
### Task 1: Convert types

- [ ] convert []string to []T in the callers
```

第一轮跑完，ralphex 打出 `all tasks completed, starting code review...` 进了 code review，这一行 `- [ ]` 原样留在计划里。

一行任务里有两处方括号。行首的 `- [ ]` 是复选框，决定这一步做没做；后面的文字是任务描述，写的人常常直接抄代码签名，`[]string` 就这么混了进来。ralphex 要判断这个框是不是在引用格式示例，看的是任务文字里有没有方括号——它用的正则把空的 `[]` 也当成了示例。

Go 的 `[]string`、Python argparse 的 `default=[]` 都会命中。同一条正则还认 `[x]`——那是清单里已勾的标记；任务文字里写 `mark all tasks [x]`，整个框同样被判成示例，索引写法 `s[x]` 也一样。v1.7.0（2026-09-07）是当前最新的发行版，这些行为都在里面，main 上的修复要等下一版。

手上的计划还没跑，可以先扫空方括号这一类：

```console
$ grep -rnE '^[[:space:]]*-[[:space:]]+\[ \].*\[\]' docs/plans
```

命中的每一行，都是完成门会提前放行的任务。`[x]`、`s[x]` 那几种不在这条命令里，机制相同，后面有对照表。

## 一条正则，把两个位置的方括号混在一起

[`pkg/plan/parse.go`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L51) 里有一条正则，注释写着它认的是什么：

```go
// formatInText matches [ ] or [x] in checkbox text — description/example, not actionable for completion check.
formatInText = regexp.MustCompile(`\[\s*[ xX]?\s*\]`)
```

注释说它匹配 `[ ]` 或 `[x]`。字符类 `[ xX]` 后面带着问号，整个字符类可以不出现，`[]` 于是也命中。判定落在 `Checkbox.IsActionable()` 里（v1.7.0 的 `:250`），它只看文字，不看勾选状态：

```go
func (cb Checkbox) IsActionable() bool {
	return !formatInText.MatchString(cb.Text)
}
```

命中就返回 false，这个框被归进「只是在说明格式，不是任务」。写计划的人看到的是 `- [ ]` 没动，ralphex 看到的是这条任务没有可执行内容。

完成门在两处问这个问题：解析出任务节时逐个任务看（[`Task.HasUncompletedActionableWork`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L256)）；一个任务节都没解析出来时，它退到按行扫文件（[`FileHasUncompletedCheckbox`](https://github.com/umputun/ralphex/blob/v1.7.0/pkg/plan/parse.go#L157)）。两条路不会同时走，问的都是同一句 `!cb.Checked && cb.IsActionable()`——所以连零任务节的畸形计划也一样漏。

![有任务节与零任务节两条路，最后都交给同一个 IsActionable；问号让空方括号也命中](assets/two-paths.png)

## 这条豁免原本是堵死循环用的

[#222](https://github.com/umputun/ralphex/pull/222)（2026-03-17 合并，+275/−20）之前，完成检查只做一件事：按行读计划文件，看到 `- [ ]` 就认为还有没做完的。计划模板里 `## Success criteria`、`## Overview`、`## Context` 这些段也会出现复选框，agent 不会去勾，完成信号于是每次都被拒绝，运行一直循环到迭代上限。

这个 PR 把检查改成先解析计划，只认 `### Task N:` 与 `### Iteration N:` 段里的框。同一笔还豁免了「文字里出现 `[ ]` 或 `[x]`」的框，因为模板里有这么一行：

```markdown
- [ ] use this format for [ ] unchecked items
```

它只是在说明格式，不该拦住完成信号。豁免落成 `formatInText`，完成门的两条路都调它，判断保持一致。

要认的只有 `[ ]` 和 `[x]`——计划格式定义的两种标记；`[]` 不在其中。错在字符类是可选的。

## 16 行真实任务

这不是构造出来的形状。ralphex 仓库自己的 [`docs/plans/`](https://github.com/umputun/ralphex/tree/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans) 里，任务文字带 `[]` 的复选框有 16 行，分布在 7 个文件，最早的一份写于 2026-01-25，最晚的 2026-05-29：

```text
- [x] Add `ClaudeErrorPatterns []string` to `Values` struct
- [x] define `-E/--env` flag with `action="append"`, `default=[]`
- [x] extract `buildPendingSectionEvents(name, phase, ts) []Event` ...
```

`[]string` 是 Go 的切片类型，`[]Event` 是项目自己的事件类型，`default=[]` 是 Python argparse 的写法——都在描述代码，与计划格式无关。最早一行在 [`2026-01-25-interactive-plan-creation.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/2026-01-25-interactive-plan-creation.md#L138)，是给 `AskQuestion` 加 `options []string` 参数。

这 16 行现在都在 `docs/plans/completed/` 里勾成了 `[x]`；计划执行时它们是 `- [ ]`。其中 14 行写在 #222 之前，豁免还不存在，当时不受影响；剩下两行来自 2026-05-14 与 2026-05-29 的两份计划，写在 v0.24.0 之后，带问号的正则已经随发行版出去了。今天把这 16 行里任何一行放回未勾选，结果都一样。

## 一个字符的修法，没盖住 `[x]`

[#484](https://github.com/umputun/ralphex/pull/484) 的改动是把问号去掉，`pkg/plan/parse.go` 这一笔 +1/−1：

```go
formatInText = regexp.MustCompile(`\[\s*[ xX]\s*\]`)
```

字符类必须出现，`[]` 不再命中。把上面 16 行逐行放回未勾选，交给这一笔前后的两版解析器：父提交 [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a) 上 16 行全部判成示例、完成门全部放行；合并 [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e) 上 0 行。

这一笔只改了空方括号这一类。别的写法在前后两版里各是什么结果，列在一起才看得清：

| 任务文字里的片段 | 父提交 `cd1ca6b1` | 合并 `904f2302` |
| --- | --- | --- |
| `[]string`、`default=[]` | 命中，判成示例 | 不命中，算任务 |
| 方括号里一个 tab | 命中 | 不命中 |
| `[ ]`、`[x]`、方括号里两个空格 | 命中 | 命中 |
| `s[x]`、`mark all tasks [x]` | 命中 | 命中 |
| `["CLAUDE.md"]`、`a[0]`、`[=true]` | 不命中 | 不命中 |

`[ ]`、`[x]`、方括号里两个空格这一格是它有意保留的：计划格式的两种标记本来就该认。`s[x]`、`mark all tasks [x]` 那一格是它没盖住的：任务文字里这么写，整个框照样被判成示例。tab 那格只是正则形状的边角——父版允许字符类空着，`\s*` 把 tab 吃掉就匹配；合并版要求字符类出现，而 `[ xX]` 只认空格或 `x`，方括号里只有一个 tab 时没有字符给它。

新增的测试只覆盖 `[]string` 那一行：断言 `IsActionable()` 为真、`HasUncompletedActionableWork()` 为真。相邻两个用例的断言仍是旧行为——`- [ ] use this format for [ ] unchecked items` 不算可执行项，`- [ ] use [ ] for format example` 旁边的真任务仍然算数。

补丁是按最小改动提的：只让字符类必须出现，不动豁免本身。豁免还在，就还是得靠文字去猜哪个框不是在说任务。

## 41 分钟后，维护者把整条豁免删了

[#484](https://github.com/umputun/ralphex/pull/484) 合并于 2026-11-22 18:14:59Z。41 分 22 秒之后，维护者自己的 [#486](https://github.com/umputun/ralphex/pull/486) 合了进来，合并提交 [`50843f0`](https://github.com/umputun/ralphex/commit/50843f0801609b08446b379e4d9f7ecc02d68f1c)。

它把 `formatInText` 和 `Checkbox.IsActionable` 整个删掉，`HasUncompletedActionableWork` 改名 `HasUncompletedCheckbox`：所有未勾选的框都算未完成。`pkg/plan/parse.go` 这一笔 +40/−46，`task.go` +4/−4。PR 里写的理由是：

> [#484](https://github.com/umputun/ralphex/pull/484) narrowed that to `[x]`, but the rule still hid real work: "mark all tasks `[x]`" or an index like `s[x]` counted as done, so a run could accept `ALL_TASKS_DONE` with those tasks open.

`mark all tasks [x]` 和 `s[x]` 正是上表里没变的那一格。仓库自己的计划另有 4 行是这种写法，比如 [`20260424-watch-mode-reactivate-tailing.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260424-watch-mode-reactivate-tailing.md#L294) 里的「mark all tasks `[x]`」，以及 [`20260512-resolve-renamed-plan.md`](https://github.com/umputun/ralphex/blob/abaf2af797acceee1a05514fbfc9b2101672a6be/docs/plans/completed/20260512-resolve-renamed-plan.md#L137) 里那句「file present + has `[ ]` → true」。它们在 #484 之后仍然会被判成示例，完成门照样放行。

真正的格式示例怎么办？`task.txt` 已经让 agent 把没法完成的框勾上（[#228](https://github.com/umputun/ralphex/pull/228)），一行示例最多多跑一轮，不再有理由把它藏起来。同一笔还收紧了围栏代码块的识别：opener 可以任意缩进，closer 最多比 opener 深 3 格，tab 按 4 列算——豁免拿掉之后，围栏里的示例框会不会被当成任务，取决于这条边界。

`HasUncompletedTasks` 里那句 warning 的文案没变，仍然写着「plan still has [ ] items」，尽管现在它数的是所有未勾选的框。

测试跟着重写，`parse_test.go` 一侧 +128/−45；源码两处加起来 +44/−50。

## 读者手上的 v1.7.0

[v1.7.0](https://github.com/umputun/ralphex/releases/tag/v1.7.0)（2026-09-07）是最新的发行版，里面的 `pkg/plan/parse.go` 还是带问号的写法，`formatInText` 在 `:51`，`IsActionable` 在 `:250`。#484 与 #486 都在 main 上，v1.7.0 之后没有新的 release，两笔修复都还没有发行。

也就是说，两层问题都还在：`[]string` 被判成示例，`s[x]`、`mark all tasks [x]` 也被判成示例。下一版带上的是 #486 的整块删除，不是 #484 的一个字符。

计划里的任务文字常常直接抄代码签名——Go 的 `[]string`、Python argparse 的 `default=[]`、shell 的 `a[0]`。在 v1.7.0 上，前两种会让完成门提前放行。还没跑的计划，用前面那行 grep 扫一遍；命中的行要么把任务拆开、别让方括号出现在任务文字里，要么等下一版把 #486 带上来。在 ralphex 自己的仓库里，这条命令现在命中 0 行——16 行都在 `completed/` 里勾成了 `[x]`；把其中任意一行放回 `- [ ]`，它就命中。

## 复现

两版 `pkg/plan/parse.go` 原样放在 [`空方括号_ralphex/plan_bracket_demo`](https://github.com/Master-Norna/notes/tree/main/%E7%A9%BA%E6%96%B9%E6%8B%AC%E5%8F%B7_ralphex/plan_bracket_demo) 的 `before/` 与 `after/`，完成门按 `pkg/processor/phase/task.go` 的 `HasUncompletedTasks` 逐行复刻，不需要 ralphex 本体。`go run .` 跑 13 个合成用例与 16 行真实任务，每个用例并排给出两版的判断：

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

`go test ./...` 断言这些结果，零依赖，Go 1.24+。

完成门要回答的只有一句：还有没有没勾的框，确实是一项任务。`[]string` 让这一句提前答成了「没有」；#484 把例外收窄一格，#486 干脆不再靠文字去猜。凡是按 Markdown 复选框推进的 runner，都会遇到同一个分界：任务文字里的方括号，和清单语法里的方括号，不是一回事。

上游：`umputun/ralphex`，[#484](https://github.com/umputun/ralphex/pull/484)，父提交 [`cd1ca6b1`](https://github.com/umputun/ralphex/commit/cd1ca6b18958bc2b4bdae71657b412611dcd6e3a)，合并提交 [`904f2302`](https://github.com/umputun/ralphex/commit/904f23025dd7390528585841fc3c1543b23c559e)。
