# CUBIC：持久拥塞下 ssthresh 的两版处理

这个小工程是 quinn 的 CUBIC 拥塞控制器事件处理路径的最小移植。两版（#2903 修复前后）跑同一个持久拥塞剧本，输出逐 RTT 的窗口轨迹。不跑真实连接，不发动真 UDP。

配套文章：[中文版](../cubic_持久拥塞_ssthresh_二次削减_中文版.md) / [English](../Cubic_Persistent_Congestion_Second_Cut_EN.md)。

## 两个版本

|版本|持久拥塞事件后的 `ssthresh`|对应|
|---|---|---|
|`Version::fixed`|0.7 × 事件前窗口（公共路径一次削减）|#2903 合并后|
|`Version::buggy`|0.49 × 事件前窗口（分支再读一次已被削过的窗口，乘 0.7）|#2903 之前|

原型取自 quinn 固定提交 [`2a9f45e`](https://github.com/quinn-rs/quinn/commit/2a9f45e47899608ba8875260969667144fb9ef6c) 的 [`cubic.rs`](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs)。两版的唯一差别：`buggy` 的持久拥塞分支还会再读一次 `window`、乘一次 `BETA_CUBIC`——而那五行在 `fixed` 里就是被删掉的部分。事件处理的顺序与上游相同。

移植留下了完整的事件路径，省略了 spurious 回滚、MTU 更新与工厂/配置等与本文无关的部件：时间用 u64 毫秒，rtt 每次调用固定传入。

## 运行

需要 Rust 工具链；无第三方 crate 依赖。在本目录运行：

```sh
cargo test
cargo test --release
cargo run --example recovery
```

debug / release 各有 5 条测试：两版事件后状态、非持久路径一致性、小窗口钳制、恢复先后。

`recovery` 打印文章里的两个场景：

|场景（rtt = 100ms）|修复后|修复前|
|---|---|---|
|事件前窗口 9600B|2 个 RTT 回 9600B|停 4800B 四个 RTT，再按 1200B 一格推，12 个 RTT 才回|
|事件前窗口 4800B|1 个 RTT 回 4800B|6 个 RTT 回（修复前 `ssthresh` 被钳在最小窗口 2400B）|

重绘文章配图需要 Python 与 Pillow、Matplotlib：`python make_fig.py`。fig2 的轨迹数据经 `cargo run --example plot_data` 实时导出，图、文章里的表与单元测试同一份状态。

上游代码采用 MIT 许可，许可证副本见 [LICENSE](LICENSE)，来源为 [quinn LICENSE-MIT](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/LICENSE-MIT)。
