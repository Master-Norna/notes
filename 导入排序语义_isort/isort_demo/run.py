"""isort #2675 修前/修后对照复现。

同一份输入，分别喂给父提交（修复前，1745766e）与合并提交（修复后，3415efa）
的 isort 源码快照，对照格式化输出、行尾注释与 lint 结果。

用法：
    python run.py            # 完整对照报告（装了 flake8 会加跑 lint）
    python run.py --offline  # 不调用 flake8
    python run.py --test     # 断言自测，全部通过退出码 0

快照无独立版本元数据，版本一律以 git SHA 标识（isort 的 __version__ 会误读
解释器环境里已安装的同名发行版，本脚本不使用它）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MERGED_SHA = "3415efa3668f5514c57dfa4291d83021a575b56f"
PARENT_SHA = "1745766e5cc705eec7179c1122fcdf5b5b6e7546"

CONFIG = "force_grid_wrap=2, multi_line_output=GRID(0), line_length=79"

CASES = [
    # (标题, 输入, 说明)
    ("主反例：不折行也进 grid", "from ugly import a, b  # noqa: F401\n",
     "force_grid_wrap=2 让两个名字也走 grid；语句不超宽，不触发折行分支"),
    ("对照A：需要折行的 grid", None,
     "19 个名字超出 60 列，走 grid 的折行分支（修复不应改变这里的行为）"),
    ("对照B：没有注释的输入", "from ugly import a, b\n",
     "comments 为空时 add_to_line 应原样返回，修复不得添乱"),
]

WRAP_INPUT = "from ugly import a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s  # noqa: F401\n"
WRAP_LINE_LENGTH = 60


def load_isort(pkg_root: Path):
    """在当前进程加载指定快照目录下的 isort 包，并核验模块确实来自快照。"""
    for name in [m for m in sys.modules if m == "isort" or m.startswith("isort.")]:
        del sys.modules[name]
    sys.path.insert(0, str(pkg_root))
    try:
        import isort

        loaded = Path(isort.__file__).resolve()
        expected = (pkg_root / "isort" / "__init__.py").resolve()
        if loaded != expected:
            raise RuntimeError(
                f"加载到的不是快照源码：{loaded}\n（解释器环境里可能装有同名 isort）"
            )
        return isort
    finally:
        sys.path.pop(0)


def run_case(isort, title: str, code: str, line_length: int = 79) -> dict:
    """对一版 isort 跑一组输入，返回输出、注释计数与幂等信息。"""
    out1 = isort.code(code, force_grid_wrap=2, multi_line_output=0, line_length=line_length)
    out2 = isort.code(out1, force_grid_wrap=2, multi_line_output=0, line_length=line_length)
    return {
        "title": title,
        "input": code,
        "output": out1,
        "noqa_kept": "# noqa" in out1,
        "idempotent": out1 == out2,
        "second_run": out2,
    }


def flake8_check(code: str) -> tuple[int, str]:
    """把代码写进临时文件跑 flake8 --select=F401，返回 (退出码, 摘要)。"""
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8", newline="\n"
    ) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "flake8", "--select=F401", "--count", path],
            capture_output=True,
            text=True,
        )
        summary = (proc.stdout.strip() or proc.stderr.strip()).replace(path, "sample.py")
        return proc.returncode, summary
    finally:
        Path(path).unlink(missing_ok=True)


def fmt_bool(v: bool) -> str:
    return "是" if v else "否"


def report(offline: bool) -> int:
    before = load_isort(HERE / "isort_before")
    after = load_isort(HERE / "isort_after")
    versions = {
        f"修复前 isort @ {PARENT_SHA[:12]}": before,
        f"修复后 isort @ {MERGED_SHA[:12]}": after,
    }

    print(f"输入配置：{CONFIG}")
    print(f"flake8：{'跳过（--offline 或未安装）' if offline else '参与对照'}")
    print()

    for title, code, note in CASES:
        actual = WRAP_INPUT if code is None else code
        ll = WRAP_LINE_LENGTH if code is None else 79
        print("=" * 72)
        print(f"【{title}】{note}")
        print(f"输入：\n{actual}", end="" if actual.endswith("\n") else "\n")
        for label, isort in versions.items():
            r = run_case(isort, title, actual, line_length=ll)
            print(f"-- {label}")
            print(f"   输出：\n{r['output']}", end="" if r["output"].endswith("\n") else "\n")
            print(f"   行尾 noqa 注释保留：{fmt_bool(r['noqa_kept'])}"
                  f"　二次格式化输出不变：{fmt_bool(r['idempotent'])}")
            if not offline and "noqa" in actual and code is not None:
                rc, summary = flake8_check(r["output"])
                print(f"   flake8 --select=F401：退出码 {rc}，{summary or '无输出'}")
        if code is None:
            # 对照A 两版输出必须一致：注释都落在折行处，修复不动折行分支
            outs = []
            for isort in versions.values():
                outs.append(run_case(isort, title, actual, line_length=ll)["output"])
            print(f"-- 两版输出一致：{fmt_bool(outs[0] == outs[1])}")
        print()

    return 0


def selftest(offline: bool) -> int:
    before = load_isort(HERE / "isort_before")
    after = load_isort(HERE / "isort_after")

    checks: list[tuple[str, bool]] = []

    r = run_case(before, "主反例", "from ugly import a, b  # noqa: F401\n")
    checks.append(("修复前：noqa 注释被丢弃", r["output"] == "from ugly import (a, b)\n"))
    checks.append(("修复前：输出幂等", r["idempotent"]))

    r = run_case(after, "主反例", "from ugly import a, b  # noqa: F401\n")
    checks.append(("修复后：noqa 注释保留", r["output"] == "from ugly import (a, b)  # noqa: F401\n"))
    checks.append(("修复后：输出幂等", r["idempotent"]))

    # 对照A：折行分支行为不变（PR 回归测试钉住的位置）
    b_out = run_case(before, "对照A", WRAP_INPUT, line_length=WRAP_LINE_LENGTH)["output"]
    a_out = run_case(after, "对照A", WRAP_INPUT, line_length=WRAP_LINE_LENGTH)["output"]
    checks.append(("对照A：两版输出一致（折行分支未变）", b_out == a_out))
    checks.append(("对照A：注释落在折行行尾", "# noqa: F401" in b_out.split("\n")[0]))

    # 对照B：无注释输入不受影响
    b_nc = run_case(before, "对照B", "from ugly import a, b\n")["output"]
    a_nc = run_case(after, "对照B", "from ugly import a, b\n")["output"]
    checks.append(("对照B：无注释输出两版一致", b_nc == a_nc == "from ugly import (a, b)\n"))

    if not offline:
        rc_b, _ = flake8_check("from ugly import (a, b)\n")
        rc_a, _ = flake8_check("from ugly import (a, b)  # noqa: F401\n")
        checks.append(("flake8：修复前输出触发 F401（退出码 1）", rc_b == 1))
        checks.append(("flake8：修复后输出干净（退出码 0）", rc_a == 0))

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
    parser.add_argument("--offline", action="store_true", help="不调用 flake8")
    parser.add_argument("--test", action="store_true", help="断言自测")
    args = parser.parse_args()
    if args.test:
        return selftest(args.offline)
    return report(args.offline)


if __name__ == "__main__":
    raise SystemExit(main())
