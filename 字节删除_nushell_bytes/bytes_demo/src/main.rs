use bytes_demo::extracted::{first, merge, merge_parent, old_merge, old_parent};
use bytes_demo::{call, oracle_all, oracle_end, words, RemoveFn};

fn run(
    remove: RemoveFn,
    input: &[u8],
    pattern: &[u8],
    end: bool,
    all: bool,
) -> Result<Vec<u8>, ()> {
    std::panic::catch_unwind(|| call(remove, input, pattern, end, all)).map_err(|_| ())
}

fn hex(bytes: &[u8]) -> String {
    if bytes.is_empty() {
        "0x[]".to_string()
    } else {
        format!(
            "0x[{}]",
            bytes
                .iter()
                .map(|byte| format!("{byte:02X}"))
                .collect::<Vec<_>>()
                .join(" ")
        )
    }
}

fn main() {
    std::panic::set_hook(Box::new(|_| {}));

    println!(
        "SCOPE=exact extracted remove_impl from five fixed Nushell commits; stand-in Value/Span/Arguments; NOT a Nushell binary"
    );
    println!("PREcondition=nonempty patterns only; the real run() rejects an empty pattern before remove_impl");

    let cases: &[(&str, &[u8], &[u8])] = &[
        ("issue-original", &[0xFF], &[0x00]),
        ("missing-multibyte", &[0x10, 0x11, 0x12, 0x13], &[0xAA, 0xBB]),
        ("pattern-longer-than-input", &[0x10, 0x11], &[0xAA, 0xBB, 0xCC]),
        ("offset-zero", &[0xAA, 0xBB, 0x10], &[0xAA, 0xBB]),
        ("pattern-equals-input", &[0xAA, 0xBB], &[0xAA, 0xBB]),
        ("last-occurrence-not-suffix", &[0x01, 0x02, 0x01, 0x02, 0x01], &[0x01, 0x02]),
        ("overlapping-pattern", &[0x01, 0x02, 0x01, 0x02, 0x01], &[0x01, 0x02, 0x01]),
        ("empty-input", &[], &[0xAA]),
    ];

    for (name, input, pattern) in cases {
        println!(
            "CASE {name} input={} pattern={}",
            hex(input),
            hex(pattern)
        );
        for (label, remove) in [
            ("old-parent", old_parent::remove_impl as RemoveFn),
            ("old-merge", old_merge::remove_impl as RemoveFn),
            ("merge-parent", merge_parent::remove_impl as RemoveFn),
            ("first", first::remove_impl as RemoveFn),
            ("merge", merge::remove_impl as RemoveFn),
        ] {
            match run(remove, input, pattern, true, false) {
                Ok(value) => println!("  {label:<14} {}", hex(&value)),
                Err(_) => println!("  {label:<14} PANIC"),
            }
        }
    }

    let alphabet = [0u8, 1u8];
    let inputs = words(&alphabet, 5, 0);
    let patterns = words(&alphabet, 3, 1);
    let mut pairs = 0usize;
    let mut first_vs_merge = 0usize;
    let mut merge_vs_oracle = 0usize;
    let mut old_merge_vs_oracle = 0usize;
    let mut old_merge_vs_merge_parent = 0usize;
    let mut old_parent_panics = 0usize;
    let mut old_parent_vs_oracle = 0usize;
    let mut loss_formula_ok = 0usize;
    let mut single_byte_misses = 0usize;
    let mut empty_input_multi_byte_misses = 0usize;

    for input in &inputs {
        for pattern in &patterns {
            pairs += 1;
            let expected = oracle_end(input, pattern);
            let merged = call(merge::remove_impl, input, pattern, true, false);
            let first_value = call(first::remove_impl, input, pattern, true, false);
            let parent = call(merge_parent::remove_impl, input, pattern, true, false);

            if first_value != merged {
                first_vs_merge += 1;
            }
            if merged != expected {
                merge_vs_oracle += 1;
            }
            if call(old_merge::remove_impl, input, pattern, true, false) != expected {
                old_merge_vs_oracle += 1;
            }
            if parent != call(old_merge::remove_impl, input, pattern, true, false) {
                old_merge_vs_merge_parent += 1;
            }

            match run(old_parent::remove_impl, input, pattern, true, false) {
                Ok(value) => {
                    if value != expected {
                        old_parent_vs_oracle += 1;
                    }
                }
                Err(_) => {
                    old_parent_panics += 1;
                    old_parent_vs_oracle += 1;
                    if pattern.len() == 1 {
                        single_byte_misses += 1;
                    }
                    if input.is_empty() && pattern.len() > 1 {
                        empty_input_multi_byte_misses += 1;
                    }
                }
            }

            let old_value = call(old_merge::remove_impl, input, pattern, true, false);
            let lost = input.len().saturating_sub(old_value.len());
            let predicted = input.len().min(pattern.len().saturating_sub(1));
            if lost != predicted {
                // Only the not-found path is expected to lose bytes; a found
                // pattern may legitimately remove more than the prefix.
                if old_value == expected {
                    // Found: no formula claim.
                } else {
                    panic!(
                        "loss formula mismatch: input={} pattern={} old={} lost={lost} predicted={predicted}",
                        hex(input),
                        hex(pattern),
                        hex(&old_value)
                    );
                }
            } else if old_value != expected {
                loss_formula_ok += 1;
            }
        }
    }

    println!(
        "SCAN alphabet=[00,01] input_len=0..5 pattern_len=1..3 pairs={pairs}"
    );
    println!("  first_vs_merge_mismatches={first_vs_merge}");
    println!("  merge_vs_oracle_mismatches={merge_vs_oracle}");
    println!("  old_merge_vs_oracle_mismatches={old_merge_vs_oracle}");
    println!("  old_merge_vs_merge_parent_mismatches={old_merge_vs_merge_parent}");
    println!("  old_parent_panics={old_parent_panics}");
    println!("  old_parent_vs_oracle_mismatches={old_parent_vs_oracle}");
    println!("  not_found_loss_matches_min_n_m_minus_1={loss_formula_ok}");
    println!("  old_merge_correct_misses={}", old_parent_panics - old_merge_vs_oracle);
    println!("    single_byte_pattern_misses={single_byte_misses}");
    println!("    empty_input_multi_byte_pattern_misses={empty_input_multi_byte_misses}");

    let input = [0x01u8, 0x02, 0x01, 0x02, 0x01];
    let pattern = [0x01u8, 0x02, 0x01];
    println!(
        "BOUNDARY input={} pattern={}",
        hex(&input),
        hex(&pattern)
    );
    println!(
        "  merge end-only  = {}",
        hex(&call(merge::remove_impl, &input, &pattern, true, false))
    );
    println!(
        "  merge end+all   = {}",
        hex(&call(merge::remove_impl, &input, &pattern, true, true))
    );
    println!(
        "  oracle end+all  = {}",
        hex(&oracle_all(&input, &pattern))
    );
}
