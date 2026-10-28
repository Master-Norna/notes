//! 完整恢复轨迹的导出，给 `../../make_fig.py` 画图用，本身不作为正文阅读。
//!
//! 每行：`场景<TAB>值序列`；x=0 为事件后即时窗口，x=i 为第 i 个 RTT 结束时的窗口。
//! 先恢复完的版本用其终止值补满，画到另一版恢复完成为止。

use cubic_demo::{recovery_trace, Version};

fn series(trace: &[u64], pad: usize) -> Vec<u64> {
    (0..pad).map(|i| trace.get(1 + i).copied().unwrap_or(*trace.last().unwrap())).collect()
}

fn dump(label: &str, pre: u64) {
    let buggy = recovery_trace(Version::buggy, pre, 100, 60);
    let fixed = recovery_trace(Version::fixed, pre, 100, 60);
    let pad = buggy.len().max(fixed.len()) - 1;
    let buggy: Vec<String> = series(&buggy, pad).iter().map(u64::to_string).collect();
    let fixed: Vec<String> = series(&fixed, pad).iter().map(u64::to_string).collect();
    println!("{label} bug\t{}", buggy.join(" "));
    println!("{label} fix\t{}", fixed.join(" "));
}

fn main() {
    dump("std", 9600);
    dump("small", 4800);
}
