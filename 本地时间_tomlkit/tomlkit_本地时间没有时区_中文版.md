# 写出去的时间，自己读不回来

tomlkit 的卖点是 round-trip：读进来的文档，写出去还保持原样。下面这段的最后一行抛异常。

```python
from datetime import time, timedelta, timezone
from tomlkit import dumps, item, parse

t = time(7, 32, tzinfo=timezone(timedelta(hours=2)))
parse(dumps({"t": item(t)}))
# InvalidTimeError: Invalid time at line 1 col 18
```

它写出的那一行是 `t = 07:32:00+02:00`，自己的解析器不认。

## 六个字符，没有位置

TOML 1.0 对 Local Time 的定义是：

> If you include only the time portion of an RFC 3339 formatted date-time, it will represent that time of day without any relation to a specific day or any offset or timezone.

规范给的例子是 `lt1 = 07:32:00`。

![同一个 time 对象，五个字段；TOML 的 Local Time 只有前面四个的位置](assets/local-time-slots.png)

`07:32:00` 是 Local Time。**`+02:00` 这六个字符，在 TOML 的 Local Time 语法里没有对应的位置。**

偏移 TOML 也能写，但那叫 Offset Date-Time，必须同时带日期：`1979-05-27T07:32:00+02:00`。单独的 time 没有地方挂它。

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

`isoformat()` 是 Python 的格式，会把 `tzinfo` 渲染成偏移，而 TOML 的 Local Time 没有这一段。

另一处是 `Time._new()`，`replace()` 走那里，raw 同样是 `result.isoformat()`。

## 只改写出端

\#613 增加了一个 `_format_time()`：

```python
def _format_time(value: time) -> str:
    # TOML local times carry no offset or timezone ...
    s = f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    if value.microsecond:
        s += f".{value.microsecond:06d}".rstrip("0")
    return s
```

`item()` 和 `Time._new()` 都改用它。

合并版见 [`ce8f8ee` 的 `items.py`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L209) 与 [`_format_time()`](https://github.com/python-poetry/tomlkit/blob/ce8f8ee982411c4afef5cfb90df7313cc5f7d779/tomlkit/items.py#L237-L246)。

只用时、分、秒、微秒，不读 `tzinfo`。微秒非零时补足六位再去尾零：`123450` 写成 `.12345`，`0` 不写小数点。

解析器没有改。`parse("t = 07:32:00+02:00")` 修前修后都抛 `InvalidTimeError`——TOML 里没有这个语法。

## 冲突来自隔壁

\#613 合并前，维护者留了一句 "Please resolve the conflict"。

冲突来自 #620：它给 `Time` 和 `DateTime` 加了标准库的 `fold` 参数，改的正是 `Time._new()` 附近。两个 PR 在同一天合入，#620 早了三个半小时。作者 rebase 到最新 master 后，`fold=result.fold` 和 `_format_time(result)` 共存在同一个构造函数里：

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

## 七行输出

| 用例 | 修前 `763bd66` | 合并版 `ce8f8ee` |
|---|---|---|
| `item(time(7, 32, tzinfo=+02:00)).as_string()` | `07:32:00+02:00` | `07:32:00` |
| 微秒 `123450` | `07:32:00.123450+02:00` | `07:32:00.12345` |
| `replace(hour=13)` | `13:32:00+02:00` | `13:32:00` |
| `dumps({"t": item(...)})` | `t = 07:32:00+02:00` | `t = 07:32:00` |
| 把上一步 `parse()` 回来 | `InvalidTimeError` | 成功，读回 `07:32:00` |
| 无时区的 `time(7, 32)` | `07:32:00` | `07:32:00` |
| 直接 `parse("t = 07:32:00+02:00")` | `InvalidTimeError` | `InvalidTimeError` |

最后两行说明改的只是写出端：无时区的时间，输出一个字节没变；解析器对偏移的拒绝照旧。

`0.15.2` 的发布说明明确列出了 #613。用发布轮子 `tomlkit-0.15.2-py3-none-any.whl` 再跑一次，输出和合并版一致：`07:32:00`，读得回来。

## 读回来的是什么

```python
parse(dumps({"t": item(t)}))["t"]     # 07:32:00
```

能读回来了。读回来的 `Time` 是 `07:32:00`，`tzinfo` 是 `None`——那一行文本里没有这段信息。

`local_time_demo/run.py --test` 跑上表七行。

`Time` 里，Python 的 `time` 能带时区、能带 `fold`；写进 TOML 的那一段只有时分秒和可选的微秒。多出来的留在对象上，不进文件。
