# Git diff 路径解析复现（skylos #1196）

同一个 `git diff`，两个解析器。`get_changed_line_ranges` 走 `_parse_unified_diff`，`_get_per_file_diffs` 走自己的一套行扫描；修前只有后者会把 Git 的引号路径、空格后的 TAB、hunk 里的伪头、裸 CR 造出的假头读错，于是安全回归检查拿到的文件键不是真实路径，或者整个文件的 diff 根本没进来。

本工程把两版 `skylos/cicd/review.py` 里的四个函数原样取出来，用真实 Git 仓库造五类 diff，对照两份映射。

## 运行

```console
python -B run.py --test
```

需要 Git 在 `PATH` 里；Python 3.11+，无第三方依赖。`--test` 会断言两版的键与修复前后行为，并打印完整的 JSON 对照。

## 目录

- `vendor/parent/diff_paths.py`：父提交 `7cf919a103a416982d0a1fd7c79008424f47d274` 的 `_parse_unified_diff`、`_new_diff_header_path`、`_get_per_file_diffs`，逐字提取。
- `vendor/merged/diff_paths.py`：合并提交 `380b2a3e315ca05f5546139c691b678114e38dc4` 的同名函数。
- `vendor/skylos/core/git_safety.py`：上游同文件的逐字拷贝，提供 `worktree_safe_git_command` 与 `read_only_git_environment`。
- `vendor/skylos/done/base.py`：`_unquote_c_style` 的逐字提取。
- `vendor/LICENSE`：上游 Apache-2.0。

提取脚本与来源哈希记在 `../.yan/git-diff-paths/`，不随本工程发布。

## 五个场景

| 场景 | Git 输出里的形状 | 父版键 | 合并版键 |
| --- | --- | --- | --- |
| 非 ASCII 文件名 | `+++ "b/src/vues_caf\303\251.py"` | 无 | `src/vues_café.py` |
| 文件名带空格 | `+++ b/src/my views.py\t` | `src/my views.py\t` | `src/my views.py` |
| hunk 里的 `++ b/victim.js` | 源码行渲染成 `+++ b/victim.js` | `victim.js` | `src/evil.js` |
| 源码里的裸 CR | CR 被通用换行拆成列首 `diff --git` | `src/app.py`（但 hunk 被截断） | `src/app.py` |
| 非 UTF-8 源字节 | `text=True` 解码失败 | `AttributeError` | `src/latin1.py` |

前四行是键的差异；第四、第五行还决定被删掉的 `@login_required` 能不能到达 `detect_security_regressions`。`--test` 会检查父版在非 ASCII 与裸 CR 两个场景里拿不到那行删除，合并版都能拿到。
