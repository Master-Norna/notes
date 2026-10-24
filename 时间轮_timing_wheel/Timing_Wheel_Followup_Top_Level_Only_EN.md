# Why the Timing Wheel's `+1` Stayed Only at the Top

When I published [The `+1` That Wasn't Supposed to Be There](Timing_Wheels_From_SOSP_1987_to_tokio_EN.md), #8519 was still in review. I wrote a confident sentence:

> At lower levels the `+1` is a harmless no-op: `level_for` guarantees no entry ever lands in the `now` slot at a lower level (it's always empty there), so skipping or not makes no difference. The fix only bites at the top level — which is precisely the only level where this can happen.

The conclusion — the `+1` ends up only at the top — turned out to be right. The reason was not. Lower-level current slots are not always empty; a cascade can fill them. My text reached that conclusion; my code applied `+1` at every level.

`level_for` really does keep a freshly inserted entry out of a lower level's current slot. But `insert` is not the only write path.

**A property that holds after an insert need not survive a cascade.** I checked the state after `insert` and described it as an invariant of the whole structure.

On October 10, 2026, maintainer Darksonn posted two tests in the [review of #8519](https://github.com/tokio-rs/tokio/pull/8519#discussion_r4237816039): `64ms / 65ms` and `4096ms / 4160ms`. No twelve-day wait, no enormous sleep; each pair differs by a single slot width — 1ms and 64ms.

The PR merged on October 11 (commit [`2fb5757`](https://github.com/tokio-rs/tokio/commit/2fb5757a97a94b3173f8fdd7b6280423b63da6e6)). What merged was not the all-level `+1` from my first post. It was a `+1` only at the top.

The two tests split my original reasoning in half: one half is about where the scan starts, the other about how entries enter the current slot. I had not looked at the second half.

## 1. The code that actually merged

The final scan computes its starting slot like this ([pinned source](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio-util/src/time/wheel/level.rs#L103-L122)):

```rust
let mut now_slot = ((now / slot_range(self.level)) % LEVEL_MULT as u64) as usize;
// Only the top level acts as a pseudo-ring buffer, where the slot
// holding `now` may contain a timer a whole rotation away. Scan that
// slot last. Lower levels must include the current slot because
// cascading can place timers there that are ready to expire.
if self.level == super::NUM_LEVELS - 1 {
    now_slot += 1;
}
let occupied = self.occupied.rotate_right(now_slot as u32);
let zeros = occupied.trailing_zeros() as usize;
let slot = (zeros + now_slot) % LEVEL_MULT;
```

The important change is not the `if` itself. It is the distinction between two meanings of “the current slot”:

| Location | What the current slot may hold | Scan order |
|---|---|---|
| Top level | A distant timer wrapped by the pseudo-ring: logically a full rotation away, physically in the current slot | Start at the next slot; examine the current slot last |
| Lower levels | A timer just cascaded down from above, ready for immediate processing | The current slot must be allowed first |

“Last” is not “never.” `rotate_right` only rotates the `occupied` bitmap, and `trailing_zeros` finds the first set bit from the low end; no bit is cleared. If the current top-level slot is the only occupied slot, the scan still selects it after wrapping around.

The first post explained why the top level has to yield. The review supplied the other half: why the lower levels must not.

## 2. 64ms: a cascade writes into the current slot

Each level has 64 slots. L0 slots are 1ms wide, L1 slots are 64ms wide, and top-level slots are `2^30`ms wide (about 12 days).

Insert two entries at `elapsed = 0`: a is due at 64ms, b at 65ms.

`level_for` takes the highest set bit of `elapsed ^ when`. Both `0 ^ 64` and `0 ^ 65` have their highest bit at `2^6`, so both entries go to L1. Since `64 / 64 = 1` and `65 / 64 = 1`, they land in L1 slot 1, which covers `[64, 128)`.

At 64ms, L1 slot 1 is processed. tokio-util does not return expired entries directly from an upper level; it first moves them down one level. The cascade calls `add_entry(when, ...)`, and the slot index depends only on `when`; `level_for` is not consulted again:

```text
L1 slot 1  [64, 128)
  a @ 64ms  ──►  L0 slot 0   ← current slot at elapsed = 64
  b @ 65ms  ──►  L0 slot 1
```

The wheel then advances `elapsed` to 64. Since `64 % 64 = 0`, L0's current slot is slot 0.

**L0's current slot is not empty. It holds a timer that is due now.**

Add one at every level, and the L0 scan starts at slot 1. It selects `b` first. Slot 0, where `a` sits, is selected only after the scan wraps around; so `b` is delivered before `a`.

In the monotonic driver used here, both debug and release produce:

```text
all-level +1   b @ 65ms → a @ 65ms
merged         a @ 64ms → b @ 65ms
```

`a`'s deadline is 64; it is not “simultaneous” with `b`. In this 1ms example, `a` is taken on the next `poll`, and the observed wake is also 65ms. But two timers with different deadlines should not have their delivery order determined by the scan start.

There is a trap in writing the experiment. When `Wheel::poll` returns an L0 entry, it does not necessarily update the internal `elapsed` to the caller's `now`. After delivering `b`, the broken wheel can report `poll_at = 64` again. A driver must not turn time backward. The simulation uses `wake = max(wake, poll_at)` to keep observed time monotonic; otherwise it would print the impossible history “`b` at 65ms, then `a` at 64ms.”

The maintainer's original counterexample is a public-API `DelayQueue` test ([merged test](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio-util/tests/time_delay_queue.rs#L812-L832)):

```rust
#[tokio::test(start_paused = true)]
async fn cascade_into_level_zero_slot_zero() {
    let mut queue = DelayQueue::new();

    queue.insert("a", ms(64));
    queue.insert("b", ms(65));

    assert_eq!(queue.next().await.unwrap().into_inner(), "a");
    assert_eq!(queue.next().await.unwrap().into_inner(), "b");
}
```

Tokio's paused clock checks the order of `next()` directly. The small program here lifts the wheel out so that each cascade and delivery can be examined separately.

## 3. 4096ms: skipping the current slot can strand an entry in the past

The second pair crosses one more level: a is due at 4096ms, b at 4160ms.

Inserted at `elapsed = 0`, `4096 = 2^12` and `4160 = 2^12 + 64`, so the highest differing bit is `2^12`; both entries go to L2 slot 1, covering `[4096, 8192)`.

At 4096ms, that slot cascades into L1: `a` goes to slot 0, `b` to slot 1. L1 slots are 64ms wide, and `(4096 / 64) % 64 = 0`, so L1's current slot is also slot 0.

The all-level `+1` starts at L1 slot 1 and processes `b` first. `b` is moved down to L0 slot 0; `a` remains in L1 slot 0. The wheel advances to 4160ms. L0 now has only slot 0 occupied; the scan starts at slot 1, wraps around, and still selects slot 0, so `b` is delivered at 4160ms.

Now L1 slot 0 starts at 4096, which is earlier than 4160. There is a branch in `Level::next_expiration` for exactly this case (with the pseudo-ring comment omitted):

```rust
let level_start = now - (now % level_range);
let mut deadline = level_start + slot as u64 * slot_range;
if deadline < now {
    // ... top-level pseudo-ring explanation ...
    debug_assert_eq!(self.level, super::NUM_LEVELS - 1);
    deadline += level_range;
}
```

That branch is meant only for the top level, because only the top level stores a timer a whole rotation away in a current physical slot. The all-level `+1` has sent a lower-level slot into it.

In debug, before `Wheel::next_expiration` returns the L0 expiration at 4160, it runs `no_expirations_before` against the higher levels. It asks L1 about slot 0, gets `deadline = 4096 < now = 4160`, and the `debug_assert_eq!(self.level, 5)` fails:

```text
assertion `left == right` failed
  left: 1
 right: 5
```

In release the assertion is compiled out. The code adds one full L1 rotation (4096ms) to the stale start, and `a` is scheduled for 8192ms. The experiment reports:

```text
all-level +1   b @ 4160ms → a @ 8192ms
merged         a @ 4096ms → b @ 4160ms
```

The first pair is an ordering failure: `a` should have gone first, but `b` got ahead. That pair never reaches this branch: `a` stays in L0 slot 0, and L0's current slot is slot 0, so the slot's deadline equals `now` and `< now` is false. The second is worse: `a` is left in a slot whose start is already in the past, and the next `poll_at` calculation can only apply the pseudo-ring assumption and push it a full rotation later.

The same `+1` moves “the next slot” one step out at the top. At a lower level, it can push work that is already due into the next rotation. Both look like skipping the current slot; they do not mean the same thing.

## 4. The second write path I missed

My first explanation followed only `Wheel::insert`: choose a level with `level_for(elapsed, when)`, then call that level's `add_entry`.

For a non-top level actually selected by `level_for`, the highest differing bit of `elapsed ^ when` lies in the six bits used for that level's slot index. The two slot indices therefore differ. After an ordinary insert, the lower-level current slot really is empty.

But that is a state, not an invariant over every write path. tokio-util has a second path in [`poll_expiration`](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio-util/src/time/wheel/mod.rs#L206-L222):

```rust
let next_level = expiration.level - 1;
self.levels[next_level].add_entry(when, item, store);
```

It **moves entries down exactly one level, without calling `level_for` again**. `add_entry` computes the slot from `when` alone, so `a`, just moved from L1 to L0, can land exactly in L0's current slot.

I had mistaken an insertion rule for a property preserved by every write path. An old test named `lower_level_now_slot_is_empty` exercised one timeline that never encountered the counterexample; its name claimed much more than its assertions established. It is now `historical_lower_level_smoke_case`, kept only as a smoke test for the old timeline, with explicit cascade regressions tested separately.

### Why can the runtime keep the all-level `+1`?

The runtime and tokio-util wheels look similar, but their cascades are not the same.

The runtime's [`process_expiration`](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio/src/runtime/time/wheel/mod.rs#L223-L260) does not simply use `level - 1`. It takes all entries out of the slot first, then decides each one: expired entries go to `pending`; entries not yet due are assigned a level again:

```rust
match unsafe { item.mark_pending(deadline) } {
    Ok(()) => self.pending.push_front(item),
    Err(expiration_tick) => {
        let level = level_for(expiration.deadline, expiration_tick);
        unsafe { self.levels[level].add_entry(item); }
    }
}
```

The important line is `level_for(expiration.deadline, expiration_tick)`. Its rule guarantees that, for a non-top level, the destination slot is not the slot containing `expiration.deadline`. After the slot is processed, `elapsed` advances to exactly `expiration.deadline`, so the invariant still holds in the runtime. At the merged commit, its level scan is still an all-level `+1`.

tokio-util replaced that step with `level - 1`. The scan policy and the cascade policy are a pair; carrying over the scan without the cascade is what puts entries into a lower-level current slot.

## 5. Three versions, two kinds of failure

Keeping only the merged implementation would hide the reason for the offset. Keeping only the first post's two versions would hide the regression introduced by applying it everywhere. The verification project now keeps all three:

| Module | Scan rule | Role |
|---|---|---|
| `wheel_buggy` | Start at the current slot on every level | Original behavior, before the fix |
| `wheel_fixed` | Add one on every level | The first post's proposed fix; the historical name does not mean it is finally correct |
| `wheel_merged` | Add one only on the top level | The scan rule merged in #8519 |

All three share the same `add_entry`, `poll_expiration`, and `level_for`; the difference is confined to `next_occupied_slot`. Here are the results of `cargo run --release --example followup`. Every timestamp is an absolute number of milliseconds from the wheel's origin:

| Input | No offset | All-level `+1` | Top-level-only `+1` |
|---|---|---|---|
| Top-level pseudo-ring: `elapsed=2`, near=`2^30+1000`, far=`2^36+1` | far@68719476737 → near@69793219560 | near@1073742824 → far@68719476737 | near@1073742824 → far@68719476737 |
| 64 / 65 | a@64 → b@65 | b@65 → a@65 | a@64 → b@65 |
| 4096 / 4160 | a@4096 → b@4160 | b@4160 → a@8192 | a@4096 → b@4160 |

The first row preserves the original finding: without any offset, a wrapped top-level entry can still block a nearer timer and delay it by a full top-level rotation. The other two rows show why the remedy cannot be applied at every level.

The three versions were also exercised in debug mode. The no-offset top-level counterexample and the all-level `+1` 4096/4160 counterexample each hit their assertion; the 64/65 ordering error is visible in both modes.

Two additional checks probe the boundaries:

- When the current top-level slot is the only occupied slot, the merged version still processes it. “Scan last” really does differ from “never scan.”
- The merged version was also checked across cascade boundaries from L1 through L5, rotations `{1, 2, 63, 64, 65}`, and both insertion orders: 50 timelines, all delivered at their deadlines.

Upstream added 10 slot-scan unit tests and the two `DelayQueue` cascade tests from the review. The unit tests cover an empty level, a single slot, the nearest slot forward, skipping the current slot, the current slot as the only occupied one, the last slot, and `next_expiration`'s slot-start and top-level wrap calculations; the two `DelayQueue` tests are the 64/65 and 4096/4160 cases. The three-version experiment here lives in one small project and reproduces the table above.

## 6. The `+1` stayed; its jurisdiction changed

Writing only “the PR merged” would miss what this correction actually changed.

The original counterexample established that starting at the current top-level slot can put a distant timer ahead of a nearby one. It did not establish that starting at the next slot is safe at every level.

The 64/65ms and 4096/4160ms pairs separate those claims. The first lets `b` get ahead of `a` in a lower-level current slot; the second leaves `a` in a slot that has already started, and release pushes it to 8192ms.

The `+1` was not deleted. It ended up where the argument actually supports it: at the top.

Before claiming that a slot is always empty, find every path that can write into it. I found `insert`; I missed the cascade. Two tests measured in tens of milliseconds and a few seconds filled the gap.

The `+1` is still there. It just stands in a narrower place than my first post claimed — and a more accurate one.

## Reproduction and sources

From the repository root:

```sh
cd 时间轮_timing_wheel/wheel_demo
cargo test
cargo test --release
cargo run --example followup
cargo run --release --example followup
```

Verification environment: Rust 1.98.1 on Windows. No twelve-day wait, no additional third-party crate dependencies. See [`wheel_demo/README.md`](wheel_demo/README.md) for the project layout and version mapping.

- [Previous post: The `+1` That Wasn't Supposed to Be There](Timing_Wheels_From_SOSP_1987_to_tokio_EN.md) / [中文版：时间轮的 `+1`，为什么最后只留在顶层](时间轮_续篇_只在顶层加一_中文版.md)
- [#8519: final PR and merge record](https://github.com/tokio-rs/tokio/pull/8519)
- [Darksonn's review: top-level-only offset and the two cascade counterexamples](https://github.com/tokio-rs/tokio/pull/8519#discussion_r4237816039)
- [My correction in the review thread](https://github.com/tokio-rs/tokio/pull/8519#discussion_r4238066023)
- [#8334: the original runtime fix and the pgdog incident](https://github.com/tokio-rs/tokio/pull/8334)
- [Upstream tokio-util slot-scan unit tests](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio-util/src/time/wheel/level.rs#L250-L360)

### Footnote

① Delivery times in this post come from the monotonic driver in `wheel_demo`; debug and release results are recorded separately. The 10 unit tests and two `DelayQueue` tests live at pinned commit `2fb5757`. The project here replaces the storage adapter and drops the in-module tests when extracting the wheel, so its test count does not correspond one-to-one with upstream.

② The runtime's [`next_expiration`](https://github.com/tokio-rs/tokio/blob/2fb5757a97a94b3173f8fdd7b6280423b63da6e6/tokio/src/runtime/time/wheel/level.rs#L52-L89) uses `deadline <= now`; tokio-util uses `deadline < now`. The former relies on non-top current slots being empty; the latter allows a lower-level current slot to expire exactly at `now`. Each comparison matches its own scan policy.
