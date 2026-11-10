# Git 给路径加了引号，这个文件就从 review 里消失了

一个删掉 `@login_required` 的改动，可以从 skylos 的 PR 审查里整条走过去：文件在改动列表里，review 发了，评论里没有安全回归。

同一个 `git diff`，skylos 里有两个地方在解析。[`get_changed_line_ranges`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L299) 挑出这次改动涉及的行，扫描器找到的 finding 按它过滤；[`_get_per_file_diffs`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L427) 把 diff 按文件切开，交给 [`detect_security_regressions`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L500)，由后者看 `@login_required` 这类控制有没有被删。`get_changed_line_ranges` 认路径走 `_new_diff_header_path`，`_get_per_file_diffs` 直接切 `line[6:]`。读错的是后一个。

于是改动范围是对的，普通 finding 也在，只有安全回归这一路没有输入。报告里那一栏是空的；空着和干净，在输出上分不出来。

## `text=True` 和 `line[6:]`

父提交 `7cf919a1` 的 `skylos/cicd/review.py` 里，`_get_per_file_diffs` 读 diff 的方式很直接：

```python
result = subprocess.run(
    diff_cmd,
    cwd=cwd,
    capture_output=True,
    text=True,
    env=read_only_git_environment(),
)
...
for line in result.stdout.splitlines():
    if line.startswith("diff --git"):
        ...
    elif line.startswith("+++ b/"):
        current_file = line[6:]
        current_lines.append(line)
```

两个假定。`+++` 后面一定是 `b/`，第 6 个字符起是路径；`text=True` 拿回来的 stdout 一定是当前 locale 能解码的文本，而 `subprocess` 用通用换行读取，`\r`、`\n`、`\r\n` 都算行边界。

同一个文件里的 [`_parse_unified_diff`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L373) 没有这两个假定。它的 [`_new_diff_header_path`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L410) 处理 Git 的 C 风格引号、TAB 后缀和 `/dev/null`；`get_changed_line_ranges` 也按字节读、显式解码。同一个 diff 格式，两种写法并存。

## diff 被读了两次

一次 `skylos cicd review` 里，[`run_pr_review`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L48) 先把 diff 读一遍：

```python
changed_ranges = get_changed_line_ranges(
    diff_base,
    cwd=review_root,
    raise_on_error=True,
    include_deletion_anchors=False,
)
```

