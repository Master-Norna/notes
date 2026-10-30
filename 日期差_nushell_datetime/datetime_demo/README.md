# 日期差：三版真实 Nushell 同场复现

这不是用 Python 重写 `datetime-diff`：`runner.nu` 在**同一个真实 Nu 进程**里分别导入三份完整、未经修改的上游 `mod.nu`。Python 标准库只负责启动 Nu、提供输入、读取 JSON，以及用独立的公历计算检查结果。

## 环境与运行

- Python 3.11+；本次实际验证为 Python 3.12.14、Windows x64。
- 官方 Nu **0.116.1** 便携版；不必安装 Rust、不必编译 Nushell、不必安装 Python 第三方包。其他 Nu 版本与平台未实测。
- 源码与完整上游 MIT `LICENSE` 已附在本目录。正常运行不访问网络，不自动下载，也不回退到 Python 计算结果冒充 Nu。

以下命令均从仓库根目录执行。

### 仅一次：在线准备便携 Nu（Windows x64）

```powershell
python -B -S 日期差_nushell_datetime/datetime_demo/prepare_nu.py
```

该脚本从[官方固定版本 release](https://github.com/nushell/nushell/releases/tag/0.116.1)下载 ZIP，验证 SHA-256，只解出 `nu.exe`。文件放在仓库的 `.yan/datetime/tools/`，不修改系统、PATH、配置或注册表。ZIP 与可执行文件的哈希、下载固定链接见脚本和生成的 `runtime.json`。若已有同名 ZIP，脚本校验后直接使用它，不联网。

也可自行取得对应平台的官方 Nu 0.116.1，将 `nu` 加入 PATH，或在下面命令中追加 `--nu '绝对路径/nu.exe'`。自动查找顺序为 `--nu` → PATH → 本仓库 `.yan/datetime/tools/nu-0.116.1/nu.exe`。便携包与运行日志不是 demo 的公开源码组成部分。

### 此后离线：具名回归

```powershell
python -B -S 日期差_nushell_datetime/datetime_demo/run.py --test
```

`--test` 与默认运行相同，执行 31 条具名输入（30 条非逆序、一条逆序），打印三版结果。包括月中、月末、闰年/平年、跨年、原始日号相同但时刻不足、九位小数的借位链、不同 UTC offset，以及 1900/2000/2100/2400 世纪边界。

### 此后离线：真实 Nu 批量性质检查

```powershell
python -B -S 日期差_nushell_datetime/datetime_demo/run.py --test --scan --output .yan/datetime/runs/scan
```

额外生成 **6,550 条**确定性输入：起始年 1999、2000、2023、2024，各月合法的 1/15/28/29/30/31 日；日期间隔 0/1/27/28/29/30/31/59/366 天；午夜、12:00→06:00、23:59:59.999999999→00:00 三组时刻，去掉同日内逆序的组合。连同具名输入一共 6,581 条、三版共 19,743 次真实 Nu 算法调用；这些是输入行数，不宣称所有日期对互不重复。

`--output` 保存原始 `inputs.json`、未经计算替换的 `nu-stdout.json`、stderr、Nu 命令、`summary.json`、`table.json`、`table.md`。不传 `--output` 就不写日志。日志请放 `.yan/`，不要加入公开提交。单次 Nu 子进程限时 300 秒；本次批量执行只需数秒，**没有进行性能基准比较**。

## 固定的三版源码

上游仓库均为 [nushell/nushell](https://github.com/nushell/nushell)，源码路径均为 `crates/nu-std/std/dt/mod.nu`。

| 目录 | 角色 | 固定 revision |
|---|---|---|
| `upstream/before/` | #19109 合并前第一父提交；已包含 #19064 的借前一月逻辑 | [`c3b7a5aebea0119d88bba4608bc6a3f81bb54a45`](https://github.com/nushell/nushell/blob/c3b7a5aebea0119d88bba4608bc6a3f81bb54a45/crates/nu-std/std/dt/mod.nu) |
| `upstream/draft/` | review 指出的 clamped-month 初稿 | [`ca90358650f1afa85a5bfb05645e87e04f52baaf`](https://github.com/nushell/nushell/blob/ca90358650f1afa85a5bfb05645e87e04f52baaf/crates/nu-std/std/dt/mod.nu) |
| `upstream/after/` | #19109 最终 merge | [`996de1f9a48520c8679e6d791f3260b722d5116e`](https://github.com/nushell/nushell/blob/996de1f9a48520c8679e6d791f3260b722d5116e/crates/nu-std/std/dt/mod.nu) |

`provenance.json` 列出逐文件字节数、SHA-256、Git blob SHA-1 和固定链接；每次运行先校验它们。三版 `LICENSE` 相同，本目录保留完整原件（1,094 字节），不是许可证摘要。

`runner.nu` 只做命名空间隔离、解析输入、调用、捕获逆序错误和导出结果；**没有删除 `@example`，没有补写或替换上游函数**。启动参数是 `nu --no-config-file --no-std-lib runner.nu inputs.json`，避免用户配置以及当前 Nu 内置标准库里的同名命令混入。演示测的是这三份模块在共同的 0.116.1 解释器上的结果，不是分别构建三份完整 Nushell 二进制。

## 输入解析与世纪闰日：与日期差算法分开

本次首次扫描使用不指定格式的 `into datetime`，Python 对 Nu 解析后的 UTC 字段做独立检查，发现 `2000-02-29T00:00:00Z` 被 Nu 0.116.1 转成 **2000-02-28**；独立探针又观察到 2400 年同样的情况，2024 年样例正常。

因此最终 wrapper 明确使用 `into datetime --format '%+'` 解析 RFC3339 输入，再把真正的 datetime 值传给三份原始模块。此显式格式路径在本次所有输入上均通过 UTC 字段逐项核对，纳秒也不丢失。**这是调用层输入准备，不是对三版算法的修补**。首次失败与单独探针保留在内部取证日志；不能把这一绕开方式写成 #19109 修复了解析器。

可离线复跑独立探针，输出输入、手写预期 UTC record、两条解析路径的实际 record，以及 known mismatch 标记。该模式不调用 `datetime-diff`，已知解析问题只是观察结果，不作为 #19109 的回归失败；显式路径若不符合预期则退出非零。

```powershell
python -B -S 日期差_nushell_datetime/datetime_demo/run.py --parser-probe --output .yan/datetime/runs/parser-probe
```

也可直接运行 `nu --no-config-file --no-std-lib 日期差_nushell_datetime/datetime_demo/parser_probe.nu`。最小单例（PowerShell，`$nu` 换成实际路径）：

```powershell
$nu = '.yan/datetime/tools/nu-0.116.1/nu.exe'
& $nu --no-config-file --no-std-lib -c "'2000-02-29T00:00:00Z' | into datetime | into record"
& $nu --no-config-file --no-std-lib -c "'2000-02-29T00:00:00Z' | into datetime --format '%+' | into record"
```

## 检查的语义

月份不是固定长度的 duration。最终版采用以下拆分约定，输入先归一为 UTC：

1. 从原始年月差计算候选整月数。若 later 的**原始日号更小**，或**日号相同但时刻更早**，减一月。不能先把 earlier 的日号钳到短月月末，再据此宣布满月。
2. 把 earlier **直接一次性**加上选定的总月数，日号 clamp 到目标月的最后一天；时刻保持 earlier 的 UTC 时刻。这就是月份锚点。不是逐月反复相加，因为多次 clamp 会丢掉原日号。
3. 从锚点到 later 的精确余量拆成日、时、分、秒、毫秒、微秒、纳秒。
4. 重构定义：`clamp_add_months(earlier, 12 * year + month) + day/time remainder == later`。Python 使用公历 `date` 和整数纳秒做这一独立检查，不把一个月乘以 30 天。

所有三版输出都检查非负、单位范围、重构和与最终约定的一致性；旧版与初稿的问题作为预期差异统计，最终版出现任何一项失败都会退出非零。对旧版已满足非负、单位范围和重构的输入，另直接断言最终版 record 与旧版完全相同，防止参考模型掩盖兼容性变化。具名结果另有手写期望，不只依赖参考模型；逆序输入须三版都拒绝。重构不是唯一要求：初稿可以既非负又成功重构，仍然改变了原先的整月拆分约定。

特别区分：

- `2023-01-15 12:00 → 2023-02-15 06:00`：日号相同、时刻不足，三版都是 **30 天 18 小时**，最终整月数为 0。
- `2023-01-31 12:00 → 2023-02-28 06:00`：原始日号已经不足，不是上述 tie-break 的例子，三版都是 **27 天 18 小时**。

## 本次真实输出摘要

除特别注明外，下面都是 2023 年 UTC 午夜。

| 输入 earlier → later | before | draft | after |
|---|---|---|---|
| 1/15 → 3/1 | 1 月 14 天 | 1 月 14 天 | 1 月 14 天 |
| 1/31 → 3/1 | 1 月 **−2 天** | 1 月 1 天 | 1 月 1 天 |
| 1/31 → 2/28 | 28 天 | **1 月** | 28 天 |
| 3/31 → 4/30 | 30 天 | **1 月** | 30 天 |
| 2024/2/29 → 2025/2/28 | 11 月 30 天 | **1 年** | 11 月 30 天 |
| 1/31 12:00 → 2/28 13:00 | 28 天 1 小时 | **1 月 1 小时** | 28 天 1 小时 |
| 2022/12/31 → 2023/3/1 | 2 月 −2 天 | 2 月 1 天 | 2 月 1 天 |
| 1/29 → 3/1 | 1 月 0 天 | 1 月 1 天 | 1 月 1 天 |

本次 6,580 条非逆序输入的统计（每版另拒绝 1 条逆序输入）：

| 检查失败数 | before | draft | after |
|---|---:|---:|---:|
| 含负分量 | 16 | 0 | 0 |
| 标准单位范围错误 | 0 | 0 | 0 |
| clamped 月份锚点 + 余量不能重构 | 217 | 0 | 0 |
| 与最终拆分约定不一致 | 217 | 32 | 0 |

旧版满足非负、单位范围和重构的 **6,363 条**输入，最终版逐字段全部保留（`compatible_changes_failures = 0`）；初稿在这个相同子集里改变了 32 条输出。

范围检查只约束 month 为 0…11、hour 为 0…23、分秒为 0…59、各子秒分量为 0…999；day 不是“必须小于 30”，其非负性另外检查。这不是对全部日期、全部时区规则或所有 Nu 版本的正确性证明，也不包含闰秒/本地夏令时语义。
