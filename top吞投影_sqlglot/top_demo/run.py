# 15 形状 × 2 版 sqlglot 的 TOP 探针矩阵：30.33.0（修前）与 30.33.0+dc4afaf5（修后）。
#
# 用法：
#   python run.py            打印两版对照表
#   python run.py --test     断言整矩阵（版本串 + 15 形全部输出）+ 逐文件核对 provenance
#   python run.py --emit DIR 两版探针 JSON 与 matrix.md 落到 DIR
#
# 两版源码原样 vendor 在本目录 vendor/a/、vendor/b/（provenance 见 provenance.txt），
# 工程自包含：任意 Python 3 机器直接跑，全程不联网（探针自带 socket audit hook）。

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")
ERR_LIMIT = "Required keyword: 'expression' missing for <class 'sqlglot.expressions.query.Limit'>"

# (dialect, sql, kind, payload)
# kind="ok"：payload=(out, projections)，out 与投影列表须逐字相等
# kind="err"：payload=错误信息前缀，实测消息（去 ANSI、压空白后）须以其开头
MATRIX_A = [
    ("snowflake", "SELECT top, x FROM t", "ok", ("SELECT FROM t LIMIT x", [])),
    ("snowflake", "SELECT top FROM t", "err", ERR_LIMIT),
    ("snowflake", "SELECT top.x FROM t AS top", "err", ERR_LIMIT),
    ("snowflake", "SELECT TOP(x) FROM t", "ok", ("SELECT FROM t LIMIT x", [])),
    ("snowflake", "SELECT TOP(5), x FROM t", "ok", ("SELECT FROM t LIMIT 5, x", [])),
    ("snowflake", "SELECT TOP 5 x FROM t", "ok", ("SELECT x FROM t LIMIT 5", ["x"])),
    ("oracle", "SELECT top, x FROM t", "ok", ("SELECT FROM t FETCH FIRST x ROWS ONLY", [])),
    ("oracle", "SELECT TOP 5 x FROM t", "ok", ("SELECT x FROM t FETCH FIRST 5 ROWS ONLY", ["x"])),
    ("oracle", "SELECT TOP(5), x FROM t", "ok", ("SELECT FROM t FETCH FIRST x ROWS ONLY", [])),
    ("tsql", "SELECT top FROM t", "err", ERR_LIMIT),
    ("tsql", "SELECT top, x FROM t", "ok", ("SELECT TOP (x) FROM t", [])),
    ("tsql", "SELECT TOP (5) x FROM t", "ok", ("SELECT TOP 5 x FROM t", ["x"])),
    ("teradata", "SELECT top FROM t", "err", ERR_LIMIT),
    ("redshift", "SELECT top FROM t", "err", ERR_LIMIT),
    ("redshift", "SELECT TOP 1 x FROM t", "ok", ("SELECT x FROM t LIMIT 1", ["x"])),
]

MATRIX_B = [
    ("snowflake", "SELECT top, x FROM t", "ok", ("SELECT top, x FROM t", ["top", "x"])),
    ("snowflake", "SELECT top FROM t", "ok", ("SELECT top FROM t", ["top"])),
    ("snowflake", "SELECT top.x FROM t AS top", "ok", ("SELECT top.x FROM t AS top", ["top.x"])),
    ("snowflake", "SELECT TOP(x) FROM t", "ok", ("SELECT TOP(x) FROM t", ["TOP(x)"])),
    ("snowflake", "SELECT TOP(5), x FROM t", "ok", ("SELECT TOP(5), x FROM t", ["TOP(5)", "x"])),
    ("snowflake", "SELECT TOP 5 x FROM t", "ok", ("SELECT x FROM t LIMIT 5", ["x"])),
    ("oracle", "SELECT top, x FROM t", "ok", ("SELECT top, x FROM t", ["top", "x"])),
    ("oracle", "SELECT TOP 5 x FROM t", "err", "Invalid expression / Unexpected token"),
    ("oracle", "SELECT TOP(5), x FROM t", "ok", ("SELECT TOP(5), x FROM t", ["TOP(5)", "x"])),
    ("tsql", "SELECT top FROM t", "err", ERR_LIMIT),
    ("tsql", "SELECT top, x FROM t", "ok", ("SELECT TOP (x) FROM t", [])),
    ("tsql", "SELECT TOP (5) x FROM t", "ok", ("SELECT TOP 5 x FROM t", ["x"])),
    ("teradata", "SELECT top FROM t", "err", ERR_LIMIT),
    ("redshift", "SELECT top FROM t", "err", ERR_LIMIT),
    ("redshift", "SELECT TOP 1 x FROM t", "ok", ("SELECT x FROM t LIMIT 1", ["x"])),
]