这份 ranges 用来过滤扫描器在整棵树上找到的 finding：落在改动行里的才留下，走的是 [`filter_findings_to_diff`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/skylos/cicd/review.py#L529)。第二遍是安全回归：

```python
regression_findings = _detect_regressions_from_diff(
    diff_base, cwd=review_root, raise_on_error=True
)
```

它要每个文件各自的 diff 文本，才能看出 `@login_required` 这类控制被删掉。`_get_per_file_diffs` 就是为这一步服务的。顺带说，两条命令连 `--unified` 都不一样：`get_changed_line_ranges` 用 `--unified=0`，它只要行号；`_get_per_file_diffs` 用 `--unified=3`，要带上下文才能看出装饰器被删。

两条链路的结果最后合在一起发评论：第二遍读错，安全回归没有输入；第一遍没读错，普通 finding 照常。

## 五种形状

PR 里列了四种，加上解码失败一共五种。工程 `Git路径_skylos/git_diff_paths_demo/` 用真实 Git 仓库逐个造出来，两版函数原样跑。

`_detect_regressions_from_diff` 做的事是遍历 `file_diffs.items()`，对每个文件的 diff 文本调一次 `detect_security_regressions(diff_text, file_path)`。字典里没有这个文件，后面就没有任何一步会碰到它。

### 路径里有非 ASCII 字节

[`core.quotePath`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corequotePath) 默认开着，Git 会把非 ASCII 路径整个包进引号，字节写成八进制：

```text
+++ "b/src/vues_caf\303\251.py"
```

`line.startswith("+++ b/")` 不成立，这个文件的 diff 整个跳过。`get_changed_line_ranges` 用同一个 `_new_diff_header_path`，读出来是 `src/vues_café.py`。改动列表里有它，审查结果里没有。

### 文件名里有空格

未加引号的路径后面，Git 补一个 TAB：

```text
+++ b/src/my views.py\t
```

`line[6:]` 把 TAB 带进键里。`file_diffs` 的键成了 `src/my views.py\t`，后面拿这个键去和 PR 的 diff 对，路径对不上；如果这条 finding 被发成行内评论，评论会落在 diff 之外。

### hunk 里有一行长得像文件头

一个新增的 JS 模板字符串里有：

```text
++ b/victim.js
```

渲染到 diff 里是 `+++ b/victim.js`，和真正的文件头只差一个字符。修前的扫描没有「在不在 hunk 里」的概念，看到 `+++ b/` 就认成新文件。整个 hunk 挂到 `victim.js` 名下，`src/evil.js` 的改动就此消失。

### 源码里有一个裸 CR

测试文件里有一行：

```python
note = "a\rdiff --git a/zz/zz b/zz/zz"
```

`\r` 在 Python 源码里是普通字符，`text=True` 的通用换行把它当行边界。Git 输出的 diff 里这一行被拆成两行，第二行从列首开始：

```text
diff --git a/zz/zz b/zz/zz
```

扫描器看到列首的 `diff --git`，认为进入了新文件。原来文件的 hunk 到此为止，后面被删掉的 `@login_required` 落进「新文件」，`src/app.py` 的 diff 不完整。

### 非 UTF-8 的源字节

latin-1 编码的源文件，diff 里带 `0xE9`。`text=True` 按本机 locale（UTF-8）解码，读到 `0xE9` 失败。异常不在 `run()` 里抛——读取在另一个线程，`result.stdout` 变成 `None`，下一行报：

```text
AttributeError: 'NoneType' object has no attribute 'splitlines'
```

这一次 `skylos cicd review` 没跑完就断了。

## 改了三处

合并提交 `380b2a3e` 对 `review.py` 是 +22/−4：

```python
result = subprocess.run(
    diff_cmd,
    cwd=cwd,
    capture_output=True,
    env=read_only_git_environment(),
)
...
diff_output = result.stdout
if isinstance(diff_output, bytes):
    diff_output = diff_output.decode("utf-8", errors="replace")
...
elif line.startswith("+++ ") and not in_hunk:
    current_file = _new_diff_header_path(line[4:])
```

- 不再传 `text=True`，读回 bytes，显式 `decode("utf-8", errors="replace")`。非 UTF-8 字节变成替换字符，文件的键和 hunk 还在。
- `+++` 的处理换成 `_new_diff_header_path`。引号、TAB、`/dev/null` 已经在函数里，不用重写一遍。
- 加 `in_hunk`：见到 `@@` 置位，见到 `diff --git` 复位。hunk 里的 `+++` 是源码。

`text=True` 也能带 `errors="replace"`，但解码只是两个问题之一：通用换行还在，裸 CR 造出的假头照样有。读 bytes 自己 decode，换行只按 `\n` 切，两个问题一起解决。合并版的注释写的是 `like get_changed_line_ranges`——改法就是把这一处改成和那一处一样。

`_new_diff_header_path` 对不认识的形状不猜：路径不以 `b/` 开头、引号不闭合，都直接 `raise ValueError`。异常从 `_get_per_file_diffs` 的循环里冒出去，由 `run_pr_review` 的 `except ValueError` 接住，打印 `Skylos PR review unavailable`，退出码 2。review 会停下来，但不会带着一份少了一个文件的报告收工。

PR 的 precision 一节写的是「恢复被静默丢掉的 finding，去掉一条格式错误的评论路径」。

## 五个场景跑出来的结果

工程把两版 `review.py` 的四个函数逐字取出来，用真实 Git 仓库跑五个场景。合并提交的 [`test/test_cicd_review_diff_paths.py`](https://github.com/duriantaco/skylos/blob/380b2a3e315ca05f5546139c691b678114e38dc4/test/test_cicd_review_diff_paths.py) 有四个用例，分别对应前四种形状；`--test` 的输出：

| 场景 | 父版 `_get_per_file_diffs` | 合并版 |
| --- | --- | --- |
| `vues_café.py` | `{}` | `src/vues_café.py` |
| `my views.py` | `src/my views.py\t` | `src/my views.py` |
| hunk 里的 `++ b/victim.js` | `victim.js` | `src/evil.js` |
| 裸 CR | `src/app.py`（hunk 被截断） | `src/app.py`（完整） |
| latin-1 源字节 | `AttributeError` | `src/latin1.py` |

前两行是键错了，第三行是整个文件挂错，第四行是 diff 少了一截，第五行是 review 崩了。

再看被删掉的那行装饰器：

| 场景 | 父版拿到 `-@login_required` | 合并版 |
| --- | --- | --- |
| `vues_café.py` | 否（没有 diff） | 是 |
| 裸 CR | 否（hunk 被截断） | 是 |
| latin-1 源字节 | 否（异常） | 是 |

`get_changed_line_ranges` 在这五个场景里全对——它一直走的是另一个解析器。问题不在 Git，也不在规则。

## 评论落在 diff 之外

三种键错误最后都落到同一个地方：`_post_pr_review` 发评论时按路径在 diff 里找位置。键是 `src/my views.py\t` 或 `victim.js`，GitHub 的 diff 里没有这个路径，评论会带着一个不在 diff 里的位置发出去。PR 正文把这一类写成 "posted as a comment path outside the diff"。

比评论落错更麻烦的是没有评论。非 ASCII 路径的文件在改动列表里，结论是「没问题」；裸 CR 的文件只审了一半，剩下的 hunk 当成新文件丢掉。这类工具不出错的时候，没人会去看那一栏是空的还是对的。

## 两个解析器合回一个

五种形状看着可以逐条打 `if`：解引号、去 TAB、记 hunk 状态、换一种读法。`_new_diff_header_path` 已经把这些写全了，连 `/dev/null`（删除文件时的 `+++`）和格式错误的引号都处理了；`_parse_unified_diff` 本来就有 `in_hunk`。解析逻辑本身不用动，要动的是让 `_get_per_file_diffs` 用回同一个函数。

PR 正文有一句：

> `get_changed_line_ranges` parsed the same diff correctly, so the file looked reviewed.

文件看起来被审过了。这句话是这次修复的起点：审查的输出里，「没有 finding」和「没读这个文件」长得一样，两边都显示为通过。

上游给这个行为补了四个测试，latin-1 那一条不在其中。那条的修复就是 `errors="replace"`，可注释解释的是读 bytes 的理由——通用换行会把裸 CR 读成假头——解码失败这一半没提。第五种形状在 demo 里造得出来，在上游测试里没有对应的一行。

## 复现

```console
$ python -B Git路径_skylos/git_diff_paths_demo/run.py --test
ALL PASS
```

工程只依赖 Python 3.11+ 与 Git；两版函数在 `git_diff_paths_demo/vendor/` 下，来源与行号写在文件头，Apache-2.0 许可随附。完整对照输出与上游快照留在笔记仓库的检查记录里。

上游：`duriantaco/skylos`，[#1196](https://github.com/duriantaco/skylos/pull/1196)，父提交 [`7cf919a1`](https://github.com/duriantaco/skylos/commit/7cf919a103a416982d0a1fd7c79008424f47d274)，合并提交 [`380b2a3e`](https://github.com/duriantaco/skylos/commit/380b2a3e315ca05f5546139c691b678114e38dc4)。
