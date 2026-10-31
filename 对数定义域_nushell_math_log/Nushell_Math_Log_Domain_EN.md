# It caught 1 and NaN. ∞ got through.

```nushell
> 2 | math log 1
inf
> 1 | math log 1
NaN
> 2 | math log inf
0.0
```

Three real commands on Nu 0.116.1, and not one of them is an error. The same command with `2 | math log 0` is rejected, and the message says `Base has to be greater 0`. So whether the base is valid is something the command handles; it just does not think 1 and ∞ are invalid.

`math log` computes `f64::log`. By definition `log_b(x) = ln x / ln b`. With base 1, `ln 1 = 0`, the denominator is zero, and the only possible results are ±∞ or the `0 / 0` NaN. With base ∞, `ln ∞ = ∞`, and any finite input divided by it gives 0. All of these print. All of them look like numbers.

On the input side there is one more of the same shape:

```nushell
> NaN | math log 2
NaN
```

## 1. The guard was written as "bad values don't get in"

Before the fix, the base check looked like this ([`log.rs` @ `65a22bf`](https://github.com/nushell/nushell/blob/65a22bfa4512e061ef7142914d032e2ad4a5d2ae/crates/nu-command/src/math/log.rs#L140-L150), the file shipped in 0.116.1):

```rust
fn require_positive_base(base: Spanned<f64>, head: Span) -> Result<f64, ShellError> {
    if base.item <= 0.0f64 {
        return Err(ShellError::UnsupportedInput {
            msg: "Base has to be greater 0".into(),
            ..
        });
    }
    Ok(base.item)
}
```

It reads like a complete check: a bad value is anything `<= 0`. But 1 is positive, +∞ is positive, and both walked straight through the middle of that test. NaN is stranger — **it compares false against everything**, so `NaN <= 0.0` is false and the `if` never sees it. Three things get past: the two positive numbers the test never considered, and the one value it cannot compare at all.

The input side is the same sentence with a different subject:

```rust
if val <= 0.0 {
    return Value::error(
        ShellError::UnsupportedInput { msg: "'math log' undefined for values outside the open interval (0, Inf).".into(), .. },
        span,
    );
}
```

`NaN <= 0.0` is false here as well, so `NaN | math log 2` runs all the way to `val.log(2)` and returns NaN.

The guard's shape is "if bad, then error". That shape assumes every bad value can answer "am I ≤ 0?". NaN answers no to every comparison. It is not a bad number; it is not on the number line.

## 2. The first draft closed the holes it could see

The first commit ([`8af5798`](https://github.com/nushell/nushell/commit/8af57986e3d6c10b451baba5a5199c79b644b0fd)) changed the test and the wording:

```rust
// A logarithm is only defined for a base in the open interval (0, 1) union (1, Inf):
// the base must be positive and not equal to 1. `NaN` is rejected as well, since it
// satisfies neither `> 0` nor `== 1`.
if base.item.is_nan() || base.item <= 0.0f64 || base.item == 1.0f64 {
```

`is_nan()` names NaN, `== 1.0` closes that hole, and the message becomes `Base has to be greater than 0 and not equal to 1`. Six tests came with it: three rejections (base 1, 1.0, and a NaN built as `inf - inf`) and three acceptances (bases 2, 10, e).

`+inf` was still inside the door. `2 | math log inf` returned `0.0`.

## 3. Review stopped at two places in one pass

Eight days later, fdncred's [review](https://github.com/nushell/nushell/pull/19127#pullrequestreview-5470451175) stopped at two places. The inline note was about `+inf`:

> `+inf` still gets through. The comment above says the domain is the open interval `(0, 1) ∪ (1, Inf)`, but this condition accepts `inf`... That is the same silent-garbage result this PR fixes for `1` and `NaN`.

The paragraph in the review body was about the other side — an input check in the same function, outside this diff:

> It's the same class of bug on the input side.

Two different ways of missing. `+inf` is a test written too narrow: `is_nan()` stops only NaN, while the two infinities fare differently in this function — `-inf` is caught by `<= 0`, `+inf` is not. The NaN on the input side is the same shape appearing once more: another "if bad, then error", another value it cannot see.

## 4. The merge completes one side and turns the other around

The base side keeps enumerating, with a single `is_finite()` covering NaN and both infinities ([final `log.rs`](https://github.com/nushell/nushell/blob/73f0a8983aa2f99b1e9e9383c983caf9244fadce/crates/nu-command/src/math/log.rs#L140-L153)):

```rust
if !base.item.is_finite() || base.item <= 0.0f64 || base.item == 1.0f64 {
    return Err(ShellError::UnsupportedInput {
        msg: "Base has to be a finite number greater than 0 and not equal to 1".into(),
        ..
    });
}
```

The input side stops listing bad values and starts requiring a good one:

```rust
// A positive test keeps `NaN` out of the log: `NaN > 0.0` is false, so it
// reaches the error branch instead of silently returning `NaN`.
if val > 0.0 {
    // Specialize for better precision/performance
    let val = if base == 10.0 {
        val.log10()
    } else if base == 2.0 {
        val.log2()
    } else {
        val.log(base)
    };

    Value::float(val, span)
} else {
    Value::error(
        ShellError::UnsupportedInput { msg: "'math log' undefined for values outside the open interval (0, Inf).".into(), .. },
        span,
    )
}
```

**From "bad values don't get in" to "only good values get through"**, and NaN has nowhere to hide: `NaN > 0.0` is false, so it falls into the `else`. The author's reply points out that `math ln`, in the same directory, already does it this way.

On the input side the change does nothing to any point on the axis. `-inf`, `0` and `-1` were rejected before and are rejected now; `0.5`, `2` and `+inf` get the same value on either side. What changed is the one point off the axis, NaN.

![Two axes, for the base and for the input: the cyan intervals are what the merged version lets through, red is rejected by both versions, red rings mark 1 and ∞ stopped by this fix, and NaN, in a grey dashed box, sits on neither axis](assets/fig_domain.png)

The base side could have been written positively as well (`if base.item > 0.0 && base.item != 1.0 && base.item.is_finite()`). The merge kept the enumerate-the-bad shape and only completed the list.

## 5. Infinity stays as an input, not as a base

The merged version is deliberately asymmetric: `inf | math log 2` still returns `inf`, while `2 | math log inf` is an error.

The reason is mathematical. As the input grows without bound, `log₂` grows with it, and `inf` is that limit; with an infinite base the function collapses to the constant 0, and no input carries any information. The author's [reply](https://github.com/nushell/nushell/pull/19127#discussion_r4235789344) says it plainly: `inf | math log 2` is still `inf`, "which is the correct limit", so the PR was retitled "reject invalid bases and a NaN input value" rather than claiming that every non-finite input is rejected.

## 6. Three more things in the tests

The first draft had an exact-float assertion: `16 | math log 2.718281828459045` should equal `2.772588722239781`. On this machine it does — bit for bit, `0x40062e42fefa39ef`. But neither side is an arbitrary number: the denominator is `ln(2.718281828459045)`, a value rounded to 1 rather than exactly 1, and Rust's own documentation for [`f64::log`](https://doc.rust-lang.org/std/primitive.f64.html#method.log) says the precision "varies by platform, Rust version, and can even differ within the same execution from one invocation to the next".

Move the denominator one ulp below 1, to `0.9999999999999999`, and the same expression gives `2.7725887222397816`; the assertion flips on the spot. That is not a claim that some platform really gets it wrong — it says the assertion bets correctness on the last bit of libm. The review's alternative was bases with exact results: `16 | math log 4` gives `2.0`, `8 | math log 0.5` gives `-3.0`.

The second thing is coverage: every test in the first draft sat in the `b > 1` half, and the `(0, 1)` half — the other half the PR itself calls valid — was never run.

The third is duplication: `16 | math log 2` is already covered by `const_log`; `100 | math log 10` is the first entry in `examples()`, which `test_examples` executes; and `NaN` is a literal in nushell, so no `inf - inf` is needed to produce one.

The merged tests fold the first two groups into `#[rstest]`: seven invalid bases (`1`, `1.0`, `0`, `-2`, `NaN`, `inf`, `-inf`), four valid bases (`2`, `10`, `4`, `0.5`), one NaN input, and the three original cases — 15 in all.

## 7. Three versions, one matrix

The reproduction lives in `math_log_demo/`: `build.rs` takes `require_*` and `operate` out of three fixed `log.rs` files by brace matching, and compiles them against minimal stand-ins for `Value`, `Span`, `Spanned` and `ShellError`. The algorithm and the checks are not retyped by hand; the only change is visibility.

The three versions are the parent `65a22bf` (byte-identical to the same file in 0.116.1), the first draft `8af5798`, and the merge `73f0a89`. Twelve bases times twelve inputs, 144 pairs:

| Version | Answered outside the domain | of which NaN or ±inf | Rejected inside the domain |
| --- | --- | --- | --- |
| Parent | 29 | 23 | 0 |
| First draft | 13 | 7 | 0 |
| Merge | 0 | 0 | 0 |

24 of the 29 are bases 1, NaN and ∞ against every input; the other five are five valid bases with a NaN input. The first draft cleared the sixteen pairs from base 1 and NaN. Of the 13 left, eight come from `b = ∞` and five from a NaN input.

The 35 pairs both versions answer (5 valid bases × 7 valid inputs) are identical bit for bit, 35 of 35. The fix did not touch ordinary arithmetic.

The same harness was then pointed at the official 0.116.1 binary: ten commands, and every output matched the extracted parent version, including `inf` from `2 | math log 1` and `0.0` from `2 | math log inf`.

The scope should be clear. This runs extracted functions, not a Nushell build: no parser, no pipeline, no const evaluation. `run_const` calls the same `require_*`, but the demo does not run it. The floating-point part ran only on this Windows machine; other platforms' libm were not tested. As for which release carries the fix: the merge is dated 2026-10-10, 0.116.1 shipped on 2026-10-04, and as of 2026-10-31 the newest tag in the repository is still 0.116.1.

One footnote: the parent of this merge is exactly the merge commit of the bytes-remove fix in the same repository. The two merges are 46 seconds apart.

## 8. Two ways to miss

`1` and `∞` are a test written too narrowly: `<= 0` defines "bad" too small, and adding conditions completes it. NaN is a test pointing the wrong way: it assumes every value can answer "am I bad?", and NaN says no to every comparison. The first is fixed with `== 1.0` and `is_finite()`. The second needs the sentence turned around — say what a good value looks like first.

Turning it around pays forward too: the next strange float value will land in the `else` as well, instead of slipping through some `<=`.

The [offline reproduction project](math_log_demo/) keeps the fixed `log.rs` of the parent, the first draft and the merge, extracts `require_*` and `operate` at build time, and ships the upstream MIT licence, source SHAs and hashes; commands, numbers and scope are in the [project README](math_log_demo/README.md). It compiles the extracted functions directly, needs no full Nushell, and runs offline.

The final implementation discussed here was [merged with #19127](https://github.com/nushell/nushell/commit/73f0a8983aa2f99b1e9e9383c983caf9244fadce).
