use math_log_demo::{
    accepted_outside_domain, agreement, evaluate, evaluate_int, evaluate_text,
    rejected_inside_domain, Outcome, Revision, E_LITERAL, OLD_TEST_EXPECTED,
};

fn main() {
    println!(
        "SCOPE=exact extracted require_* and operate from three fixed Nushell commits; stand-in Value/Span/Spanned/ShellError; NOT a Nushell build"
    );

    let cases: &[(&str, f64, f64)] = &[
        ("base_one", 1.0, 2.0),
        ("base_one_input_one", 1.0, 1.0),
        ("base_infinite", f64::INFINITY, 2.0),
        ("base_infinite_input_infinite", f64::INFINITY, f64::INFINITY),
        ("nan_input", 2.0, f64::NAN),
        ("infinite_input_kept", 2.0, f64::INFINITY),
        ("base_in_open_unit_interval", 0.5, 8.0),
        ("negative_input", 2.0, -1.0),
    ];

    for (label, base, input) in cases {
        println!("CASE {label} input={input:?} base={base:?}");
        for revision in Revision::ALL {
            println!(
                "  {:<6} : {}",
                revision.label(),
                evaluate(revision, *input, *base).describe()
            );
        }
    }

    println!("CASE int_input input=16 base=4");
    for revision in Revision::ALL {
        println!(
            "  {:<6} : {}",
            revision.label(),
            evaluate_int(revision, 16, 4.0).describe()
        );
    }

    println!("CASE text_input input=\"16\" base=4");
    for revision in Revision::ALL {
        println!(
            "  {:<6} : {}",
            revision.label(),
            evaluate_text(revision, "16", 4.0).describe()
        );
    }

    println!(
        "MATRIX pairs={} bases={} inputs={}",
        math_log_demo::BASES.len() * math_log_demo::INPUTS.len(),
        math_log_demo::BASES.len(),
        math_log_demo::INPUTS.len()
    );
    println!("DOMAIN base=finite and >0 and !=1 value=>0 (NaN rejected, +inf kept)");

    for revision in Revision::ALL {
        let outside = accepted_outside_domain(revision);
        let inside = rejected_inside_domain(revision);
        let non_finite = outside
            .iter()
            .filter(|row| matches!(row.outcome, Outcome::Value(value) if !value.is_finite()))
            .count();
        println!(
            "COUNT {:<6} accepted_outside_domain={} rejected_inside_domain={} non_finite_answers={}",
            revision.label(),
            outside.len(),
            inside.len(),
            non_finite
        );
    }

    let (both, identical) = agreement(Revision::Parent, Revision::Merge);
    println!("AGREEMENT parent_vs_merge accepted_by_both={both} bit_identical={identical}");

    let computed = 16f64.log(E_LITERAL);
    println!(
        "OLD_TEST 16 | math log 2.718281828459045 value={computed:?} bits={:016x} expected={OLD_TEST_EXPECTED:?} bits={:016x} equal={}",
        computed.to_bits(),
        OLD_TEST_EXPECTED.to_bits(),
        computed == OLD_TEST_EXPECTED
    );

    let one_ulp_below_one = f64::from_bits(1.0f64.to_bits() - 1);
    let shifted = 16f64.ln() / one_ulp_below_one;
    println!(
        "OLD_TEST_SENSITIVITY denominator=1-1ulp ({one_ulp_below_one:?}) quotient={shifted:?} bits={:016x} equal_to_expected={}",
        shifted.to_bits(),
        shifted == OLD_TEST_EXPECTED
    );
}
