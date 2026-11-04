# Scrapling 零阈值复现

对应上游修复：[D4Vinci/Scrapling#539](https://github.com/D4Vinci/Scrapling/pull/539)
（合并提交 `104294c2d87abe35898327ae788826a3a79887bf`，修前父提交 `49eaff11da8de7c8067cf048a5dc3e0f95b53715`）。

`vendor/parent/parser.py` 与 `vendor/merge/parser.py` 是两个固定提交里的原文。运行脚本把已安装的 `scrapling` 包复制到临时目录，只替换 `parser.py`，再分别跑真实的 `Selector.find_similar`；两次运行之间除了这一个文件，其他代码完全相同。

## 准备

需要 Python 3.10+：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install scrapling==0.5.0
```

合并提交的 `pyproject.toml` 写的是 `version = "0.5.1"`，但 PyPI 目前只有 0.5.0；demo 只替换判定函数所在的 `parser.py`，其余模块用 0.5.0。装好后可离线运行。

## 跑

```powershell
.venv/Scripts/python run.py --test
```

`--test` 断言 14 行结果符合契约；不符合时退出码为 1。退出码 1 之前先看表里的 `MISMATCH`。

## 输出

```
case                       threshold before         after          expect         ok
no attrs vs class                  0 []             ['Beta']       ['Beta']       ok
no attrs vs class                0.2 []             []             []             ok
href only vs class                 0 []             ['Beta']       ['Beta']       ok
href only vs class               0.2 []             []             []             ok
both no attrs                      0 ['Beta']       ['Beta']       ['Beta']       ok
both no attrs                    0.2 ['Beta']       ['Beta']       ['Beta']       ok
same class                         0 ['Beta']       ['Beta']       ['Beta']       ok
same class                       0.2 ['Beta']       ['Beta']       ['Beta']       ok
extra attribute penalty          0.5 ['Beta']       ['Beta']       ['Beta']       ok
extra attribute penalty          0.6 []             []             []             ok
different class                    0 ['Beta']       ['Beta']       ['Beta']       ok
different class                  0.2 []             []             []             ok
href not ignored                   0 ['Beta']       ['Beta']       ['Beta']       ok
href not ignored                 0.2 []             []             []             ok
```

实际输出见 `.yan/scrapling-threshold/runs/scrapling-demo-publish-20261103.txt`。

## 文件

- `run.py`：矩阵、子进程隔离、两版对照与断言。
- `vendor/parent/parser.py`：`49eaff11` 的原文。
- `vendor/merge/parser.py`：`104294c2` 的原文。
- `LICENSE`：上游 BSD-3-Clause 原文。

## 边界

- 页面是构造的 `<div><a>Alpha</a><a>Beta</a></div>`，不是真实站点。
- 只跑 `find_similar` 的窄矩阵，不跑上游完整测试套件。
- 其余模块来自 PyPI 0.5.0，不能声称是完整 0.5.1 发行版。

上游代码以 BSD-3-Clause 发布，本目录的 `LICENSE` 为其原文。
