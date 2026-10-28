# How ssthresh Became 0.49: The Second Cut in Quinn's CUBIC Persistent Congestion

The pre-event window is 9600 bytes (8 × 1200, the initial value in the upstream regression test), and one persistent congestion event lands on CUBIC. Per the RFC, after the event `cwnd` is pressed to the minimum window of 2400 bytes and `ssthresh` = 0.7 × pre-event window = 6720 bytes ([RFC 9438 §4.8](https://www.rfc-editor.org/rfc/rfc9438.html#section-4.8)).

Before the fix, quinn left `ssthresh` at 4704. And 4704 = 0.49 × 9600: **β_cubic got multiplied a second time**. Both versions move `cwnd` the same way; the whole difference sits at this one boundary. It is the line between slow start's doubling and congestion avoidance's step-by-step growth ([§4.6](https://www.rfc-editor.org/rfc/rfc9438.html#section-4.6)). Make it lower and the road back for the window gets longer: in the reproduction, 2 RTTs become 12, and at a smaller window 1 becomes 6.

[#2903](https://github.com/quinn-rs/quinn/pull/2903) (merged September 30, commit [`2a9f45e`](https://github.com/quinn-rs/quinn/commit/2a9f45e47899608ba8875260969667144fb9ef6c)) deletes exactly that extra multiplication and adds a regression test; one file touched. The next section goes straight to [the post-fix source](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs#L185-L237) and shows where each of the two cuts lands.

## 1. Where the Two Cuts Land

The post-fix code first ([pinned source](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs#L185-L237)), the part of `on_congestion_event` this piece is about:

```rust
let window = self.state.window as f64;   // snapshot of the pre-event window

// …fast convergence refreshes w_max first (RFC 9438 §4.7)…

// Common path: one β_cubic cut (RFC 9438 §4.6)
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

The common path runs for every congestion event: `ssthresh = 0.7 × pre-event window`, with `window` pulled to the same value. The persistent congestion branch does only the extras — reset the recovery state, pin `w_max` to the current window, zero out the congestion-avoidance credit, and press `window` to the minimum window (`2 × 1200` bytes).

Before the fix, that branch carried five more lines:

```rust
// 4.7 Timeout - reduce ssthresh based on BETA_CUBIC
self.state.ssthresh = cmp::max(
    (self.state.window as f64 * BETA_CUBIC) as u64,
    self.minimum_window(),
);
```

Walk it once with a pre-event window of 9600 bytes:

| Step | Value read by the second cut | ssthresh, pre-fix | ssthresh, post-fix | window |
|---|---|---:|---:|---:|
| Before the event | — | 9600 | 9600 | 9600 |
| Common path | — | 6720 | 6720 | 6720 |
| Persistent branch | 6720 (already cut) | **4704** | 6720 (untouched) | 2400 |

The pre-event state is identical in both versions; the fork happens entirely inside the persistent branch: same formula, but the value being multiplied is 6720 instead of 9600.

## 2. The Spec Calls for One Cut

Persistent congestion is a QUIC notion ([RFC 9002 §7.6](https://www.rfc-editor.org/rfc/rfc9002.html#section-7.6)): losses persisting beyond `(smoothed_rtt + max(4×rttvar, timer granularity) + max_ack_delay) × kThreshold` trigger it, and quinn's `kThreshold` defaults to 3, so this path usually means the loss lasted roughly three PTOs — heavier than a scatter of lost packets.

CUBIC handles it through the timeout path. [RFC 9438 §4.8](https://www.rfc-editor.org/rfc/rfc9438.html#section-4.8), verbatim:

> In the case of a timeout, CUBIC follows Reno to reduce *cwnd* but sets *ssthresh* using β_cubic (same as in Section 4.6) in a way that is different from Reno TCP.

And the cut §4.6 describes is anchored to the pre-event flight window: `ssthresh = flight_size × β_cubic`. Read together, the two sections say one thing: after a timeout, `ssthresh` is **once** the 0.7 of the pre-event window, no second cut.

The old code's comment said `4.7 Timeout` — that is not a typo. In the older RFC 8312, Timeout *was* [§4.7](https://www.rfc-editor.org/rfc/rfc8312.html#section-4.7), with "sets ssthresh using beta_cubic (same as in Section 4.5)" — the same statement as RFC 9438's. The clause has always meant "post-event `ssthresh` is 0.7 of the pre-event window". The code turned that into an **extra step** inside the persistent branch, by which point the base being multiplied was already the value the common path had cut.

## 3. NewReno Never Had This

quinn's other controller, `NewReno`, has a full twin of the branch ([new_reno.rs](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/new_reno.rs#L85-L105)):

```rust
self.window = (self.window as f32 * self.config.loss_reduction_factor) as u64;
self.window = self.window.max(self.minimum_window());
self.ssthresh = self.window;

if is_persistent_congestion {
    self.window = self.minimum_window();
}
```

`ssthresh` is assigned exactly once; the persistent branch touches only `window`. CUBIC's path carries the extra curve parameters, the branch is longer, and the five lines landed there.

## 4. How Heavy Is 0.49

`ssthresh` is the boundary between slow start and congestion avoidance. At the end of a persistent congestion event the recovery state is cleared, so the sender re-enters slow start from the minimum window, doubling until `ssthresh`, then takes over with CUBIC's cubic growth. A 30%-lower `ssthresh` shortens slow start and lengthens the climb back.

The `cubic_demo` in this repo is a minimal port of exactly this path; both versions run the same script: pre-event window 9600 bytes, rtt 100ms, one persistent congestion event, then each RTT sends the whole current window and it is all acknowledged, until the window is back to its pre-event size. Both versions start from 2400B (the minimum window) after the event:

| Event-after RTT | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| post-fix | 4800 | **9600** | 9600 | 9600 | 9600 | 9600 | 9600 | 9600 | 9600 | 9600 | 9600 | 9600 |
| pre-fix | 4800 | 4800 | 4800 | 4800 | 4800 | 6000 | 6000 | 7200 | 8400 | 8400 | 8400 | **9600** |

Standard window (9600B pre-event): at RTT 1 both are 4800 — 2400 has not touched either threshold yet, so slow start doubles as usual. At RTT 2 they split: above 6720, the post-fix version keeps doubling and is home at 9600; the pre-fix 4800 has already crossed the 4704 line and slides into congestion avoidance — four more RTTs pinned at 4800, then one 1200-byte cell per RTT (6000, 7200, 8400), back to 9600 only at RTT 12.

Small window: with 4800 bytes pre-event, 0.49 × 4800 = 2352 is already below the minimum window of 2400 and gets clamped; 0.7 × 4800 = 3360 stays above it. Still that same 0.49 — the clamp just holds the pre-fix `ssthresh` at 2400B, a smaller drop, but the post-fix version's first growth is straight back to the pre-event size (1 RTT) while the pre-fix version pushes one cell at a time for 6:

| Event-after RTT | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| post-fix | **4800** | 4800 | 4800 | 4800 | 4800 | 4800 |
| pre-fix | 2400 | 2400 | 2400 | 3600 | 3600 | **4800** |

## 5. The Test Pins the Claim to One Line

The regression test in the PR is short ([cubic.rs](https://github.com/quinn-rs/quinn/blob/2a9f45e47899608ba8875260969667144fb9ef6c/quinn-proto/src/congestion/cubic.rs#L329-L346)):

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

The assertion is exactly Section 2's sentence: after a persistent congestion event, `ssthresh == 0.7 × pre-event window` and `cwnd` is down to the minimum window only. Run the 0.49 version and the first assertion catches it. The PR's verification: `cargo test -p quinn-proto`, all 333 tests pass, clippy and fmt clean.

The `cubic_demo` port keeps the full ordering of the event handling and simplifies three things: time is integral milliseconds, rtt is fixed per call, and the spurious-rollback and MTU-update branches are dropped. Every difference between the two versions is exactly whether those five lines are there:

- [`cubic_demo`](cubic_demo/): `cargo test`, five tests (post-event state in both versions, non-persistent path agreement, clamping, recovery order), passing in debug and release; `cargo run --example recovery` prints the two traces above.

## The Takeaway

This is one of those errors that only exists when a formula is applied in the wrong place: `ssthresh = 0.7 × window` is correct in isolation, and so is the spec clause the comment points at — it simply should not sit after the common-path cut. The spec's "cut once" was implemented as "cut once in the common path, once more in the branch", and the second time it picks up an already-shrunk window.

The upstream fix rewrites nothing — delete five lines, add a test.
