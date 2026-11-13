# Iceberg 替换失败复现工程

复现 pixeltable #1889：`if_exists='replace'` 先把旧表 `drop`、再把写好的临时表 `rename` 成目标名；两步之间失败时，`finally` 会无条件把临时表也删掉——旧表已经没了，新的也被删了。

两版 `pixeltable/io/iceberg.py` 原样放在 `vendor/`：

| 目录 | 来源 | 说明 |
| --- | --- | --- |
| `vendor/base/iceberg.py` | pixeltable/pixeltable @ `2eca8e44e31dc4ad6eee2c602615cb35e5d89dcc` | 修复前 |
| `vendor/merge/iceberg.py` | pixeltable/pixeltable @ `b76619839123f2f4402fb78ee8348adcc6f87f2f` | #1889 合并后 |

其余代码来自 pixeltable 0.7.24，它的 `pixeltable/io/iceberg.py` 与父提交逐字节相同。脚本按文件加载对应版本，替换 `pixeltable.io.export_iceberg`，不修改安装目录。

上游许可证见 `LICENSE`（Apache-2.0）。

## 环境

```text
python -m venv venv
venv\Scripts\pip install pixeltable==0.7.24 "pyiceberg[sql-sqlite]"
venv\Scripts\python -B run.py --test
```

工程只用本机的 SQLite 目录（`SqlCatalog` + 本地 warehouse），不联网。

### 一个本机才有的前置步骤

pixeltable 自带 PostgreSQL 16，首次运行会用 `initdb` 建集群。这台机器是中文系统 locale，bundled `initdb` 在 UTF-8 集群的 post-bootstrap 阶段会报 `invalid byte sequence for encoding "UTF8"`；用 `-E SQL_ASCII --locale=C` 能建出来。脚本因此先建 SQL_ASCII 集群，再把 `postgres` 与 `pixeltable` 两个库从 `template0` 重建为 UTF-8，然后交给 pixeltable。换到 locale 正常的机器上，这一步换成普通的 `initdb` 即可，复现的结论不变。

## 五个场景

目录都被一个 `FailingCatalog` 包住，在替换的不同步骤注入失败：

| 场景 | 注入 |
| --- | --- |
| `rename-fails/no-target` | 原本没有目标表；`rename_table` 抛错 |
| `drop-applied-then-raises` | 目标表存在；`drop_table` 已生效后抛错 |
| `drop-fails-before-effect` | 目标表存在；`drop_table` 未生效就抛错 |
| `target-check-fails` | 目标表存在；`drop` 生效后抛错，`table_exists` 也抛错 |
| `replace-succeeds` | 不注入，走成功路径 |

每个场景都会记录：目标表还在不在、临时表有几张、临时表里有多少行、错误信息里有没有点名临时表。

## 预期输出

修复前：前三个失败场景和前四个里的三个，导出写完的数据一行不剩——目标表已 `drop`，临时表被 `finally` 删掉。`parent left no copy after 3/5 failed swaps`。

修复后：

- `rename-fails/no-target`、`drop-applied-then-raises`、`target-check-fails`：目标表不存在，临时表留下来，3 行完整，错误信息里给出临时表名；
- `drop-fails-before-effect`：目标表还在（1 行），临时表照旧清掉，不堆积；
- `replace-succeeds`：目标表 3 行，没有临时表残留。

`merged failed 0/5 expectations`。

文中数字均出自 `--test` 的输出，存档在 `../.yan/pixeltable-iceberg/runs/`。
