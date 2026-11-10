# 直播事件双发复现（ralphex #474）

`--serve` 加 watch 目录时，dashboard 同时走两条路：进程内的 `BroadcastLogger` 把每行直接推到 SSE，watcher 又发现同一个 `progress-*.txt`，从字节 0 起再读一遍。于是每行发两次。run 结束以后还有第二段：`RefreshStates` 清掉 live 标记，但会话既没被标成已加载、`lastOffset` 还是 0，下一次目录扫描会把整个文件重放进同一个会话。

本工程把两版 `pkg/web` 里的判定顺序抽成一个可跑的小模型：进度文件、BroadcastLogger、tailer 换成切片和计数，其余照原样保留 `!isLiveOutput` 门、`finishLiveOutput` 与 `resetForNewRun` 的顺序。

## 运行

```console
go run .
go test ./...
```

Go 1.21+，无第三方依赖。

## 输出

```text
parent: live line delivered 2 times, replayed 1 after the run
merged: live line delivered 1 times, replayed 0 after the run
```

上游两版源码上的真实回归测试给出同样的四个数字：父版 `TestReproLiveLinePublishedOnce` 收到 2 次、`TestReproFinishedLiveSessionReplays` 重放 1 行；合并版分别是 1 和 0。测试文件与两版源码快照留在仓库的检查记录里，不随本工程发布。

## 来源

- 父提交：`6f395870f7811be59e2dd1e25080d418c7172caa`
- 合并提交：`4647771bbe038b0a83e831ffcc07cf7ee978908b`
- 相关文件：`pkg/web/session.go`（`liveOutput`、`finishLiveOutput`、`StartTailing`、`Reactivate`、`resetForNewRun`）、`pkg/web/session_manager.go`（`updateSession` 的加载门、`RefreshStates`）、`pkg/web/dashboard.go`（`Start` 里的注册与标记）。
- 许可：上游 MIT，见 `LICENSE`。

这是机制模型，不是上游代码的逐字提取；`go.mod` 里的模块名只为本地运行。
