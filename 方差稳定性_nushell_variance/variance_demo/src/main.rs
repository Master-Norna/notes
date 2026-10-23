//! Reproduction harness for nushell #19108 (`math variance` numerical stability).
//!
//! Every variant below is a direct transcription of an actual implementation
//! shape: `naive` is the pre-#19108 `sum_of_squares` path (f64 arithmetic, same
//! operation order), `shifted` is the merged fix, and the rest are the
//! alternatives that were considered in the PR thread.
//!
//! Run with `cargo run --release`; it prints the tables used in the write-up and
//! writes `out/curve.csv` / `out/constants.csv` for `plot_fig1.py`.

use std::fs;
use std::hint::black_box;
use std::time::Instant;

/// Pre-#19108: `SS = Σx² − (Σx)²/n`, then `SS / n`.
fn naive(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    let mut sum_x = 0.0f64;
    let mut sum_x2 = 0.0f64;
    for &x in xs {
        let v2 = x * x;
        sum_x2 += v2;
        sum_x += x;
    }
    let sum_x_squared = sum_x * sum_x;
    let ss = sum_x2 - sum_x_squared / n;
    ss / n
}

/// Plain two-pass: mean first, then `Σ(x − mean)² / n`.
fn two_pass_plain(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    let sum: f64 = xs.iter().sum();
    let mean = sum / n;
    let ss: f64 = xs.iter().map(|&x| (x - mean) * (x - mean)).sum();
    ss / n
}

/// Mean as `Σ(x / n)`, then two-pass.
fn mean_div_n(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    let mean: f64 = xs.iter().map(|&x| x / n).sum();
    let ss: f64 = xs.iter().map(|&x| (x - mean) * (x - mean)).sum();
    ss / n
}

/// Björck's corrected two-pass: `ss − (Σd)²/n`.
fn corrected_two_pass(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    let sum: f64 = xs.iter().sum();
    let mean = sum / n;
    let mut ss = 0.0f64;
    let mut sum_d = 0.0f64;
    for &x in xs {
        let d = x - mean;
        ss += d * d;
        sum_d += d;
    }
    (ss - sum_d * sum_d / n) / n
}

/// Welford's online update.
fn welford(xs: &[f64]) -> f64 {
    let mut mean = 0.0f64;
    let mut m2 = 0.0f64;
    let mut count = 0.0f64;
    for &x in xs {
        count += 1.0;
        let delta = x - mean;
        mean += delta / count;
        let delta2 = x - mean;
        m2 += delta * delta2;
    }
    m2 / count
}

/// The merged #19108 fix: `r = x − min`, `m = Σr/n`, `Σ(r − m)² / n`.
fn shifted(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    let origin = xs.iter().copied().fold(f64::INFINITY, f64::min);
    let mean: f64 = xs.iter().map(|&x| x - origin).sum::<f64>() / n;
    let ss: f64 = xs.iter().map(|&x| ((x - origin) - mean).powi(2)).sum();
    ss / n
}

struct Case {
    name: &'static str,
    xs: Vec<f64>,
    expected: f64,
    note: &'static str,
}

fn cases() -> Vec<Case> {
    vec![
        Case {
            name: "float_pair",
            xs: vec![506_250_000.0, 506_250_001.0],
            expected: 0.25,
            note: "the PR's opening repro; old path returned -32.0",
        },
        Case {
            name: "int_triple",
            xs: vec![1_000_000_000.0, 1_000_000_001.0, 1_000_000_002.0],
            expected: 2.0 / 3.0,
            note: "old path returned 0.0",
        },
        Case {
            name: "const_1e150_x64",
            xs: vec![1e150; 64],
            expected: 0.0,
            note: "plain two-pass regresses here; shifted is exactly 0",
        },
        Case {
            name: "const_0p3_x10",
            xs: vec![0.3; 10],
            expected: 0.0,
            note: "same regression, ordinary magnitude",
        },
        Case {
            name: "const_2p62_x7",
            xs: vec![4.611686018427388e18; 7],
            expected: 0.0,
            note: "constant sequence at 2^62, n=7",
        },
        Case {
            name: "huge_equal",
            xs: vec![1e308, 1e308],
            expected: 0.0,
            note: "naive: inf − inf = NaN; plain two-pass mean overflows to inf",
        },
        Case {
            name: "just_above_2p52",
            xs: vec![4_503_599_627_370_496.0, 4_503_599_627_370_497.0],
            expected: 0.25,
            note: "shifted (and corrected two-pass) get this exact",
        },
        Case {
            name: "above_2p53",
            xs: vec![9_007_199_254_740_993.0, 9_007_199_254_740_994.0],
            expected: 1.0,
            note: "as f64: 2^53 and 2^53+2; true value of the ints is 0.25",
        },
        Case {
            name: "over_i64_square",
            xs: vec![4_000_000_000.0, 4_000_000_001.0],
            expected: 0.25,
            note: "old int path raised OperatorOverflow",
        },
        Case {
            name: "spread_overflows",
            xs: vec![1e300, 1e300 + 1e285],
            expected: f64::INFINITY,
            note: "true variance ≈ 2.5e569 does not fit in f64",
        },
        Case {
            name: "neg_huge",
            xs: vec![-1e308, 1e308, 1e308, 1e308],
            expected: f64::NAN,
            note: "true variance ≈ 7.5e615 does not fit in f64; NaN/inf both acceptable",
        },
    ]
}

