# 阈值写 0，过滤为什么没关

`find_similar(similarity_threshold=0)` 的文档说，阈值是属性比较的百分比。把它写成 0，就是关闭属性过滤。下面这个页面里，第一个链接没有属性，第二个链接有 `class="sale"`：

```python
page = Selector('<div><a>Alpha</a><a href="/beta" class="sale">Beta</a></div>')
reference = page.css("a")[0]
reference.find_similar(similarity_threshold=0)   # []
```

返回空。Beta 和 Alpha 同 tag、同深度、同父级，结构筛选已经把它选进来了；属性过滤写 0 本该放行，它却在这里被丢掉。

## 结构筛过一遍，属性只是最后一步

`find_similar` 分两段工作。第一段是结构预筛：用 XPath 找同 tag、同深度、同父/祖父 tag 的元素（[1025-1084 行](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/scrapling/parser.py#L1025-L1084)）。第二段才是 `__are_alike`，按属性值算相似度，和阈值比较。

0 阈值关闭的是第二段。第一段已经认定"这些是同层同构的候选"，第二段没有理由把它们全清空。

## `checks` 是分母，有三种来源

`__are_alike` 把每个比较项的相似度加进 `score`，同时数 `checks` 作分母。`checks` 怎么来，取决于参考元素有没有属性：

| 参考属性 | 候选属性 | `checks` | `score` | 旧代码结果 |
| --- | --- | --- | --- | --- |
| 有 | 任意 | `max(len(original), len(candidate))` | 各属性相似度之和 | 按分数比较阈值 |
| 无 | 无 | 1 | 1 | 100%，通过 |
| 无 | 有 | 0 | 0 | `False`，不管阈值 |

前两行都有分数可算。第三行没有：参考没有属性，就没有"键"可以拿去和候选的 `class="sale"` 比较，`checks` 停在 0。

旧代码在 [1020-1022 行](https://github.com/D4Vinci/Scrapling/blob/49eaff11da8de7c8067cf048a5dc3e0f95b53715/scrapling/parser.py#L1020-L1022)收尾：

```python
if checks:
    return round(score / checks, 2) >= similarity_threshold
return False
```

**`checks == 0` 不是"不相似"，是"没有可比的属性"。** 旧代码把它直接判死，绕过了阈值。于是 0 阈值下出现一个奇怪的分裂：有属性但完全不相似的候选能过（分数 0，`0 >= 0` 为真），没有属性可比的候选反而过不了。这不是阈值的语义，是哨兵值的语义。

## 前史：`max` 修的是另一个方向

这个分母不是第一次被改。2026 年 6 月的 [#322](https://github.com/D4Vinci/Scrapling/issues/322) 报告了另一个方向的问题：分母用 `len(candidate_attributes)`，候选属性比参考少时分母偏小，分数被抬高。维护者在 issue 里回复：

> using `len(candidate_attributes)` is intentional. It penalizes candidates who have extra attributes not present in the original element, making them less "alike". ... when the candidate has fewer attributes than the original, the score gets inflated instead of penalized ... The correct fix ... is: `checks += max(len(original_attributes), len(candidate_attributes))`

[`9c0c857`](https://github.com/D4Vinci/Scrapling/commit/9c0c857245726352a8502b1e4822a444ade96543) 按这个写法落地。`max` 同时保住两个方向：候选多一个属性时，分母变大，分数被压低；候选少一个属性时，分母不缩小，分数不会虚高。

但 `max` 只在 `original_attributes` 非空时执行。参考没有属性时，代码走的是 `else` 分支，根本不进 `max`。**`max` 修好了分母偏小，但没有管到分母为零。** #539 补的是这一格。

## 修法：把 0 分交给阈值

[\#539](https://github.com/D4Vinci/Scrapling/pull/539) 的修复只有一行：把 `return False` 换成 `return 0 >= similarity_threshold`。

不是 `return True`，因为正阈值仍然要排除这类候选：参考没有属性、候选有 `class`，相似度就是 0；阈值 0.2 时 `0 >= 0.2` 为假，Beta 不该出现。只有 0 阈值才放行。这样"没有可比属性"被定义成一个分数（0），而不是一个提前返回的结论；阈值仍然做它该做的判断。

文档里还有一句话：两边都没有属性时是 100% 匹配。那是有分母的那一格——`score += 1; checks += 1`。这次补的是它的反面：分母数不出来的时候，分数是 0，不是"不算"。两句话合起来，属性比较这一段的取值才算闭合。

## 什么情况下才会踩到

四个条件得同时成立：

- 阈值真的传了 0。`find_similar` 的默认值是 `0.2`；库内唯一一次调用出现在 Scrapy 集成的文档示例里（[`integrations/scrapy.py:69`](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/scrapling/integrations/scrapy.py#L69)），用的就是默认值，走不到这条分支。踩到的一定是显式传 0 的人。
- 参考元素没有可比较的属性。`ignore_attributes` 默认是 `("href", "src")`，所以 `<a href="/alpha">Alpha</a>` 这种元素也算"没有属性"——它唯一的属性被忽略了。
- 候选元素有属性。候选也是先减掉忽略列表再比，所以候选身上得有 `class`、`id` 这类留下来的东西。
- `match_text` 是默认的 `False`。打开文本比较后 `checks` 至少加 1，`if checks` 那一支根本轮不到。

四个条件凑齐的场景不算罕见：导航条里除了当前项，其余链接都只有 `href`（默认被忽略）。拿第一个链接当参考去找同类，当前项带着 `class="active"`，0.2 会把它漏掉；想要"同类链接一个不漏"，就得把阈值写成 0。文档在 [`similarity_threshold` 那一段](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/scrapling/parser.py#L1041-L1046)自己也说，预筛出来的元素"99% likely to be correct"，属性比较只是最后一道——0 正是"我信任结构"的写法。

## 十四行矩阵

复现工程用两个固定提交的 `parser.py` 跑同一组页面：7 个案例，每个案例两个阈值，共 14 行。页面都是 `<div class="list"><a 参考>Alpha</a><a 候选>Beta</a></div>`，取第一个链接做 `find_similar`。

| 案例 | 阈值 | 修前 | 修后 |
| --- | ---: | --- | --- |
| 参考无属性，候选 `class="sale"` | 0 | `[]` | `['Beta']` |
| 同上 | 0.2 | `[]` | `[]` |
| 参考只有 `href`（默认忽略），候选多 `class` | 0 | `[]` | `['Beta']` |
| 同上 | 0.2 | `[]` | `[]` |
| 两边都无属性 | 0 | `['Beta']` | `['Beta']` |
| 同上 | 0.2 | `['Beta']` | `['Beta']` |
| 两边同类名 `class="product"` | 0 | `['Beta']` | `['Beta']` |
| 同上 | 0.2 | `['Beta']` | `['Beta']` |
| 参考 `class="product"`，候选多 `id="x"` | 0.5 | `['Beta']` | `['Beta']` |
| 同上 | 0.6 | `[]` | `[]` |
| 类名不同 `product` / `deal` | 0 | `['Beta']` | `['Beta']` |
| 同上 | 0.2 | `[]` | `[]` |
| `ignore_attributes=()`，`href` 参与比较 | 0 | `['Beta']` | `['Beta']` |
| 同上 | 0.2 | `[]` | `[]` |

跑一遍：

```powershell
.venv/Scripts/python run.py --test
```

末尾三行：

```text
rows: 14
before: 2 mismatches
after:  0 mismatches
```

修前 2 行不符，修后 0 行。

## 只有两行变了

14 行里修前修后不一样的只有两行：`no attrs vs class` 和 `href only vs class` 在阈值 0 时从 `[]` 变成 `['Beta']`。其余 12 行一个字节没变。

最像的那一行反而没变：`class="product"` 对 `class="deal"` 的相似度是 0，分母是 1，`0 >= 0` 在旧代码里也成立，修前就返回 `['Beta']`。**旧代码丢的不是"0 分"，而是"没有分母的 0 分"**——这也解释了 bug 为什么藏得住：绝大多数 0 分路径本来就是对的。

最后两行是反过来的对照：把 `ignore_attributes` 传成 `()`，`href` 参与比较，`"aaa"` 对 `"zzz"` 同样得 0 分，但因为有分母，修前修后都对。同样是"0 分"，有没有分母，结果分到了两边。

## 上游的测试怎么写的

PR 里的测试是参数化的，两行装饰器把两种参考元素和两个阈值铺成四个用例（[`tests/parser/test_find_similar_advanced.py`，35-37 行](https://github.com/D4Vinci/Scrapling/blob/104294c2d87abe35898327ae788826a3a79887bf/tests/parser/test_find_similar_advanced.py#L35-L37)）：

```python
@pytest.mark.parametrize("reference_attributes", ["", 'href="/alpha"'])
@pytest.mark.parametrize("threshold, expected", [(0, ["Beta"]), (0.2, [])])
def test_find_similar_zero_threshold_without_reference_attributes(
    self, reference_attributes: str, threshold: float, expected: list[str]
) -> None:
    """A zero threshold disables attribute filtering even without scored attributes."""
```

docstring 那句就是维护者对契约的表述：0 阈值关掉属性过滤，"没有可打分属性"也算在内。两种参考元素正好覆盖正文里的前两条——真的没有属性，和只有 `href`。

0 不是"降低门槛"，是"关掉这一步"。关掉之后，剩下的判断只有结构预筛那一层——它本来就在文档里被描述成 99% 靠得住。旧代码在最后一步又替它做了一次决定，依据却是一个哨兵值：分母数不出来，就当不相似。

完整的页面构造、两版快照来源和运行方式在 `threshold_demo/README.md`，这次运行的完整输出在 `.yan/scrapling-threshold/runs/scrapling-demo-publish-20261103.txt`。
