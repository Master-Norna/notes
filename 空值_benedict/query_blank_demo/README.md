# python-benedict #604：查询串里的空值被丢掉

用未修改的 benedict 上游源码，对照 `from_query_string` / `to_query_string` 对空值（`a=`）的处理，观察键是否保留以及往返是否稳定。

## 固定版本

| 对照 | benedict 源码提交 |
| --- | --- |
| before：#604 的实际直接父提交 | `c36e48c6a6b6ef60c6dbf4e0572d23efcb545ab5` |
| after：#604 合并提交 | `5cb4922f285baddf9c9ee1612a67a0ef1d370efb` |

来源：[PR #604](https://github.com/fabiocaccamo/python-benedict/pull/604)、[父提交](https://github.com/fabiocaccamo/python-benedict/commit/c36e48c6a6b6ef60c6dbf4e0572d23efcb545ab5)、[合并提交](https://github.com/fabiocaccamo/python-benedict/commit/5cb4922f285baddf9c9ee1612a67a0ef1d370efb)。

`vendor/before/benedict`、`vendor/after/benedict` 各是两版 `benedict/` 包的完整副本，附 MIT `LICENSE`。`provenance.json` 记录 tarball 地址与 SHA-256、每个源码文件的 SHA-256。

## 环境与准备

已在 Windows、Python 3.12.14 上验证。benedict 导入时会加载全部序列化器，需要以下依赖（版本不限，实测版本见括号）：

```powershell
python -m pip install python-slugify typing_extensions openpyxl xlrd PyYAML tomli-w ftfy mailchecker phonenumbers python-dateutil python-fsutil
```

`run.py` 不会安装依赖，也不会联网。

## 运行

```powershell
python run.py --test
```

每个用例在独立解释器（`-I -B -X utf8`）里跑，`sys.path` 只指向其中一版。`--json results.json` 可把原始结果写到文件。

## 预期结果

| 用例 | before | after |
| --- | --- | --- |
| `empty_and_value`（`a=&b=2`） | `{'b': '2'}` | `{'a': '', 'b': '2'}` |
| `single_empty`（`a=`） | `{}` | `{'a': ''}` |
| `trailing_empty`（`a=1&b=`） | `{'a': '1'}` | `{'a': '1', 'b': ''}` |
| `roundtrip_empty` | 编码 `a=`，解码回 `{}` | 解码回 `{'a': ''}` |
| `roundtrip_mixed` | 编码 `a=&b=2`，解码回 `{'b': '2'}` | 解码回 `{'a': '', 'b': '2'}` |
| `bracket_empty`（`a[b]=&a[c]=2`） | `{'a': {'c': '2'}}` | `{'a': {'b': '', 'c': '2'}}` |
| `encoded_space`（`a=%20&b=+`） | `{'a': ' ', 'b': ' '}` | 同左 |
| `missing_equals`（`a&b=2`） | `ValueError` | `ValueError` |

## 说明

本工程只覆盖 `benedict.from_query_string` / `format="query_string"` 这一个序列化器，不涉及 JSON、YAML、TOML 等其他格式。多值键仍只取第一个值，这是 `_parse_bracket_notation` 的既有行为。
