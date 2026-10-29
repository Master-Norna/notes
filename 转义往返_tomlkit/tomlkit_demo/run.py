"""tomlkit #612 修前/修后对照复现。

同一个操作（给已有的字符串值追加文本），分别喂给父提交（修复前，7903965）
与合并提交（修复后，61941de）的 tomlkit 源码快照，对照序列化输出与
「写出的文本读回」结果。

用法：
    python run.py          # 完整对照报告
    python run.py --test   # 断言自测，全部通过退出码 0

快照无独立版本元数据（两版 __init__.py 都写着 0.15.1），版本一律以 git SHA
标识。零第三方依赖，可完全离线运行；Python >= 3.9。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MERGED_SHA = "61941deb3c7155e88d5f038148b33a599c04a530"
PARENT_SHA = "79039653cbe5ff2a2e23042717455a2ac4875539"


def load_tomlkit(pkg_root: Path):
    """在当前进程加载指定快照目录下的 tomlkit 包，并核验模块确实来自快照。"""
    for name in [m for m in sys.modules if m == "tomlkit" or m.startswith("tomlkit.")]:
        del sys.modules[name]
    sys.path.insert(0, str(pkg_root))
    try:
        import tomlkit

        loaded = Path(tomlkit.__file__).resolve()
        expected = (pkg_root / "tomlkit" / "__init__.py").resolve()
        if loaded != expected:
            raise RuntimeError(
                f"加载到的不是快照源码：{loaded}\n（解释器环境里可能装有同名 tomlkit）"
            )
        return tomlkit
    finally:
        sys.path.pop(0)


def readback(tomlkit, literal: str):
    """把一段序列化文本读回 TOML，返回 (成功?, 值或异常摘要)。"""
    try:
        doc = tomlkit.parse(f"k = {literal}\n")
        return True, repr(doc["k"])
    except Exception as e:  # noqa: BLE001 - 反例就是要把异常对照出来
        return False, f"{type(e).__name__}: {str(e).splitlines()[0]}"


def roundtrip_doc(tomlkit) -> tuple[str, bool, str]:
    """文档级往返：解析 k = "foo"，追加一个引号，写出去再读回来。"""
    doc = tomlkit.parse('k = "foo"\n')
    doc["k"] += '"'
    written = tomlkit.dumps(doc)
    try:
        doc2 = tomlkit.loads(written)
        return written, True, repr(doc2["k"])
    except Exception as e:  # noqa: BLE001
        return written, False, f"{type(e).__name__}: {str(e).splitlines()[0]}"


CASES = [
    # (标题, 操作说明, 构造函数)
    (
        "主反例：追加一个双引号",
        'i = item("foo")\ni += \'"\'',
        lambda tk: tk.item("foo") + '"',
    ),
    (
        "追加一个反斜杠",
        'i = item("foo")\ni += "\\\\"',
        lambda tk: tk.item("foo") + "\\",
    ),
    (
        "追加一个换行（控制字符）",
        'i = item("foo")\ni += "\\n"',
        lambda tk: tk.item("foo") + "\n",
    ),
    (
        "对照A：右侧本来就是 String",
        'j = item("foo")\nj += item(\'"\')',
        lambda tk: tk.item("foo") + tk.item('"'),
    ),
    (
        "对照B：追加普通文本",
        'k = item("foo")\nk += " bar"',
        lambda tk: tk.item("foo") + " bar",
    ),
    (
        "边界：字面串追加自己的定界符（修复未覆盖）",
        "i = value(\"'foo'\")  # TOML 字面串，值 foo\ni += \"'\"",
        lambda tk: tk.api.value("'foo'") + "'",
    ),
]


def report() -> int:
    before = load_tomlkit(HERE / "tomlkit_before")
    after = load_tomlkit(HERE / "tomlkit_after")
    versions = [
        (f"修复前 tomlkit @ {PARENT_SHA[:12]}", before),
        (f"修复后 tomlkit @ {MERGED_SHA[:12]}", after),
    ]

    print(f"Python {sys.version.split()[0]}，快照均以 git SHA 标识")
    print()

    for title, note, make in CASES:
        print("=" * 72)
        print(f"【{title}】\n{note}")
        for label, tk in versions:
            item = make(tk)
            literal = item.as_string()
            ok, detail = readback(tk, literal)
            mark = "读回成功" if ok else "读回失败"
            print(f"-- {label}")
            print(f"   逻辑值 i == {item!r}　(as_string 前)")
            print(f"   as_string() -> {literal}")
            print(f"   {mark}: {detail}")
        print()

    print("=" * 72)
    print("【文档级往返】doc = parse('k = \"foo\"')；doc[\"k\"] += '\"'；dumps 后 loads")
    for label, tk in versions:
        written, ok, detail = roundtrip_doc(tk)
        mark = "读回成功" if ok else "读回失败"
        print(f"-- {label}")
        print(f"   dumps -> {written!r}")
        print(f"   {mark}: {detail}")
    print()

    return 0


def selftest() -> int:
    before = load_tomlkit(HERE / "tomlkit_before")
    after = load_tomlkit(HERE / "tomlkit_after")

    checks: list[tuple[str, bool]] = []

    # 主反例：追加双引号
    i = before.item("foo") + '"'
    checks.append(("修复前：值不受影响（i == 'foo\"'）", i == 'foo"'))
    checks.append(("修复前：as_string 拼出 \"foo\"\"", i.as_string() == '"foo""'))
    ok, _ = readback(before, i.as_string())
    checks.append(("修复前：写出的文本读不回", not ok))

    i = after.item("foo") + '"'
    checks.append(("修复后：值不受影响（i == 'foo\"'）", i == 'foo"'))
    checks.append(("修复后：as_string 转义为 \"foo\\\"\"", i.as_string() == '"foo\\""'))
    ok, v = readback(after, i.as_string())
    checks.append((f"修复后：读回 {v} == 'foo\"'", ok and v == repr('foo"')))

    # 追加反斜杠
    i = before.item("foo") + "\\"
    ok, _ = readback(before, i.as_string())
    checks.append(("修复前：反斜杠同样读不回", not ok))

    i = after.item("foo") + "\\"
    ok, v = readback(after, i.as_string())
    checks.append(("修复后：反斜杠读回 'foo\\\\'", ok and v == repr("foo\\")))

    # 追加换行
    i = before.item("foo") + "\n"
    ok, _ = readback(before, i.as_string())
    checks.append(("修复前：换行同样读不回", not ok))

    i = after.item("foo") + "\n"
    ok, v = readback(after, i.as_string())
    checks.append(("修复后：换行读回 'foo\\n'", ok and v == repr("foo\n")))

    # 对照A：右侧本来就是 String，两版一致（#235 修过的路径保持不变）
    j_b = before.item("foo") + before.item('"')
    j_a = after.item("foo") + after.item('"')
    checks.append(("对照A：String+String 两版输出一致", j_b.as_string() == j_a.as_string() == '"foo\\""'))
    ok, _ = readback(after, j_a.as_string())
    checks.append(("对照A：读回成功", ok))

    # 对照B：普通文本，两版一致
    k_b = before.item("foo") + " bar"
    k_a = after.item("foo") + " bar"
    checks.append(("对照B：普通文本两版输出一致", k_b.as_string() == k_a.as_string() == '"foo bar"'))

    # 文档级往返
    w_b, ok_b, _ = roundtrip_doc(before)
    checks.append((f"文档级：修复前 dumps 为 {w_b!r} 且读不回", w_b == 'k = "foo""\n' and not ok_b))
    w_a, ok_a, v_a = roundtrip_doc(after)
    checks.append((f"文档级：修复后 dumps 为 {w_a!r} 且读回 {v_a}", w_a == 'k = "foo\\""\n' and ok_a and v_a == repr('foo"')))

    # 边界：TOML 字面串（'…'）没有转义机制，追加自己的定界符两版都坏——
    # 修复只给 basic string 接上转义；构造时 from_raw 会当场拒绝，追加路径不检查。
    b = before.api.value("'foo'") + "'"
    a = after.api.value("'foo'") + "'"
    ok_b, _ = readback(before, b.as_string())
    ok_a, _ = readback(after, a.as_string())
    checks.append((
        "边界：字面串追加单引号两版都读不回（修复未覆盖）",
        b.as_string() == a.as_string() == "'foo''" and not ok_b and not ok_a,
    ))
    try:
        after.items.String.from_raw("foo'", after.items.StringType.SLL, escape=False)
        raised = False
    except Exception:  # noqa: BLE001 - 预期就是 InvalidStringError
        raised = True
    checks.append(("对照：构造路径 from_raw 对字面串里的引号当场拒绝", raised))

    width = max(len(name) for name, _ in checks)
    failed = 0
    for name, ok in checks:
        print(f"[{'通过' if ok else '失败'}] {name.ljust(width)}")
        failed += 0 if ok else 1
    total = len(checks)
    print(f"{total - failed}/{total} 通过")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="断言自测")
    args = parser.parse_args()
    return selftest() if args.test else report()


if __name__ == "__main__":
    raise SystemExit(main())
