# skylos #1228 复现：预过滤器与规则的两份词表

`skylos/rules/danger/danger.py` 的 `scan_file_with_tree()` 先用一段文本预筛决定要不要跑
`scan_python_security_gaps()`。#1228 父提交的预筛只认 `"match ("`、`"merge ("`、`"create ("`
三个字面量，各带一个空格；规则在另一个文件里，`_CYPHER_PATTERN` 用 `\s*` 接受任意空白。
`MATCH(`、`MATCH  (`、`MATCH\n(` 因此进不了扫描。三个字面量和 `SKY-D211` 是 #1227 当天加的，
5.6.0 里还没有它们。

本工程取两版 `python_security_gaps.py`（以及它导入的两个模块），把两版 `danger.py` 的入口
条件逐字抄出来，对同一组源码文件比「预筛放不放行」与「规则报不报」。

## 运行

```console
python -B run.py --test
```

Python 3.11+，只用标准库。另有一条测量命令，对一棵 Python 源码树统计三种匹配各命中多少文件：

```console
python -B run.py --measure <directory>
```

## 目录

- `vendor/parent/skylos/rules/danger/`：父提交 `311cfdf30ce4f92983a8a880fdc5fea88e056047` 的
  `python_security_gaps.py`、`untrusted_sources.py`、`module_namespace.py` 逐字拷贝；`__init__.py`
  置空，只保留这三个文件。
- `vendor/merged/skylos/rules/danger/`：合并提交 `017365e64b19109199fc9d037c80b7f795e2087b` 的同名文件。
- `run.py`：`_has_any` 与两个 `prefilter` 函数逐字提取自两版 `danger.py` 的 `scan_file_with_tree()`
  （父版 `:625-681`，合并版 `:625-683`）。
- `vendor/LICENSE`：上游 Apache-2.0。

两版 `python_security_gaps.py` 都靠 `sys.path` 切换后重新导入；同名模块在两次加载之间从
`sys.modules` 清掉，两个版本各自的函数对象互不影响。

## 输出

`--test` 打四张表：

- 11 个源码文件，每个是一整段文件文本，列出父版预筛、PR 第一版 hint、合并版 hint 是否放行，
  以及规则本身报出几条 `SKY-D211`；
- 同一段源码加一行 `import requests` 后父版是否放行；
- 五个形似调用（`re.match (`、`db.create(obj)`、`def create (name)` 等）两边是否放行；
- 第一版 hint 与合并版 hint 在 `label = '<N spaces>'` 上的耗时，N 从 500 到 8000，每档连跑三次取最快。

断言：父版只放行标准写法，合并版放行全部 11 个，规则对 11 个各报 1 条；加 `requests` 后父版
放行；`re.match (` 与 `def create (` 父版放行、合并版不放行；8000 个空格上合并版低于 2 ms，
第一版从 4000 到 8000 增长约 4 倍。

## 快照来源

两版 tarball 从 `https://codeload.github.com/duriantaco/skylos/tar.gz/<sha>` 取：

| tarball | 字节 | SHA-256 |
| --- | --- | --- |
| `skylos-311cfdf30ce4f92983a8a880fdc5fea88e056047.tar.gz` | 56,664,771 | `6C3C454FDDBDDD0371E076477DFCD58179557447CF4E83C6744C71B98F2D95F7` |
| `skylos-017365e64b19109199fc9d037c80b7f795e2087b.tar.gz` | 56,665,997 | `7449B3462A0D1942F91868A76C85DB1198A3C644D5A7E284A4BCE66D7129C628` |

`vendor/` 下六个源码文件与 tarball 里的成员逐字节相同（LF 换行，未做转换）：

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `parent/skylos/rules/danger/python_security_gaps.py` | 50,540 | `971ad77ca6cd1febc259cbbbeebae60c5f52c914651734d0f84dcabfabc03155` |
| `merged/skylos/rules/danger/python_security_gaps.py` | 51,632 | `0be5328e6d8e4851518bc067b72d13c46787f071563a06bf03219a3d2f9661b3` |
| `parent|merged/skylos/rules/danger/untrusted_sources.py` | 49,916 | `a7a290ca8d48631f0d4f358ee0fdea1b888829259ae7174142f2545410edba06` |
| `parent|merged/skylos/rules/danger/module_namespace.py` | 25,710 | `0e2473dbc3deeb47ebd6e6a621ebfae8c6fcd7540235003a7b8d27f6b7e18272` |

