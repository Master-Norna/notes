# ssthresh 怎么会是 0.49：quinn CUBIC 持久拥塞里的两次削减

事件前，拥塞窗口是 9600 字节（8 × 1200，上游回归测试的初值）。发生持久拥塞后，修复后的 quinn 把 `cwnd` 降到最小窗口 2400 字节，`ssthresh` 则按事件前的 `cwnd` 乘一次 0.7，得到 6720 字节。

修复前的 quinn 把 `ssthresh` 留成了 4704。4704 = 0.49 × 9600：**β_cubic 被乘了第二下**。`cwnd` 两版相同，差别全在这条界线上——它是慢启动翻倍和拥塞避免一格一格推的分界（[§4.6](https://www.rfc-editor.org/rfc/rfc9438.html#section-4.6)），矮了，事件后窗口回来的路就长：复现例子里，2 个 RTT 被拖成 12 个，小窗口下 1 个拖成 6 个。

[#2903](https://github.com/quinn-rs/quinn/pull/2903)（9 月 30 日合并，提交 [`2a9f45e`](https://github.com/quinn-rs/quinn/commit/2a9f45e47899608ba8875260969667144fb9ef6c)）删的就是那一下多出的乘法，补上回归测试，只改一个文件。下一节直接上[修后源码](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs#L185-L237)，看两次削减各自落在哪。

## 一、两个削减的位置

先看修后的代码（[固定源码](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs#L185-L237)），`on_congestion_event` 与本篇相关的部分：

```rust
let window = self.state.window as f64;   // 事件前窗口的快照

// ……快速收敛先更新 w_max（RFC 9438 §4.7）……

// 公共路径：一次 β_cubic 削减（RFC 9438 §4.6）
self.state.ssthresh = cmp::max((window * BETA_CUBIC) as u64, self.minimum_window());
self.state.window = self.state.ssthresh;
self.state.k = self.state.cubic_k(self.current_mtu);
self.state.cwnd_inc = (self.state.cwnd_inc as f64 * BETA_CUBIC) as u64;

if is_persistent_congestion {
    // ssthresh already carries the single β_cubic reduction of the pre-event window
    // applied above; RFC 9438 §4.8 (Timeout) requires no further reduction of ssthresh,
    // only cwnd lowered to the minimum window.
    self.state.recovery_start_time = None;
    self.state.w_max = self.state.window as f64;
    self.state.cwnd_inc = 0;
    self.state.window = self.minimum_window();
}
```

公共路径对所有拥塞事件都执行：`ssthresh = 0.7 × 事件前窗口`，并把 `window` 拉到同一个值。持久拥塞分支只做额外的事——清恢复状态、把 `w_max` 压到当前窗口、清掉拥塞避免的累积信用、把 `window` 压到最小窗口（`2 × 1200` 字节）。

修复前，这个分支里还多着五行：

```rust
// 4.7 Timeout - reduce ssthresh based on BETA_CUBIC
self.state.ssthresh = cmp::max(
    (self.state.window as f64 * BETA_CUBIC) as u64,
    self.minimum_window(),
);
```

事件前窗口取 9600 字节（8 × 1200），走一遍：

| 步骤 | 二次削减读到的值 | 修复前 ssthresh | 修复后 ssthresh | window |
|---|---|---:|---:|---:|
| 事件前 | — | 9600 | 9600 | 9600 |
| 公共路径 | — | 6720 | 6720 | 6720 |
| 持久拥塞分支 | 6720（已削过） | **4704** | 6720（不动） | 2400 |

事件前的状态对两版都一样，分叉完全发生在持久拥塞分支里：同一个公式，修复前乘进去的是 6720 而不是 9600。

![事件后 ssthresh 落在哪里（同一把尺子：事件前窗口 → 一次 0.7 → 0.49）](assets/fig1_ssthresh_two_cuts.png)

## 二、规范说的是减一次

持久拥塞是 QUIC 自己的概念。[RFC 9002 §7.6.1](https://www.rfc-editor.org/rfc/rfc9002.html#section-7.6.1) 给出的持续时间阈值是 `(smoothed_rtt + max(4×rttvar, 时钟粒度) + max_ack_delay) × kPersistentCongestionThreshold`，quinn 的倍数默认 3。

但超过这段时间还不够：[§7.6.2](https://www.rfc-editor.org/rfc/rfc9002.html#section-7.6.2) 要求收到 ACK 后，判定两个会引发确认的包（ack-eliciting）丢失，两包发送时间之差超过阈值，且其间发送的包跨包号空间都没有被确认；这两个包发送时还必须已经有 RTT 样本。

这里比较的是发送时间跨度，**不要求实际连续触发三次 PTO**；该持续时间计算也始终计入 `max_ack_delay`，与部分包号空间的 PTO 计算有别。

quinn 的 CUBIC 对它的处理走的是超时路径，[RFC 9438 §4.8](https://www.rfc-editor.org/rfc/rfc9438.html#section-4.8) 的原文：

> In the case of a timeout, CUBIC follows Reno to reduce *cwnd* but sets *ssthresh* using β_cubic (same as in Section 4.6) in a way that is different from Reno TCP.

而 [§4.6](https://www.rfc-editor.org/rfc/rfc9438.html#section-4.6) 的基本公式是 `ssthresh = flight_size × β_cubic`（另有最小值约束）。`flight_size` 是网络中尚未确认的数据量，`cwnd` 是允许的拥塞窗口，两者不一定相等。可以把 `cwnd` 看作发货额度，`flight_size` 看作已经发出、还没签收的货量：额度有 9600，不代表路上就一定有 9600；如果应用暂时只交出 4800 的数据，实际在途量就可能只有额度的一半。

RFC 也允许实现使用 `cwnd`，但要求另有措施：在在途数据量小于 `cwnd` 时，阻止 `cwnd` 继续增长。本文讨论的是 quinn 以事件前 `cwnd` 为基准的具体实现：公共路径已经乘过一次 0.7，超时处理不应再对削减后的窗口乘第二次。

旧代码的注释写着 `4.7 Timeout`——那不是编号写错了。旧版 RFC 8312 里 Timeout 就是 [§4.7](https://www.rfc-editor.org/rfc/rfc8312.html#section-4.7)，原文 "sets ssthresh using beta_cubic (same as in Section 4.5)"，和 RFC 9438 说的是同一件事。两版条款都让超时处理沿用拥塞事件的 β_cubic 削减，而不是追加一次削减；旧代码却把它当成持久拥塞分支里的一个**追加步骤**，乘的基准已经变成了公共路径削完的值。

## 三、同一个问题，NewReno 没有

quinn 的另一个控制器 `NewReno` 有完整的同款分支（[new_reno.rs](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/new_reno.rs#L85-L105)）：

```rust
self.window = (self.window as f32 * self.config.loss_reduction_factor) as u64;
self.window = self.window.max(self.minimum_window());
self.ssthresh = self.window;

if is_persistent_congestion {
    self.window = self.minimum_window();
}
```

`ssthresh` 只被赋值一次，持久拥塞分支只动 `window`。CUBIC 的路径多曲线参数，持久拥塞分支更长，多出的五行就落在这上面。

## 四、0.49 有多重

继续用发货来想：发生拥塞后，额度先被压到很小，接下来要试着恢复。`ssthresh` 不是当前额度，也不是以后不能超过的上限，而是“何时停止快速扩量、改为小步试探”的分界。对应到代码，窗口低于它时走慢启动，随确认字节数增长；达到它后进入拥塞避免，由 CUBIC 控制增长。

所以，阈值更低不等于恢复更快。窗口来到 4800B 时，若分界是 6720B，下一轮还可以走慢启动；若分界已经降到 4704B，同样的 4800B 就会进入拥塞避免。两版此刻的窗口一样大，接下来却走了不同的增长路径。

仓库里的 `cubic_demo` 是控制器逻辑的最小移植，不跑完整 QUIC 连接。两个版本跑同一个剧本：事件前窗口 9600 字节、RTT 固定 100ms，直接调用一次持久拥塞事件处理，之后每个 RTT 按当前窗口模拟发送，再用一次 `on_ack` 调用确认整个窗口；没有新增丢包，也不模拟逐包 ACK、pacing 或应用受限。窗口回到事件前大小就停止。

下面的 2 / 12、1 / 6 个 RTT 描述的是这个模型里的窗口恢复，不代表完整连接的恢复时延或吞吐收益。事件后两版都从 2400B（最小窗口）出发：

![cubic_demo 固定 RTT、每 RTT 一次全窗口 ACK 模型下的窗口轨迹：左为事件前 9600B，右为 4800B](assets/fig2_recovery.png)

左图是标准窗口（事件前 9600B）：第一个 RTT 两版都是 4800——2400 还没碰各自的阈值，慢启动如常翻倍。第二个 RTT 分道：fixed 的 4800 仍低于 6720，继续慢启动翻倍回到 9600；buggy 的 4800 已经越过 4704 的阈值，滑进拥塞避免：窗口又停住 4 个 RTT，随后以 1200 字节为步长继续增长，中间仍有停顿，依次经过 6000、7200、8400，到第 12 个 RTT 才回到 9600。

右图是小窗口：事件前 4800 字节时，0.49 × 4800 = 2352 已经低于最小窗口 2400，被钳制定住；0.7 × 4800 = 3360 还留在上面。相差的还是那个 0.49，只是钳制把 buggy 的 `ssthresh` 顶在 2400B——矮得少一点，但 fixed 第一次增长就直接回到事件前大小（1 个 RTT），buggy 一格一格推了 6 个 RTT。

## 五、测试把断言钉在一行上

PR 里的回归测试不长（[cubic.rs](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs#L329-L346)）：

```rust
#[test]
fn persistent_congestion_does_not_double_reduce_ssthresh() {
    let now = Instant::now();
    let config = Arc::new(CubicConfig::default());
    let mut cubic = Cubic::new(config, now, BASE_DATAGRAM_SIZE as u16);
    let window = 8 * BASE_DATAGRAM_SIZE;

    cubic.state.window = window;
    cubic.state.ssthresh = window;
    cubic.state.w_max = window as f64;

    cubic.on_congestion_event(now, now + Duration::from_millis(1), true, false, 0);

    // RFC 9438 §4.8 (Timeout): ssthresh is the pre-event window reduced by β_cubic
    // exactly once, as in §4.6; only cwnd is lowered to the minimum window.
    assert_eq!(cubic.state.ssthresh, (window as f64 * BETA_CUBIC) as u64);
    assert_eq!(cubic.state.window, 2 * BASE_DATAGRAM_SIZE);
}
```

断言钉住的是 quinn 的实现行为：持久拥塞事件之后，`ssthresh == 0.7 × 事件前窗口`，`cwnd` 只剩最小窗口。换成 0.49 的版本，第一行断言就给抓住。PR 的验证记录：`cargo test -p quinn-proto` 333 个测试全过，clippy 与 fmt 干净。

`cubic_demo` 的移植保留了事件处理的完整顺序，简化了三件事：时间用毫秒整数、rtt 每次调用固定、去掉 spurious 回滚和 MTU 更新的枝节。两版的全部差异就是那五行在不在：

- [`cubic_demo`](cubic_demo/)：`cargo test` 五个测试（两版事件后状态、非持久路径一致性、钳制、恢复先后），debug/release 都过；`cargo run --example recovery` 打印上一节的两个轨迹。

## 写在最后

问题不在 0.7，而在取值的时机。quinn 本来要用事件前的 `cwnd` 算 `ssthresh`，分支里读到的却是公共路径已经削过的 `window`。同一个 β_cubic，就这样对同一场拥塞生效了两次。读这类状态更新，除了核对公式，还得沿着赋值顺序看：右侧的 `window` 到这里时，还是原来那个值吗？

上游的修法没有重写任何逻辑——删五行，加测试。

2026-10-28 修订：区分 RFC 的 `flight_size` 与 quinn 使用的 `cwnd`，补全持久拥塞判定条件，明确恢复 RTT 数字对应的模拟发送与 ACK 模型，并疏开机制图的标签间距。
