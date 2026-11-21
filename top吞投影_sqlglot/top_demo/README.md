# top_demo：列名叫 `top` 的两版 sqlglot 行为矩阵

`SELECT top, x FROM t` 在五个把 `TOP` 当限定词的方言（snowflake / oracle / tsql / teradata / redshift）里会被读成 `TOP <limit>`。本工程用 15 个 SQL 形状（含 3 个真 TOP limit 的控制形）把两版行为钉死：

- **A：`sqlglot==30.33.0`**（PyPI 当前最新，2026-11-17），修复未进任何发行版；
- **B：`30.33.0+dc4afaf5`**，`dc4afaf5` 是 [#9295](https://github.com/tobymao/sqlglot/pull/9295) 在 main 上的合并提交（修 [#9284](https://github.com/tobymao/sqlglot/issues/9284)）。

两版源码原样 vendor 在 `vendor/a/`、`vendor/b/`（纯 Python、无依赖，`provenance.txt` 记来源与逐文件 SHA-256）。工程自包含：任意 Python 3 的机器直接跑，不需要装任何东西，全程不联网（探针带 socket audit hook）。

矩阵本身在 `run.py` 的 `MATRIX_A` / `MATRIX_B`（每行含期望输出与投影列表，报错行断言到错误前缀）；`--test` 对两版逐行断言，并逐文件核对 `vendor/` 的 provenance，全过打印 `ALL PASS`。

## 运行

```powershell
python top_demo/run.py             # 打印两版对照表
python top_demo/run.py --test      # 断言整矩阵 + provenance
python top_demo/run.py --emit DIR  # 两版 JSON + matrix.md 落到 DIR
```

## 来源

- A：PyPI `sqlglot==30.33.0` 的 wheel `sqlglot-30.33.0-py3-none-any.whl`（829420 B，sha256 `A5B279FE7397A9FB6CDD0274A13A5FCEE0FA83AC6FF617083F1F2832031E90BC`，上传 2026-11-17T12:19:01）内 `sqlglot/` 全部文件。
- B：`main` @ [`dc4afaf5`](https://github.com/tobymao/sqlglot/commit/dc4afaf5c9a6748a004998ed13e3b438e20e431e)（#9295 合并提交，父 `09a454dd`）的 codeload tarball（sha256 `D99EFE9BC60FE5C736FF1ADA514884DCB088EAEB9873B1BAC3A9AE3C631C09F9`）内 `sqlglot/` 全部文件；`_version.py` 不在仓库里（build 生成），取本地安装时 setuptools-scm 生成的那份（版本串 `30.33.0+dc4afaf5`），用的就是安装该 tarball 时的 `VCS_VERSIONING_PRETEND_VERSION`。
- 已核对：wheel 与 PyPI 装出的 30.33.0、tarball 与本地装出的 30.33.0+dc4afaf5，逐文件字节一致。
- 上游为 MIT 许可，见本目录 `LICENSE`。
- 30.x 包布局：主解析器 `sqlglot/parser.py`，方言 tokenizer 在 `sqlglot/dialects/`，方言解析器在 `sqlglot/parsers/`。
