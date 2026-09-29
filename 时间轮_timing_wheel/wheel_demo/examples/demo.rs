//! 打印 fixed / buggy 两个 wheel 在伪环场景下的真实行为
//!
//! 重点：poll_at —— runtime driver 的 park_internal 只取一次 poll_at，
//! 然后 park 到那个时刻，期间没有任何唤醒源。poll_at 被伪环条目劫持 =
//! driver 睡一整圈 = 所有短周期 timer "挂起"（pgdog 事故）。

use wheel_demo::stack::{Item, SlotStack, VecStore};

// 场景 A：最小复现（elapsed=2）
const FAR_A: u64 = (1 << 36) + 1; // 顶层槽 0（伪环，与 now 同槽）
const NEAR_A: u64 = (1 << 30) + 1_000; // 顶层槽 1

// 场景 B：pgdog 事故镜像
//   运行 12 天（elapsed = 2^30）。长 sleep：when = 2^36 - 1（fudge 进顶层，
//   slot 0 = now_slot）。5 秒 interval：XOR 距离 ~2^32 → level_for 放顶层槽 1。
const EL_B: u64 = 1 << 30;
const LONG_B: u64 = (1 << 36) - 1;
const INT_B: u64 = (1 << 30) + 5_000;

fn fmt(v: u64) -> String {
    let d = v / 86_400_000;
    let r = v % 86_400_000;
    if d > 0 { format!("{}天{}ms", d, r) } else { format!("{}ms", v) }
}

fn run_buggy(el: u64, a: u64, b: u64, la: &'static str, lb: &'static str) {
    let mut store = VecStore::default();
    store.items.push(Item(a, la));
    store.items.push(Item(b, lb));
    let mut w = wheel_demo::wheel_buggy::Wheel::<SlotStack>::new();
    w.poll(el, &mut store);
    w.insert(b, 1, &mut store).unwrap(); // 短 interval 先在
    w.insert(a, 0, &mut store).unwrap(); // 长 sleep 后插（占住 now_slot）
    let at = wheel_demo::wheel_buggy::Wheel::poll_at(&w);
    println!(
        "BUGGY  poll_at = {:?}   ← driver 会 park 到这里: {}",
        at,
        at.as_ref().map(|v| fmt(*v)).unwrap_or_default()
    );
    while let Some(next) = wheel_demo::wheel_buggy::Wheel::poll_at(&w) {
        if let Some(k) = wheel_demo::wheel_buggy::Wheel::poll(&mut w, next, &mut store) {
            println!(
                "       fires {:12} @ {} ({})",
                store.items[k].1,
                next,
                fmt(next)
            );
        }
    }
}

fn run_fixed(el: u64, a: u64, b: u64, la: &'static str, lb: &'static str) {
    let mut store = VecStore::default();
    store.items.push(Item(a, la));
    store.items.push(Item(b, lb));
    let mut w = wheel_demo::wheel_fixed::Wheel::<SlotStack>::new();
    w.poll(el, &mut store);
    w.insert(b, 1, &mut store).unwrap();
    w.insert(a, 0, &mut store).unwrap();
    let at = wheel_demo::wheel_fixed::Wheel::poll_at(&w);
    println!(
        "FIXED  poll_at = {:?}   ← driver 会 park 到这里: {}",
        at,
        at.as_ref().map(|v| fmt(*v)).unwrap_or_default()
    );
    while let Some(next) = wheel_demo::wheel_fixed::Wheel::poll_at(&w) {
        if let Some(k) = wheel_demo::wheel_fixed::Wheel::poll(&mut w, next, &mut store) {
            println!(
                "       fires {:12} @ {} ({})",
                store.items[k].1,
                next,
                fmt(next)
            );
        }
    }
}

fn main() {
    println!("===== 场景 A：最小复现（elapsed=2）=====");
    println!(
        "FAR = {} ({}), NEAR = {} ({})",
        FAR_A,
        fmt(FAR_A),
        NEAR_A,
        fmt(NEAR_A)
    );
    run_buggy(2, FAR_A, NEAR_A, "far", "near");
    run_fixed(2, FAR_A, NEAR_A, "far", "near");

    println!("\n===== 场景 B：低层短 timer 免疫（运行 12 天，长 sleep + 5 秒 interval）=====");
    println!(
        "LONG = {} (顶层), INTERVAL = {} (5 秒后到期, level_for → 低层)",
        LONG_B,
        INT_B
    );
    println!("预期：buggy 与 fixed 一致 —— 伪环只在顶层，低层短 timer 不受影响");
    run_buggy(EL_B, LONG_B, INT_B, "long_sleep", "interval_5s");
    run_fixed(EL_B, LONG_B, INT_B, "long_sleep", "interval_5s");
}
