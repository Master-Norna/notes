# AnyIO：取消 receive 后，谁把读取暂停？

这是 [AnyIO PR #1424](https://github.com/agronholm/anyio/pull/1424) 的真实 TCP 复现。相同的 `probe.py` 分别在两个独立 Python 子进程中运行，不修改上游源码，也不模拟 transport。

| 版本 | 固定提交 |
| --- | --- |
| before | [`633965bad02a857574b3dbad03d1ef9f35e9caa4`](https://github.com/agronholm/anyio/tree/633965bad02a857574b3dbad03d1ef9f35e9caa4) |
| after | [`6219807568bd7c32f2c08f923c7d93f95c836127`](https://github.com/agronholm/anyio/tree/6219807568bd7c32f2c08f923c7d93f95c836127) |

## 运行

需要 Python 3.12+，已在 Windows 11 / Python 3.12.14 验证。进入本目录后：

```powershell
python -m pip install -r requirements.txt
python run.py --test
```

第一次运行通过标准库 `urllib` 下载两个固定 SHA 的 GitHub zip，保存在本目录的 `.sources/`，之后直接复用。`requirements.txt` 只有上游需要的 `idna` 与 `typing_extensions`；不必安装 AnyIO，已安装的 AnyIO 也不会代替快照。脚本通过 `PYTHONPATH=快照/src` 选择源码，校验 `_asyncio.py` 的 SHA256，并检查探针返回的实际导入路径。源码缓存、字节码均由本目录的忽略规则排除，不进入提交。

再次运行可以完全离线，并保留详细 JSON：

```powershell
python run.py --offline --repeat 10 --output results.json
```

`--offline` 禁止下载；缓存不全就报错，不回退到 pip 安装的 AnyIO。`--output` 仅在显式指定时写文件，包含完整 SHA、Python/系统/事件循环、导入路径、实际观察时长、取消标志、队列与数据校验结果。`results.json` 是用户自行指定的结果文件，不属于源码缓存。

Windows 默认使用 Proactor；另测 Selector：

```powershell
python run.py --offline --loop selector --test --repeat 10
```

已有解压源码时，可用 `python run.py --source-root D:\snapshots\anyio --offline --test`，不下载。该路径下应有 `before/<快照目录>/src/anyio` 与 `after/<快照目录>/src/anyio`，也支持 `before/src/anyio`、`after/src/anyio`。

## 三项检查

1. **已取消的 scope。** 按上游新增回归测试的顺序：建立连接，`scope.cancel()`，再 `await stream.receive()`。检查取消确实穿过 `receive()`，随后由该 scope 接住，并观察 `transport.is_reading()`。
2. **已经阻塞的 receive。** 子任务进入自己的取消域；`wait_all_tasks_blocked()` 后确认没有数据、接收未完成、transport 正在读取，再取消它。等待子任务退出后检查取消传播和读取状态。不是用短暂 `sleep` 猜测它是否阻塞。
3. **取消后的缓冲与恢复。** 取消阻塞接收后，对端通过真实的 `127.0.0.1` TCP socket 发送 4 MiB。接收端等待约 0.3 秒，其间不调用 `receive()`；随后统计 `protocol.read_queue` 的字节数，再恢复接收。全部内容逐字节比较并计算 SHA256；继续发送新消息、反向回复 `ack`，确认连接仍可双向使用。

发送任务与接收流程并行。即使修复版让发送端等待，观察窗口结束后也会开始接收，不会先等发送完成而死锁。每次探针有 20 秒总超时，父进程对子进程另设 90 秒上限；未完成的发送/accept 任务和 socket 都在退出时清理。

`--test` 对每份源码运行 3 项标准库 `unittest` 集成测试，共 6 项，然后运行并打印探针快照。before 的通过表示**成功复现旧缺陷**：预期读取仍开启、队列确实有积累；after 的通过才表示取消后读取回到暂停状态。两版都必须取消正常传播、最终数据完整、连接可复用。

## 实测

Windows 11 `10.0.26300`、Python `3.12.14`，默认 `ProactorEventLoop`，一次实际输出：

```text
before #1 ProactorEventLoop already_reading=True blocked_reading=True queue=4194304 B/0.3s sender_done=True received=4194304 B intact=True reused=True
after  #1 ProactorEventLoop already_reading=False blocked_reading=False queue=0 B/0.3s sender_done=True received=4194304 B intact=True reused=True
PASS: expected before/after states, cancellation, full payload and bidirectional reuse
```

额外各复跑 10 次（每版、每种循环均为 10 次）：

| 循环 | before 的队列范围 | after 的队列范围 | 每版 10 次取消/完整性/复用检查 |
| --- | ---: | ---: | --- |
| `ProactorEventLoop` | 4,194,304–4,194,304 B | 0–0 B | 全过 |
| `_WindowsSelectorEventLoop` | 4,194,304–4,194,304 B | 0–0 B | 全过 |

两种循环的 3×2 项 unittest 也均通过；另外实际验证过默认下载入口与已有缓存的离线入口。全部 4 MiB 载荷的 SHA256 为 `2b07811057df887086f06a67edc6ebf911de8b6741156e7a2eb1416a4b8b1b2e`。

## 观察边界

这是 loopback 的机制快照，不是 RSS 测量、内存上界或吞吐 benchmark。统计的是 AnyIO 的用户态队列，不包括内核缓冲；`read_queue`、`_transport` 是诊断用的私有实现细节。0.3 秒是等待目标，调度与时钟精度会影响实际采样，JSON 另记 `observed_seconds`。

本机修复后队列为 0，但脚本不把 0 当成跨平台保证：可能还有在途回调。关键断言是取消后 `is_reading() == False`，且恢复接收后数据完整、连接可用。两版的 `sender_done=True` 也说明这次 4 MiB 能进入系统缓冲，不能宣称修复后发送端会立即阻塞。

`LICENSE` 原样保留上游 MIT 正文及 Alex Grönholm 署名。
