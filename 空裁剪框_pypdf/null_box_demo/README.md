# 空裁剪框复现工程

复现 py-pdf/pypdf #4375：页面字典里 `/CropBox` 是 `null` 时，`/TrimBox`、`/ArtBox`、`/BleedBox` 的回退链会在这个空值上停住，读框与 `scale_by()` 一起失败。

两版库原样放在 `vendor/`：

| 目录 | 来源 | 说明 |
| --- | --- | --- |
| `vendor/base-8eeb0509/` | py-pdf/pypdf @ `8eeb0509d712e324e68e2bd38aff69e3b672e0cd` | 修复前 |
| `vendor/merge-049dbfb3/` | py-pdf/pypdf @ `049dbfb366931b0f86ea6956951b5b7d6f27b01e` | #4375 合并后 |

上游许可证见 `LICENSE`（BSD-3-Clause）。

## 跑法

只需要 Python 3.9 以上，无第三方依赖：

```text
python -B run.py --test
```

每个用例在独立的 `python -I -B` 子进程里跑，两个快照各占一次 `sys.path`，互不干扰。加 `--json PATH` 可把完整结果写成 JSON；`--emit DIR` 会写出三份样例 PDF（`null-cropbox.pdf`、`indirect-null-cropbox.pdf`、`healthy.pdf`）。

## 用例与读法

| 用例 | 做什么 |
| --- | --- |
| `healthy` | 没有空框的页面，对照组 |
| `null-cropbox/trimbox-first` | `/CropBox null`，先读 `/TrimBox` |
| `null-cropbox/cropbox-first` | 同一个页面，先读 `/CropBox`，再读 `/TrimBox` |
| `null-cropbox/artbox-first` | 先读 `/ArtBox` |
| `null-cropbox/bleedbox-first` | 先读 `/BleedBox` |
| `indirect-null/trimbox-first` | `/CropBox` 指向一个间接的 `null` 对象 |
| `null-cropbox/scale-by` | `writer.add_page(...)` 后 `scale_by(0.5)` |
| `null-cropbox/after-cropbox-read` | 读过一次 `/CropBox` 之后，字典里留下什么 |

`cropbox-first` 这一行的意义：`_get_rectangle()` 解析完会把结果写回页面字典（`_set_rectangle`），所以先读 `/CropBox` 会把回退到的 `/MediaBox` 数组存成新的 `/CropBox`，后面的框就读不到那个空值了。修前不是「这个文件读不了」，而是「读的顺序决定读不读得了」。

`after-cropbox-read` 给出写回后的类型：`RectangleObject`，值 `[0, 0, 100, 200]`。

## 预期输出

修复前：8 个用例里 5 个抛 `ValueError: Expected an array of four values for /…, got NullObject`；`cropbox-first` 与 `healthy` 正常。

修复后：8 个用例全过，目标框都是 `[0, 0, 100, 200]`，`scale_by` 后是 `[0, 0, 50, 100]`。

文中数字均出自 `--test` 的输出，存档在 `../.yan/pypdf-nullbox/runs/`。
