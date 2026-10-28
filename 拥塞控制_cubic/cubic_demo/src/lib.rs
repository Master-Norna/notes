//! quinn CUBIC 拥塞事件处理路径的最小复现。
//!
//! 原型：quinn-rs/quinn `quinn-proto/src/congestion/cubic.rs`
//! 固定提交 2a9f45e47899608ba8875260969667144fb9ef6c（2026-09-30，PR #2903 合并后）。
//!
//! 简化：
//! - 时间用 u64 毫秒，替代 `Instant`；
//! - `RttEstimator` 简化为每次调用传入固定 `rtt`；
//! - 去掉 spurious 回滚、MTU 更新与工厂/配置等与本文无关的部件。
//!
//! 两个版本唯一的区别：`Version::Buggy` 在持久拥塞分支里对 `ssthresh`
//! 再乘一次 `BETA_CUBIC`——读取的 `window` 已经在公共路径里被减过一遍。
//! `Version::Fixed` 即 #2903 删除那五行之后的代码。

/// 持久拥塞时对 `ssthresh` 只保留公共路径的一次 β_cubic 削减（#2903 之后）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Version {
    #[allow(non_camel_case_types)]
    fixed,
    /// #2903 之前的行为：持久拥塞分支再做一次 `ssthresh *= β_cubic`。
    #[allow(non_camel_case_types)]
    buggy,
}

/// 对应 quinn-proto 的 `BASE_DATAGRAM_SIZE`。
pub const BASE_DATAGRAM_SIZE: u64 = 1200;

const BETA_CUBIC: f64 = 0.7;
const C: f64 = 0.4;

#[derive(Debug, Clone, Copy)]
pub struct Cubic {
    pub version: Version,
    current_mtu: u64,
    /// 拥塞窗口（字节）。
    pub window: u64,
    /// 慢启动阈值（字节）。
    pub ssthresh: u64,
    /// CUBIC 窗口大小上限（字节）。
    pub w_max: f64,
    /// CUBIC 时移（秒）。
    pub k: f64,
    /// 拥塞避免阶段累积的信用（字节）。
    pub cwnd_inc: u64,
    /// 进入恢复的时间（毫秒）；持久拥塞处理完置 None。
    pub recovery_start: Option<u64>,
}

impl Cubic {
    /// 与 `Cubic::new` 相同的初值：`initial_window = 14720.clamp(2*mtu, 10*mtu)`，
    /// `ssthresh = u64::MAX`（即一开始就处于拥塞避免）。
    pub fn new(version: Version, current_mtu: u64) -> Self {
        Self {
            version,
            current_mtu,
            window: 14720.clamp(2 * current_mtu, 10 * current_mtu),
            ssthresh: u64::MAX,
            w_max: 0.0,
            k: 0.0,
            cwnd_inc: 0,
            recovery_start: None,
        }
    }

    fn minimum_window(&self) -> u64 {
        2 * self.current_mtu
    }

    // K = cbrt(w_max * (1 - β_cubic) / C)（RFC 9438 式 2 的字节换算形式）
    fn cubic_k(&self) -> f64 {
        (self.w_max / self.current_mtu as f64 * (1.0 - BETA_CUBIC) / C).cbrt()
    }

    // W_cubic(t) = C * (t - k)^3 + w_max（式 1）
    fn w_cubic(&self, t: f64) -> f64 {
        (C * (t - self.k).powi(3) + self.w_max / self.current_mtu as f64) * self.current_mtu
            as f64
    }

    // W_est(t)（式 4），Reno 友好区域下界
    fn w_est(&self, t: f64, rtt: f64) -> f64 {
        (self.w_max / self.current_mtu as f64 * BETA_CUBIC
            + 3.0 * (1.0 - BETA_CUBIC) / (1.0 + BETA_CUBIC) * t / rtt)
            * self.current_mtu as f64
    }