fn fmt(x: f64) -> String {
    if x.is_nan() {
        "NaN".to_string()
    } else if x.is_infinite() {
        if x.is_sign_negative() {
            "-inf".into()
        } else {
            "inf".into()
        }
    } else if x == 0.0 {
        if x.is_sign_negative() {
            "-0".into()
        } else {
            "0".into()
        }
    } else if x.abs() >= 1e-4 && x.abs() < 1e16 {
        format!("{x}")
    } else {
        format!("{x:.3e}")
    }
}

fn table() {
    println!("## Cases (population variance, n as denominator)\n");
    println!("| case | expected | naive | 2-pass | Σ(x/n) | corrected | Welford | shifted |");
    println!("|---|---|---|---|---|---|---|---|");
    for c in cases() {
        println!(
            "| `{}` | {} | {} | {} | {} | {} | {} | {} |",
            c.name,
            fmt(c.expected),
            fmt(naive(&c.xs)),
            fmt(two_pass_plain(&c.xs)),
            fmt(mean_div_n(&c.xs)),
            fmt(corrected_two_pass(&c.xs)),
            fmt(welford(&c.xs)),
            fmt(shifted(&c.xs)),
        );
    }
    println!();
    for c in cases() {
        println!("- `{}`: {}", c.name, c.note);
    }
    println!();
}

/// Grid of two-point samples: for each binary exponent k, 64 mantissas
/// m = 1 + j/64, a = m * 2^k, sample [a, a+1], true variance 0.25.
fn grid() -> Vec<(u32, f64, f64, f64, bool)> {
    let mut rows = Vec::new();
    for k in 10..=52u32 {
        let mut errs = Vec::new();
        let mut any_negative = false;
        let mut max_err: f64 = 0.0;
        let mut shift_err: f64 = 0.0;
        for j in 0..64 {
            let m = 1.0 + (j as f64) / 64.0;
            let a = m * 2f64.powi(k as i32);
            let xs = [a, a + 1.0];
            if xs[0] == xs[1] {
                continue;
            }
            let nv = naive(&xs);
            let sv = shifted(&xs);
            if nv < 0.0 {
                any_negative = true;
            }
            let e = ((nv - 0.25) / 0.25).abs();
            let es = ((sv - 0.25) / 0.25).abs();
            errs.push(e);
            if e > max_err {
                max_err = e;
            }
            if es > shift_err {
                shift_err = es;
            }
        }
        errs.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let median = errs[errs.len() / 2];
        rows.push((k, median, max_err, shift_err, any_negative));
    }
    rows
}

fn sweep() {
    println!("## Sweep: [a, a+1] over 64 mantissas per exponent, true variance 0.25\n");
    println!(
        "k,median_rel_err_naive,max_rel_err_naive,max_rel_err_shifted,any_negative,median_digits"
    );
    let mut negative_ks = Vec::new();
    let mut first_below_one_digit = None;
    for &(k, med, max, shift_max, neg) in &grid() {
        let digits = if med == 0.0 {
            f64::INFINITY
        } else {
            -med.log10()
        };
        if neg {
            negative_ks.push(k);
        }
        if first_below_one_digit.is_none() && med > 1.0 {
            first_below_one_digit = Some(k);
        }
        println!(
            "{k},{med:.6e},{max:.6e},{shift_max:.6e},{},{digits:.2}",
            if neg { 1 } else { 0 }
        );
    }
    println!();
    println!("negative variance appears at exponents: {:?}", negative_ks);
    println!(
        "median naive error passes 100% at k = {:?} (a ≈ 2^{})",
        first_below_one_digit,
        first_below_one_digit.unwrap_or(0)
    );
    println!();
}

