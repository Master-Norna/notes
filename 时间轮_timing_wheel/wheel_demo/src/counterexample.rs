//! 反例：顶层伪环形缓冲 + 无 +1 偏移 → 近端条目被推迟一整圈
//!
//! 可达场景（全部通过合法 insert 构造，tokio-util 的 MAX_DURATION 检查可过）：
//! - 先插入 NEAR = 2^30 + 100（12 天 + 1 秒，顶层槽 1），把 elapsed 推到 2；
//! - 再插入 FAR = 2^36 + 1：slot_for 落在顶层槽 0 —— 与 now（elapsed=2，也在槽 0）
//!   同槽。它是"逻辑上整整一圈之后"的条目（伪环 wrap）：物理在槽 0，
//!   真实 deadline 在 256 天后。
//!
//! 顶层 now 槽被伪环条目占据时，+1 才起作用：
//! - fixed（含 +1）：扫描从槽 1 开始 → 命中 NEAR → poll_at = 2^30（12 天）。
//! - buggy（无 +1）：扫描从槽 0 开始 → 命中 FAR → deadline 算成槽起点 0（< now）
//!   → +level_range 修正 → poll_at = 2^36（256 天）。
//!   结果：NEAR 本应 12 天 + 1 秒到期，实际被推迟整整一圈（256 天）。

use crate::stack::{Item, SlotStack, VecStore};

const FAR: u64 = (1 << 36) + 1; // 256 天后到期 → 顶层槽 0（伪环 wrap，与 now 同槽）
const NEAR: u64 = (1 << 30) + 1_000; // 12 天 + 1 秒后到期 → 顶层槽 1
const LAP: u64 = 1 << 36; // 顶层一圈 ≈ 256 天

fn setup_buggy() -> (crate::wheel_buggy::Wheel<SlotStack>, VecStore) {
    let mut store = VecStore::default();
    store.items.push(Item(NEAR, "near"));
    let k_near = 0usize;
    store.items.push(Item(FAR, "far"));
    let k_far = 1usize;

    let mut wheel = crate::wheel_buggy::Wheel::<SlotStack>::new();
    wheel.insert(NEAR, k_near, &mut store).unwrap();
    wheel.poll(2, &mut store); // 把 elapsed 推到 2（now 落在顶层槽 0）
    wheel.insert(FAR, k_far, &mut store).unwrap();
    (wheel, store)
}

fn setup_fixed() -> (crate::wheel_fixed::Wheel<SlotStack>, VecStore) {
    let mut store = VecStore::default();
    store.items.push(Item(NEAR, "near"));
    let k_near = 0usize;
    store.items.push(Item(FAR, "far"));
    let k_far = 1usize;

    let mut wheel = crate::wheel_fixed::Wheel::<SlotStack>::new();
    wheel.insert(NEAR, k_near, &mut store).unwrap();
    wheel.poll(2, &mut store);
    wheel.insert(FAR, k_far, &mut store).unwrap();
    (wheel, store)
}

/// 模拟驱动循环：每次按 poll_at 报告的 deadline 醒来，记录弹出顺序。
fn schedule_buggy(
    wheel: &mut crate::wheel_buggy::Wheel<SlotStack>,
    store: &mut VecStore,
) -> Vec<(&'static str, u64)> {
    let mut out = Vec::new();
    while let Some(next) = crate::wheel_buggy::Wheel::poll_at(wheel) {
        if let Some(k) = crate::wheel_buggy::Wheel::poll(wheel, next, store) {
            out.push((store.items[k].1, next));
        }
    }
    out
}

fn schedule_fixed(
    wheel: &mut crate::wheel_fixed::Wheel<SlotStack>,
    store: &mut VecStore,
) -> Vec<(&'static str, u64)> {
    let mut out = Vec::new();
    while let Some(next) = crate::wheel_fixed::Wheel::poll_at(wheel) {
        if let Some(k) = crate::wheel_fixed::Wheel::poll(wheel, next, store) {
            out.push((store.items[k].1, next));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn buggy_poll_at_jumps_a_full_lap() {
        let (wheel, _store) = setup_buggy();
        assert_eq!(
            crate::wheel_buggy::Wheel::poll_at(&wheel),
            Some(LAP),
            "buggy: 应被伪环条目劫持到 256 天（2^36），而非 12 天（2^30）"
        );
    }

    #[test]
    fn fixed_poll_at_reports_near() {
        let (wheel, _store) = setup_fixed();
        assert_eq!(
            crate::wheel_fixed::Wheel::poll_at(&wheel),
            Some(1 << 30),
            "fixed: 应报告 12 天（顶层槽 1 起点）"
        );
    }

    #[test]
    fn buggy_schedule_delays_near_by_a_full_lap() {
        let (mut wheel, mut store) = setup_buggy();
        let schedule = schedule_buggy(&mut wheel, &mut store);
        // far 准点（256 天后）；near 被推迟整整一圈（2^36）
        assert_eq!(
            schedule,
            vec![("far", FAR), ("near", LAP + NEAR)],
            "buggy: near 本应 2^30+1000 到期，实际推迟 2^36（约 795 天，顶层一整圈）"
        );
    }

    #[test]
    fn fixed_schedule_fires_on_time() {
        let (mut wheel, mut store) = setup_fixed();
        let schedule = schedule_fixed(&mut wheel, &mut store);
        assert_eq!(
            schedule,
            vec![("near", NEAR), ("far", FAR)],
            "fixed: near 12 天 + 1 秒到期，far 256 天 + 1 秒到期"
        );
    }

    /// 低层不变量：now 槽在低层永远空（level_for 按相对距离放置，
    /// 同槽 ⇒ XOR 距离 < 槽宽 ⇒ 不会落到顶层），所以 +1 在低层是无害的 no-op。
    #[test]
    fn lower_level_now_slot_is_empty() {
        let mut store = VecStore::default();
        store.items.push(Item(10, "ten_ms"));
        let k_ten = 0usize;
        store.items.push(Item(NEAR, "near"));
        let k_near = 1usize;
        store.items.push(Item(FAR, "far"));
        let k_far = 2usize;

        let mut wheel = crate::wheel_fixed::Wheel::<SlotStack>::new();
        wheel.insert(10, k_ten, &mut store).unwrap();
        wheel.poll(2, &mut store);
        wheel.insert(NEAR, k_near, &mut store).unwrap();
        wheel.insert(FAR, k_far, &mut store).unwrap();

        let schedule = schedule_fixed(&mut wheel, &mut store);
        assert_eq!(
            schedule,
            vec![("ten_ms", 10), ("near", NEAR), ("far", FAR)],
            "fixed: 10ms 条目不受 +1 影响，照样 10ms 到期"
        );
    }
}