    /// 对应 `Controller::on_ack`（去掉 app_limited 与 ECN 参数）。
    pub fn on_ack(&mut self, now: u64, sent: u64, bytes: u64, rtt_ms: u64) {
        let rtt = rtt_ms as f64 / 1000.0;

        if self
            .recovery_start
            .map(|t| sent <= t)
            .unwrap_or(false)
        {
            return;
        }

        if self.window < self.ssthresh {
            // 慢启动：窗口随确认的字节数增长
            self.window = self.window.saturating_add(bytes);
        } else {
            // 拥塞避免
            let ca_start = match self.recovery_start {
                Some(t) => t,
                None => {
                    // 持久拥塞后首次进入拥塞避免：重置曲线
                    self.recovery_start = Some(now);
                    self.w_max = self.window as f64;
                    self.k = 0.0;
                    now
                }
            };

            let t = (now - ca_start) as f64 / 1000.0;
            let w_cubic = self.w_cubic(t + rtt);
            let w_est = self.w_est(t, rtt);

            let mut cubic_cwnd = self.window;
            if w_cubic < w_est {
                cubic_cwnd = cubic_cwnd.max(w_est as u64);
            } else if cubic_cwnd < w_cubic as u64 {
                let cubic_inc =
                    (w_cubic - cubic_cwnd as f64) / cubic_cwnd as f64 * self.current_mtu as f64;
                cubic_cwnd = cubic_cwnd.saturating_add(cubic_inc as u64);
            }

            self.cwnd_inc = self.cwnd_inc.saturating_add(cubic_cwnd - self.window);
            if self.cwnd_inc >= self.current_mtu {
                self.window += self.current_mtu;
                self.cwnd_inc -= self.current_mtu;
            }
        }
    }

    /// 对应 `Controller::on_congestion_event`（去掉 ECN 参数）。
    pub fn on_congestion_event(&mut self, now: u64, sent: u64, is_persistent: bool) {
        if self
            .recovery_start
            .map(|t| sent <= t)
            .unwrap_or(false)
        {
            return;
        }

        self.recovery_start = Some(now);
        let window = self.window as f64;

        // 快速收敛：窗口低于 W_max 时进一步压低 W_max（RFC 9438 §4.7）
        if window < self.w_max {
            self.w_max = window * (1.0 + BETA_CUBIC) / 2.0;
        } else {
            self.w_max = window;
        }

        // 公共路径：一次 β_cubic 削减（RFC 9438 §4.6）
        self.ssthresh = (window * BETA_CUBIC) as u64;
        self.ssthresh = self.ssthresh.max(self.minimum_window());
        self.window = self.ssthresh;
        self.k = self.cubic_k();
        self.cwnd_inc = (self.cwnd_inc as f64 * BETA_CUBIC) as u64;

        if is_persistent {
            // RFC 9438 §4.8（Timeout）：ssthresh 不再削减，只把窗口压到最小
            self.recovery_start = None;
            self.w_max = self.window as f64;
            self.cwnd_inc = 0;

            if self.version == Version::buggy {
                // #2903 之前的第二次削减。此处 window 已是 0.7 × 事件前窗口。
                self.ssthresh = (self.window as f64 * BETA_CUBIC) as u64;
                self.ssthresh = self.ssthresh.max(self.minimum_window());
            }

            self.window = self.minimum_window();
        }
    }
}

/// `trace` 中窗口首次回到 `target` 的 RTT 序号（`trace[0]` 事件前、
/// `trace[1]` 事件后即时值，`trace[1+n]` 为第 `n` 个 RTT 结束）。
pub fn recovered_at(trace: &[u64], target: u64) -> Option<usize> {
    trace.get(2..)?.iter().position(|&w| w >= target).map(|p| p + 1)
}

/// 事件后即时 `ssthresh` 的直接算术：buggy 在公共路径乘一次 `0.7`、
/// 持久分支再乘一次，每步以最小窗口（2×mtu）为下界。
pub fn ssthresh_after_event(pre_window: u64, version: Version) -> u64 {
    let mut s = pre_window;
    for _ in 0..(1 + usize::from(version == Version::buggy)) {
        s = ((s as f64) * 0.7).max(2.0 * BASE_DATAGRAM_SIZE as f64) as u64;
    }
    s
}

