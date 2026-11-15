# 图像缓冲区算错：两版 pypdf 对照

`_validate_image_size()` 要用「每像素多少字节」乘以像素数，去判断 Pillow 会为这张图分配多少内存。修前它取的是 `len(mode)`——模式名字的长度。这个 demo 把父提交与合并提交两份 `pypdf` 放在一起，对同一组图像问同一个问题，看两边各自给出什么答案。

两份源码都是固定提交的完整包，导入时靠 `sys.path` 决定用哪一版；两个版本的 `pypdf.__version__` 都是 `7.0.0`，合并提交没有改版本号。

## 跑法

需要 Python 3.9+ 与 Pillow（`pip install pillow`）。

```text
python -B run.py --test      # 纯函数判定 + 真实容器图像，不分配大块内存
python -B run.py --mem       # 再用进程私有内存实测 Pillow 的每像素字节数（需要 psutil）
python -B run.py --emit DIR  # 顺带把两份探针输出写成 JSON
```

`--test` 全部通过时打印 `ALL PASS`，退出码 0。

输出分四段：

1. `Image.MODES` 报的 20 个模式，各自在父版、合并版与 Pillow 源码里占多少字节每像素；
2. 六张图在默认上限 75,000,000 下的放行/拒绝，以及两边各算出的字节数；
3. 三张真实文件（16 位 PNG、32 位 TIFF）走 `_create_image_from_buffer()` 的结果，上限压到 3,000,000 以便用小图触发；
4. `--mem` 时，`Image.new(mode, (8000, 8000))` 前后进程私有内存的差，除以 64,000,000 像素。

第 4 段用 `psutil.Process().memory_info().private`，每个模式单独起一个进程，避免分配器复用上一块内存。数字会随 Pillow 版本与本机分配器略有浮动，量级与整数位稳定。

## vendor 来源

| 目录 | 提交 | 说明 |
| --- | --- | --- |
| `vendor/pypdf-parent/` | `5a936f961c64c791682f997fec83221fa85b51b0` | 合并提交的父提交 |
| `vendor/pypdf-merged/` | `1cd993b984e7cbbb0cd5f9b23800b7d06b7ec6ee` | PR #4374 的合并提交 |

两份都是从 GitHub 的 codeload tarball 解出的 `pypdf/` 包，未改动任何文件；完整哈希与文件数见 `provenance.json`。上游许可证随附在 `LICENSE`（pypdf 的 BSD 许可）。

`probe.py` 只在给定 vendor 路径下导入 `pypdf`，不读网络，也不碰本机已装的 pypdf。
