# 空方括号复现（ralphex #484）

`formatInText` 用来认出「任务文字里引用了格式示例」的复选框，比如 `- [ ] use this format for [ ] unchecked items`。它的字符类 `[ xX]?` 带问号，空 `[]` 也命中；任务文字里的 `[]string`、`[]T`、`default=[]` 于是被当成示例，`Checkbox.IsActionable()` 返回 false，完成门看不到这一项。

本工程把父提交与合并提交的 `pkg/plan/parse.go` 原样放进 `before/` 与 `after/`，同一份计划交给两版；完成门是对 `pkg/processor/phase/task.go` 里 `TaskPhase.HasUncompletedTasks` 的逐行小模型：先遍历任务，只有计划解析出零个任务节时才退到 `FileHasUncompletedCheckbox`。

## 运行

```console
go test ./...
go run .
```

Go 1.24+，无第三方依赖。

## 输出

```text
case               before                       after
slice-type         not actionable, completed    actionable, continuing
format-example     not actionable, completed    not actionable, completed
mixed              actionable, continuing       actionable, continuing
checked-slice      not actionable, completed    not actionable, completed
bracket-x          not actionable, completed    not actionable, completed
spaces             not actionable, completed    not actionable, completed
tab                not actionable, completed    actionable, continuing
cli-flag           actionable, continuing       actionable, continuing
array-index        actionable, continuing       actionable, continuing
index-x            not actionable, completed    not actionable, completed
marker-x           not actionable, completed    not actionable, completed
no-task-slice      no task section, completed   no task section, continuing
no-task-example    no task section, completed   no task section, completed

real docs/plans rows: 16
  before: 16/16 rows end the gate as completed
  after:  0/16 rows end the gate as completed
```

`fixtures/real_checkboxes.tsv` 是仓库 `docs/plans/` 里 16 行任务文字带 `[]` 的 checkbox，格式 `file:line<TAB>text`；每行单独改回 `- [ ]` 跑一遍。

## 来源

- 父提交：`cd1ca6b18958bc2b4bdae71657b412611dcd6e3a`
- 合并提交：`904f23025dd7390528585841fc3c1543b23c559e`
- 相关文件：`pkg/plan/parse.go`（`formatInText`、`Checkbox.IsActionable`、`Task.HasUncompletedActionableWork`、`FileHasUncompletedCheckbox`）、`pkg/processor/phase/task.go`（`TaskPhase.Run` 的完成信号、`HasUncompletedTasks`）。
- 许可：上游 MIT，见 `LICENSE`。

这是对完成门的小模型，不是上游 `TaskPhase` 的逐字提取；`parse.go` 两版是原样快照。
