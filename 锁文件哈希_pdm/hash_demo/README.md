# PDM #3956：归档哈希的离线对照

这个工程在同一份 pylock 输入上运行修复前后的真实 PDM 函数，观察
`packages.archive.hashes → candidate.hashes → requirements / pylock package`。
只需 **Python 3.11+ 的标准库**，不安装 PDM、不联网、不下载或安装 wheel。

## 运行

在仓库根目录执行：

```powershell
python 锁文件哈希_pdm/hash_demo/run.py
python 锁文件哈希_pdm/hash_demo/run.py --test
```

第一条输出完整 JSON 对照，包括输入、内部哈希记录、requirements 文本或异常，以及
pylock 的 package 字典。第二条执行 5 个测试方法，包含 12 组场景和源码完整性检查。
还可以用 `python -B -S .../run.py --test` 禁用字节码缓存和 site-packages，核对确实没有第三方依赖。
运行期间 socket 被禁用；URL 使用 `example.invalid`，不访问该地址。

## 固定来源

- 上游：[pdm-project/pdm #3956](https://github.com/pdm-project/pdm/pull/3956)
- 修复前：合并提交的**直接父提交** `3b82f5291988aa8d6a5c1f92b695c5b18ce170bd`
- 修复后：最终合并提交 `adfdb5dccacc0153ad7bf6b14354ad8e46b9801b`
- 这不是 PR 描述中开发时使用的 `301ca8c…` 基线；也不把 PR 合并等同于发行版发布。

`upstream/` 中是从固定提交逐行抽取的 13 个函数，**函数体没有改写**。
保留了原来的方法缩进、注解及局部 import，只增加容纳方法的类壳和未来注解 import。
逐个函数的原始行号、固定源码链接、片段 SHA-256 和抽取文件 SHA-256 见
[provenance.json](provenance.json)。`--test` 会校验抽取文件及 LICENSE 的摘要。

| 文件 | 实际执行的上游逻辑 |
| --- | --- |
| `upstream/before.py` / `after.py` | `LockedRepository._read_lockfile`、完整 `_read_pylock`、`_identify_candidate`、`get_hashes` |
| `upstream/candidate.py` | `Candidate.__init__`、`identify`、`__str__`；初始化空 hashes 和创建 link 均来自真实构造函数 |
| `upstream/requirements.py` | 完整 requirements `export()`，包括缺哈希异常和 `--hash` 输出循环 |
| `upstream/pylock.py` | 完整 `PyLockConverter.make_package()`，包括 archive、wheel/sdist 的输出分支 |

共享的 Candidate / requirements / pylock 源文件在这两个提交之间逐字相同；
抽取时已经比较了这三个完整文件。修前修后的区别因此确实来自真实 reader，而非手写两套答案。
[LICENSE](LICENSE) 是[合并 SHA 上游 MIT 许可证](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/LICENSE)的完整原文。

## 用例与输出

本地用标准库生成一个确定性的最小 wheel：`demo-1.0-py3-none-any.whl`。
它含模块、METADATA、WHEEL、RECORD，实际 **943 字节**；对这些实际字节计算哈希：

```text
sha256:81587057128a1e692e478824cd4609b92964e2f0fe9565e2ba2a4c0ea3b9eb5b
sha512:e321ec0dd71580d44f8a05255269c9af2ff312b3866192e51ff2632ee8451e941ea5d22531321336c1fc7f81209061280d9725e6ce8f30078457260fec536671
```

| 场景 | 数量 | 修复前 | 修复后 |
| --- | ---: | --- | --- |
| URL / 相对本地 wheel × 单 / 双算法 | 4 | 内部列表为空；requirements 报错；pylock archive 缺 hashes | 恢复 1 / 2 条 FileHash；requirements 与 pylock 均保留值 |
| 普通 `packages.wheels` / `packages.sdist` × 单 / 双算法输入 | 4 | 正常导出 | 与修复前完全相同 |
| URL / 相对路径 × 缺 hashes / 空 hashes | 4 | 默认 requirements 报错，pylock 不含 hashes | 仍然如此，不会凭空生成哈希 |

普通 wheels/sdist 的既有 reader 分支只取输入中的第一个算法；这里故意断言其行为不变，
**并不声称此次修复为这个分支增加了多算法支持**。sdist 例是该分支的字典兼容性对照，
没有生成或下载 tarball，不用于声称验证真实 sdist 内容哈希。

URL 正例额外带 `#subdirectory=src`，检查 FileHash 的 url 不含 fragment；
本地正例检查 url 是项目目录下 wheel 的绝对 `file:` URI、file 是 wheel 文件名。
所有 archive 正例还检查修后哈希重新读入仍保持一致。
`--no-hashes` 对照在两版都能输出不带 `--hash` 的 requirements，它不是恢复数据的办法。

默认 JSON 输出的本地 URI 指向一次性临时目录，会随运行变化；
wheel 字节、哈希及 URL 例的主要数据是确定的。临时文件会自动清理。

## 最小替身的范围

`support.py` 提供环境适配，**不实现哈希装载或导出的对照答案**：

- Requirement / FileRequirement 只承载本例的名字、版本、URL、路径、subdirectory 与字符串格式；不等同于完整 PEP 508 解析器。
- Link 只提供 URL、去 fragment 的 URL 和文件名；不等同于完整 unearth URL/平台语义。
- 候选对象使用抽取的真实 `Candidate.__init__`，但不是完整 Candidate 类；Python 约束 setter、准备/下载、安装等不在本例中。
- 项目与仓库的环境、后端地址展开、package 容器用小对象承载；不运行完整 `BaseRepository` 初始化。
- TOML 容器替换成 dict/list，pylock 的观察结果是**真实 make_package() 生成的字典**；不冒充完整 CLI TOML 序列化。
- requirements 函数的局部 Candidate import 指向同一个抽取类，未安装外部 PDM。
- 不测试依赖解析、marker/组选择、多平台、远程下载、文件校验安全性，也不测试原生 pdm.lock 的整条写入流程。

缺失或空 archive.hashes 是规范不完整输入，用于证明“不伪造哈希”；本修复没有新增 schema 校验。
URL fragment 的读取用于核对去片段地址，不保证 subdirectory 往返序列化：
该固定版本 converter 的 archive 分支没有写回独立 subdirectory，属于另一问题，见
[后续 PR #3964](https://github.com/pdm-project/pdm/pull/3964)。

## 规范与内部表示

- [pylock archive 可以是 wheel 或 sdist](https://github.com/pypa/packaging.python.org/blob/6a46e9923342d5512167cbc2ca4393928abb8520/source/specifications/pylock-toml.rst#L429-L444)
- [archive.hashes 必填且至少有一项](https://github.com/pypa/packaging.python.org/blob/6a46e9923342d5512167cbc2ca4393928abb8520/source/specifications/pylock-toml.rst#L499-L513)
- [相对 archive.path 应相对于锁文件位置](https://github.com/pypa/packaging.python.org/blob/6a46e9923342d5512167cbc2ca4393928abb8520/source/specifications/pylock-toml.rst#L458-L471)

真实 `BaseRepository.get_hashes()` 的
[既有 FileHash 表示](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/models/repositories/base.py#L299-L319)
包含 `url`、`file`、`hash`。
[原生锁序列化](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/project/lockfile/pdmlock.py#L113-L125)
在 static URLs 策略下取 `item["url"]`（117 行），否则取 `item["file"]`（119 行），
所以归档读入不能只放一个 hash 字符串。

## 真实 PDM 八例交叉核验

另外在 Windows / Python 3.12.14 上，对同一组上游回归测试运行真实 PDM：
直接父提交 **8 failed**，合并提交 **8 passed**，两边均无 setup / collection errors。
其中 4 例检查 reader，4 例执行 `add --no-sync → lock → export`，
使用上游的 `first-2.0.2-py2.py3-none-any.whl`，不是本 demo 的 demo wheel。
集成依赖在线准备，网络栈按固定上游 `pdm.lock` 的版本安装；为中文路径下的
findpython 隔离子进程显式启用 UTF-8，不修改 PDM 源码或 HTTP 依赖行为。
这不是完整 PDM 测试套件结果，也不是离线 demo 的运行前提。