/// 模拟一段持久拥塞后的恢复：
///
/// 事件前窗口 = `pre_window`（窗口、ssthresh、w_max 同为该值，与上游回归测试
/// 的初值一致）；在 t=1000ms 触发持久拥塞事件；之后每个 RTT 按当前窗口发送、
/// 全量确认（链路恢复、不再应用受限），直到窗口回到事件前大小或跑满 `max_rtt`。
///
/// 返回的序列：`trace[0]` 为事件前，`trace[1]` 为事件后即时值，
/// `trace[i]`（i≥2）为第 i-1 个 RTT 结束时的窗口。
pub fn recovery_trace(version: Version, pre_window: u64, rtt_ms: u64, max_rtt: usize) -> Vec<u64> {
    let mut c = Cubic::new(version, BASE_DATAGRAM_SIZE);
    c.window = pre_window;
    c.ssthresh = pre_window;
    c.w_max = pre_window as f64;

    let mut trace = vec![pre_window];
    c.on_congestion_event(1000, 1001, true);
    trace.push(c.window);

    let mut now = 1000u64;
    for _ in 0..max_rtt {
        now += rtt_ms;
        let bytes = c.window.min(pre_window);
        c.on_ack(now, now - 1, bytes, rtt_ms);
        trace.push(c.window);
        if c.window >= pre_window {
            break;
        }
    }
    trace
}

#[cfg(test)]
mod tests {
    use super::*;

    fn state_after_persistent(version: Version, pre: u64) -> (u64, u64) {
        let mut c = Cubic::new(version, BASE_DATAGRAM_SIZE);
        c.window = pre;
        c.ssthresh = pre;
        c.w_max = pre as f64;
        c.on_congestion_event(1000, 1001, true);
        (c.ssthresh, c.window)
    }

    #[test]
    fn buggy_double_reduces_ssthresh() {
        // 事件前 9600B（8×1200）：0.7 × 0.7 = 0.49
        let (ssthresh, window) = state_after_persistent(Version::buggy, 9600);
        assert_eq!(ssthresh, 4704);
        assert_eq!(window, 2400);
    }

    #[test]
    fn fixed_keeps_single_reduction() {
        let (ssthresh, window) = state_after_persistent(Version::fixed, 9600);
        assert_eq!(ssthresh, 6720);
        assert_eq!(window, 2400);
    }

    #[test]
    fn non_persistent_path_is_identical() {
        let mut a = Cubic::new(Version::buggy, BASE_DATAGRAM_SIZE);
        let mut b = Cubic::new(Version::fixed, BASE_DATAGRAM_SIZE);
        for c in [&mut a, &mut b].iter_mut() {
            c.window = 9600;
            c.ssthresh = 9600;
            c.w_max = 9600.0;
        }
        a.on_congestion_event(1000, 1001, false);
        b.on_congestion_event(1000, 1001, false);
        assert_eq!(a.ssthresh, 6720);
        assert_eq!(a.window, 6720);
        assert_eq!(a.window, b.window);
        assert_eq!(a.ssthresh, b.ssthresh);
    }

    #[test]
    fn small_window_clamp_differs() {
        // 事件前 4800B：fixed ssthresh = 3360；buggy 再乘 0.7 得 2352，
        // 被最小窗口 2400 顶住。
        let (buggy_ssthresh, _) = state_after_persistent(Version::buggy, 4800);
        let (fixed_ssthresh, _) = state_after_persistent(Version::fixed, 4800);
        assert_eq!(fixed_ssthresh, 3360);
        assert_eq!(buggy_ssthresh, 2400);
    }

    #[test]
    fn fixed_recovers_faster() {
        // fixed：ssthresh = 6720，2400 → 4800 → 9600 慢启动，第 2 个 RTT 结束回到事件前窗口。
        let fixed = recovery_trace(Version::fixed, 9600, 100, 60);
        let buggy = recovery_trace(Version::buggy, 9600, 100, 60);

        assert_eq!(fixed, vec![9600, 2400, 4800, 9600]);

        // buggy：第 1 个 RTT 的 4800 已越过 4704 的阈值，直接进入拥塞避免。
        assert!(buggy[2] >= 4704);
        let fb = recovered_at(&buggy, 9600).unwrap();
        assert!(fb > 2, "buggy = {:?}", buggy);
        assert!(buggy[fb] < 9600); // 上一个 RTT 结束时还在阈值下
        assert_eq!(buggy[fb + 1], 9600);
    }
}
