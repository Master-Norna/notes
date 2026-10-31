# bytes remove 五版对照

从 Nushell 固定提交的 `remove.rs` 里自动提取 `remove_impl`，用最小的
`Value`、`Span`、`Arguments` 代用品编译，对照 #11428 之前、#11428 之后、
#19107 的父提交、首稿和合并版。

这不是一个 Nushell 构建。没有解析器、管道、命令注册或 metadata 处理；
`cargo run` 看到的只是这五个固定版本里 `remove_impl` 的返回值。

## 版本

| 标签 | 提交 | 含义 |
| --- | --- | --- |
| `old-parent` | `95220520639910c77d79c31bece37c468d54aeec` | #11428 之前 |
| `old-merge` | `15421dc45e6b8b831b6cacebe80b37eda46fbcd9` | #11428 合并后：`left > 0` 守卫 |
| `merge-parent` | `8696b5246f7a920156a0be08f29ce7fefe16d885` | #19107 的父提交 |
| `first` | `9e99b50de7dd8cb37b5b8b4187d3972afe6e291c` | #19107 首稿：`left < 0` 返回原输入 |
| `merge` | `65a22bfa4512e061ef7142914d032e2ad4a5d2ae` | #19107 合并：`windows(..).rposition(..)` |

`build.rs` 在构建时从 `upstream/<标签>/remove.rs` 取出 `remove_impl`
的完整函数体，只把可见性改成 `pub`；算法不是手抄的。上游文件、来源与
哈希见 `PROVENANCE.md`。

## 运行

```powershell
cargo run --manifest-path 字节删除_nushell_bytes/bytes_demo/Cargo.toml
cargo test --manifest-path 字节删除_nushell_bytes/bytes_demo/Cargo.toml
```

`cargo run` 打印具名反例、882 对穷举统计和 `--end --all` 边界。
`cargo test` 断言同样的数字：

- 882 对（字母表 `[00, 01]`，输入长度 0–5，模式长度 1–3）
- `first` 与 `merge` 差异 0
- `merge` 与独立 oracle 差异 0
- `old-merge` 与 oracle 差异 474
- `old-parent` 在这些输入上 panic 498 次
- `old-merge` 与 `merge-parent` 差异 0
- 474 个未命中案例丢失的字节数都等于 `min(输入长度, 模式长度 - 1)`

## 范围

- 只接受非空模式。真实命令的 `run()` 在进入 `remove_impl` 之前拒绝空模式；
  demo 的 `call()` 用断言记录这个前提，`windows(0)` 的 panic 不属于被测函数。
- `--end` 是删最后一次出现，不是“只匹配后缀”；`--end --all` 会走 forward
  分支，忽略 `--end`。demo 只验证这两条在当前代码里的结果，不声称它们
  是这次修复的目标。
- metadata 的 `content_type` 清空不在 demo 里；它发生在命令层的 `run()`。
- 不构建、不下载、不运行完整 Nushell；上游提交是否进入某个发行版，不由
  这个工程推断。

## 许可

`upstream/LICENSE` 是 Nushell 在合并提交处的 MIT 许可证原文。
