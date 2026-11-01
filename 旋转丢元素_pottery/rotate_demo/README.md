# Pottery：转四步，少了一个元素

用两份**完整、固定提交的 pottery 源码**，在进程内的 **fakeredis** 模拟器上对照 [pottery #857](https://github.com/brainix/pottery/pull/857) 修前与合并版。不是真实 Redis 服务，也不安装 pottery 或 fakeredis。

## 运行

最低 **Python 3.11**，只用标准库和工程内已带的三份纯 Python 依赖。本轮实测 CPython 3.12.14。

从仓库根目录运行：

```powershell
python -B -S 旋转丢元素_pottery/rotate_demo/run.py --test
python -B -S 旋转丢元素_pottery/rotate_demo/run.py --test --json
python -B -S 旋转丢元素_pottery/rotate_demo/run.py --test --output rotate.json
```

也可以把整个 `rotate_demo/` 单独复制出去，在任意工作目录用其 `run.py` 的绝对路径执行。不依赖仓库其他文件、`.yan/`、Git、网络或 pip。

- `--test` 明确请求全部断言；不传也执行同样的校验。
- `--json` 让 stdout 只含完整 JSON；`--output PATH` 同时保存相同格式的报告。
- 入口会确认 `-I -B -S`，缺少时自动启动相同解释器的隔离子进程，再为两版分别启动子进程。`-I` 忽略 `PYTHONPATH` 与用户 site，`-S` 不加载 site-packages，`-B` 不写 `.pyc`。
- 子进程安装 Python audit hook，拒绝所有 `socket.*` 事件；fakeredis 是进程内模拟器，不会建立真实连接。
- 只加载原样的 `pottery/deque.py` 及其依赖；`pottery/__init__.py` 还会导入需要可选 `mmh3` 扩展的 BloomFilter/HyperLogLog，与本例无关，因而没有走顶层 `from pottery import RedisDeque`。`deque.py` 本身未改一行。

成功输出：

```text
Python 3.12.14  backend: fakeredis (in-process emulator), NOT a Redis server
parent f6e59b0127f3: 369 cases, 204 mismatches
merge  4e98b44cb888: 369 cases, 0 mismatches

length=3  n   stdlib/merge        parent              parent commands
----------------------------------------------------------------------------------------------
        4  [3, 1, 2]            [1, 2, 3]            LPUSH case 3 2 1; LTRIM case 0 2
       -4  [2, 3, 1]            [2, 3]               RPUSH case 1 2 3; LTRIM case 4 6
        6  [1, 2, 3]            [1, 2, 3]            LPUSH case 3 2 1; LTRIM case 0 2
       -6  [1, 2, 3]            []                   RPUSH case 1 2 3; LTRIM case 6 8
        7  [3, 1, 2]            [1, 2, 3]            LPUSH case 3 2 1; LTRIM case 0 2
       -7  [2, 3, 1]            []                   RPUSH case 1 2 3; LTRIM case 7 9

10-element rotate(-2): actual [2, 3, 4, 5, 6, 7, 8, 9, 0, 1]
  commands: RPUSH cost 0 1; LTRIM cost 2 11
  bare modulo would be 8, pushing 8 values

PASS: all 369 cases match collections.deque after the fix; the pre-fix version loses elements at the boundary.
```

## 输入与观测

每个长度 0–8、步数 −20–20 的用例都新建一个 `FakeRedis`，用 `RedisDeque(range(1, length+1))` 初始化，然后只追踪 `rotate()` 期间发出的命令。读回值用 `LRANGE key 0 -1`；期望值来自同长度的 `collections.deque.rotate`。

`rotate()` 内部走 `MULTI`/`EXEC`，所以命令按 pipeline 顺序记录；表中只列 `LPUSH`/`RPUSH`/`LTRIM`，`WATCH`、`LLEN`、`MULTI` 等不计入“搬了几个值”。

## 固定版本与来源

| 目录 | 固定提交 | 角色 |
|---|---|---|
| `vendor/parent/` | [`f6e59b0127f3375278fd473450fff1152548f7c7`](https://github.com/brainix/pottery/commit/f6e59b0127f3375278fd473450fff1152548f7c7) | #857 合并提交的实际第一父提交（修前） |
| `vendor/merge/` | [`4e98b44cb888f08660c5f6f943fac4f62c95b3e5`](https://github.com/brainix/pottery/commit/4e98b44cb888f08660c5f6f943fac4f62c95b3e5) | #857 合并版 |

工程自带 `fakeredis 2.38.0`（BSD-3-Clause）、`redis 8.1.0`（MIT）、`sortedcontainers 2.4.0`（Apache-2.0）的纯 Python 源码与许可证，放在 `vendor/site/`。`provenance.json` 记录两版 pottery 的 codeload URL、归档 SHA-256/字节数、两版共 38 个源码文件的哈希，以及 193 个依赖文件的哈希。完整 tar 归档不随工程分发。

## 测了哪些合同

| 用例 | 修前 parent | 合并版 merge |
|---|---|---|
| `[1,2,3].rotate(4)` | `[1,2,3]`，`LPUSH 3 2 1` 后 `LTRIM 0 2` | `[3,1,2]`，`LPUSH 3` 后 `LTRIM 0 2` |
| `[1,2,3].rotate(-4)` | `[2,3]`，`RPUSH 1 2 3` 后 `LTRIM 4 6` | `[2,3,1]`，`RPUSH 1` 后 `LTRIM 1 3` |
| `[1,2,3].rotate(6)` | `[1,2,3]`（碰巧对），仍整份 push/trim | `[1,2,3]`，不发 push/trim |
| `[1,2,3].rotate(-6)` | `[]`，`LTRIM 6 8` 把内容全裁掉 | `[1,2,3]`，不发 push/trim |
| `[1,2,3].rotate(7)` | `[1,2,3]`，`LTRIM 0 2` | `[3,1,2]`，`LPUSH 3` 后 `LTRIM 0 2` |
| `[1,2,3].rotate(-7)` | `[]`，`LTRIM 7 9` | `[2,3,1]`，`RPUSH 1` 后 `LTRIM 1 3` |
| 0–8 长度 × −20–20 步（369 例） | 204 例与 `collections.deque` 不符 | 0 例不符 |
| `rotate(None / "a" / 0.5)` | `TypeError` | `TypeError` |

`-6` 和 `6` 都是整圈，修前却仍构造 push/trim：整圈负向会把 `LTRIM` 的起点推到原长度之外，于是内容被裁空。合并版在 `n %= length` 后直接返回，不再发命令。

10 元素 `rotate(-2)` 是“为什么不用裸取模”的对照：`-2 % 10 == 8`，裸取模会把左移 2 个变成右移 8 个；合并版把 `8` 折回 `-2`，实际只 `RPUSH` 两个值。本轮测到的是**命令参数与最终列表**，不是耗时或吞吐量。

## 范围

这是 fakeredis 进程内模拟，不是真实 Redis 服务。没有覆盖真实服务的并发、WATCH 竞争、网络故障、持久化、TTL、跨版本差异、`maxlen` 与 `rotate` 的组合，也没有验证超大整数或非普通 `int` 的边界。固定提交合并事实不等于首次发行版本或受影响版本范围。
