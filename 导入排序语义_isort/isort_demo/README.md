isort #2675 修前/修后对照复现
============================

同一份输入，分别交给 isort 修复前（父提交 1745766e）与修复后（合并提交
3415efa）的源码快照，对照格式化输出、行尾 noqa 注释与 flake8 结果。

来源
----
- 修复后快照：https://github.com/PyCQA/isort/tree/3415efa3668f5514c57dfa4291d83021a575b56f
- 修复前快照：https://github.com/PyCQA/isort/tree/1745766e5cc705eec7179c1122fcdf5b5b6e7546
  （3415efa 的父提交，即 PR #2675 的基线）
- 两份快照均取自对应 SHA 的源码 tarball，`isort/` 包目录原样放入
  `isort_before/` 与 `isort_after/`；上游 LICENSE（MIT）随附。
- 对应修复：https://github.com/PyCQA/isort/pull/2675

环境
----
- Python 3.12+（快照使用标准库 tomllib；PR 在 Python 3.12 上验证）
- `pip install mypy_extensions`（快照 `isort/settings.py` 的硬依赖）
- 可选 `pip install flake8`：参与 lint 对照；不装也可 `--offline` 跑
- 快照无独立版本元数据：isort 的 `__version__` 走 importlib.metadata，
  会误读解释器环境里已安装的同名发行版，版本一律以 git SHA 为准
  （run.py 加载后会核验模块确实来自快照目录）。

用法
----
    python run.py            # 完整对照报告
    python run.py --offline  # 不调用 flake8
    python run.py --test     # 断言自测，全部通过退出码 0

三组对照
--------
1. 主反例：`from ugly import a, b  # noqa: F401`，
   配置 force_grid_wrap=2, multi_line_output=GRID(0), line_length=79。
   语句不超宽、不触发折行，但两个名字已进入 grid 布局：
   修复前输出 `from ugly import (a, b)`——noqa 注释丢失，flake8 报出两条
   F401（'ugly.a' 与 'ugly.b'）；修复后输出
   `from ugly import (a, b)  # noqa: F401`——注释保留，lint 干净。
2. 对照A：19 个名字超出 60 列，走 grid 的折行分支。
   两版输出逐字一致，注释都落在折行行尾——修复不改变折行分支的行为。
3. 对照B：没有注释的输入。两版输出一致——修复不给正常输出添乱。
