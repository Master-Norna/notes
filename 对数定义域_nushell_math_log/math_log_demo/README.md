# math log 三版对照

从 Nushell 固定提交的 `crates/nu-command/src/math/log.rs` 里自动提取
`require_positive_base` / `require_valid_base` 与 `operate`，用最小的
`Value`、`Span`、`Spanned`、`ShellError` 代用品编译，对照 #19127 的父提交、
首稿和合并版：同一个底数、同一个输入，三版各给出什么。

这不是一个 Nushell 构建。没有解析器、管道、const 求值、cell path 或命令注册；
`cargo run` 看到的只是这三版里那两个函数的判定与返回值。

## 版本

| 标签 | 提交 | 含义 |
| --- | --- | --- |
| `parent` | `65a22bfa4512e061ef7142914d032e2ad4a5d2ae` | #19127 的父提交，也是 #19107 的合并提交；与 0.116.1 的 `log.rs` 逐字节相同 |
| `first` | `8af57986e3d6c10b451baba5a5199c79b644b0fd` | #19127 首稿：底数拒绝 `1` 与 `NaN` |
| `merge` | `73f0a8983aa2f99b1e9e9383c983caf9244fadce` | #19127 合并：底数要求有限，输入侧改成正向判断 |

`build.rs` 在构建时从 `upstream/<标签>/log.rs` 取出两个函数的完整函数体，
只把可见性改成 `pub`；判定逻辑与算术不是手抄的。上游文件、来源与哈希见
`PROVENANCE.md`。

## 运行

```powershell
cargo run --manifest-path 对数定义域_nushell_math_log/math_log_demo/Cargo.toml
cargo test --manifest-path 对数定义域_nushell_math_log/math_log_demo/Cargo.toml
```

`cargo run` 打印具名案例、12 × 12 的判定矩阵统计和旧断言的本机复算。
`cargo test` 断言同样的数字：

- 矩阵 144 对：底数 12 个 × 输入 12 个
- 域外仍被回答：`parent` 29 对（其中 23 个结果是 `NaN` 或 `±inf`），`first` 13 对
  （7 个非有限），`merge` 0 对
- 域内被拒绝：三版都是 0 对
- `parent` 与 `merge` 都回答的 35 对：逐位相同 35 对
- `2 | math log 1` → `inf`，`1 | math log 1` → `NaN`，`2 | math log inf` → `0.0`，
  `NaN | math log 2` → `NaN`；合并版这四条全部报错
- `inf | math log 2` 三版都返回 `inf`：这一条是作者有意保留的
- 旧断言 `16 | math log 2.718281828459045`：本机得 `2.772588722239781`
  （`0x40062e42fefa39ef`）；把分母换成 1 下面一个 ulp 的 `0.9999999999999999`，
  同一个式子得 `2.7725887222397816`，断言不再成立
- 与官方 0.116.1 二进制的 10 条命令输出逐条相同

## 范围

- 被测的是两个提取出来的函数，不是命令本身。`run()` 里的 const 路径、
  cell path、范围与列表展开、错误渲染都不在 demo 里；`run_const` 只是调用
  同一个 `require_*`。
- 底数的「有限」要求与输入的「正数」要求是这次修复定下的判定，不是数学上
  唯一的选择；`+inf` 作为输入被保留，见正文。
- demo 只在本机（Windows，本机 libm）上跑浮点。旧断言的跨平台风险是评审
  提出的，本工程只演示这条断言对一个 ulp 的敏感，不声称在别的平台上真的
  失败过。
- 不构建、不下载、不运行完整 Nushell；上游提交是否进入某个发行版，不由这
  个工程推断。

## 许可

`upstream/LICENSE` 是 Nushell 在合并提交处的 MIT 许可证原文。
