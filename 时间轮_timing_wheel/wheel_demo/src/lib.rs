//! 时间轮 +1 偏移验证工程
//!
//! `wheel_fixed` = tokio-audit 当前 checkout（含 +1 修复，level.rs L117）
//! `wheel_buggy` = 同一份代码去掉 +1（即 #8334 之前的行为）
//!
//! 两个模块逐字节相同，唯一差异是 `next_occupied_slot` 里的 `+ 1`。

pub mod counterexample;
pub mod stack;
#[path = "wheel_fixed/mod.rs"]
pub mod wheel_fixed;
#[path = "wheel_buggy/mod.rs"]
pub mod wheel_buggy;
