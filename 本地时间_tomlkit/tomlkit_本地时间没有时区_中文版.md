# 写出去的时间，自己读不回来

tomlkit 的卖点是 round-trip：读进来的文档，写出去还保持原样。下面这段的最后一行抛异常。

```python
from datetime import time, timedelta, timezone
from tomlkit import dumps, item, parse

t = time(7, 32, tzinfo=timezone(timedelta(hours=2)))
parse(dumps({"t": item(t)}))
# InvalidTimeError: Invalid time at line 1 col 18
```

它写出的那一行是 `t = 07:32:00+02:00`，自己的解析器不认。这一行不是谁手写错的：tomlkit 自己从 Python 的 `time` 对象渲染出它，从 2018 年 7 月一直渲染到 2026 年 9 月。

## 六个字符，没有位置

[TOML 1.0](https://toml.io/en/v1.0.0#local-time) 对 Local Time 的定义是：

> If you include only the time portion of an RFC 3339 formatted date-time, it will represent that time of day without any relation to a specific day or any offset or timezone.

规范给的例子是 `lt1 = 07:32:00`。

![同一个 time 对象，五个字段；TOML 的 Local Time 只有前面四个的位置](assets/local-time-slots.png)

`07:32:00` 是 Local Time。**`+02:00` 这六个字符，在 TOML 的 Local Time 语法里没有对应的位置。**

偏移 TOML 也能写，但那叫 [Offset Date-Time](https://toml.io/en/v1.0.0#offset-date-time)，必须同时带日期：`1979-05-27T07:32:00+02:00`。单独的 time 没有地方挂它。这不是 tomlkit 一家的口径：标准库的 `tomllib` 把 `t = 07:32:00` 读成不带时区的 `datetime.time(7, 32)`，对 `t = 07:32:00+02:00` 直接报 `Expected newline or end of document after a statement`。

## raw 不是 isoformat 的副本

`Time` 这个 item 同时存两样东西：Python 的 `tzinfo`，和要写进 TOML 的 `raw` 字面量。

`tzinfo` 留在 Python 对象上没有问题——`datetime.time` 本来就可以带时区。问题出在 `raw` 被当成了 `isoformat()` 的副本。修前版里，`item()` 构造 `Time` 时这样写：

```python
Time(
    value.hour,
    value.minute,
    value.second,
    value.microsecond,
    value.tzinfo,
    Trivia(),
    value.isoformat(),      # -> '07:32:00+02:00'
    fold=value.fold,
)
```

在 `item()` 里，`datetime` 那一支就在这段上面几行，raw 是 `value.isoformat().replace("+00:00", "Z")`；`time` 这一支直接是 `value.isoformat()`。

`isoformat()` 是 Python 的格式。按[它的文档](https://docs.python.org/3/library/datetime.html#datetime.time.isoformat)，只要 `tzinfo` 不是 `None`，末尾就追加上 UTC 偏移——那正是 TOML 的 Local Time 没有的一段。

另一处是 `Time._new()`，`replace()` 走那里，raw 同样是 `result.isoformat()`。

## 这一行写了八年

几处写的是同一句 `isoformat()`，它们不是同一天进去的。

最早的一处在 2018 年 7 月 8 日的 [`4a09449`](https://github.com/python-poetry/tomlkit/commit/4a094491aae8fd0de32e8a19296fb4bb6b32bbc8)：那时的包还叫 `tomllib`，`api.py` 里的 `item()` 按类型分派，`datetime` 那支已经带 `.replace("+00:00", "Z")`，`time` 那支直接是 `value.isoformat()`。十天后 [`d02e9ec`](https://github.com/python-poetry/tomlkit/commit/d02e9ec2ef7543ad775b19f27f021be6f187d14a) 把这段分派搬进 `tomlkit/items.py`，写法原样带过去。第二处在 2022 年 4 月的 [`5118514`](https://github.com/python-poetry/tomlkit/commit/5118514fa1f193ff92c3d26b4d4da2f0a94f70e2)（#189）：给 `Time` 补 `replace()` 与 `_new()` 时，同一条 `raw = result.isoformat()` 又写了一遍。

两处之间隔了三年多，选中的是同一个函数，因为它在 Python 这边就是“把时间写成字符串”的默认答案。只有 TOML 这边不接受。从 2018 年 7 月到 2026 年 9 月，这段代码换了包名、换了文件、换了构造函数，只有这一句没换。

它不容易被发现，是因为日常读写的路径根本不经过这两处：从 TOML 文本 `parse()` 出来的 `Time` 带着原文的 `raw`，`dumps()` 原样吐回去。只有拿 Python 的 `time` 对象去 `item()`，或者改一个 `Time` 的字段走 `replace()`，才会现场渲染。也就是说，把接口或数据库给的带时区时间写进配置文件的人会踩到，而他第一次踩到的时候，看到的是下一次读文件抛 `InvalidTimeError`——异常指向文档，不指向库。

所以受影响的也不是某一个版本：从 2018 年那次提交起，只要程序把带时区的 `time` 交给了 `item()`，写出的文件就带着这六个字符。修的是 0.15.2。

## 只改写出端

[#613](https://github.com/python-poetry/tomlkit/pull/613) 增加了一个 `_format_time()`：

```python
def _format_time(value: time) -> str:
    # TOML local times carry no offset or timezone ...
    s = f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    if value.microsecond:
        s += f".{value.microsecond:06d}".rstrip("0")
    return s
```

`item()` 和 `Time._new()` 都改用它。合并版见 [`ce8f8ee` 的 `items.py`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L209) 与 [`_format_time()`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L237-L246)。

只用时、分、秒、微秒，不读 `tzinfo`。微秒非零时补足六位再去尾零：`123450` 写成 `.12345`，`0` 不写小数点。

解析器没有改。`parse("t = 07:32:00+02:00")` 修前修后都抛 `InvalidTimeError`——TOML 里没有这个语法，库不该替它发明一个。

## 哪些会变，哪些不会

改的是“从 Python 对象新建一个 `Time`”，所以能碰到它的输入和碰不到的输入得分清楚。表分四段：前四行是 `time` 自己的渲染，第五行是 `fold`，第六到八行是 `datetime`，第九行是数组元素，最后两行是读进来再写回去的路径。每个格子都出自 `local_time_demo/run.py` 的实跑输出：

| 输入 | 修前 `763bd66` | 合并版 `ce8f8ee` | 原因 |
|---|---|---|---|
| `time(7, 32, tzinfo=utc)` | `07:32:00+00:00` | `07:32:00` | UTC 的偏移也是偏移 |
| 微秒 `100000`，带时区 | `07:32:00.100000+02:00` | `07:32:00.1` | 补六位再去尾零 |
| 微秒 `1`，带时区 | `07:32:00.000001+02:00` | `07:32:00.000001` | 前导零要留着 |
| 微秒 `123450`，无时区 | `07:32:00.123450` | `07:32:00.12345` | 无时区也跟着去尾零，值不变 |
| `time(7, 32, fold=1)` | `07:32:00` | `07:32:00` | `fold` 不写进文本 |
| 带时区的 `datetime` | `2026-11-04T07:32:00+02:00` | 同左 | Offset Date-Time 合法 |
| UTC 的 `datetime` | `2026-11-04T07:32:00Z` | 同左 | `item()` 把 `+00:00` 写成 `Z` |
| `datetime.replace(hour=13)` | `2026-11-04T13:32:00+00:00` | 同左 | `_new()` 不换成 `Z`，两版都这样 |
| 数组里的带时区 `time` | `a = [07:32:00+02:00]` | `a = [07:32:00]` | 数组元素同样现场渲染 |
| `parse()` 后原样 `dumps()` | `t = 07:32:00.123450` | 同左 | 读进来的文本逐字保留 |
| `parse()` 后 `replace(minute=33)` | `t = 07:33:00.123450` | `t = 07:33:00.12345` | 改字段才重排 |

PR 描述里那句“Naive times are byte-for-byte unchanged”对整秒的时间成立；无时区但带微秒、末尾是 0 的，文本会短几位——读回来还是同一个 `time(7, 32, 0, 123450)`。这一格是实测出来的，PR 的总结句没有提它。

`datetime` 那一列全是“同左”，因为 Offset Date-Time 本来就收偏移，这里没有错误可修。修前修后唯一没变的是写法上的小地方：`item()` 把 UTC 写成 `Z`，`replace()` 写成 `+00:00`，两种都合法，两个版本都这样。

## 跑一遍

```powershell
python -B -S 本地时间_tomlkit/local_time_demo/run.py --test
```

两版完整源码都在工程里（`vendor/parent`、`vendor/merge`），不装 tomlkit、不联网，子进程用 `-I -B -S` 隔离并拒绝 `socket.*`：

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

PASS: parent writes 07:32:00+02:00 and cannot parse its own output; merge writes 07:32:00, parses it back, leaves whole-second naive times unchanged, and touches neither datetime nor parsed text.
```

同一份输出后面还有一节 `boundary cases`，就是上面那张表。`--json` 打完整报告，`--output PATH` 存一份，`--emit DIR` 让两版各写一个 TOML 文件，合并版另外留一份合法样例——下一节要用。

## 你的文件是不是这一类

修前版写出的东西长这样：

```toml
[schedule]
start = 07:32:00+02:00
```

这种行只要出现过，多半是 tomlkit ≤0.15.1 从带时区的 `time` 写出来的；手写也会写错，形状一样。`scan_local_times.py` 扫一个目录里的 `*.toml`，找的就是这种形状：

```powershell
python -B -S 本地时间_tomlkit/local_time_demo/run.py --emit emitted
python -B -S 本地时间_tomlkit/local_time_demo/scan_local_times.py emitted
```

```text
emitted/legal.toml: clean
emitted/merge.toml: clean
emitted/parent.toml:2:9  07:32:00+02:00
emitted/parent.toml: tomllib rejects this file: TOMLDecodeError: Expected newline or end of document after a statement (at line 2, column 17)
--- 3 file(s) scanned, 1 hit(s), 1 rejected by tomllib
```

`legal.toml` 里两行容易误报的写法都没报：`note = "07:32:00+02:00"` 是字符串，`stamp = 1979-05-27T07:32:00+02:00` 是合法的 Offset Date-Time。扫描器报 `文件:行:列`，有命中或文件被 `tomllib` 拒绝时退出码 1。

**升级只保证以后写出的对。已经写坏的文件，0.15.2 也读不回来**——解析器对 `t = 07:32:00+02:00` 的态度两版一样，都抛 `InvalidTimeError`。那六个字符得手工删掉，按扫描器给的位置改。如果那份 TOML 本来就是程序生成的，更省事的做法是先升级再重跑生成器；扫描器用来确认哪些文件还得人看。

## 冲突来自隔壁

\#613 合并前，维护者留了一句 “Please resolve the conflict”。

冲突来自 [#620](https://github.com/python-poetry/tomlkit/pull/620)：它给 `Time` 和 `DateTime` 加了标准库的 `fold` 参数，改的正是 `Time._new()` 附近，起因是 [#619](https://github.com/python-poetry/tomlkit/issues/619)。两个 PR 在同一天合入，#620 早了三个半小时。作者 rebase 到最新 master 后，`fold=result.fold` 和 `_format_time(result)` 共存在同一个构造函数里：

```python
def _new(self, result: time) -> Time:
    raw = _format_time(result)
    return Time(
        ...,
        raw,
        fold=result.fold,
    )
```

`fold` 描述的是夏令时回拨时同一个本地时间出现两次，属于 Python `time` 对象自身的语义；`_format_time()` 决定的是这个对象怎么写进 TOML。两件事落在同一个构造函数里，互不相干。

## 读回来的是什么

```python
parse(dumps({"t": item(t)}))["t"]     # 07:32:00
```

能读回来了。读回来的 `Time` 是 `07:32:00`，`tzinfo` 是 `None`——那一行文本里没有这段信息。

`0.15.2` 的[发布说明](https://github.com/python-poetry/tomlkit/releases/tag/0.15.2)明确列出了 #613，[CHANGELOG](https://github.com/python-poetry/tomlkit/blob/0.15.2/CHANGELOG.md) 那一条写的是 “Fix a tz-aware `datetime.time` rendering with a UTC offset …; it now renders as a local time”。用发布轮子 `tomlkit-0.15.2-py3-none-any.whl` 再跑一次，输出和合并版一致：`07:32:00`，读得回来。

上游给这个行为补的测试在 [`tests/test_items.py` 第 847 行](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tests/test_items.py#L847)：`item()` 出来是 `07:32:00`，`parse` 回来等于 `time(7, 32)`；`replace(hour=13)` 是 `13:32:00`，读回来等于 `time(13, 32)`。测的就是这两处出口。

所以这不是一个“丢信息”的修复。TOML 的 Local Time 从来就装不下偏移，以前是库硬塞了进去；现在多出来的部分留在 Python 对象上，不进文件。要带上时区，就得写成带日期的 Offset Date-Time，那是另一种类型。
