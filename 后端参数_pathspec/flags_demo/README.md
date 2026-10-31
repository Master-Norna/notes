# Pathspec #151：三版真实后端离线对照

本工程用固定源码和真实 `google-re2==1.1.20251105`、`hyperscan==0.9.1`，对照 [Pathspec #151](https://github.com/cpburnz/python-pathspec/pull/151) 修前、初稿、合并版的 flags 携带与后端选择。不是重写 helper 的模型，也不使用机器上另装的 pathspec。

## 固定版本与源码

| 名称 | 固定提交 | 含义 |
| --- | --- | --- |
| before | `88a9b711e0120a1eb16d5627fb68d15e3187c6ad` | 合并提交第一父节点 |
| draft | `21e4342c73fd02be6458b9b2353e9f63fa1824a0` | 强推前的初稿，不是 before 的直接后继 |
| after | `157bccfbc24777aed9330223a546487b0f3d7f1b` | PR 合并瞬间，不含后续清理 |

`vendor/<版本>/` 包含各版完整 `pathspec/` 包及上游 `LICENSE-MIT`、`LICENSE-MPL-2.0`、`LICENSING.md`，每版 35 个文件，未修改源码。before / after 来自本地固定 SHA 的 `git archive`，draft 来自固定 SHA 的 GitHub codeload 原始归档；没有用 patch 拼造初稿。原始包及许可文件的逐文件 SHA256、归档 SHA256 和来源 URL 见 [`provenance.json`](provenance.json)。`vendor/.gitattributes` 禁止 Git 文本转换，避免 Windows autocrlf 改变快照字节；运行前会校验文件集合及每个哈希。

上游正在从 MPL-2.0 迁往 MIT，新旧代码的授权区分保留在每版的 `LICENSING.md`，不能把整个快照笼统标成 MIT。原生轮子不随仓库分发，准备时从 PyPI 官方文件地址下载，安装后保留其各自许可元数据。

## 环境与一次在线准备

这里的精确轮子锁定 **CPython 3.12、Windows x86-64**，本次实测为 Python 3.12.14 / Windows 11。其他 Python ABI、平台、CPU 或运行库组合不在此锁文件的验证范围。需要先有 Python 3.12 及其标准库 `venv` / `ensurepip`。

从**本工程目录**执行 PowerShell：

```powershell
# 仅此步骤允许联网：下载两个精确轮子、校验官方 SHA256，随后以 --no-index 安装。
python -B prepare.py --download --venv .local/first-venv

# 模拟断网后的全新机器环境：不加 --download，不复用 first-venv。
python -B prepare.py --wheelhouse .local/wheelhouse --venv .local/fresh-venv

# 所有运行均禁网；--offline / --test 是显式写法，省略也仍跑同样断言。
& .local/fresh-venv/Scripts/python.exe -I -B run.py --offline --test --json .local/result.json
```

`prepare.py` 拒绝复用已有 venv。要重做请换一个尚不存在的 `--venv` 路径。轮子已在 wheelhouse 时，第二步不联网、不走索引、不源码编译：使用 `--no-index --find-links --only-binary=:all: --require-hashes --no-deps`，且不继承系统 site-packages。安装前验证 [`wheels.json`](wheels.json) 的文件名和 SHA256，pip 再按 [`requirements.txt`](requirements.txt) 校验一次。缺文件或哈希不符即失败。

`.local/` 已在本工程 `.gitignore` 排除，勿将 venv、轮子、运行结果纳入提交。若已有两个精确版本且原生库均能加载，也可直接 `python -B run.py --test --json .local/result.json`，但这不替代全新环境安装的检验。

## 主矩阵：16 个字符串场景

每版在独立子进程中导入自己的快照，使用 `-I -B`，避免 `PYTHONPATH`、同名已安装包与模块缓存串版。每场景同时测 `PathSpec`、`GitIgnoreSpec`，每类请求 `simple`、`re2`、`hyperscan`、`best`、默认 `None`。

- 无外部 flags；外部 `IGNORECASE`、`MULTILINE`、`DOTALL`、`IMS`、`VERBOSE`、`ASCII | IGNORECASE`、单独 `ASCII`。
- inline I / M / S / IMS；inline I 加外部 M，区分“文本本来携带”与“外部新增”。
- `GitIgnoreSpecPattern('logs/')` 和 `GitIgnoreSpecPattern('logs')` 重编译为 `re.I`，覆盖必需/可选目录 marker 的目录和文件分支，并用不匹配路径作对照。
- 普通模式与 VERBOSE 模式混合的整份 spec：核对自动选择对**整个 spec** 回退，且普通模式及 pattern index 不丢失。

每个成功构造的 spec 都调用公开 `check_file` 与 `match_file`，断言匹配结果及 include / index。每次后端选择都检查具体 class 和 module；RE2 额外检查实际 `_set` 是 `re2.Set`，Hyperscan 检查 `_db` 是 `hyperscan.Database`。这两个私有属性只用于固定 SHA 下的身份核验；匹配结果仍走公开 API。

### 核心结果

以下表为 `PathSpec` 的正样本；`GitIgnoreSpec` 对这些 regex 场景也得到了相同结果。各项均另有负样本。`best` 和默认 `None` 在这里一致；两个原生库都可加载时，自动原生选择为 RE2。

| 场景 | 版本 | simple | 显式 re2 / hyperscan | best / 默认 |
| --- | --- | --- | --- | --- |
| `^secret$` + `re.I`，`SECRET` | before | True | False / False | RE2，False |
| 同上 | draft | True | ValueError / ValueError | simple，True |
| 同上 | after | True | True / True | RE2，True |
| 外部 M / S / IMS，各自正样本 | before | True | False / False | RE2，False |
| 同上 | draft | True | ValueError / ValueError | simple，True |
| 同上 | after | True | True / True | RE2，True |
| `^S E C R E T$` + `re.X`，`SECRET` | before | True | False / False | RE2，False |
| 同上 | draft / after | True | ValueError / ValueError | simple，True |
| `^[a-z]+$` + `re.A \| re.I`，`SECRET` | before | True | False / False | RE2，False |
| 同上 | draft / after | True | ValueError / ValueError | simple，True |
| `(?i)^secret$`，`SECRET` | 三版 | True | True / True | RE2，True |

主矩阵是 **16 × 2 类 spec × 5 个请求 × 3 版 = 480 项构造/策略检查，480 项通过**。其中 56 项是预期的显式 `ValueError`，不是 480 份 spec 都成功构造。

| 主矩阵计数 | before | draft | after | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 构造/策略检查 | 160 | 160 | 160 | 480 |
| 预期拒绝 | 0 | 44 | 12 | 56 |
| 成功构造 | 160 | 116 | 148 | 424 |

424 份 spec 完成 922 个样本检查；每个样本分别调用 `check_file` 和 `match_file`（共 1844 次公开匹配调用）。这不是上游全套测试数量，也不是引擎普遍等价的证明。

## bytes 组单独记数

另有 4 个 bytes **正则表达式**场景：plain、外部 I、外部 IMS、inline I，仍各测三版、两类 spec、五个请求，共 120 项构造/策略检查，不合计入上述 480。

构造形式是 `RegexPattern(re.compile(b'^secret$', re.I), include=True)`；传给 `check_file` / `match_file` 的路径仍是 str，**没有硬塞 bytes 路径**。

- 112 项成功构造；draft 对外部 I / IMS 的显式原生请求共 8 项预期拒绝。
- 成功构造中的 80 份原生 spec 用 str 路径完成 160 个样本检查，实际经过 RE2 / Hyperscan；这验证了 bytes 前缀对应的原生编译/匹配链路，不只是 helper 输出。
- 32 份 simple spec 各以两个 str 路径检查；Python 的 bytes regex 不能搜索 str，故 `check_file`、`match_file` 都应抛 `TypeError`。共 64 对公开接口边界检查，全部明确断言，不静默跳过。draft 的自动选择会回退 simple，因此也处于该限制内。

不要据此把 bytes 正则和 bytes 路径当成同一项 API 能力，也不要宣称所有后端对 bytes 都一致。

## 输出、失败及禁网边界

`--json` 输出包含环境、解释器路径、原生包版本及模块路径、原生二进制 SHA256、各版源码路径/提交、来源校验数、逐场景表达式/flags/输入/后端/结果或异常，以及主矩阵、bytes 组两个独立汇总。所有预期值写在 demo 中，再与真实对象比对；不是由另一个模拟后端给出结果。

缺少任一原生库、版本不符、导入/加载失败、后端身份不符、快照字节变更或断言失败都会**非零退出**；不会降格成仅 simple 或跳过原生测试。显式拒绝必须恰为 `ValueError` 且提示 `backend='simple'`，意外失败不能充数。

worker 在导入上游及原生库前封锁 Python socket 创建、连接及 DNS，安装审计 hook 阻止 socket 操作和子进程逃逸；允许不涉及外网的 `gethostname` 用来记录平台。每版各有四项禁网自检，原始 socket 引用也会被审计 hook 拦下。父进程仅启动固定的三个 worker，也封锁常用 socket 入口。**这是 Python 进程级保护，不是拦截任意原生代码直连的系统防火墙**；运行与源码校验没有下载代码。

## 没有证明什么

- 没有重验所有 Python regex 语法、Unicode 字符类或 case-folding 的跨引擎等价。`ASCII | IGNORECASE` 用 ASCII 正负样本验证策略，不把旧讨论中 `ſ` 的结果写成此次实测。
- 不覆盖任意 foreign compiled regex、LOCALE/未知位的端到端行为、所有复杂目录优先级或 `+=` 状态一致性历史；目录检查只是这里两种稳定构造的固定样本。
- 不做性能评测，不把 PR 合并等同于某个 PyPI 版本已经发布。两原生库均存在时的自动选择已测；“仅装 Hyperscan”“仅 simple 可用”等安装组合不属于此矩阵，缺原生库在本 demo 中应直接失败。
