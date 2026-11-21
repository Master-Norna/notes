# `http://foo.bar/\n` 过了 jsonschema 的格式校验，`urllib` 却把它当成另一个地址

`jsonschema.Draft202012Validator.FORMAT_CHECKER.conforms("http://foo.bar/\n", "uri")` 返回 `True`。同一个字符串交给 `urllib.parse.urlsplit`，换行被悄悄删掉，得到的是 `http://foo.bar/`；交给 `http.client`，请求行里带换行直接抛 `InvalidURL`。

三个组件，三种看法。而且不止 URI：`date-time`、`time`、`uri`、`uri-reference`、`iri`、`iri-reference`、`hostname` 七个 format 都会放行末尾多出来的一个换行（U+000A）。

先说清楚前提：`format` 在 JSON Schema 里默认只是注解。只有把 `format_checker` 显式交给 validator，这些检查才会真的跑。下面说的都是「已经开了 format 校验」的情形。

## 官方套件已经说这些值非法

2026 年 8 月到 9 月，JSON-Schema-Test-Suite 给这七个 format 逐个补了「尾随换行 invalid」的用例：date-time [#959](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/959)（8 月 3 日）、hostname [#1023](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1023)（8 月 4 日）、iri [#1067](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1067)（8 月 13 日）、uri-reference [#1083](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1083) 与 iri-reference [#1144](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1144)（8 月 24 日）、time [#1135](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1135)（8 月 25 日）、uri [#1169](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1169)（9 月 3 日）。10 月 hostname 又补了一条空白字符的用例（[#1226](https://github.com/json-schema-org/JSON-Schema-Test-Suite/pull/1226)）。这些 PR 是同一轮清理：在这之前，套件里没有一条 `data` 含换行的 format 用例，末尾多一个换行这种「看起来对、实际不对」的形状一直没被断言过。

用例本身很短，比如 URI 那条是 `"http://foo.bar/\n"`、`valid: false`；date-time 那条是 `"1985-04-12T23:20:50Z\n"`、`valid: false`。同一份文件里，去掉换行的原值仍然是 `valid: true`。也就是说，套件认定的问题就是末尾那一个 `\n`，不是别的。

把这几条交给 jsonschema 4.26.0（当前 PyPI 最新版）的 `Draft202012Validator.FORMAT_CHECKER`，结果是这样：

| format | 套件里的值 | 套件判 | 4.26.0 判 |
| --- | --- | --- | --- |
| `date-time` | `"1985-04-12T23:20:50Z\n"` | 非法 | 合法 |
| `time` | `"08:30:06Z\n"` | 非法 | 合法 |
| `hostname` | `"example.com\n"` | 非法 | 合法 |
| `uri` | `"http://foo.bar/\n"` | 非法 | 合法 |
| `uri-reference` | `"/p\n"` | 非法 | 合法 |
| `iri` | `"http://ƒøø.ßår/\n"` | 非法 | 合法 |
| `iri-reference` | `"/âππ\n"` | 非法 | 合法 |

七条全部判成合法——和套件的结论正好相反。`main` 上 `_format.py` 最近一次改动停在 2026 年 10 月 4 日的 `84bae0ea`，到 11 月 16 日也没有加过针对尾随换行的守卫。

## 三条委托链，收尾都用了 `$`

jsonschema 自己没有写这些格式的语法。`date-time` 交给 `rfc3339-validator`，`time` 在值前面拼一个 `1970-01-01T` 之后复用同一条路，URI 与 IRI 的四个 format 交给 `rfc3987`，`hostname` 交给 `fqdn`。

三处收尾各是一行：

- `rfc3339_validator.py:32`，`RFC3339_REGEX` 的最后是 `$`；
- `rfc3987.py:424`，`get_compiled_pattern('^%%(%s)s$' % rule).match(string)`；
- `fqdn/__init__.py:30`，`PREFERRED_NAME_SYNTAX_REGEXSTR` 以 `[.]?$` 结尾。

三个包、三段时间，写的都是同一个形状。原因不在谁抄了谁，在 Python 正则里 `$` 的含义本身。

![`$` 停在换行之前，`\Z` 要求真正的串尾](assets/dollar-vs-Z.png)

## `$` 不是字符串结尾

Python 的 `re` 里，`$` 匹配「字符串末尾，或者末尾换行符之前」。所以：

```python
import re
re.match(r"^1985-04-12T23:20:50Z$",  "1985-04-12T23:20:50Z\n")  # match
re.match(r"^1985-04-12T23:20:50Z\Z", "1985-04-12T23:20:50Z\n")  # None
re.fullmatch(r"1985-04-12T23:20:50Z", "1985-04-12T23:20:50Z\n") # None
```

`$` 的锚点落在 `Z` 与 `\n` 之间，正则只要吃到 `Z` 就算成功，换行留在匹配之外；`\Z` 只认真正的串尾，换行还没被吃掉，所以匹配失败。

这解释了两个容易看漏的细节。第一，`\r\n` 结尾的值会被拒：`$` 只认 `\n` 这一个字符，`\r` 卡在锚点前面，正则吃不掉它。第二，前面多一个空格也会被拒，因为 `^` 后面立刻要求四位年份。放行的只有末尾恰好一个 `\n` 这一种形状，非对称得很。

`$` 在 `re.MULTILINE` 下还会匹配每一行的行尾，范围更宽。这三处都没有开 `MULTILINE`，所以只漏掉最后那一个换行。

Python 3.14 起，标准库补了一个 `\z`，文档写的是「只匹配字符串末尾」，`\Z` 保留为它的兼容别名。三个包里写的 `$` 是老写法，在 3.14 上语义也没有变——它仍然在末尾换行之前收尾。

## 同一个库里的反例

jsonschema 并不是所有 format 都这样。同一份 `_format.py` 里：

`date` 用 `_RE_DATE.fullmatch`，再交给 `date.fromisoformat`；`uuid` 用 `UUID()` 解析，再检查四个连字符的位置；`duration` 交给 `isoduration.parse_duration`，最后要求值以 `D`、`M`、`Y`、`W`、`H`、`S` 之一结尾。这三个在矩阵里都拒绝了尾随换行。

`duration` 那条值得看一眼：它挡住换行不是因为校验了换行，而是因为「最后一个字符必须是单位字母」这个额外条件把 `\n` 排除了。换句话说，同一个库里，收尾写成 `fullmatch`、交给真正的解析器、或者加一条末尾条件，结果都不同；写成 `$` 的三条链，就都放行了。

`email` 是另一个方向：jsonschema 的 `is_email` 只检查字符串里有没有 `@`，比 `$` 还宽——套件里 `"test@iana.org\n"` 那条用例同样判非法，jsonschema 会放行，而且它放行的远不止这一条。

## 下游看到的是什么

这类值大多不是手敲进去的。按行读文件时 `readline()` 会把行尾的 `\n` 一起带回来，`subprocess` 抓到的输出、按行切开的日志字段、从别处复制来的配置值，都可能以「值 + 换行」的形状出现。校验器放行之后，真正消费它的组件并不会跟着宽容：

| 消费者 | 输入 | 结果 |
| --- | --- | --- |
| jsonschema `format: uri` | `http://foo.bar/\n` | 通过 |
| `urllib.parse.urlsplit` | 同上 | `path` 为 `/`，`geturl()` 为 `http://foo.bar/`（换行被删） |
| `http.client.putrequest` | 请求目标 `/\n` | `InvalidURL: URL can't contain control characters` |
| `http.client.putheader` | 头部值 `example.com\n` | `ValueError: Invalid header value` |
| `datetime.fromisoformat` | `1985-04-12T23:20:50Z\n` | `ValueError: Invalid isoformat string` |
| `json.dumps` | 任何带尾随换行的值 | 转义成 `\\n`，日志里看不出来 |

`urlsplit` 那一行是这次最值得记的：它在解析前会删掉 `\t`、`\r`、`\n` 三个字节（`_UNSAFE_URL_BYTES_TO_REMOVE`，为的是对齐浏览器的容错行为）。所以 `"http://foo.bar/a\nb"` 解析出来是 `http://foo.bar/ab`——**斜杠后面那一格的内容变了**，不是报错，是静默变成了另一个地址。校验器看到的是 A，下游拿到的是 B。

`json.dumps` 那一行则解释了为什么这类值不容易在日志里被发现：换行被转义成两个字符 `\n`，日志上是一条完整的 JSON。

## 自查

如果要确认自己的服务里有没有这条路，最直接的是把七个 format 连同裸值一起跑一遍：

```python
from jsonschema import Draft202012Validator

FC = Draft202012Validator.FORMAT_CHECKER
CASES = {
    "date-time": "1985-04-12T23:20:50Z",
    "time": "08:30:06Z",
    "hostname": "example.com",
    "uri": "http://foo.bar/",
    "uri-reference": "/p",
    "iri": "http://ƒøø.ßår/",
    "iri-reference": "/âππ",
}
for fmt, value in CASES.items():
    v = Draft202012Validator({"format": fmt}, format_checker=FC)
    print(fmt, v.is_valid(value), v.is_valid(value + "\n"))
```

当前版本上，七行的第二列都是 `True`。同样的 14 条也放在本仓库的 `格式尾随换行_jsonschema/trailing_newline_demo/` 里，`run.py --test` 会把「按现在的行为」与「加一行守卫之后」两组结果并排打出来。

有一个容易踩的细节：`FormatChecker()` 与 `Draft202012Validator.FORMAT_CHECKER` 不是同一套。前者复制的是类级注册表，同名 checker 以后注册的为准，`time` 落到 draft3 的 `%H:%M:%S` 解析上；后者按 draft 分开注册，`time` 才是 RFC 3339 那条链。自查要用后者，或者直接用带 `format_checker` 的 validator。

## 修法

修法有两种粒度。一种是三个包各自把收尾从 `$` 改成 `\Z`（或者 `fullmatch`）；另一种是在 `jsonschema/_format.py` 的委托前加一处形状守卫，七个 format 共用。后一种更集中，因为三个包的维护节奏不同，而套件的用例已经先一步收紧了。

改 `$` 为 `\Z` 是最小的改法：`rfc3987` 的 pattern 是 `'^%%(%s)s$'` 这样拼出来的，只动末尾一个字符；`fqdn` 有两份 pattern（一份允许下划线），两份都要改。`fullmatch` 更彻底，但要把 pattern 开头的 `^` 一并去掉，对拼接式的 pattern 来说反而动得多。形状守卫则不动上游包，只在调用前多一次 `endswith` 判断——代价是每个委托点都要记得加。

三个包的发布节奏也影响改在哪一侧：rfc3987 的 1.3.8 停在 2018 年，rfc3339-validator 的 0.1.4 停在 2021 年，fqdn 的 1.6.0 是 2026 年 9 月发的。两个多年没动的包，要它们为这条边单独发版不太现实。

`trailing_newline_demo/run.py --test` 里两组结果是这样的：

- 按发布版的行为，七个 format 的裸值与「裸值 + 换行」共 14 条全部被接受；
- 在每次委托前加一句 `value.endswith("\n")` 之后，七条裸值仍被接受，七条带换行的全部被拒。

两组都符合预期时输出 `ALL PASS`。工程里 vendor 的是三个包的发布版文件（rfc3339-validator 0.1.4、rfc3987 1.3.8、fqdn 1.6.0），许可证随附；把同样的 14 条交给真正的 jsonschema 4.26.0，判定与本工程逐条一致。

上游：`python-jsonschema/jsonschema`，[#1588](https://github.com/python-jsonschema/jsonschema/issues/1588)。
