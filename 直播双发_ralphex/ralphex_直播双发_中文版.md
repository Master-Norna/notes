# 同一行日志，dashboard 收到了两次

```text
$ ralphex --serve --watch ~/plans
dashboard: http://localhost:8080

[12:00:01] TASK 1/3: add the retry guard
[12:00:01] TASK 1/3: add the retry guard
```

一次 run，一行进度，浏览器里出现两次。刷新页面，整段历史又从头来一遍。

ralphex 读一份 Markdown 计划，拆成任务，调用 Claude 或 Codex 执行，进度写进 `progress-*.txt`。`--serve` 起一个 dashboard，用 SSE 把进度推给浏览器。单会话模式下事件源只有一条：进程里的 `BroadcastLogger` 包住 progress logger，每次 `Print` 既写文件，也推事件。

多会话模式多出一条。`--serve` 带 watch 目录时，watcher 扫目录里的 `progress-*.txt`，每个文件建一个 session 和一个 `Tailer`，从字节 0 读——这样别的 run 的进度也能显示。当前这个 run 的进度文件也在被扫的目录里。

watch 目录不是多余的：`--worktree` 的 run 把进度写在自己的 worktree 下，dashboard 要同时看几个 run，就得有个不依赖进程内对象的东西把文件捡起来。`Tailer` 记 `lastOffset`，只读新增的字节；`loadProgressFileIntoSession` 在文件已完成时一次读全量。两条读法都默认「这个文件没有别人在实时推」。

## 同一个文件，两条读法

`Dashboard.Start` 起来先建 session：

```go
session := NewSession("main", d.baseLog.Path())
broadcastLog := NewBroadcastLogger(d.baseLog, session, d.holder)
...
sm.Register(session)
```

session 注册进 `SessionManager`。`BroadcastLogger` 每写一行，先落进 `progress-*.txt`，再直接 `broadcast` 给 SSE 客户端。

watcher 发现同一个文件后，走 `updateSession` → `handleStateTransition` → `StartTailing`，tailer 从 offset 0 读。文件里已经有 `BroadcastLogger` 刚写下的行，同一行于是被第二次发布：一次来自内存，一次来自文件。

watcher 也知道这个文件被锁着——`IsActive` 先查 `IsPathLockedByCurrentProcess`，被本进程锁也算 active，然后才去试 flock。可这把锁不携带「是哪个 session 在喂」的信息，同一个文件照样被当成活跃会话，照常开 tailer。

重复的不只是一行 output：section header 画两遍，同一个任务被标两次边界，任务计数翻倍。SSE 的 replay buffer 里存的也是重复后的事件，刷新页面不是「恢复干净状态」，是把重复再过一遍。

## 先给 session 打个标记

`SessionState` 只有 `active` 和 `completed` 两个值，「事件从哪来」不在这两个值里。初版修复在外面加了一个独立的布尔字段：`Dashboard.Start` 在注册前给 session 标一个 [`liveOutput`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L113)。

```go
session.SetState(SessionStateActive)
session.markLiveOutput()
```

[`StartTailing`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L434) 与 [`Reactivate`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L476) 看到这个标记就早退——事件已经由 `BroadcastLogger` 直播了，不用再开一条文件读取。`updateSession` 的 loader 门也跟着加了 `!session.isLiveOutput()`：一个从没被 loader 读过的 live session，不能在 run 结束时被当成「完成了但还没加载」的文件。

按这段改完，run 进行中的重复没有了。

这条路径只在多会话模式下存在，也就是 `useMultiSession := len(d.watchDirs) > 0 || len(d.configWatchDirs) > 0`。单会话时 `sm` 根本不存在，session 直接交给 `NewServer`，所以初版修复管的是「`--serve` 配了 watch 目录」这一种情况。

## run 结束，整个文件又读了一遍

维护者看完，CHANGES_REQUESTED：in-run 的重复没了，但 run 结束以后整个文件还会重放。

> the in-run duplication is gone, but the session still gets the whole run replayed once the run ends.

