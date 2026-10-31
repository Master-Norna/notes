//! Minimal stand-ins for the Nushell types used by `require_*` and `operate`.
//!
//! This is deliberately not a Nushell build: there is no parser, pipeline,
//! const evaluation, cell path or command registration here. The upstream
//! function bodies are extracted from the fixed snapshots by `build.rs`.

#[derive(Clone, Copy, Debug)]
pub struct Span;

#[derive(Clone, Debug)]
pub struct Spanned<T> {
    pub item: T,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum Value {
    Int { val: i64, span: Span },
    Float { val: f64, span: Span },
    String { val: String, span: Span },
    Nothing { span: Span },
    Error { error: ShellError, span: Span },
}

impl Value {
    pub fn float(val: f64, span: Span) -> Self {
        Value::Float { val, span }
    }

    pub fn error(error: ShellError, span: Span) -> Self {
        Value::Error { error, span }
    }

    pub fn span(&self) -> Span {
        match self {
            Value::Int { span, .. }
            | Value::Float { span, .. }
            | Value::String { span, .. }
            | Value::Nothing { span }
            | Value::Error { span, .. } => *span,
        }
    }

    pub fn get_type(&self) -> &'static str {
        match self {
            Value::Int { .. } => "int",
            Value::Float { .. } => "float",
            Value::String { .. } => "string",
            Value::Nothing { .. } => "nothing",
            Value::Error { .. } => "error",
        }
    }
}

#[derive(Clone, Debug)]
pub enum ShellError {
    UnsupportedInput {
        msg: String,
        input: String,
        msg_span: Span,
        input_span: Span,
    },
    OnlySupportsThisInputType {
        exp_input_type: String,
        wrong_type: String,
        dst_span: Span,
        src_span: Span,
    },
}

impl ShellError {
    pub fn message(&self) -> &str {
        match self {
            ShellError::UnsupportedInput { msg, .. } => msg,
            ShellError::OnlySupportsThisInputType { .. } => "only supports number input",
        }
    }
}

pub mod math {
    pub mod utils {
        pub const NUMBER_INPUT_TYPES: &str = "int, float";
    }
}

pub mod extracted {
    include!(concat!(env!("OUT_DIR"), "/extracted.rs"));
}

/// The three fixed revisions of `crates/nu-command/src/math/log.rs`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Revision {
    /// `0.116.1` / #19127 parent: `base <= 0` and `val <= 0.0`.
    Parent,
    /// #19127 first draft: base `1` and `NaN` rejected, `inf` and the input side untouched.
    First,
    /// #19127 merged: `!is_finite() || <= 0 || == 1`, and the input tested for positivity.
    Merge,
}

impl Revision {
    pub const ALL: [Revision; 3] = [Revision::Parent, Revision::First, Revision::Merge];

    pub fn label(self) -> &'static str {
        match self {
            Revision::Parent => "parent",
            Revision::First => "first",
            Revision::Merge => "merge",
        }
    }
}

#[derive(Clone, Debug)]
pub enum Outcome {
    /// The command produced a float. NaN and the infinities are values too.
    Value(f64),
    /// The command returned a shell error instead of a value.
    Rejected(String),
}

impl Outcome {
    pub fn describe(&self) -> String {
        match self {
            Outcome::Value(value) => format!("{value:?}"),
            Outcome::Rejected(message) => format!("rejected: {message}"),
        }
    }

    pub fn same_as(&self, other: &Outcome) -> bool {
        match (self, other) {
            (Outcome::Value(left), Outcome::Value(right)) => left.to_bits() == right.to_bits(),
            (Outcome::Rejected(left), Outcome::Rejected(right)) => left == right,
            _ => false,
        }
    }
}

fn finish(
    checked: Result<f64, ShellError>,
    value: Value,
    span: Span,
    operate: fn(Value, Span, f64) -> Value,
) -> Outcome {
    match checked {
        Err(error) => Outcome::Rejected(error.message().to_string()),
        Ok(base) => match operate(value, span, base) {
            Value::Float { val, .. } => Outcome::Value(val),
            Value::Int { val, .. } => Outcome::Value(val as f64),
            Value::Error { error, .. } => Outcome::Rejected(error.message().to_string()),
            other => Outcome::Rejected(format!("operate returned a {}", other.get_type())),
        },
    }
}

