# PageRange 相加看顺序：两版 pypdf 对照

`PageRange.__add__` 合并两段页码区间，两边相隔就抛 `ValueError`。修前它按起点排两个操作数，起点相同时谁先谁后取决于谁写在左边：`PageRange("2:0") + PageRange("2:5")` 抛 "Can't add PageRanges with gap"，反过来写却返回 `2:5`。这个 demo 把父提交与合并提交两份 `pypdf` 放在一起，对同一组区间做同一个加法，看两边各自给出什么答案。

两份源码都是固定提交的完整 `pypdf/` 包，导入时靠 `sys.path` 决定用哪一版；两个版本代码只差 `pagerange.py` 里的一行比较（外加注释）。

## 跑法

只需要 Python 3.9+，不需要装 pypdf，也不联网：

```text
python -B run.py          # 打印两份构建的对照
python -B run.py --test   # 逐条断言预期行为，全部通过打印 ALL PASS，退出码 0
```

输出分三段：

1. `PageRange("2:0")` 与 `PageRange("2:5")` 在一份 10 页文档里各解析出哪些页（前者是空区间）；
2. 三对区间在 `+` 下的结果：空区间在前的两对加法、一对真正有 gap 的 `0:2 + 5:8`；
3. 同一个加法喂给 `writer.append(reader, pages=…)`，往 10 页的空白文档里加页，数剩下的页数。

## vendor 来源

| 目录 | 提交 | 说明 |
| --- | --- | --- |
| `vendor/pypdf-parent/` | `8ffe8f2e3dda1fc34c312b71e1112ad9a361de6e` | 合并提交的父提交（7.1.1 之后、7.2.0 之前的 main） |
| `vendor/pypdf-merged/` | `d0620116c87df3dcb97365ae3d631af2f8c8dfa9` | PR #4468 的合并提交（随 7.2.0 发行） |

两份都是从 GitHub 的 codeload tarball 解出的 `pypdf/` 包，未改动任何文件；完整哈希与文件数见 `provenance.json`。上游许可证随附在 `LICENSE`（pypdf 的 BSD 许可）。

`probe.py` 只在给定 vendor 路径下导入 `pypdf`，不读网络，也不碰本机已装的 pypdf。
