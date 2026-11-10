# The same log line arrived twice in the dashboard

```text
$ ralphex --serve --watch ~/plans
dashboard: http://localhost:8080

[12:00:01] TASK 1/3: add the retry guard
[12:00:01] TASK 1/3: add the retry guard
```

One run, one progress line, twice in the browser. Refresh the page and the whole history comes round again from the top.

ralphex reads a Markdown plan, splits it into tasks, calls Claude or Codex to execute them, and writes progress into `progress-*.txt`. `--serve` starts a dashboard that pushes progress to the browser over SSE. In single-session mode there is exactly one source: a `BroadcastLogger` in the same process wraps the progress logger, and every `Print` both writes the file and pushes an event.

Multi-session mode adds a second. When `--serve` has a watch directory, the watcher scans it for `progress-*.txt`, builds a session and a `Tailer` for each file, and reads from byte 0 — that is how progress from other runs gets displayed. The current run's progress file is in the directory being scanned too.

The watch directory is not redundant: a `--worktree` run writes its progress under its own worktree, and for the dashboard to watch several runs at once there has to be something that picks files up without depending on in-process objects. `Tailer` keeps `lastOffset` and reads only new bytes; `loadProgressFileIntoSession` reads a finished file whole. Both readings assume nobody else is pushing events for this file.

## One file, two readers

`Dashboard.Start` creates the session first:

```go
session := NewSession("main", d.baseLog.Path())
broadcastLog := NewBroadcastLogger(d.baseLog, session, d.holder)
...
sm.Register(session)
```

The session is registered with the `SessionManager`. Every line `BroadcastLogger` writes lands in `progress-*.txt` and is then broadcast directly to SSE clients.

When the watcher finds the same file, it goes `updateSession` → `handleStateTransition` → `StartTailing`, and the tailer reads from offset 0. The file already holds the lines `BroadcastLogger` just wrote, so the same line is published a second time: once from memory, once from the file.

The watcher knows the file is locked, too — `IsActive` checks `IsPathLockedByCurrentProcess` first, counting a lock held by this process as active, and only then tries flock. But the lock carries no information about which session is feeding the file, so the same file is taken for an active session and a tailer opens as usual.

What duplicates is not only an output line: a section header is drawn twice, a task is marked twice at its boundary, and the task count doubles. The SSE replay buffer stores the duplicated events as well, so refreshing the page is not "back to a clean state" — it replays the duplication.

## First, mark the session

`SessionState` has two values, `active` and `completed`, and "where the events come from" is not among them. The first fix adds a separate boolean outside: `Dashboard.Start` marks the session [`liveOutput`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L113) before registering it.

```go
session.SetState(SessionStateActive)
session.markLiveOutput()
```

[`StartTailing`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L434) and [`Reactivate`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L476) return early when they see the mark — the events are already live from `BroadcastLogger`, so there is no reason to open a file reader. The loader gate in `updateSession` gains a `!session.isLiveOutput()` too: a live session the loader has never read must not be taken for a "finished but not yet loaded" file when the run ends.

With that in place, duplication during a run is gone.

This path only exists in multi-session mode, that is `useMultiSession := len(d.watchDirs) > 0 || len(d.configWatchDirs) > 0`. In single-session mode `sm` does not exist at all and the session goes straight to `NewServer`, so the first fix covers one case: `--serve` with a watch directory.

## The run ends, and the whole file is read again

The maintainer read it and requested changes: the in-run duplication is gone, but the replay after the run is not.

> the in-run duplication is gone, but the session still gets the whole run replayed once the run ends.