路径是这样的：run 结束，[`RefreshStates`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session_manager.go#L383) 发现会话不再活跃，状态改成 completed，停掉 tailer，然后清掉 `liveOutput`。但 session 从来没有被标记成 loaded——它的内容不是从文件加载的，是 `BroadcastLogger` 直接推的。`lastOffset` 也还是 0。

下一次目录扫描（比如同目录里另一个 `--worktree` run 写了新的进度文件）会再走一遍 `updateSession`。这次 session 不是 live 了，`MarkLoadedIfNot` 返回 true，`lastOffset == 0`，loader 把整个文件读进同一个 session。所有行第二次出现，刷新页面也一样。

修复放在 [`finishLiveOutput`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L270) 里：清 `liveOutput` 的同一个锁区把 `loaded` 置上。

```go
func (s *Session) finishLiveOutput() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.liveOutput {
		return
	}
	s.liveOutput = false
	s.loaded = true
}
```

`lastOffset` 故意留在 0。这里有一个不显眼的边界：同一个计划在同一秒内重跑，`Started:` 时间戳不变，`updateSession` 的重启检测不会触发，文件被截断重写。如果 `lastOffset` 被设成旧文件的大小，新 run 的读取会从中间开始，开头几行直接丢掉。留在 0，新 run 从字节 0 读；旧的 live session 已经被标记 loaded，不会再碰这个文件。

[`resetForNewRun`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L349) 也要把 `liveOutput` 清掉。同一个进度文件被新 run 重写后，它不再由上一个 run 的 `BroadcastLogger` 喂养，该回到普通的 tailer 路径。漏了这一句，新 run 会一直空着。

## 同一次 review 的另外四条

这次 review 是 CHANGES_REQUESTED，blocking 一条，smaller 四条。后四条里，两条是行为缺陷，两条是测试问题。

`archivePlan` 失败时写的是 `WARN:` 行。watch 模式下 tailer 会把文件里这行读回 dashboard；`--serve` 的 live session 没有 tailer，这行永远到不了界面。修法是让 `archivePlan` 拿 runner logger，[`BroadcastLogger.Warn`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/broadcast_logger.go#L164) 在转发给内层 logger 的同时，也发一个 warn 事件。

`LogDiffStats` 同理：完成时的 diff 统计只写进文件，live session 看不到。[`BroadcastLogger.LogDiffStats`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/broadcast_logger.go#L174) 在写文件之外，把 `DIFFSTATS: files=… additions=… deletions=…` 作为一条 output 事件发出去。

这两处和重复问题不是一回事，前提却一样：live session 的事件只能来自 `BroadcastLogger`，写进文件的东西不会自己回到界面。既然取消了 tailer，原来靠它读回来的行就得从别处补上。

另外两条小意见都在测试上：`resetForNewRun` 的 `liveOutput=false` 没有测试；`Eventually` 等 `SessionStateActive` 的那个条件，其实立刻为真。

## 四个数字

工程 `直播双发_ralphex/live_double_tail_demo/` 把两版的判定顺序抽成一个小模型：进度文件、`BroadcastLogger`、tailer 换成切片与计数，`!isLiveOutput` 门、`finishLiveOutput`、`resetForNewRun` 的顺序照原样保留。

```console
$ go run .
parent: live line delivered 2 times, replayed 1 after the run
merged: live line delivered 1 times, replayed 0 after the run
```

在两版真实源码里跑同一份复现测试，得到同样的四个数字：

| 测试 | 父版 | 合并版 |
| --- | --- | --- |
| 一行 live 输出到达 SSE 的次数 | 2 | 1 |
| run 结束后重放的行数 | 1 | 0 |

PR 一共加了七个测试，上表两行各占一个：`TestDashboard_Start_MultiSessionDoesNotDuplicateLiveEvents` 数 live 行到达 SSE 的次数，`TestSessionManager_LiveSessionDoesNotReplayFinishedFile` 看 run 结束后会不会重放。两个盯转发（`Warn`、`LogDiffStats`），剩下三个盯 session：live session 不被 tail、新 run 能接着跑、重跑同一份计划时重新走 tailer。

这七个测试在父版上跑不起来：`markLiveOutput`、`isLiveOutput`、`Warn`、`LogDiffStats` 在父版里都不存在，`go test` 直接编译失败，报了七行未定义方法。要复现得绕开编译——把判定顺序写成不碰新方法的测试，标记那一步用接口断言探一下：父版探不到，走原来的路径；合并版探到了，标记生效。上表那四个数字是这么跑出来的。

重放的样子比表格里那一行难看：整个文件从头读进 session，历史里每一行都出现第二次。dashboard 还开着别的 run 时，那些 session 不受影响——问题只出在被两条源同时喂的那一个上。

## 那个测试自己骗自己

初版的回归测试用 `Eventually` 等 `SessionStateActive`，看起来合理。实际上 `Dashboard.Start` 自己就把 session 设成了 Active，这个条件立刻为真，等待退化成固定 200ms 的 sleep。discovery 慢一点，测试就会在 watcher 还没跑起来时去数事件，得到 0 而不是 2。

review 指出这一点，改成等 `GetMetadata().StartTime` 非零——只有 discovery 会写这个字段。测试从此等的是「watcher 真的看过这个目录」，而不是「session 刚好处于某个状态」。

等错了条件，父版数到 0 次也会失败，看着像 bug 复现了，其实那一刻什么都没发生。

上游：`umputun/ralphex`，[#474](https://github.com/umputun/ralphex/pull/474)，父提交 [`6f395870`](https://github.com/umputun/ralphex/commit/6f395870f7811be59e2dd1e25080d418c7172caa)，合并提交 [`4647771b`](https://github.com/umputun/ralphex/commit/4647771bbe038b0a83e831ffcc07cf7ee978908b)。review 原文见 [pull/474 讨论](https://github.com/umputun/ralphex/pull/474#pullrequestreview-5819043862)。
