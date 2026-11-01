# pypdf：负的 startxref 指针

用两份**完整、固定提交的 pypdf 源码**离线对照 [pypdf #4144](https://github.com/py-pdf/pypdf/pull/4144) 修前与合并版。不安装 pypdf，不需要 pytest、网络或外部 PDF 样本。

## 运行

最低 **Python 3.11**，只用标准库。本轮实测 CPython 3.12.14；未声称跑过所有 pypdf 支持的 Python 版本。

从仓库根目录运行：

```powershell
python -B -S 负指针_pypdf/negative_startxref_demo/run.py --test
python -B -S 负指针_pypdf/negative_startxref_demo/run.py --test --json
python -B -S 负指针_pypdf/negative_startxref_demo/run.py --test --output negative-startxref.json
```

也可以把整个 `negative_startxref_demo/` 单独复制出去，在任意工作目录用其 `run.py` 的绝对路径执行。不依赖仓库其他文件、`.yan/`、Git、网络或安装步骤。

- `--test` 明确请求全部断言；不传也执行同样的校验。
- `--json` 让 stdout 只含完整 JSON；`--output PATH` 同时保存相同格式的报告，父目录按需创建。失败时 stderr 输出原因，退出码非零。
- 入口会确认 `-I -B -S`，缺少时自动启动相同解释器的隔离子进程，再为两版分别启动 `-I -B -S` 子进程。`-I` 忽略 `PYTHONPATH` 与用户 site，`-S` 不加载 site-packages，`-B` 不写 `.pyc`。
- 子进程安装 Python audit hook，拒绝所有 `socket.*` 事件；这是离线运行约束，不是对恶意 Python 代码的操作系统级安全沙箱。

成功输出：

```text
Python 3.12.14  (two complete pypdf snapshots, no install)
case                   parent b78c2aa                   merge 91a73b5
------------------------------------------------------------------------------------------
healthy                ok pages=1 warnings=0            ok pages=1 warnings=0
zero                   ok pages=1 warnings=2            ok pages=1 warnings=2
negative               ValueError: negative seek value -257 ok pages=1 warnings=3
negative_strict        ValueError: negative seek value -257 PdfReadError: Broken xref table
zero_strict            PdfReadError: Broken xref table  PdfReadError: Broken xref table

PASS: parent leaks ValueError(-257); merge warns, recovers one page, and raises PdfReadError in strict mode.
```

## 输入是怎么造的

用**当前版本的 `PdfWriter`** 生成一个正常的一页 PDF，只改写末尾 `startxref` 后面的数字：

```python
healthy = ...                     # PdfWriter -> BytesIO
marker  = healthy.rfind(b"startxref")
offset  = int(healthy[marker:eof].split(b"\n")[1])   # 本轮为 256
negative = healthy[:marker] + b"startxref\n-256\n%%EOF" + tail
```

其余字节完全不动，所以两版读到的是同一份文件；差别只在指针的正负。`zero` 用例把同一个指针改成 `0`，用来确认 #3157 的旧修复在修前版里已经生效。

## 固定版本与来源

| 目录 | 固定提交 | 角色 |
|---|---|---|
| `vendor/parent/` | [`b78c2aa5301ee4fb1ee024b9838923945ab357b6`](https://github.com/py-pdf/pypdf/commit/b78c2aa5301ee4fb1ee024b9838923945ab357b6) | #4144 合并提交的实际第一父提交（修前） |
| `vendor/merge/` | [`91a73b5e8e9701efdad26b865964c2a53cb110b3`](https://github.com/py-pdf/pypdf/commit/91a73b5e8e9701efdad26b865964c2a53cb110b3) | #4144 合并版 |

每版包含上游 `pypdf/` 下全部 60 个文件，以及原样 `LICENSE`。两版都报告 `pypdf 6.19.0`；版本字符串相同不代表源码相同，差异在 `_reader.py` 的 `read()` 里。

[`provenance.json`](provenance.json) 记录固定 SHA、codeload URL、归档 SHA-256/字节数，以及入库的 120 个快照文件的来源字节数与 SHA-256。完整 tar 归档不随工程分发。

## 测了哪些合同

| 用例 | 断言 |
|---|---|
| `healthy` | 两版都读出一页，均无警告 |
| `zero` | 两版都走 #3157 的修复路径：一页，警告 `incorrect startxref pointer(4)`、`parsing for Object Streams` |
| `negative` | 修前抛 `ValueError: negative seek value -257`；合并版一页，按顺序警告 `Negative startxref pointer (-256), treating it as zero.`、`incorrect startxref pointer(4)`、`parsing for Object Streams` |
| `negative_strict` | 修前仍抛 `ValueError`；合并版抛 pypdf 的 `PdfReadError: Broken xref table`，只先记一条负数警告 |
| `zero_strict` | 两版都抛 `PdfReadError: Broken xref table`，不记警告 |

`-257` 不是笔误：代码先执行 `seek(startxref - 1)`，`-256 - 1` 就是 `-257`。这个数字直接来自本轮输出，也解释了为什么修前的异常看起来像 Python 的 `open()` 错误，而不是 pypdf 的格式错误。

## 范围

这是一个一页、无压缩、无加密 PDF 的窄复现；只覆盖 `read()` 入口的 `startxref` 归一化，以及 `strict=False/True` 两条路径。没有覆盖所有畸形 PDF、其他负偏移位置、xref 流、增量更新、加密文件或完整上游测试套件。固定提交合并事实不等于首次发行版本或受影响版本范围。
