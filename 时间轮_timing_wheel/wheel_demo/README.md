# 时间轮：三种扫描规则的对照

这个小工程抽取 tokio-util 的时间轮，配上测试用的 `Stack` / `Store`，用确定的毫秒 tick 重现顶层伪环问题和级联反例。不运行真实时钟，也不需要等待 12 天。

配套文章：[首篇](../时间轮_论文对照_tokio_中文版.md) / [续篇](../时间轮_续篇_只在顶层加一_中文版.md)。

## 三份实现

|模块|扫描起点|对应版本|
|---|---|---|
|`wheel_buggy`|当前槽|#8519 修复前|
|`wheel_fixed`|所有层的下一槽|首篇使用的初稿修复，存在级联回归；保留旧名字以便对照|
|`wheel_merged`|顶层从下一槽开始，低层从当前槽开始|#8519 最终合并的扫描规则|

`wheel_merged` 的扫描函数对应 tokio 合并提交 [`2fb5757`](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio-util/src/time/wheel/level.rs#L103-L120)。三个模块使用相同的 wheel 推进逻辑；`wheel_fixed` 不是“最终正确版”。

工程替换了上游存储类型并省去了上游模块内测试，没有包含完整 `DelayQueue` 或 runtime。这里的测试数不等于 Tokio 仓库的测试数。

## 运行

需要 Rust 工具链；无第三方 crate 依赖。在本目录运行：

```sh
cargo test
cargo test --release
cargo run --example followup
cargo run --release --example followup
```

debug / release 各有 9 个测试，覆盖历史场景、三版本差异、顶层只有当前槽非空以及多层级联边界。

`followup` 示例会捕获预期的断言失败，继续打印其他版本的结果。模拟驱动保持 `wake = max(wake, poll_at)`，不会因错误实现报告过去的候选时刻而把观测时间倒拨。

### 结果摘要

表中的时刻为从 wheel 起点计算的绝对毫秒。`a` 是先到期的条目，`b` 是后到期的条目。

|场景|无偏移|全层 `+1`|仅顶层 `+1`|
|---|---|---|---|
|64 / 65，两种模式|a@64 → b@65|b@65 → a@65|a@64 → b@65|
|4096 / 4160，debug|a@4096 → b@4160|断言失败|a@4096 → b@4160|
|4096 / 4160，release|a@4096 → b@4160|b@4160 → a@8192|a@4096 → b@4160|
|顶层伪环，debug|断言失败|near 准点|near 准点|
|顶层伪环，release|near 延迟顶层一圈|near 准点|near 准点|

顶层伪环场景：`elapsed=2`，near=`2^30+1000`，far=`2^36+1`。顶层一圈是 `2^36`ms，约 795 天。只有当前槽占用时，`+1` 仍会绕回并选中它；它只是把该槽排在扫描最后，没有清除占用位。

## 首篇的示例

这些示例保留首篇的两版本对照，输出中的 `FIXED` 指初稿全层 `+1`，不是最终合并方案。请使用 release 模式观察完整的延迟结果：

```sh
cargo run --release --example demo    # 最小顶层反例与不跨顶层边界的对照
cargo run --release --example pgdog   # 跨 2^30 边界的 5 秒 timer
cargo run --release --example sweep   # 扫描初次 poll_at 的差异
```

旧测试 `lower_level_now_slot_is_empty` 已改名为 `historical_lower_level_smoke_case`。它只验证一条正常时间线，不能证明“低层当前槽永远为空”；续篇中的两组级联反例说明这个推论不成立。

重画续篇配图需 Python 与 Pillow：`python make_followup_fig.py`。脚本默认使用 Windows 微软雅黑；其他平台可用 `CJK_FONT`、`CJK_FONT_BOLD` 指定中文字体。

上游代码采用 MIT 许可，许可证副本见 [LICENSE](LICENSE)，来源为 [Tokio LICENSE](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/LICENSE)。
