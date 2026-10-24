//! Run in both debug and release mode: cargo run [--release] --example followup
use wheel_demo::followup::{all_levels, merged, original, Trace};

type Simulate = fn(u64, &[(u64, &'static str)]) -> Result<Trace, String>;

fn main() {
    // We report caught assertion failures below instead of printing panic backtraces.
    let previous_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(|_| {}));
    println!("debug_assertions={}", cfg!(debug_assertions));
    let variants: [(&str, Simulate); 3] = [
        ("original", original),
        ("all_levels", all_levels),
        ("merged", merged),
    ];
    let scenarios: [(&str, u64, [(u64, &str); 2]); 3] = [
        (
            "wrapped top slot",
            2,
            [((1 << 30) + 1000, "near"), ((1 << 36) + 1, "far")],
        ),
        ("cascade 64/65", 0, [(64, "a"), (65, "b")]),
        ("cascade 4096/4160", 0, [(4096, "a"), (4160, "b")]),
    ];
    for (scenario, elapsed, entries) in scenarios {
        println!("\n{scenario}");
        for (name, simulate) in variants {
            match simulate(elapsed, &entries) {
                Ok(trace) => println!(
                    "{name:10} first_poll_at={:?}, fired={:?}",
                    trace.first_poll_at, trace.fired
                ),
                Err(error) => println!("{name:10} PANIC: {error}"),
            }
        }
    }
    std::panic::set_hook(previous_hook);
}