/// Run one revision on a float input, the way `run()` does: validate the base
/// first, then hand the value to `operate`.
pub fn evaluate(revision: Revision, input: f64, base: f64) -> Outcome {
    let span = Span;
    let value = Value::Float { val: input, span };
    match revision {
        Revision::Parent => finish(
            extracted::parent::require_positive_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::parent::operate,
        ),
        Revision::First => finish(
            extracted::first::require_positive_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::first::operate,
        ),
        Revision::Merge => finish(
            extracted::merge::require_valid_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::merge::operate,
        ),
    }
}

/// Same, for an integer input (the command converts ints with `val as f64`).
pub fn evaluate_int(revision: Revision, input: i64, base: f64) -> Outcome {
    let span = Span;
    let value = Value::Int { val: input, span };
    match revision {
        Revision::Parent => finish(
            extracted::parent::require_positive_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::parent::operate,
        ),
        Revision::First => finish(
            extracted::first::require_positive_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::first::operate,
        ),
        Revision::Merge => finish(
            extracted::merge::require_valid_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::merge::operate,
        ),
    }
}

/// Same, for a non-numeric input: all three revisions reject it in the same place.
pub fn evaluate_text(revision: Revision, input: &str, base: f64) -> Outcome {
    let span = Span;
    let value = Value::String {
        val: input.to_string(),
        span,
    };
    match revision {
        Revision::Parent => finish(
            extracted::parent::require_positive_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::parent::operate,
        ),
        Revision::First => finish(
            extracted::first::require_positive_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::first::operate,
        ),
        Revision::Merge => finish(
            extracted::merge::require_valid_base(Spanned { item: base, span }, span),
            value,
            span,
            extracted::merge::operate,
        ),
    }
}

/// The domain the fix settles on: the base is a finite number in `(0, 1) ∪ (1, Inf)`,
/// the value is a positive number. `+inf` as a value is deliberately kept (its
/// logarithm is the limit `±inf`); NaN never passes either test.
pub fn base_in_domain(base: f64) -> bool {
    base.is_finite() && base > 0.0 && base != 1.0
}

pub fn value_in_domain(value: f64) -> bool {
    value > 0.0
}

pub const BASES: [f64; 12] = [
    1.0,
    f64::NAN,
    f64::INFINITY,
    f64::NEG_INFINITY,
    0.0,
    -0.0,
    -2.0,
    2.0,
    4.0,
    10.0,
    0.5,
    3.5,
];

pub const INPUTS: [f64; 12] = [
    f64::NAN,
    f64::INFINITY,
    f64::NEG_INFINITY,
    0.0,
    -0.0,
    -1.0,
    0.5,
    1.0,
    2.0,
    8.0,
    16.0,
    100.0,
];

pub struct Row {
    pub base: f64,
    pub input: f64,
    pub outcome: Outcome,
}

/// Pairs the command answers although one side is outside the domain.
pub fn accepted_outside_domain(revision: Revision) -> Vec<Row> {
    let mut rows = Vec::new();
    for base in BASES {
        for input in INPUTS {
            if base_in_domain(base) && value_in_domain(input) {
                continue;
            }
            let outcome = evaluate(revision, input, base);
            if matches!(outcome, Outcome::Value(_)) {
                rows.push(Row {
                    base,
                    input,
                    outcome,
                });
            }
        }
    }
    rows
}

/// Pairs inside the domain that the command rejects.
pub fn rejected_inside_domain(revision: Revision) -> Vec<Row> {
    let mut rows = Vec::new();
    for base in BASES {
        for input in INPUTS {
            if !(base_in_domain(base) && value_in_domain(input)) {
                continue;
            }
            let outcome = evaluate(revision, input, base);
            if matches!(outcome, Outcome::Rejected(_)) {
                rows.push(Row {
                    base,
                    input,
                    outcome,
                });
            }
        }
    }
    rows
}

/// Pairs both revisions answer; `true` when the two floats are bit-identical.
pub fn agreement(revision: Revision, other: Revision) -> (usize, usize) {
    let mut both = 0;
    let mut identical = 0;
    for base in BASES {
        for input in INPUTS {
            let left = evaluate(revision, input, base);
            let right = evaluate(other, input, base);
            if let (Outcome::Value(_), Outcome::Value(_)) = (&left, &right) {
                both += 1;
                if left.same_as(&right) {
                    identical += 1;
                }
            }
        }
    }
    (both, identical)
}

/// The value the removed `can_log_base_e` test expected from
/// `16 | math log 2.718281828459045`.
pub const OLD_TEST_EXPECTED: f64 = 2.772588722239781;
pub const E_LITERAL: f64 = 2.718281828459045;
