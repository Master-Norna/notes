# `a=` 和没有 `a`，差的是一个空字符串

一次查询串往返：

```python
from benedict import benedict

benedict({"a": ""}).to_query_string()   # 'a='
benedict.from_query_string("a=")        # {}   ← 修前
```

编码那一侧把 `{"a": ""}` 写成 `a=`，解码那一侧把 `a=` 读成「没有这个键」。同一个库，两个方向对空值的看法不一致。

混在一串参数里更常见：

```python
benedict.from_query_string("a=&b=2")    # {'b': '2'}            ← 修前
benedict.from_query_string("a=&b=2")    # {'a': '', 'b': '2'}   ← 修后
```

[python-benedict #604](https://github.com/fabiocaccamo/python-benedict/pull/604)，改动一行：给 `parse_qs` 加 `keep_blank_values=True`——这个参数默认是 `False`。

## `a` 和 `a=` 是两件事

查询串里，`a` 只有一个键名、没有等号，benedict 当场判它非法（后面 `missing_equals` 那组就是它）；`a=` 有键、有等号，值是空字符串。表单里留空的可选字段、清空后仍要提交的搜索框，发出去都是后面这种。`urlencode({"a": ""})` 也输出 `a=`，而不是把键省掉。

benedict 的编码用的就是 `urlencode`：

```python
data = urlencode(d, **kwargs)
```

出去的一侧没有歧义。问题全在回来的路上。

标准库把选择权交给调用方。`parse_qs` 的文档写明：`keep_blank_values` 为真时，百分号编码查询里的空值保留成空字符串；为假（默认）时，空值被忽略，当作没有包含这个键。也就是说 Python 不替谁决定哪种语义更对，只要求读之前先站一边。

## 校验放行，解析丢弃

`QueryStringSerializer.decode` 分两步（`benedict/serializers/query_string.py:59`）。第一步用正则逐段校验：

```python
pair_re = re.compile(r"^[^\s=&]+=[^\s&]*$")
pairs = s.split("&")
if pairs and not pairs[-1]:
    pairs = pairs[:-1]
if all(pair_re.match(pair) for pair in pairs):
    data = parse_qs(s)          # 父提交的写法；合并版这里是 keep_blank_values=True
    return self._parse_bracket_notation(data)
raise ValueError(f"Invalid query string: {s}")
```

`=` 后面那个 `*` 允许零个字符，`a=` 过得去。正则上方的注释写着 value 只需避开空白和 `&`，没要求至少一个字符。校验这一侧的意图是留。同一段代码里，`pairs[:-1]` 还顺手放行了尾部多一个 `&` 的写法——`a=1&` 一直算合法。

第二步 `parse_qs(s)` 用的是标准库默认值。`keep_blank_values=False`，值为空的键不进结果。

同一段输入，前一步判它合法，后一步把它扔掉。

于是 `a=` 的结果是 `{}`。嵌套写法也一样：`a[b]=&a[c]=2` 只剩 `{'a': {'c': '2'}}`。

## 改在第二个调用上

合并版只动了一行（`:76`），上面留了句注释，说 `pair_re` 本来就接受空值，保留下来才前后一致：

```python
data = parse_qs(s, keep_blank_values=True)
```

`parse_qs` 于是把 `a=` 解析成 `{'a': ['']}`，`_parse_bracket_notation` 对普通键取 `values[0]`：

```python
else:
    result[key] = values[0]
```

得到 `''`。嵌套键走另一条分支，`a[b]=` 变成 `{'a': {'b': ''}}`。这个函数一行没改，它的 docstring 里那句「普通键总是返回标量字符串」也照旧成立。

对齐这两处，另一个方向也能走：让 `pair_re` 拒掉空值，跟 `parse_qs` 的默认站到一边。代价是 `a=` 从此算非法查询串，而 `benedict({"a": ""}).to_query_string()` 写出来的正是它——编码器的输出，解码器拒收。这个 PR 选的是反方向：让解析跟着校验走。

## 八组输入

```text
== empty_and_value     before {'b': '2'}            after {'a': '', 'b': '2'}
== single_empty        before {}                    after {'a': ''}
== trailing_empty      before {'a': '1'}            after {'a': '1', 'b': ''}
== roundtrip_empty     before decoded {}            after decoded {'a': ''}
== roundtrip_mixed     before decoded {'b': '2'}    after decoded {'a': '', 'b': '2'}
== encoded_space       before {'a': ' ', 'b': ' '}  after {'a': ' ', 'b': ' '}
== bracket_empty       before {'a': {'c': '2'}}     after {'a': {'b': '', 'c': '2'}}
== missing_equals      before ValueError            after ValueError
```

`encoded_space` 是 `a=%20&b=+`，两版都解成空格，`keep_blank_values` 不碰百分号解码。`missing_equals` 是 `a&b=2`，两版都抛 `ValueError`——修复没有放宽「每个键必须有等号」这条规则。`roundtrip_empty` 是最直接的验收：`{'a': ''}` 编码成 `a=`，解回来仍是 `{'a': ''}`。`bracket_empty` 说明嵌套里的空值也留住了。

真正意外的是同一个键出现多次。`a=&a=1` 修前得到 `{'a': '1'}`，修后得到 `{'a': ''}`。`_parse_bracket_notation` 一直只取 `values[0]`：修前第一个值是被 `parse_qs` 丢掉的空串，排在后面的 `1` 顶上来；修后第一个值保住了。顺序第一次开始算数。

数组写法不在这次范围里。`a[]=` 修前是 `{}`，修后是 `{'a': ['']}`——列表，不是字符串，走的是 `_parse_bracket_notation` 的数组分支。既有行为，本次没动，也没算进 `--test` 的断言。上面这两条和 `a=1&`（尾部空段，两版都是 `{'a': '1'}`）是另跑探针拿到的，不在这八组里。

`--test` 按用例逐条断言，用的就是这些 JSON。`missing_equals` 那条只断言两版都失败（`ok` 为假）；报错文字两版都是 `Invalid query string: a&b=2`，是看输出对上的，不在断言里。

## 影响面是一条路

benedict 读查询串有两个入口：

```python
benedict.from_query_string("a=&b=2")          # 静态方法
benedict("a=&b=2", format="query_string")     # 构造函数
```

后者转调前者（`io_dict.py` 里 `from_query_string` 就是 `cls(s, format="query_string")`），一处修复两边都通。JSON、YAML、TOML、XML 那些序列化器不走这段代码，空字符串在它们里本来也没有「被当成缺失」的规则。

依赖旧行为的代码会看到多出来的键。修前要空值语义只能自己预处理——把 `a=` 换成占位符、读完再换回来，或者绕开 benedict 直接调 `parse_qs(s, keep_blank_values=True)`。修后这条绕路可以省掉，代价是 `a=&b=2` 从 `{'b': '2'}` 变成 `{'a': '', 'b': '2'}`。有意的行为变化。

落到具体调用上，差的是这一行：`d.get("a", "默认值")`。修前返回 `'默认值'`，`"a" in d` 是 `False`，字典长度 1；修后返回 `''`，`"a" in d` 是 `True`，长度 2。默认值和空串，在「参数没填」和「参数填了空」本来就该分开处理的接口里，是两个分支。

## 三步都正常返回

`a=` 进来，正则通过，`parse_qs` 返回 `{}`，`_parse_bracket_notation` 对空字典返回空字典，`decode` 正常返回。没有异常、没有警告、没有一条日志。

两个组件各自都合理：`pair_re` 的作者想留空值，`parse_qs` 的默认值想滤空值；放进同一个函数，谁也没错。断口在往返上——编码器写出去的东西，解码器读不回来。这种错不会自己冒出来，除非测试正好覆盖「空值」这一格。

PR 的 Related issue 一栏写的是 None：这处不一致是读代码时发现的，不是谁报了 bug。补上的回归测试叫 `test_from_query_string_with_empty_values`，就放在原有的 `test_from_query_string_with_trailing_ampersand` 后面——先说「尾部多一个 `&` 也合法」，再说「空值也是值」，顺序上正好接住。测试断言三件事：静态方法读出来是 `{'a': '', 'b': '2'}`；构造函数 `benedict("a=&b=2", format="query_string")` 同样；再 `to_query_string()` 回去，仍是 `a=&b=2`。

还有个容易找错的 API：`parse_qsl`。它返回键值对列表，默认同样丢空值，参数也叫 `keep_blank_values`。这次只改了 `parse_qs` 的调用；将来若有人把实现换成 `parse_qsl`，参数得跟着带过去，否则同样的毛病换个位置回来。

补丁新增 19 行，含测试；生产代码改动一行。

## 复现

工程在 `空值_benedict/query_blank_demo/`，父提交 `c36e48c6` 与合并提交 `5cb4922f` 的 `benedict/` 包原样放在 `vendor/before`、`vendor/after`。每个用例起一个子进程，`sys.path` 只指向其中一版；输入以 JSON 传进去，结果也以 JSON 打回来，两版逐键比对。`--json` 把这一轮的结果连同两个提交号写进文件，留档用：

```text
python run.py --test
```

运行前需要 benedict 的运行时依赖（`python-slugify`、`typing_extensions`，以及导入序列化器时用到的 `openpyxl`、`xlrd`、`PyYAML`、`tomli-w`、`ftfy` 等，见工程 README）。`--test` 断言的是：修前的四组空值输入丢键、修后保留；`encoded_space` 两版一致；`missing_equals` 两版都报错；嵌套空值保留。

## 参考

- python-benedict PR [#604](https://github.com/fabiocaccamo/python-benedict/pull/604)；父提交 [`c36e48c6`](https://github.com/fabiocaccamo/python-benedict/commit/c36e48c6a6b6ef60c6dbf4e0572d23efcb545ab5)、合并提交 [`5cb4922f`](https://github.com/fabiocaccamo/python-benedict/commit/5cb4922f285baddf9c9ee1612a67a0ef1d370efb)。
- 修改文件：[`benedict/serializers/query_string.py`](https://github.com/fabiocaccamo/python-benedict/blob/5cb4922f285baddf9c9ee1612a67a0ef1d370efb/benedict/serializers/query_string.py)、[`tests/dicts/io/test_io_dict_query_string.py`](https://github.com/fabiocaccamo/python-benedict/blob/5cb4922f285baddf9c9ee1612a67a0ef1d370efb/tests/dicts/io/test_io_dict_query_string.py)。
- 标准库：[`urllib.parse.parse_qs`](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.parse_qs)、[`urllib.parse.urlencode`](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlencode)。
