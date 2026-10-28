# CUBIC：持久拥塞下 ssthresh 的两版处理

这个小工程是 quinn 的 CUBIC 拥塞控制器事件处理路径的最小移植。两版（#2903 修复前后）跑同一个持久拥塞剧本，输出逐 RTT 的窗口轨迹。它只模拟控制器状态变化，不做完整 QUIC 连接测试，也不发送 UDP；恢复 RTT 数字对应下述固定发送与 ACK 模型，不是实际网络性能提升的倍率。

配套文章：[中文版](../cubic_持久拥塞_ssthresh_二次削减_中文版.md) / [English](../Cubic_Persistent_Congestion_Second_Cut_EN.md)。

## 两个版本

|版本|持久拥塞事件后的 `ssthresh`|对应|
|---|---|---|
|`Version::fixed`|0.7 × 事件前窗口（公共路径一次削减）|#2903 合并后|
|`Version::buggy`|0.49 × 事件前窗口（分支再读一次已被削过的窗口，乘 0.7）|#2903 之前|

原型取自 quinn 固定提交 [`2a9f45e`](https://github.com/quinn-rs/quinn/commit/2a9f45e47899608ba8875260969667144fb9ef6c) 的 [`cubic.rs`](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs)。两版的唯一差别：`buggy` 的持久拥塞分支还会再读一次 `window`、乘一次 `BETA_CUBIC`——而那五行在 `fixed` 里就是被删掉的部分。事件处理的顺序与上游相同。表中窗口指事件前的 `cwnd`，两版计算都以最小窗口 2400B 为下限（逐次削减时取整）；RFC 9438 §4.6 的基本公式使用的是 `flight_size`，区别见文章第二节。

移植留下了完整的事件路径，省略了 spurious 回滚、MTU 更新与工厂/配置等与本文无关的部件：时间用 u64 毫秒，rtt 每次调用固定传入。

## 运行

需要 Rust 工具链；无第三方 crate 依赖。在本目录运行：

```sh
cargo test
cargo test --release
cargo run --example recovery
```

debug / release 各有 5 条测试：两版事件后状态、非持久路径一致性、小窗口钳制、恢复先后。

`recovery` 直接调用持久拥塞事件处理，不模拟其丢包判定。之后固定 RTT 为 100ms，每个 RTT 按当前窗口模拟发送，并用一次 `on_ack` 调用确认整个窗口；没有后续丢包、逐包 ACK 调度、pacing 或应用受限。窗口达到事件前大小即停止。以下是该模型下的两个场景：

|场景（rtt = 100ms）|修复后|修复前|
|---|---|---|
|事件前窗口 9600B|2 个 RTT 回 9600B|首次到 4800B 后停四个 RTT，再以 1200B 为步长、间有停顿地增长，第 12 个 RTT 回到 9600B|
|事件前窗口 4800B|1 个 RTT 回 4800B|6 个 RTT 回（修复前 `ssthresh` 被钳在最小窗口 2400B）|

重绘文章配图需要 Python 与 Pillow、Matplotlib：`python make_fig.py`。fig2 的轨迹数据经 `cargo run --example plot_data` 实时导出，图、文章里的表与单元测试同一份状态。

上游代码采用 MIT 许可，许可证副本见 [LICENSE](LICENSE)，来源为 [quinn LICENSE-MIT](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/LICENSE-MIT)。
