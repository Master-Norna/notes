# 探针：15 个形状 × 一版 vendored sqlglot。禁网（socket audit hook）。输出 JSON 到 stdout。
# 用法：python probe.py <vendor 目录>
#   <vendor 目录> 是含 sqlglot/ 包的目录，即 top_demo/vendor/a 或 top_demo/vendor/b。
#   建议以 `python -I -B -X utf8` 启动，避免环境里已装的 sqlglot 混进来。
import json
import os
import sys
from pathlib import Path

def _deny(event, data):
    if event == "socket.socket.connect":
        raise RuntimeError("probe is offline; socket blocked")

sys.addaudithook(_deny)

if len(sys.argv) < 2 or not (Path(sys.argv[1]) / "sqlglot").is_dir():
    print("用法：python probe.py <vendor 目录>（如 top_demo/vendor/a）", file=sys.stderr)
    sys.exit(2)
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

import sqlglot
from sqlglot import parse_one
from sqlglot.errors import ParseError

SHAPES = [
    ("snowflake", "SELECT top, x FROM t"),      # 静默吞投影（逗号形）
    ("snowflake", "SELECT top FROM t"),         # 显式 ParseError（单形）
    ("snowflake", "SELECT top.x FROM t AS top"),
    ("snowflake", "SELECT TOP(x) FROM t"),
    ("snowflake", "SELECT TOP(5), x FROM t"),
    ("snowflake", "SELECT TOP 5 x FROM t"),     # 真 TOP limit（控制）
    ("oracle", "SELECT top, x FROM t"),
    ("oracle", "SELECT TOP 5 x FROM t"),
    ("oracle", "SELECT TOP(5), x FROM t"),
    ("tsql", "SELECT top FROM t"),
    ("tsql", "SELECT top, x FROM t"),
    ("tsql", "SELECT TOP (5) x FROM t"),        # TSQL 括号计数形（控制）
    ("teradata", "SELECT top FROM t"),
    ("redshift", "SELECT top FROM t"),
    ("redshift", "SELECT TOP 1 x FROM t"),      # redshift limit 形（控制）
]

rows = []
for dialect, sql in SHAPES:
    try:
        e = parse_one(sql, read=dialect)
        projections = [p.sql(dialect=dialect) for p in e.expressions]
        rows.append({"dialect": dialect, "sql": sql, "ok": True,
                     "out": e.sql(dialect=dialect), "projections": projections})
    except ParseError as ex:
        rows.append({"dialect": dialect, "sql": sql, "ok": False,
                     "error": " ".join(str(ex).split())[:300]})

print(json.dumps({"version": sqlglot.__version__, "rows": rows},
                 indent=1, ensure_ascii=False))