def run_probe(vendor):
    import os
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-X", "utf8", str(DEMO / "probe.py"), str(vendor)],
        capture_output=True, text=True, timeout=180, cwd=str(DEMO), env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError("probe 失败（%s）：%s" % (vendor, proc.stderr.strip()[-800:]))
    return json.loads(proc.stdout)

def norm(msg):
    return " ".join(ANSI.sub("", msg).split())

def validate(label, data, matrix, version_rule):
    fails = []
    version = data.get("version", "")
    if version_rule == "exact" and version != "30.33.0":
        fails.append("%s 版本串：%r != '30.33.0'" % (label, version))
    if version_rule == "needle" and "dc4afaf5" not in version:
        fails.append("%s 版本串 %r 不含 'dc4afaf5'" % (label, version))
    rows = data.get("rows", [])
    if len(rows) != len(matrix):
        fails.append("%s 行数 %d != %d" % (label, len(rows), len(matrix)))
        rows = rows[: len(matrix)]
    for (dialect, sql, kind, payload), row in zip(matrix, rows):
        where = "%s %r" % (dialect, sql)
        if (row.get("dialect"), row.get("sql")) != (dialect, sql):
            fails.append("%s 行列错位：%r" % (where, row))
            continue
        if kind == "ok":
            out, projections = payload
            if not row.get("ok"):
                fails.append("%s 期望可解析，实际 ParseError：%r" % (where, row.get("error")))
            elif row.get("out") != out:
                fails.append("%s out 不符：期望 %r，实际 %r" % (where, out, row.get("out")))
            elif row.get("projections") != projections:
                fails.append("%s 投影不符：期望 %r，实际 %r" % (where, out, row.get("projections")))
        else:
            if row.get("ok"):
                fails.append("%s 期望 ParseError，实际可解析：%r" % (where, row.get("out")))
            elif not norm(row.get("error", "")).startswith(payload):
                fails.append("%s 错误前缀不符：%r" % (where, norm(row.get("error", ""))[:120]))
    return fails

def check_provenance():
    """provenance.txt 逐文件 SHA-256 与 vendor/ 实际字节比对；返回不符列表。"""
    text = (DEMO / "provenance.txt").read_text(encoding="utf-8")
    fails = []
    vend = DEMO / "vendor"
    count = 0
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split("  ", 1)
        p = vend / rel
        if not p.is_file():
            fails.append("缺文件：%s" % rel)
            continue
        count += 1
        actual = hashlib.sha256(p.read_bytes()).hexdigest().upper()
        if actual != digest.upper():
            fails.append("SHA-256 不符：%s" % rel)
    if count != 372:
        fails.append("provenance 文件数 %d != 372" % count)
    return fails

def cell(row):
    if row.get("ok"):
        proj = ", ".join(row.get("projections", [])) or "（空）"
        return "`%s` · 投影 [%s]" % (row.get("out"), proj)
    return "**ParseError**（`%s…`）" % norm(row.get("error", ""))[:44]

def table_markdown(data_a, data_b):
    lines = ["| dialect · SQL | 30.33.0（修前） | dc4afaf5（修后） |",
             "|---|---|---|"]
    for i, (dialect, sql, _, _) in enumerate(MATRIX_A):
        lines.append("| %s · `%s` | %s | %s |" % (
            dialect, sql, cell(data_a["rows"][i]), cell(data_b["rows"][i])))
    return "\n".join(lines)

def main():
    args = sys.argv[1:]
    mode = next((a for a in args if a in ("--test", "--emit")), None)
    emit_dir = args[args.index("--emit") + 1] if "--emit" in args else None

    if mode == "--emit" and not emit_dir:
        print("--emit 需要一个目录参数", file=sys.stderr)
        sys.exit(2)

    data_a = run_probe(DEMO / "vendor" / "a")
    data_b = run_probe(DEMO / "vendor" / "b")

    if mode == "--test":
        fails = check_provenance()
        fails = ["provenance " + f for f in fails]
        fails += validate("A", data_a, MATRIX_A, "exact")
        fails += validate("B", data_b, MATRIX_B, "needle")
        for f in fails:
            print("FAIL  " + f)
        if fails:
            print("%d 处不符" % len(fails))
            sys.exit(1)
        print("版本：%s / %s" % (data_a["version"], data_b["version"]))
        print("provenance 372 文件 SHA-256 全对")
        print("15 形 × 2 版全部断言通过")
        print("ALL PASS")
        return

    if mode == "--emit":
        out = Path(emit_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "probe-A-30.33.0.json").write_text(
            json.dumps(data_a, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (out / "probe-B-dc4afaf5.json").write_text(
            json.dumps(data_b, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (out / "matrix.md").write_text(table_markdown(data_a, data_b) + "\n", encoding="utf-8")
        print("已写出 %s（probe-A / probe-B / matrix.md）" % out)
        return

    print(table_markdown(data_a, data_b))

if __name__ == "__main__":
    main()
