# 报错是 −257，文件里写的是 −256

把一份 PDF 末尾的 `startxref` 改成 `-256`，pypdf 抛出的是：

```text
ValueError: negative seek value -257
```

文件里写的是 −256，错误消息说的是 −257。差的那 1 不是笔误，它指出了哪一行先碰到这个值。

`startxref` 后面的数字是 xref 表的字节偏移。复现用的样例一共 431 字节，xref 表在 256，`startxref` 这个关键字本身在 411。pypdf 读到这个数，并不直接 `seek` 过去——它先往回退一个字节，看 xref 前面是不是空白。256 退到 255，落在文件里；−256 退到 −257，落在文件开头之前 257 个字节。

![同样一次读取，指针的两个落点；以及同一个值流向的三个去处](assets/startxref-map.png)

## 一个值，三个去处

`read()` 把 `_find_startxref_pos()` 的返回值存进 `self._startxref`，之后这个值被三个地方用：

- [`_get_xref_issues()`](https://github.com/py-pdf/pypdf/blob/b78c2aa5301ee4fb1ee024b9838923945ab357b6/pypdf/_reader.py#L1310-L1313) 执行 `stream.seek(startxref - 1)`，检查前导空白；
- [`_read_xref_tables_and_trailers()`](https://github.com/py-pdf/pypdf/blob/b78c2aa5301ee4fb1ee024b9838923945ab357b6/pypdf/_reader.py#L1090) 执行 `stream.seek(startxref)`，真正去读表；
- writer 写增量更新时，把 `self._startxref` 当作 [`/Prev`](https://github.com/py-pdf/pypdf/blob/b78c2aa5301ee4fb1ee024b9838923945ab357b6/pypdf/_writer.py#L1520)。

`int(b"-256")` 是合法的。`seek(-256)` 也是合法的 Python 调用——它只是把位置放到文件外面。所以第一个 `seek()` 在 −257 上抛 `ValueError`；就算绕过它，第二个会在 −256 上抛同样的错；writer 则会把负数原样写进 `/Prev`。

## 2025 年挡住过一次，挡的是 0

2025 年 2 月 24 日，[#3151](https://github.com/py-pdf/pypdf/issues/3151) 报告了一份有两个 xref 表的 PDF，`PdfReader` 抛 `ValueError: negative seek value -1`。报告里写：

> It would be nice if this file was parsed, but IMO at least if it can't be parsed, it should return a malformed error.

那份文件的 `startxref` 是 0，减一得 −1。两天后 [#3157](https://github.com/py-pdf/pypdf/pull/3157) 合入，在 `_get_xref_issues()` 里加了四行：

```python
if startxref == 0:
    return 4
```

零被挡住了，负数没有。`return 4` 的意思是"这个 xref 有问题"，调用方会转去重建表——所以 0 指针能读出一页。

**这道门只装在三个去处中的一个上，而且只认一个值。**

## 修在出口

\#4144 的改动在 `read()` 里，紧跟 `_find_startxref_pos()`：

```python
startxref = self._find_startxref_pos(stream)
if startxref < 0:
    # A negative offset cannot point into the file. Treat it like the
    # zero case (#3157) so the xref table is repaired instead of
    # leaking a ValueError from a negative seek.
    logger_warning(
        "Negative startxref pointer (%(startxref)d), treating it as zero.",
        source=__name__,
        startxref=startxref,
    )
    startxref = 0
self._startxref = startxref
```

合并版见 [`91a73b5` 的 `read()`](https://github.com/py-pdf/pypdf/blob/91a73b5e8e9701efdad26b865964c2a53cb110b3/pypdf/_reader.py#L713-L738)。

为什么不把原来那道门改成 `< 1`？因为那只改了 `_get_xref_issues()` 一个调用点。`_read_xref_tables_and_trailers()` 仍然会拿到负数并 `seek()`；`self._startxref` 也仍然是负数。

归一化之后，负数走的是 #3157 已经铺好的零路径：`_get_xref_issues()` 返回 4，非 strict 模式记一条警告并调用 `_rebuild_xref_table()`，strict 模式抛 `PdfReadError("Broken xref table")`。恢复用的还是同一套代码。

## 同一个文件，两版对照

复现工程把两版完整 pypdf 源码放在一起，用同一个 `PdfWriter` 生成一页 PDF，只改写末尾 `startxref` 后面的数字。这份样例的偏移是 256，所以负指针是 −256。

| 输入 | 修前 `b78c2aa` | 合并版 `91a73b5` |
|---|---|---|
| 正常 `256` | 一页，无警告 | 一页，无警告 |
| `0` | 一页；`incorrect startxref pointer(4)`、`parsing for Object Streams` | 同左 |
| `-256`，非 strict | `ValueError: negative seek value -257` | 一页；`Negative startxref pointer (-256), treating it as zero.`、`incorrect startxref pointer(4)`、`parsing for Object Streams` |
| `-256`，strict | `ValueError: negative seek value -257` | `PdfReadError: Broken xref table`，先记一条负数警告 |
| `0`，strict | `PdfReadError: Broken xref table`，无警告 | 同左 |

`0` 那一行是控制组：它证明修前版确实已经包含 #3157 的修复，失败只发生在负数上。strict 那两行是同一个行为：坏文件仍然读不出来，但抛的是 pypdf 自己的异常，和零指针一致。

这五个用例都能重跑：`negative_startxref_demo/` 里放着 `b78c2aa` 和 `91a73b5` 两版 pypdf 源码，`run.py` 一次跑完。

补丁的 review 只有一处实质意见，stefan6419846 问为什么不把完整的警告消息写进断言。作者改了断言，忘了 push，又被追了一句 `Did you forget to push these changes?`，回了个 `Yes..`，补推之后才通过。

最终版本在 [`tests/test_reader.py#L2098`](https://github.com/py-pdf/pypdf/blob/91a73b5e8e9701efdad26b865964c2a53cb110b3/tests/test_reader.py#L2098) 里逐条比对三条警告的顺序，另外加了一条：健康文件一条警告都不产生。
