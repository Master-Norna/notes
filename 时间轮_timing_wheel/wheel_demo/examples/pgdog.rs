//! 场景 B2：pgdog 事故的精确机制
//!
//! 触发条件（全部由代码验证）：
//! 1. elapsed 紧贴 2^30（12 天）边界之下：elapsed = 2^30 - 1000
//! 2. 一个 max 时长 timer（when = elapsed + 2^36）：
//!    slot_for(when, 5) == now_slot —— 恒等式 (elapsed+2^36)>>30 ≡ (elapsed>>30) (mod 64)
//!    → 它恰好占住 now 所在的顶层槽（伪环条目）
//! 3. 一个 5 秒 interval 跨过 2^30 边界：when = elapsed + 5000
//!    level_for: elapsed ^ when ≈ 2^31 → ilog2 = 30 → 30/6 = 5 → 顶层！
//!    slot_for(when, 5) = 1（now_slot 之后的槽）
//!
//! buggy：扫描从 now_slot(0) 开始 → 命中伪环条目 → deadline 修正 +2^36
//!        → poll_at = 2^36（795 天后）→ driver park 795 天 → interval 挂起
//! fixed：+1 跳过 now_slot → 扫描从槽 1 开始 → 命中 interval → poll_at = 2^30（1 秒后）

use wheel_demo::stack::{Item, SlotStack, VecStore};

const EL: u64 = (1 << 30) - 1_000; // 12 天 - 1 秒
const MAXT: u64 = EL + (1 << 36) - 2_000; // 贴近 max 时长 → 顶层 now_slot（伪环）
const INTV: u64 = EL + 5_000; // 跨过 2^30 边界的 5 秒 interval → 顶层槽 1

fn fmt(v: u64) -> String {
    let d = v / 86_400_000;
    let r = v % 86_400_000;
    if d > 0 { format!("{}天{}ms", d, r) } else { format!("{}ms", v) }
}

fn run_buggy() {
    let mut store = VecStore::default();
    store.items.push(Item(MAXT, "max_timer"));
    store.items.push(Item(INTV, "interval_5s"));
    let mut w = wheel_demo::wheel_buggy::Wheel::<SlotStack>::new();
    w.poll(EL, &mut store);
    w.insert(MAXT, 0, &mut store).unwrap();
    w.insert(INTV, 1, &mut store).unwrap();
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

fn run_fixed() {
    let mut store = VecStore::default();
    store.items.push(Item(MAXT, "max_timer"));
    store.items.push(Item(INTV, "interval_5s"));
    let mut w = wheel_demo::wheel_fixed::Wheel::<SlotStack>::new();
    w.poll(EL, &mut store);
    w.insert(MAXT, 0, &mut store).unwrap();
    w.insert(INTV, 1, &mut store).unwrap();
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
    println!("===== 场景 B2：pgdog 精确机制（elapsed = 2^30 - 1000，紧贴 12 天边界）=====");
    println!(
        "MAX_TIMER = {} (max 时长, 顶层 now_slot 伪环)",
        MAXT
    );
    println!(
        "INTERVAL  = {} (现在起 5 秒后到期, 跨 2^30 边界 → XOR 爆炸 → 顶层槽 1)",
        INTV
    );
    run_buggy();
    run_fixed();
}
