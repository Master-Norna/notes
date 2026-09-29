//! 扫描：找 buggy 与 fixed 行为分叉的精确条件
//! 固定：一个长 sleep（fudge 进顶层）+ 一个短 interval
//! 变：elapsed（运行时长）
//! 判据：poll_at 是否被伪环条目劫持（buggy poll_at > fixed poll_at）

use wheel_demo::stack::{Item, SlotStack, VecStore};

fn poll_at_buggy(el: u64, long: u64, near: u64) -> Option<u64> {
    let mut store = VecStore::default();
    store.items.push(Item(long, "long"));
    store.items.push(Item(near, "near"));
    let mut w = wheel_demo::wheel_buggy::Wheel::<SlotStack>::new();
    w.poll(el, &mut store);
    w.insert(near, 1, &mut store).ok()?;
    w.insert(long, 0, &mut store).ok()?;
    wheel_demo::wheel_buggy::Wheel::poll_at(&w)
}

fn poll_at_fixed(el: u64, long: u64, near: u64) -> Option<u64> {
    let mut store = VecStore::default();
    store.items.push(Item(long, "long"));
    store.items.push(Item(near, "near"));
    let mut w = wheel_demo::wheel_fixed::Wheel::<SlotStack>::new();
    w.poll(el, &mut store);
    w.insert(near, 1, &mut store).ok()?;
    w.insert(long, 0, &mut store).ok()?;
    wheel_demo::wheel_fixed::Wheel::poll_at(&w)
}

fn main() {
    // 长 sleep 固定在 2^36 + 1000（fudge 进顶层，伪环）
    let long = (1u64 << 36) + 1000;
    // 短 interval：相对 now 的 5 秒
    // 扫描 elapsed，找 buggy != fixed 的窗口
    println!("long = {} (fudge 进顶层)", long);
    println!("\nelapsed        buggy_poll_at          fixed_poll_at          分叉?");
    let mut diverged = 0;
    for el_ms in [
        2u64,
        1000,
        1 << 20,
        1 << 24,
        1 << 28,
        1 << 30, // 12天
        (1 << 30) + 5_000,
        (1 << 30) * 2,
        (1 << 30) * 10,
        1 << 35,
        (1 << 36) - 1000,
        1 << 36,
        (1 << 36) + 100,
        (1 << 36) + 1000,
        (1 << 36) + 100_000,
    ] {
        let near = el_ms + 5_000; // interval：now + 5s
        let b = poll_at_buggy(el_ms, long, near);
        let f = poll_at_fixed(el_ms, long, near);
        let div = b != f;
        if div {
            diverged += 1;
        }
        println!(
            "{:>14}  {:>20}  {:>20}  {}",
            el_ms,
            b.map(|v| v.to_string()).unwrap_or_else(|| "-".into()),
            f.map(|v| v.to_string()).unwrap_or_else(|| "-".into()),
            if div { "◀◀◀ 分叉" } else { "" }
        );
    }
    println!("\n共 {} 个分叉点", diverged);
}
