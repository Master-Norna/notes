use math_log_demo::{
    accepted_outside_domain, agreement, base_in_domain, evaluate, evaluate_int, evaluate_text,
    rejected_inside_domain, value_in_domain, Outcome, Revision, E_LITERAL, OLD_TEST_EXPECTED,
};

fn value(outcome: &Outcome) -> f64 {
    match outcome {
        Outcome::Value(value) => *value,
        Outcome::Rejected(message) => panic!("expected a value, got an error: {message}"),
    }
}

fn message(outcome: &Outcome) -> &str {
    match outcome {
        Outcome::Rejected(message) => message,
        Outcome::Value(value) => panic!("expected an error, got the value {value:?}"),
    }
}

#[test]
fn the_domain_is_the_one_the_fix_states() {
    assert!(base_in_domain(2.0) && base_in_domain(0.5) && base_in_domain(3.5));
    assert!(!base_in_domain(1.0));
    assert!(!base_in_domain(0.0));
    assert!(!base_in_domain(-0.0));
    assert!(!base_in_domain(-2.0));
    assert!(!base_in_domain(f64::INFINITY));
    assert!(!base_in_domain(f64::NEG_INFINITY));
    assert!(!base_in_domain(f64::NAN));

    assert!(value_in_domain(0.5) && value_in_domain(f64::INFINITY));
    assert!(!value_in_domain(0.0) && !value_in_domain(-1.0) && !value_in_domain(f64::NAN));
}

#[test]
fn the_parent_answers_outside_its_own_domain() {
    assert_eq!(accepted_outside_domain(Revision::Parent).len(), 29);
    assert_eq!(accepted_outside_domain(Revision::First).len(), 13);
    assert_eq!(accepted_outside_domain(Revision::Merge).len(), 0);
    for revision in Revision::ALL {
        assert!(rejected_inside_domain(revision).is_empty());
    }
}

#[test]
fn base_one_returns_inf_and_nan_on_the_released_code() {
    assert_eq!(value(&evaluate(Revision::Parent, 2.0, 1.0)), f64::INFINITY);
    assert!(value(&evaluate(Revision::Parent, 1.0, 1.0)).is_nan());
    assert_eq!(
        message(&evaluate(Revision::First, 2.0, 1.0)),
        "Base has to be greater than 0 and not equal to 1"
    );
}

#[test]
fn infinite_base_survives_the_first_draft() {
    assert_eq!(value(&evaluate(Revision::First, 2.0, f64::INFINITY)), 0.0);
    assert!(value(&evaluate(Revision::First, f64::INFINITY, f64::INFINITY)).is_nan());
    assert_eq!(
        message(&evaluate(Revision::Merge, 2.0, f64::INFINITY)),
        "Base has to be a finite number greater than 0 and not equal to 1"
    );
}

#[test]
fn nan_input_is_the_same_hole_on_the_value_side() {
    assert!(value(&evaluate(Revision::Parent, f64::NAN, 2.0)).is_nan());
    assert!(value(&evaluate(Revision::First, f64::NAN, 2.0)).is_nan());
    assert_eq!(
        message(&evaluate(Revision::Merge, f64::NAN, 2.0)),
        "'math log' undefined for values outside the open interval (0, Inf)."
    );
}

#[test]
fn an_infinite_value_is_kept_on_purpose() {
    for revision in Revision::ALL {
        assert_eq!(
            value(&evaluate(revision, f64::INFINITY, 2.0)),
            f64::INFINITY
        );
    }
}

#[test]
fn valid_pairs_are_bit_identical_to_the_parent() {
    let (both, identical) = agreement(Revision::Parent, Revision::Merge);
    assert_eq!(both, 35);
    assert_eq!(identical, both);
}

#[test]
fn integer_and_text_inputs_behave_the_same_in_all_three() {
    for revision in Revision::ALL {
        assert_eq!(value(&evaluate_int(revision, 16, 4.0)), 2.0);
        assert_eq!(
            message(&evaluate_text(revision, "16", 4.0)),
            "only supports number input"
        );
    }
    assert_eq!(value(&evaluate(Revision::Parent, 8.0, 0.5)), -3.0);
    assert_eq!(value(&evaluate(Revision::Merge, 8.0, 0.5)), -3.0);
}

#[test]
fn the_parent_matches_the_official_0_116_1_binary() {
    // Captured with `nu -n -c ...` from the official 0.116.1 release, whose
    // `crates/nu-command/src/math/log.rs` hashes the same as `upstream/parent/log.rs`.
    let captured: &[(f64, f64, &str)] = &[
        (1.0, 2.0, "inf"),
        (1.0, 1.0, "NaN"),
        (f64::INFINITY, 2.0, "0.0"),
        (f64::INFINITY, f64::INFINITY, "NaN"),
        (2.0, f64::NAN, "NaN"),
        (2.0, f64::INFINITY, "inf"),
        (0.5, 8.0, "-3.0"),
        (4.0, 16.0, "2.0"),
        (f64::NAN, 2.0, "NaN"),
        (E_LITERAL, 16.0, "2.772588722239781"),
    ];
    for (base, input, expected) in captured {
        let outcome = evaluate(Revision::Parent, *input, *base);
        assert_eq!(
            outcome.describe(),
            expected.to_string(),
            "base {base:?} input {input:?}"
        );
    }
}

#[test]
fn the_removed_exact_float_assertion_depends_on_one_ulp_of_the_denominator() {
    let computed = 16f64.log(E_LITERAL);
    assert_eq!(computed, OLD_TEST_EXPECTED);
    assert_eq!(computed.to_bits(), OLD_TEST_EXPECTED.to_bits());

    let one_ulp_below_one = f64::from_bits(1.0f64.to_bits() - 1);
    let shifted = 16f64.ln() / one_ulp_below_one;
    assert_ne!(shifted, OLD_TEST_EXPECTED);
    assert_ne!(shifted.to_bits(), OLD_TEST_EXPECTED.to_bits());
}
