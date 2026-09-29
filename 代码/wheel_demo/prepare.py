# -*- coding: utf-8 -*-
"""从 tokio-audit 的 wheel 源码生成 fixed/buggy 双版本 demo crate"""
import io, os, re

SRC = r"E:\项目\GitHub仓库扫描\tokio-audit\tokio-util\src\time\wheel"
DST = r"E:\项目\Tset\代码\wheel_demo\src"

def strip_tests(src):
    i = src.find("#[cfg(all(test, not(loom)))]")
    assert i > 0, "test marker not found"
    return src[:i]

def transform_level(src, buggy):
    src = strip_tests(src)
    src = src.replace("use crate::time::wheel::Stack;", "use crate::stack::Stack;")
    src = src.replace("pub(crate) struct Level", "pub struct Level")
    src = src.replace("pub(crate) struct Expiration", "pub struct Expiration")
    src = src.replace("pub(crate) fn", "pub fn")
    if buggy:
        old = "let now_slot = ((now / slot_range(self.level)) % LEVEL_MULT as u64) as usize + 1;"
        assert old in src, "buggy +1 line not found"
        src = src.replace(old, "let now_slot = ((now / slot_range(self.level)) % LEVEL_MULT as u64) as usize;")
        src = src.replace(
            "// Add the +1 offset for the `now_slot` to ignore the slot that `now`\n        // fits in, since it's the farthest timer that could appear from `now`.",
            "// BUGGY (pre-#8334): no +1 offset. Scans starting at the slot holding `now`.",
            1,
        )
    return src

def transform_mod(src):
    src = strip_tests(src)
    for old in ("mod stack;\r\npub(crate) use self::stack::Stack;",
                "mod stack;\npub(crate) use self::stack::Stack;"):
        src = src.replace(old, "use crate::stack::Stack;")
    assert "mod stack;" not in src, "stack import not rewritten"
    src = src.replace("pub(crate) struct Wheel", "pub struct Wheel")
    src = src.replace("pub(crate) enum InsertError", "pub enum InsertError")
    src = src.replace("pub(crate) use self::level::Expiration;", "pub use self::level::Expiration;")
    src = src.replace("pub(crate) fn", "pub fn")
    return src

def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)

raw_level = io.open(SRC + r"\level.rs", encoding="utf-8").read()
raw_mod = io.open(SRC + r"\mod.rs", encoding="utf-8").read()

w(DST + r"\wheel_fixed\level.rs", transform_level(raw_level, buggy=False))
w(DST + r"\wheel_fixed\mod.rs", transform_mod(raw_mod))
w(DST + r"\wheel_buggy\level.rs", transform_level(raw_level, buggy=True))
w(DST + r"\wheel_buggy\mod.rs", transform_mod(raw_mod))
print("ok")
