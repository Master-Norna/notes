//! Three versions of the tokio-util wheel for the timing-wheel articles.
//!
//! `wheel_buggy`: no offset (before #8519).
//! `wheel_fixed`: all-level +1 (the first article's historical, incomplete fix).
//! `wheel_merged`: top-level-only +1, as merged in tokio #8519.
//!
//! Standalone wheel extraction with a test storage adapter, not a full DelayQueue.

#[cfg(test)]
mod counterexample;
pub mod followup;
pub mod stack;
pub mod wheel_fixed;
pub mod wheel_buggy;
pub mod wheel_merged;
