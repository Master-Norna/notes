# pypdf：连续注释、流停点与普通对象调用预算

使用 **三个固定提交的真实完整 pypdf Python 包**，离线对照 [pypdf #4150](https://github.com/py-pdf/pypdf/pull/4150) 修前、抽工具并合入主线但尚无快路径的中间版、最终合并版。不是把上游算法重写成三个 Python 函数，也不需要安装 pypdf、pytest 或 Pillow。

## 运行

最低 **Python 3.11**，只用标准库。上游这些提交声明支持 Python 3.9，但 Python < 3.11 需要额外的 `typing_extensions`；本工程为保持零依赖，最低版本设为 3.11。本轮实测 CPython 3.12.14；未声称跑过所有支持的 Python 版本。

从仓库根目录运行：

```powershell
python -B -S PDF注释_pypdf/comments_demo/run.py --test
python -B -S PDF注释_pypdf/comments_demo/run.py --test --json
python -B -S PDF注释_pypdf/comments_demo/run.py --test --output comments-result.json
```

也可以把整个 `comments_demo/` 单独复制出去，在任意工作目录用其 `run.py` 的绝对路径执行。不依赖仓库其他文件、`.yan/`、Git、网络、外部 PDF 样本或安装步骤。

- `--test` 明确请求全部断言；不传也执行同样的校验。
- `--json` 让 stdout 只含完整 JSON；`--output PATH` 同时保存相同格式的报告，父目录按需创建。失败时 stderr 输出原因，退出码非零。
- 入口会确认 `-I -B -S`，缺少时自动启动相同解释器的隔离子进程，再为三版分别启动 `-I -B -S` 子进程。`-I` 忽略 `PYTHONPATH` 与用户 site，`-S` 不加载 site-packages，`-B` 不写 `.pyc`。
- 隔离执行中安装 Python audit hook，拒绝所有 `socket.*` 事件；报告包括实际 `socket.socket()` 被阻止的自检。这里的 hook 是离线运行约束，不是对恶意 Python 代码的操作系统级安全沙箱。
- 导入前核对清单自身的固定 SHA-256、每个快照的完整文件集合、文件大小与 SHA-256。缺文件、改内容、额外文件都会失败，不会回退到系统安装的包。

成功输出的主表：

```text
parent       a23cc36da7a8  calls=601  calls<900=True  boundary=18  correctness=33
intermediate ad63551501ef  calls=901  calls<900=False boundary=18  correctness=33
merge        ccd8dc470e13  calls=601  calls<900=True  boundary=18  correctness=33
PASS: 3 real snapshots; file hashes, boundaries, guarded reads, EOF and call budgets verified.
```

`intermediate` 的预算失败是**预期重现的历史差异**，并非整个 demo 测试失败。源码完整性或观测结果不符才令工程失败。

## 固定版本与来源

| 目录 | 固定提交 | 角色 |
|---|---|---|
| `vendor/parent/` | [`a23cc36da7a8e86f2b551b7a6eed1d8798301c73`](https://github.com/py-pdf/pypdf/commit/a23cc36da7a8e86f2b551b7a6eed1d8798301c73) | 最终 merge 的实际第一父提交，不是可变 PR base |
| `vendor/intermediate/` | [`ad63551501ef8ad03ca91a8d1e5246a79319a048`](https://github.com/py-pdf/pypdf/commit/ad63551501ef8ad03ca91a8d1e5246a79319a048) | 真实中间提交：已有 helper 与 #4148 的测试，普通对象仍无条件调用 helper |
| `vendor/merge/` | [`ccd8dc470e13915d384fb8b4c93a351cc1d79ae6`](https://github.com/py-pdf/pypdf/commit/ccd8dc470e13915d384fb8b4c93a351cc1d79ae6) | #4150 最终合并，只有 `%` 路径进入 helper |

每版包含上游 `pypdf/` 下全部 **59 个 `.py` 文件与 `py.typed`**，以及原样 `LICENSE`、`pyproject.toml`、`tests/utils.py`、`tests/test_generic.py`，共 64 个文件。后两份仅为来源与辅助定义；不会导入整个测试模块。

[`provenance.json`](provenance.json) 记录固定 SHA、codeload URL、归档 SHA-256/字节数、全部入库快照文件的来源 URL/字节数/SHA-256，以及两个原样提取片段的行号与哈希。完整 tar 归档不随工程分发。

调用计数直接复用对应版本 `tests/utils.py` 中的 `count_function_calls` 与 `ReaderDummy`：用 AST 取原始类/函数源码片段，校验片段哈希后执行，只加 `from __future__ import annotations` 及必要的绑定，避开无关图像测试依赖。没有换用自写计数器，也没有改 pypdf 包源码。许可证见每版 `LICENSE` 和工程顶层 [LICENSE](LICENSE)（上游 BSD-3-Clause）。`.gitattributes` 对 vendor 和 LICENSE 关闭换行转换，防止 Windows checkout 改动其字节哈希。

## 测了哪些合同

### 连续前导注释

对每版都跑 `0 / 1 / 999 / 1000 / 1001 / 2000` 条，并分别使用 **LF / CR / CRLF**，每条注释后有空格与 tab。对象正文是 `42 tail`；成功时不仅检查值为 42，还检查剩余字节恰为 ` tail`。

| 连续前导注释 | 修前 parent（本轮 CPython 3.12.14，递归上限 1000） | 中间版 | 最终 merge |
|---|---|---|---|
| 0 / 1 | 42，余下 ` tail` | 同左 | 同左 |
| 999 / 1000 | 本轮为 `RecursionError` | 42，余下 ` tail` | 同左 |
| 1001 / 2000 | 本轮为 `RecursionError` | `LimitReachedError` | 同左 |

**旧版在哪一条递归失败取决于 Python 版本和调用栈余量，不是 pypdf 的固定阈值。** 工程不为 999 等特定数字断言“旧版必须失败”：旧版大输入允许成功或 `RecursionError`。有守卫的第 1001 条长正文用例只检查中间/最终版的新增合同，不对旧版定义不存在的停点要求。

中间版与最终版的限制是：**一次 `read_object` 最多跳过 1000 条连续前导注释**；第 1000 条后如果是正常对象，仍成功。若继续遇到第 1001 个 `%`，抛 `LimitReachedError` 并将流停在该 `%`，不是停在它的正文之后。另用两个独立的 `read_object` 调用，各自处理 1000 条后接的 42 与 43，验证计数不跨对象累积。

### 第 1001 条正文未被扫描

放置 1000 条已结束的注释，再接 `%` 和 **100,000 字节**正文。`BodyGuard` 检查解析器实际 `read()` 覆盖的字节区间；任何触及这条正文的读取都会直接令测试失败，而非只凭最后的 `tell()` 推断“没读”。本轮中间/最终版：

| 换行 | 第 1001 个 `%` 的偏移 | 读取触及的最大末端（不含末端字节） | 正文读取尝试 |
|---|---:|---:|---:|
| LF | 12000 | 12001 | 0 |
| CR | 12000 | 12001 | 0 |
| CRLF | 13000 | 13001 | 0 |

这里每条输入是 `% comment` + 换行 + 空格/tab，因此偏移与别的输入模板可能不同。`12001` 意味着读到了偏移 12000 的 `%`，没有读正文起点 12001。固定的 100,000 只用于见证“不会扫描超额注释正文”，不是这次修复给单条注释设置了长度上限。

### 无注释对象的调用预算

复用上游 [`tests/test_generic.py`](https://github.com/py-pdf/pypdf/blob/ccd8dc470e13915d384fb8b4c93a351cc1d79ae6/tests/test_generic.py) 的输入：`123`、`4.5`、`12 0 R` 重复 100 组，组成 300 元素数组；直接调用 `ArrayObject.read_from_stream`。先准备所有参数，再交给原样 `count_function_calls` 计数，并检查 300 个元素的值、类型路径和流剩余。

| 版本 | Python 函数调用数 | 上游预算 `calls < 3 * 300` |
|---|---:|---|
| parent | 601 | 通过 |
| intermediate | 901 | 不通过 |
| merge | 601 | 通过 |

这些是 **Python 函数调用次数，不是毫秒或吞吐量**。不能据此说“慢了 50%”。本轮重现也不是当年的 CI 日志。输入哈希、运行环境、helper 来源和各版结果都保存在 JSON 中。

### EOF 与代表性普通对象

每版还用 11 种对象（整数、浮点、名称、真假、null、文字/十六进制字符串、数组、字典、间接引用）分别搭配无注释、单条注释、混合换行三种前缀，检查类型、值、剩余流，共 33 组。

EOF 的五个小用例核对三版结果一致，保持原行为而不是宣称统一修复 EOF：

| 输入 | 三版的本轮结果 |
|---|---|
| 空输入 | `NumberObject(0)`，带 `NumberObject(b'') invalid; use 0 instead` 警告 |
| `% no line ending` | `PdfStreamError` |
| `% c` 后换行，没有对象 | `PdfReadError` |
| 注释结束后只剩空白 | `PdfReadError` |
| `42` 后立即 EOF | `NumberObject(42)` |

## 范围

这是对象 token 读取层的小输入复现，**不是完整 PDF 文件测试、上游全套测试、CVE 结论或耗时性能基准**。没有证明任意坏 PDF 都能恢复，也没有覆盖深层对象嵌套的通用递归、所有间接对象解析、加密/图像等可选功能。注释上限不等于整份 PDF 的总注释上限，也不限制单条注释长度。固定提交合并事实不等于首次发行版本或受影响版本范围。
