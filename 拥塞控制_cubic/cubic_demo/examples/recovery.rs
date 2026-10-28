//! 打印持久拥塞事件后两个版本的 ssthresh 与恢复轨迹。
//!
//! 用法：`cargo run --example recovery`

use cubic_demo::{recovered_at, recovery_trace, ssthresh_after_event, Version, BASE_DATAGRAM_SIZE};

fn print_trace(label: &str, rtt_ms: u64, buggy: &[u64], fixed: &[u64], target: u64) {
    let fb = recovered_at(buggy, target).unwrap();
    let ff = recovered_at(fixed, target).unwrap();
    println!("\n{label}（rtt = {rtt_ms}ms，事件前窗口 = {target}B）");
    println!(
        "事件后 ssthresh：buggy = {}，fixed = {}；cwnd 都是 {}",
        ssthresh_after_event(target, Version::buggy),
        ssthresh_after_event(target, Version::fixed),
        2 * BASE_DATAGRAM_SIZE,
    );
    println!("  RTT | buggy  | fixed");
    for n in 1..=fb {
        let b = buggy[1 + n];
        let f = fixed.get(1 + n).copied().unwrap_or(*fixed.last().unwrap());
        println!("{n:>4} | {b:>6} | {f:>6}");
    }
    println!(
        "回到 {}B：buggy 在第 {} 个 RTT 结束，fixed 在第 {} 个 RTT 结束",
        target, fb, ff
    );
}

fn main() {
    let (b, f) = (
        recovery_trace(Version::buggy, 9600, 100, 60),
        recovery_trace(Version::fixed, 9600, 100, 60),
    );
    print_trace("标准例", 100, &b, &f, 9600);
    let (b, f) = (
        recovery_trace(Version::buggy, 4800, 100, 60),
        recovery_trace(Version::fixed, 4800, 100, 60),
    );
    print_trace("小窗口（最小窗口钳制介入）", 100, &b, &f, 4800);
}