fn digits() {
    println!("## Selected offsets, [a, a+1], true variance 0.25\n");
    println!("a,naive,rel_err,digits,shifted");
    for a in [
        16_777_216.0,
        67_108_864.0,
        268_435_456.0,
        506_250_000.0,
        4_294_967_296.0,
        1.099_511_627_776e12,
        2.814_749_767_106_56e14,
        4_503_599_627_370_496.0,
    ] {
        let xs = [a, a + 1.0];
        let nv = naive(&xs);
        let re = ((nv - 0.25) / 0.25).abs();
        let d = if re == 0.0 {
            f64::INFINITY
        } else {
            -re.log10()
        };
        println!("{a:.0},{nv:.3e},{re:.3e},{d:.2},{:.3e}", shifted(&xs));
    }
    println!();
}

fn timing() {
    let n = 10_000_000usize;
    let xs: Vec<f64> = (0..n).map(|i| 5.0625e8 + (i % 1000) as f64).collect();
    let reps = 20;
    let t0 = Instant::now();
    for _ in 0..reps {
        black_box(naive(black_box(&xs)));
    }
    let naive_t = t0.elapsed().as_secs_f64() / reps as f64;
    let t1 = Instant::now();
    for _ in 0..reps {
        black_box(shifted(black_box(&xs)));
    }
    let shifted_t = t1.elapsed().as_secs_f64() / reps as f64;
    println!("## Cost (10M f64, release, mean of {reps} runs)\n");
    println!(
        "naive: {:.2} ms; shifted two-pass: {:.2} ms",
        naive_t * 1e3,
        shifted_t * 1e3
    );
    println!();
}

fn headline() {
    println!("## The three commands from the bug report\n");
    let xs = vec![506_250_000.0, 506_250_001.0];
    println!(
        "[506250000.0 506250001.0] | math variance  =>  naive {}, shifted {}",
        fmt(naive(&xs)),
        fmt(shifted(&xs))
    );
    println!(
        "                          | math stddev    =>  naive {}, shifted {}",
        fmt(naive(&xs).sqrt()),
        fmt(shifted(&xs).sqrt())
    );
    let xs = vec![1_000_000_000.0, 1_000_000_001.0, 1_000_000_002.0];
    println!(
        "[1000000000 1000000001 1000000002] | math variance => naive {}, shifted {}",
        fmt(naive(&xs)),
        fmt(shifted(&xs))
    );
    println!();
}

/// CSV for the figure: 64 values a..a+63, a = 10^t * (1 + j/16), true variance
/// 341.25, plus the constant-sequence cases.
/// Decade scan used in section 4: (t, [(a, naive, shifted)]), 64 values a..a+63.
fn curve_samples() -> Vec<(u32, Vec<(f64, f64, f64)>)> {
    let mut out = Vec::new();
    for t in 0..=15u32 {
        let base = 10f64.powi(t as i32);
        let mut samples = Vec::new();
        for j in 0..16 {
            let a = base * (1.0 + j as f64 / 16.0);
            let xs: Vec<f64> = (0..64).map(|i| a + i as f64).collect();
            if xs[0] == xs[63] {
                continue;
            }
            samples.push((a, naive(&xs), shifted(&xs)));
        }
        out.push((t, samples));
    }
    out
}

fn curve_table() {
    println!("## Decade scan: 64 values a..a+63, true variance 341.25\n");
    println!("t,median_rel_err_naive,exact,zero,negative,max_rel_err_naive");
    let truth = 341.25f64;
    for (t, samples) in curve_samples() {
        let mut errs: Vec<f64> = samples
            .iter()
            .map(|&(_, vn, _)| ((vn - truth) / truth).abs())
            .collect();
        errs.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let n = errs.len();
        let median = if n % 2 == 0 {
            (errs[n / 2 - 1] + errs[n / 2]) / 2.0
        } else {
            errs[n / 2]
        };
        let exact = samples.iter().filter(|&&(_, vn, _)| vn == truth).count();
        let zero = samples.iter().filter(|&&(_, vn, _)| vn == 0.0).count();
        let negative = samples.iter().filter(|&&(_, vn, _)| vn < 0.0).count();
        let max = errs.last().copied().unwrap_or(0.0);
        println!("{t},{median:.6e},{exact},{zero},{negative},{max:.6e}");
    }
    println!();
}

