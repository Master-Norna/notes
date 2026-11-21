# 尾随换行复现工程

`jsonschema` 的 `date-time`、`time`、`uri`、`uri-reference`、`iri`、`iri-reference`、`hostname` 七个 format，会接受在末尾多一个换行（U+000A）的值。这个工程把三条委托链原样搬下来，用来定位在哪个包的哪一行放行的。

三条链各自依赖一个上游验证包：

| format | 委托给 |
| --- | --- |
| `date-time` | `rfc3339-validator` |
| `time` | `rfc3339-validator`（前面拼一个 `1970-01-01T`） |
| `uri` / `uri-reference` / `iri` / `iri-reference` | `rfc3987` |
| `hostname` | `fqdn` |

`jsonschema/_format.py` 调它们的方式就是本工程 `run.py` 里 `check()` 的四行：`validate_rfc3339(instance.upper())`、`FQDN(instance, min_labels=1).is_valid`、`rfc3987.parse(instance, rule=...)`。

## 运行

```
python -B run.py --test
```

只依赖标准库，不联网、不写文件。`--emit DIR` 会把两组结果写成 JSON。

`--test` 跑两组：

- **before**：按照当前发布版的行为，裸值与「裸值 + 换行」都被接受（14 条）；
- **guard**：在每次委托前加一句 `value.endswith("\n")` 守卫，裸值仍被接受、带换行的被拒（14 条）。

两组都与预期相符时输出 `ALL PASS`，否则逐条列出不符。

## 快照来源

`vendor/` 下的文件是从 PyPI 安装后原样复制的发布版文件，没有改动：

| 包 | 版本 | 文件 | SHA-256 |
| --- | --- | --- | --- |
| rfc3339-validator | 0.1.4 | `rfc3339_validator.py` | `c220cb9495da5215a53ab173f695060294df2d1042a9cbaaf0cc622bcba09d6e` |
| rfc3987 | 1.3.8 | `rfc3987.py` | `08acc2fd747608624a32c4184176df62cfdb5da9d78ad8dd4f4108ac96c541f2` |
| fqdn | 1.6.0 | `fqdn/__init__.py` | `b155327abdb6041e2941aa07eaf3b8e3ebc4f557aa1ad516968046a477ef5403` |
| fqdn | 1.6.0 | `fqdn/_compat.py` | `b627858d2b709b4b68a031fd8219dd01df838324a22b87f58a6e1ca6f31c71d8` |
| fqdn | 1.6.0 | `fqdn/py.typed` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`（空文件） |

许可证随包放在 `vendor/LICENSES/`：`rfc3339-validator` 为 MIT，`fqdn` 为 MPL-2.0，`rfc3987` 为 GPL-3.0-or-later（`COPYING.txt`）。

## 与真库的核对

本工程复刻的是调用方式，不是 `jsonschema` 本身。把 14 条实例交给 `jsonschema 4.26.0` 的 `Draft202012Validator.FORMAT_CHECKER`，逐条与本工程的判定比较，14 条全部一致；核对脚本与输出在仓库的 `.yan/jsonschema-format/` 下（`crosscheck.py` 与 `runs/crosscheck-20261121.txt`）。
