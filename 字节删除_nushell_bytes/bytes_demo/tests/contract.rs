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

#[test]
fn old_parent_panics_when_the_pattern_is_missing() {
    for (input, pattern) in [
        (&[0xFFu8][..], &[0x00u8][..]),
        (&[0x10, 0x11, 0x12, 0x13], &[0xAA, 0xBB]),
        (&[0x10, 0x11], &[0xAA, 0xBB, 0xCC]),
        (&[], &[0xAA]),
    ] {
        assert!(
            run(old_parent::remove_impl, input, pattern, true, false).is_err(),
            "old parent should panic for input {input:02X?} and pattern {pattern:02X?}"
        );
    }
}

#[test]
fn old_merge_turns_the_panic_into_lost_prefix_bytes() {
    assert_eq!(
        call(old_merge::remove_impl, &[0x10, 0x11, 0x12, 0x13], &[0xAA, 0xBB], true, false),
        vec![0x11, 0x12, 0x13]
    );
    assert_eq!(
        call(old_merge::remove_impl, &[0x10, 0x11], &[0xAA, 0xBB, 0xCC], true, false),
        Vec::<u8>::new()
    );
    assert_eq!(
        call(old_merge::remove_impl, &[0xFF], &[0x00], true, false),
        vec![0xFF]
    );
}

#[test]
fn first_draft_and_merge_both_keep_the_whole_input() {
    for (input, pattern) in [
        (&[0x10u8, 0x11, 0x12, 0x13][..], &[0xAAu8, 0xBB][..]),
        (&[0x10, 0x11], &[0xAA, 0xBB, 0xCC]),
        (&[], &[0xAA]),
    ] {
        assert_eq!(
            call(first::remove_impl, input, pattern, true, false),
            input.to_vec()
        );
        assert_eq!(
            call(merge::remove_impl, input, pattern, true, false),
            input.to_vec()
        );
    }
}

#[test]
fn exhaustive_small_domain() {
    let alphabet = [0u8, 1u8];
    let inputs = words(&alphabet, 5, 0);
    let patterns = words(&alphabet, 3, 1);
    let mut pairs = 0usize;
    let mut first_vs_merge = 0usize;
    let mut merge_vs_oracle = 0usize;
    let mut old_merge_vs_oracle = 0usize;
    let mut old_merge_vs_merge_parent = 0usize;
    let mut old_parent_panics = 0usize;
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
            let old_value = call(old_merge::remove_impl, input, pattern, true, false);

            if first_value != merged {
                first_vs_merge += 1;
            }
            if merged != expected {
                merge_vs_oracle += 1;
            }
            if old_value != expected {
                old_merge_vs_oracle += 1;
                assert_eq!(
                    input.len().saturating_sub(old_value.len()),
                    input.len().min(pattern.len() - 1)
                );
                loss_formula_ok += 1;
            }
            if parent != old_value {
                old_merge_vs_merge_parent += 1;
            }
            if run(old_parent::remove_impl, input, pattern, true, false).is_err() {
                old_parent_panics += 1;
                if pattern.len() == 1 {
                    single_byte_misses += 1;
                }
                if input.is_empty() && pattern.len() > 1 {
                    empty_input_multi_byte_misses += 1;
                }
            }
        }
    }

    assert_eq!(pairs, 882);
    assert_eq!(first_vs_merge, 0);
    assert_eq!(merge_vs_oracle, 0);
    assert_eq!(old_merge_vs_oracle, 474);
    assert_eq!(old_merge_vs_merge_parent, 0);
    assert_eq!(old_parent_panics, 498);
    assert_eq!(loss_formula_ok, 474);
    assert_eq!(old_parent_panics - old_merge_vs_oracle, 24);
    assert_eq!(single_byte_misses, 12);
    assert_eq!(empty_input_multi_byte_misses, 12);
}

#[test]
fn offset_zero_and_pattern_equal_to_input() {
    assert_eq!(
        call(merge::remove_impl, &[0xAA, 0xBB, 0x10], &[0xAA, 0xBB], true, false),
        vec![0x10]
    );
    assert_eq!(
        call(merge::remove_impl, &[0xAA, 0xBB], &[0xAA, 0xBB], true, false),
        Vec::<u8>::new()
    );
}

#[test]
fn end_removes_the_last_occurrence_not_only_a_suffix() {
    assert_eq!(
        call(merge::remove_impl, &[1, 2, 1, 2, 1], &[1, 2], true, false),
        vec![1, 2, 1]
    );
    assert_eq!(
        call(merge::remove_impl, &[1, 2, 1, 2, 1], &[1, 2, 1], true, false),
        vec![1, 2]
    );
}

#[test]
fn end_all_ignores_end_and_uses_the_forward_branch() {
    let input = [1u8, 2, 1, 2, 1];
    let pattern = [1u8, 2, 1];
    assert_eq!(
        call(merge::remove_impl, &input, &pattern, true, false),
        vec![1, 2]
    );
    assert_eq!(
        call(merge::remove_impl, &input, &pattern, true, true),
        vec![2, 1]
    );
    assert_eq!(
        call(merge::remove_impl, &input, &pattern, true, true),
        oracle_all(&input, &pattern)
    );
}

#[test]
fn empty_pattern_is_outside_this_layer() {
    assert!(std::panic::catch_unwind(|| {
        let _ = call(merge::remove_impl, &[0xAA], &[], true, false);
    })
    .is_err());
}