The path is this: the run ends, [`RefreshStates`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session_manager.go#L383) sees the session is no longer active, sets the state to completed, stops the tailer, and clears `liveOutput`. But the session was never marked loaded — its content did not come from the file, it was pushed by `BroadcastLogger`. And `lastOffset` is still 0.

The next directory scan (say another `--worktree` run in the same directory writes a new progress file) goes through `updateSession` again. This time the session is not live, `MarkLoadedIfNot` returns true, `lastOffset == 0`, and the loader reads the whole file into the same session. Every line appears a second time, and refreshing the page does not help.

The fix lands in [`finishLiveOutput`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L270): the same locked region that clears `liveOutput` also sets `loaded`.

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

`lastOffset` is deliberately left at 0. There is an inconspicuous edge here: if the same plan is rerun within the same second, the `Started:` timestamp does not change, `updateSession`'s restart detection does not fire, and the file is truncated and rewritten. If `lastOffset` had been set to the old file's size, the new run's read would start in the middle and drop the first lines. Left at 0, a new run reads from byte 0; the old live session is already marked loaded and will not touch this file again.

[`resetForNewRun`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/session.go#L349) has to clear `liveOutput` as well. Once a new run rewrites the same progress file, it is no longer fed by the previous run's `BroadcastLogger` and belongs back on the ordinary tailer path. Miss that line and the new run stays empty.

## Four more from the same review

The review was changes-requested: one blocking item and four smaller ones. Of the four, two are behaviour defects and two are test problems.

When `archivePlan` fails it writes a `WARN:` line. Under watch mode the tailer reads that line back into the dashboard; a `--serve` live session has no tailer, so the line never reaches the UI. The fix is to give `archivePlan` the runner logger, and [`BroadcastLogger.Warn`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/broadcast_logger.go#L164) forwards to the inner logger and emits a warn event besides.

`LogDiffStats` is the same: the diff statistics at completion are only written to the file, and a live session cannot see them. [`BroadcastLogger.LogDiffStats`](https://github.com/umputun/ralphex/blob/4647771bbe038b0a83e831ffcc07cf7ee978908b/pkg/web/broadcast_logger.go#L174) writes the file and also emits `DIFFSTATS: files=… additions=… deletions=…` as an output event.

Neither of these is the duplication problem, but the premise is the same: a live session's events can only come from `BroadcastLogger`, and what is written to the file does not return to the UI by itself. Once the tailer is ruled out, the lines that used to come back through it have to be supplied from somewhere else.

The other two are about tests: `resetForNewRun`'s `liveOutput=false` has no test, and the `Eventually` condition waiting for `SessionStateActive` is in fact true immediately.

## Four numbers

The project in `直播双发_ralphex/live_double_tail_demo/` reduces both versions' decision order to a small model: the progress file, `BroadcastLogger` and tailer become slices and counters, while the `!isLiveOutput` gate, `finishLiveOutput` and `resetForNewRun` keep their original order.

```console
$ go run .
parent: live line delivered 2 times, replayed 1 after the run
merged: live line delivered 1 times, replayed 0 after the run
```

Running the same reproduction test against both versions of the real source gives the same four numbers:

| test | parent | merged |
| --- | --- | --- |
| times one live output line reaches SSE | 2 | 1 |
| lines replayed after the run ends | 1 | 0 |

The PR adds seven tests in all, two of them the rows above: `TestDashboard_Start_MultiSessionDoesNotDuplicateLiveEvents` counts how often a live line reaches SSE, and `TestSessionManager_LiveSessionDoesNotReplayFinishedFile` checks whether anything is replayed after the run. Two watch forwarding (`Warn`, `LogDiffStats`) and the remaining three watch sessions: a live session is not tailed, a new run can keep going, and rerunning the same plan goes back to the tailer.

Those seven tests do not run against the parent: `markLiveOutput`, `isLiveOutput`, `Warn` and `LogDiffStats` do not exist there, so `go test` fails to compile with seven lines of undefined methods. Reproducing means going around the compiler — write the decision order as a test that touches no new method, and probe the marking step with an interface assertion: the parent does not have it and takes the old path, the merge has it and the mark takes effect. The four numbers in the table came out that way.

The replay looks worse than its row in the table: the whole file is read into the session and every line in the history appears a second time. Other runs open in the dashboard are unaffected — the problem is only in the one session fed by two sources at once.

## The test that fooled itself

The first version of the regression test waits with `Eventually` for `SessionStateActive`, which looks reasonable. In fact `Dashboard.Start` sets the session to Active itself, so the condition is true immediately and the wait degrades to a fixed 200 ms sleep. If discovery is a little slow, the test counts events before the watcher is up and gets 0 instead of 2.

The review pointed this out and the test now waits for a non-zero `GetMetadata().StartTime`, a field only discovery writes. It waits for "the watcher has really looked at this directory" instead of "the session happens to be in some state".

Wait on the wrong condition and the parent fails even at 0 counts, which looks like the bug reproduced when in fact nothing happened at that moment.

Upstream: `umputun/ralphex`, [#474](https://github.com/umputun/ralphex/pull/474), parent commit [`6f395870`](https://github.com/umputun/ralphex/commit/6f395870f7811be59e2dd1e25080d418c7172caa), merge commit [`4647771b`](https://github.com/umputun/ralphex/commit/4647771bbe038b0a83e831ffcc07cf7ee978908b). The review itself is in the [pull/474 discussion](https://github.com/umputun/ralphex/pull/474#pullrequestreview-5819043862).
