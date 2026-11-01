# tomlkit：本地时间没有时区

用两份**完整、固定提交的 tomlkit 源码**离线对照 [tomlkit #613](https://github.com/python-poetry/tomlkit/pull/613) 修前与合并版。不安装 tomlkit，不需要网络或 pytest。

## 运行

最低 **Python 3.11**，只用标准库。本轮实测 CPython 3.12.14。

从仓库根目录运行：

```powershell
python -B -S 本地时间_tomlkit/local_time_demo/run.py --test
python -B -S 本地时间_tomlkit/local_time_demo/run.py --test --json
python -B -S 本地时间_tomlkit/local_time_demo/run.py --test --output local-time.json
```

也可以把整个 `local_time_demo/` 单独复制出去，在任意工作目录用其 `run.py` 的绝对路径执行。不依赖仓库其他文件、`.yan/`、Git、网络或安装步骤。

- `--test` 明确请求全部断言；不传也执行同样的校验。
- `--json` 让 stdout 只含完整 JSON；`--output PATH` 同时保存相同格式的报告。
- 入口会确认 `-I -B -S`，缺少时自动启动相同解释器的隔离子进程，再为两版分别启动子进程。`-I` 忽略 `PYTHONPATH` 与用户 site，`-S` 不加载 site-packages，`-B` 不写 `.pyc`。
- 子进程安装 Python audit hook，拒绝所有 `socket.*` 事件。

成功输出：

```text
Python 3.12.14  (two complete tomlkit snapshots, no install)
case                         parent 763bd66                   merge ce8f8ee
----------------------------------------------------------------------------------------------
aware.as_string()            07:32:00+02:00                   07:32:00
micro.as_string()            07:32:00.123450+02:00            07:32:00.12345
aware.replace(hour=13)       13:32:00+02:00                   13:32:00
dumps()                      t = 07:32:00+02:00               t = 07:32:00
parse(dumps())               InvalidTimeError                 ok
naive.as_string()            07:32:00                         07:32:00

PASS: parent writes 07:32:00+02:00 and cannot parse its own output; merge writes 07:32:00, parses it back, and leaves naive times unchanged.
```

## 输入与观测

`time(7, 32, tzinfo=timezone(timedelta(hours=2)))` 是 Python 的“带时区的时间”。把它交给 `tomlkit.item()`：

- 修前用 `value.isoformat()` 生成 raw 文本，得到 `07:32:00+02:00`；
- 合并版用 `_format_time()` 只取时、分、秒、微秒，得到 `07:32:00`。

再把 `dumps({"t": item(...)})` 的结果交回 `tomlkit.parse()`。修前版写出的不是合法 TOML，自己的解析器在 `+02:00` 处抛 `InvalidTimeError`；合并版能原样读回。`replace(hour=13)` 走 `Time._new()`，同样从 `isoformat()` 改为 `_format_time()`，所以也在对照表中。

## 固定版本与来源

| 目录 | 固定提交 | 角色 |
|---|---|---|
| `vendor/parent/` | [`763bd661bfed068209c03510ae94493eb2db12b5`](https://github.com/python-poetry/tomlkit/commit/763bd661bfed068209c03510ae94493eb2db12b5) | #613 合并提交的实际第一父提交（修前） |
| `vendor/merge/` | [`ce8f8ee982411c4afef5cfb90df7313cc5f7d779`](https://github.com/python-poetry/tomlkit/commit/ce8f8ee982411c4afef5cfb90df7313cc5f7d779) | #613 合并版 |

两版都报告 `tomlkit 0.15.1`；版本字符串相同不代表源码相同，差异在 `tomlkit/items.py` 的 `_format_time()` 与两处调用。**0.15.2 的发布说明明确列出了 #613**，所以这个问题也存在于已发布版本；用发布轮子 `tomlkit-0.15.2-py3-none-any.whl` 另跑一次，输出与本工程合并版一致（`07:32:00`，可读回）。

[`provenance.json`](provenance.json) 记录固定 SHA、codeload URL、归档 SHA-256/字节数，以及入库的 26 个快照文件哈希。完整 tar 归档不随工程分发。

## 测了哪些合同

| 用例 | 修前 parent | 合并版 merge |
|---|---|---|
| 带 `+02:00` 的 `time` 的 `as_string()` | `07:32:00+02:00` | `07:32:00` |
| 带微秒 `123450` | `07:32:00.123450+02:00` | `07:32:00.12345`（去尾零） |
| `item(...).replace(hour=13)` | `13:32:00+02:00` | `13:32:00` |
| `dumps({"t": item(...)})` | `t = 07:32:00+02:00` | `t = 07:32:00` |
| 把上一步的结果 `parse()` 回来 | `InvalidTimeError` | 成功，读回 `07:32:00` |
| 无时区的 `time(7, 32)` | `07:32:00` | `07:32:00`（逐字节不变） |
| 直接 `parse("t = 07:32:00+02:00")` | `InvalidTimeError` | `InvalidTimeError`（解析器本来就不接受偏移） |

最后一行是边界：合并版没有让解析器接受偏移，只是不再把偏移写进本地时间。TOML 1.0 的 Local Time 明确说它“没有日期，也没有偏移或时区”；带偏移的时间在 TOML 里应写成 Offset Date-Time，而不是 Local Time。

## 范围

这是一个 `time` 序列化与回读的窄复现。没有覆盖 `datetime`、`date`、`fold` 与偏移的组合、所有微秒精度、其他 TOML 版本或完整上游测试套件。固定提交合并事实与发布说明只证明该修复进入了 0.15.2，不证明所有旧版本都受影响，也不等于对所有输入都做了穷尽验证。
