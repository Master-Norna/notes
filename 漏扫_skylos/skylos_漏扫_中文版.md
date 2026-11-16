# `MATCH(` 少一个空格，skylos 跳过了这次安全扫描

```python
def find(graph, name):
    return graph.query(f"MATCH(p:Person {{name: '{name}'}}) RETURN p")
```

`name` 直接拼进 Cypher 的引号里。输入里带一个单引号，查询结构就变了。skylos 为这种写法准备了规则 `SKY-D211`，MEDIUM，消息开头是「a value is interpolated inside a quoted string of the Cypher text, so a quote or backslash in it changes the query」。

2026-11-13 06:37 UTC，[#1227](https://github.com/duriantaco/skylos/pull/1227) 把它合进 `main`。对上面这段代码，它不报。

把 `MATCH(` 改成 `MATCH (`，同一条规则就报了。差别只有一个空格。

八小时后，[#1228](https://github.com/duriantaco/skylos/pull/1228) 来补这个空格。

## 门口那张词表

`skylos/rules/danger/danger.py` 的 [`scan_file_with_tree()`](https://github.com/duriantaco/skylos/blob/311cfdf30ce4f92983a8a880fdc5fea88e056047/skylos/rules/danger/danger.py#L654-L679) 拿到的是一棵解析好的 AST，但它先看源码文本，决定要不要跑 `scan_python_security_gaps()`：

```python
if source is None or _has_any(
    source.lower(),
    (
        "jinja", "requests", "httpx", "urllib", "importlib", "__import__",
        "gradio", "/tmp/", "makedirs", "mkdir", "url_for", "subprocess",
        "shlex", "match (", "merge (", "create (",
    ),
):
    scan_python_security_gaps(tree, file_path, findings, project_root=project_root)
```

16 个词。前 13 个是通用危险词，后 3 个是 Cypher 字面量，各带一个空格。这 3 个是 #1227 当天加 `SKY-D211` 时一起写的，和规则本身住在同一个 PR 里、两个文件里。

规则本身在另一个文件里，[`_CYPHER_PATTERN`](https://github.com/duriantaco/skylos/blob/311cfdf30ce4f92983a8a880fdc5fea88e056047/skylos/rules/danger/python_security_gaps.py#L42-L47) 这么写：

```python
_CYPHER_PATTERN = re.compile(
    r"\b(?:MATCH|MERGE|CREATE)\s*\(\s*\w*\s*(?::|\)|\{)", re.IGNORECASE
)
_CYPHER_START = re.compile(
    r"\s*(?:OPTIONAL\s+MATCH|MATCH|MERGE|CREATE|UNWIND|WITH|CALL)\b", re.IGNORECASE
)
```

`\s*` 接受任意空白：没有、一个、两个、一个换行，都行。**门口的词表只认一个空格，屋里的正则什么都认。** 两份词表各写各的，一份在 `danger.py` 的预筛里，一份在规则文件的正则里。

预筛没命中，`scan_python_security_gaps()` 就不会被调用。这个函数里有 8 个规则 ID：`SKY-D211`、`D212`、`D348`、`D355` 到 `D359`。它们一起不跑——不是少报这一条，是整支跳过。

预筛省的是这次 AST 遍历：`scan_python_security_gaps()` 要为每个文件走一遍树，跑八组检查，一行字符串查找能先把大多数文件挡在外面。被挡掉的这一支里，5 条是 HIGH：命令参数拼接（D212）、共享临时目录（D348）、Jinja 关掉 autoescape（D355）、不可信输入选模块（D357）、Gradio 绑所有接口（D358）。它们和 Cypher 没有关系，但和 D211 坐同一条船。

## 十种写法，十种进不了门

把同一段代码换个 Cypher 拼写，父版预筛放不放行，规则本身报不报（第一行是标准写法，作对照）：

| 写法 | 父版预筛 | PR 第一版 | 合并版 | 规则报 D211 |
|---|---|---|---|---|
| `MATCH (` | 放行 | 放行 | 放行 | 1 |
| `MATCH(` | 挡下 | 放行 | 放行 | 1 |
| `MATCH  (` | 挡下 | 放行 | 放行 | 1 |
| `MATCH` 后换行再接 `(` | 挡下 | 放行 | 放行 | 1 |
| `OPTIONAL MATCH(` | 挡下 | 放行 | 放行 | 1 |
| `MERGE(` | 挡下 | 放行 | 放行 | 1 |
| `CREATE(` | 挡下 | 放行 | 放行 | 1 |
| `f"""MATCH(` | 挡下 | 放行 | 放行 | 1 |
| 三引号后换行，再 `MATCH(` | 挡下 | 放行 | 放行 | 1 |
| `WITH 1 AS one` 换行，再 `MATCH(` | 挡下 | **挡下** | 放行 | 1 |
| 源码里写 `\nMATCH(` | 挡下 | **挡下** | 放行 | 1 |

最后一列是把源码直接交给 `python_security_gaps.scan()` 的结果，绕开预筛。11 行全是 1：规则认得每一种拼写，差别全在门口。

会不会漏，还取决于同一个文件里有没有别的词。纯图查询的服务只 import neo4j 驱动，不碰 `requests`、`subprocess` 这些词，整份文件对预筛来说就是无事发生。在这样一份文件里加一行 `import requests`，父版立刻放行——不是因为 Cypher，是因为 requests。

## 把词表交回给规则

合并版把关键词提出来共享：

```python
_CYPHER_KEYWORDS = "MATCH|MERGE|CREATE"
```

hint 放进规则文件，和两个正则挨着：

```python
_SOURCE_HINT = re.compile(
    rf"(?:(?<![\w.])|(?<=\\[nrt]))(?<!def )"
    rf"(?:{_CYPHER_KEYWORDS})(?:\s|\\[nrt])*\(",
    re.IGNORECASE,
)

def mentions_graph_query(source: str) -> bool:
    return _SOURCE_HINT.search(source) is not None
```

`danger.py` 那边删掉三个字面量，换成 `or mentions_graph_query(source)`。

关键词共享之后，规则文件里的 `_CYPHER_PATTERN` 和 `_CYPHER_START` 也改成用同一个 `_CYPHER_KEYWORDS` 拼出来，以后加一种写法只改这一行。

为什么不直接复用 `_CYPHER_PATTERN`？因为预筛手上是源码文本，规则手上是 AST 解开后的字符串。源码里写着 `f"MATCH(p:Person {{name: ...}})"`，引号、`f` 前缀、双花括号、`\n` 转义都在；AST 里这些都没有了。两个正则面对的是两种输入，词表可以共享，形状不能。

这也是「先粗筛、再精查」这类结构的通病：粗筛要快，往往只写几个字面量；精查要准，写的是完整正则。两处各自演化，中间没有东西保证它们讲同一件事。

## 第一版 hint 的两个洞

第一版把 hint 锚在开引号上，注释里写着理由：`require a string quote first, so ordinary code such as re.match(pattern) or create(...) does not start the scan`。方向是对的——`re.match(` 不该触发扫描——代价是漏掉了没有紧跟在引号后面的写法：

```python
["']{1,3}\s*[^"'\n]*\b(?:MATCH|MERGE|CREATE)\s*\(
```

10 种非标准写法里，第一版放过 8 种，两种过不了。一种是 `WITH 1 AS one` 换行再 `MATCH(`：`\s*` 吃完换行后，`[^"'\n]*` 只能吃到下一个换行前，`\bMATCH` 接不上。另一种是源码里的 `\nMATCH(`：`\n` 在这里是两个字符，`n` 是词字符，`\b` 不成立。

还有一处不是漏报，是慢。`\s*` 和 `[^"'\n]*` 都能吃空格，一段长空格串会让引擎把所有切法试一遍：

![第一版 hint 与合并版 hint 在 `label = '<N spaces>'` 上的耗时](assets/backtrack.png)

8000 个空格，第一版约 0.7 秒，合并版不到 0.5 毫秒；空格每翻一倍，第一版约 4 倍。这组数是同一台机器上连跑三次取最快的一次，数量级不受单次抖动影响。这段代码对每个没命中前 13 个词的 Python 文件都要跑一次。

第二版去掉锚，在全文任意位置找关键词加括号，用两个 lookbehind 排掉普通调用：

- `(?<![\w.])`：前面不能是词字符或点，`re.match(`、`db.create(` 不触发；
- `(?<!def )`：`def create (` 不触发；
- `(?<=\\[nrt])`：前面是源码里的 `\n`、`\r`、`\t` 转义时允许触发，这时本来就没有词边界。

`(?:\s|\\[nrt])*` 只吃空白和这三种转义，没有第二个能跟它重叠的重复，回溯是线性的。

## 反例与精度

| 源码里的一段 | 父版预筛 | 合并版 |
|---|---|---|
| `re.match (name, pattern)` | 放行 | 不触发 |
| `re.match(name, pattern)` | 不触发 | 不触发 |
| `db.create(obj)` | 不触发 | 不触发 |
| `def create (name):` | 放行 | 不触发 |
| `def create(name):` | 不触发 | 不触发 |

`re.match (` 和 `def create (` 父版会放行：`"match ("`、`"create ("` 是纯子串，不看前面是什么。旧词表不只是漏，也会白扫。

宽一点会不会多扫太多？把 `\b(?:MATCH|MERGE|CREATE)\s*\(` 这种无锚定写法用在 skylos 自己的 `skylos/` 包上（1042 个 `.py` 文件），命中 162 个；最终的 hint 命中 10 个。多出来的 152 个里，144 个首个命中是 `_CONVERTER_RE.match(...)` 这类方法调用，8 个是 `merge(...)`，没有一个是 Cypher。那 10 个文件交给规则本身跑一遍，`SKY-D211` 一条也没有。父版的三个字面量在同一棵树上命中 2 个。

这组数就是复现工程里 `python -B run.py --measure <skylos 源码树>/skylos` 的输出：`files 1042`、`merged hint 10`、`wide \b hint 162`、`parent literals 2`。

## 哪些版本带着它

- 5.6.0（2026-11-11 发布）及更早：`python_security_gaps.py` 里没有 `SKY-D211`，预筛里也没有那三个 Cypher 字面量。开头那段代码在 5.6.0 上不报，不是被预筛挡住，是规则还没进来。
- #1227 与 #1228 同在 2026-11-13 进 `main`，相隔不到八小时；PyPI 上最新仍是 5.6.0，所以这个窗口没有随任何发行版出去。下一次发行会同时带上两者，预筛和规则一致。
- 窗口里被跳过的是 `scan_python_security_gaps()` 的 8 个规则 ID，其中 5 条 HIGH。扫描不会因此报错，退出码照常，只是这一支没有输出。

要判断一棵树是不是这个窗口，看 `skylos/rules/danger/danger.py` 的预筛元组：同时有 `"match ("` 和 13 个通用词、又没有 `mentions_graph_query`，就是 #1227 到 #1228 之间的形状。5.6.0 的元组里没有 `"match ("`。

复现工程在仓库 `漏扫_skylos/prefilter_demo/`：`python -B run.py --test` 打出上面的对照表和两种 hint 的耗时，只用标准库；`--measure <dir>` 在任意 Python 源码树上数三种匹配各命中多少文件。

上游：`duriantaco/skylos`，[#1228](https://github.com/duriantaco/skylos/pull/1228)，父提交 [`311cfdf3`](https://github.com/duriantaco/skylos/commit/311cfdf30ce4f92983a8a880fdc5fea88e056047)，合并提交 [`017365e6`](https://github.com/duriantaco/skylos/commit/017365e64b19109199fc9d037c80b7f795e2087b)。
