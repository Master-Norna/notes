//! Minimal stand-ins for the Nushell types used by `remove_impl`.
//!
//! This is deliberately not a Nushell build: there is no parser, pipeline,
//! metadata handling or command registration here. The upstream function
//! bodies are extracted from the fixed snapshots by `build.rs`.

#[derive(Clone, Copy, Debug)]
pub struct Span;

#[derive(Clone, Debug)]
pub struct Arguments {
    pub pattern: Vec<u8>,
    pub end: bool,
    pub all: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Value {
    pub val: Vec<u8>,
}

impl Value {
    pub fn binary(val: Vec<u8>, _span: Span) -> Self {
        Self { val }
    }
}

pub type RemoveFn = fn(&[u8], &Arguments, Span) -> Value;

pub mod extracted {
    include!(concat!(env!("OUT_DIR"), "/extracted.rs"));
}

pub fn call(
    remove: RemoveFn,
    input: &[u8],
    pattern: &[u8],
    end: bool,
    all: bool,
) -> Vec<u8> {
    assert!(
        !pattern.is_empty(),
        "precondition only: the real command's run() rejects an empty pattern before remove_impl"
    );
    remove(
        input,
        &Arguments {
            pattern: pattern.to_vec(),
            end,
            all,
        },
        Span,
    )
    .val
}

/// Independent expectation for `--end` without `--all`: remove the rightmost
/// occurrence anywhere, or leave the input unchanged.
pub fn oracle_end(input: &[u8], pattern: &[u8]) -> Vec<u8> {
    if pattern.len() <= input.len() {
        if let Some(pos) = (0..=input.len() - pattern.len())
            .rev()
            .find(|&pos| &input[pos..pos + pattern.len()] == pattern)
        {
            return [&input[..pos], &input[pos + pattern.len()..]].concat();
        }
    }
    input.to_vec()
}

/// Independent expectation for the forward branch used by `--all`
/// (including `--end --all`, which ignores `--end`).
pub fn oracle_all(input: &[u8], pattern: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut left = 0;
    while left < input.len() {
        if left + pattern.len() <= input.len()
            && input[left..left + pattern.len()] == *pattern
        {
            left += pattern.len();
        } else {
            out.push(input[left]);
            left += 1;
        }
    }
    out
}

/// Every byte string over `alphabet` of length `min..=max`, in a stable order.
pub fn words(alphabet: &[u8], max: usize, min: usize) -> Vec<Vec<u8>> {
    let mut out = Vec::new();
    for len in min..=max {
        let mut counters = vec![0usize; len];
        loop {
            out.push(counters.iter().map(|&i| alphabet[i]).collect());
            let mut position = len;
            loop {
                if position == 0 {
                    break;
                }
                position -= 1;
                counters[position] += 1;
                if counters[position] < alphabet.len() {
                    break;
                }
                counters[position] = 0;
                if position == 0 {
                    break;
                }
            }
            if len == 0 || counters.iter().all(|&i| i == 0) {
                break;
            }
        }
    }
    out
}