fn emit_csv() {
    fs::create_dir_all("out").unwrap();

    let truth = 341.25f64;
    let mut s = String::from("t,a,naive,shifted,rel_naive,rel_shifted,negative\n");
    for (t, samples) in curve_samples() {
        for (a, vn, vs) in samples {
            s.push_str(&format!(
                "{t},{a:.17e},{vn:.17e},{vs:.17e},{:.6e},{:.6e},{}\n",
                ((vn - truth) / truth).abs(),
                ((vs - truth) / truth).abs(),
                if vn < 0.0 { 1 } else { 0 }
            ));
        }
    }
    fs::write("out/curve.csv", s).unwrap();

    let constants = [
        ("const_1e150_x64", vec![1e150; 64]),
        ("const_0p3_x10", vec![0.3; 10]),
        ("const_2p62_x7", vec![4.611686018427388e18; 7]),
    ];
    let mut c = String::from("case,variant,value\n");
    for (name, xs) in constants {
        for (variant, v) in [
            ("naive", naive(&xs)),
            ("two_pass", two_pass_plain(&xs)),
            ("mean_div_n", mean_div_n(&xs)),
            ("shifted", shifted(&xs)),
        ] {
            c.push_str(&format!("{name},{variant},{v:.17e}\n"));
        }
    }
    fs::write("out/constants.csv", c).unwrap();
    println!("wrote out/curve.csv and out/constants.csv");
}

fn main() {
    headline();
    table();
    sweep();
    digits();
    timing();
    curve_table();
    emit_csv();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merged_fix_pins_the_regression_cases() {
        // Every expectation here is a documented case from nushell #19108.
        assert_eq!(shifted(&[506_250_000.0, 506_250_001.0]), 0.25);
        assert_eq!(
            shifted(&[1_000_000_000.0, 1_000_000_001.0, 1_000_000_002.0]),
            2.0 / 3.0
        );
        assert_eq!(shifted(&[1e308, 1e308]), 0.0);
        assert_eq!(shifted(&vec![1e150; 64]), 0.0);
        assert_eq!(shifted(&vec![0.3; 10]), 0.0);
        assert_eq!(shifted(&vec![4.611686018427388e18; 7]), 0.0);
        assert_eq!(
            shifted(&[4_503_599_627_370_496.0, 4_503_599_627_370_497.0]),
            0.25
        );
        assert_eq!(
            shifted(&[9_007_199_254_740_993.0, 9_007_199_254_740_994.0]),
            1.0
        );
        assert_eq!(shifted(&[4_000_000_000.0, 4_000_000_001.0]), 0.25);
        // The old formula is wrong on the same inputs; these assertions are the
        // "before" side of the before/after.
        assert_eq!(naive(&[506_250_000.0, 506_250_001.0]), -32.0);
        assert!(naive(&[506_250_000.0, 506_250_001.0]).sqrt().is_nan());
        assert_eq!(
            naive(&[1_000_000_000.0, 1_000_000_001.0, 1_000_000_002.0]),
            0.0
        );
    }

    #[test]
    fn shift_is_exact_for_every_offset_in_the_grid() {
        for k in 10..=52 {
            for j in 0..64 {
                let a = (1.0 + j as f64 / 64.0) * 2f64.powi(k);
                assert_eq!(shifted(&[a, a + 1.0]), 0.25, "k={k} j={j}");
            }
        }
    }

    #[test]
    fn welford_depends_on_order_and_plain_two_pass_misses_2p52() {
        let xs = [4_503_599_627_370_496.0, 4_503_599_627_370_497.0];
        assert_eq!(welford(&xs), 0.5);
        assert_eq!(welford(&[xs[1], xs[0]]), 0.0);
        assert_eq!(two_pass_plain(&xs), 0.5);
        assert_eq!(shifted(&xs), 0.25);
    }

    #[test]
    fn plain_two_pass_breaks_constant_sequences() {
        assert_eq!(naive(&vec![1e150; 64]), 0.0);
        assert!(two_pass_plain(&vec![1e150; 64]) != 0.0);
        assert_eq!(shifted(&vec![1e150; 64]), 0.0);
    }

    #[test]
    fn negative_variance_is_reachable() {
        assert!(naive(&[506_250_000.0, 506_250_001.0]) < 0.0);
    }

    #[test]
    fn shift_does_not_stop_square_overflow() {
        // True variance 9.9e307 fits in f64, but the largest squared
        // deviation is (9.9e154)^2 = 9.8e309, which does not.
        let mut xs = vec![0.0f64; 99];
        xs.push(1e155);
        assert_eq!(shifted(&xs), f64::INFINITY);

        // Same shape scaled down to 0..1, then scaled back by (1e155)^2.
        let mut unit = vec![0.0f64; 99];
        unit.push(1.0);
        let true_var = shifted(&unit) * 1e155 * 1e155;
        assert!(true_var.is_finite());
        assert!(
            (true_var / 9.9e307 - 1.0).abs() < 1e-12,
            "true={true_var:e}"
        );
    }

    #[test]
    fn shift_is_not_fully_order_independent() {
        let a = shifted(&[0.0, 1e16, 1.0, 1.0]);
        let b = shifted(&[0.0, 1.0, 1.0, 1e16]);
        assert!(a != b);
        assert!(((a - b) / b).abs() < 1e-15, "a={a:e} b={b:e}");
    }
}
