dateutil #1583 修前/修后对照复现
================================

同一个 `date(2000, 1, 1) + relativedelta(yearday=366)`，分别交给 dateutil
修复前（父提交 `5391455e`）与修复后（合并提交 `d23ff760`）的源码快照，对照
返回日期、`relativedelta` 的字段，以及 2000–2399 的逐日枚举。

来源
----
- PR：<https://github.com/dateutil/dateutil/pull/1583>
- 修复后快照：<https://github.com/dateutil/dateutil/tree/d23ff760f8448b51579016d96f39590018445724>
- 修复前快照：<https://github.com/dateutil/dateutil/tree/5391455e7c7839e300b63649041806fb5219432e>
  （`d23ff760` 的父提交，即 PR #1583 的基线）
- `vendor/parent/dateutil/` 与 `vendor/merged/dateutil/` 下的
  `relativedelta.py`、`_common.py` 逐字节取自对应 SHA 的 `git show`，
  哈希写在 `provenance.json`。`__init__.py` 是 demo 用的最小包骨架，
  不是上游文件。
- 上游 LICENSE 随附。

环境
----
- Python 3.11+，只用标准库（实测 3.12.14）
- 不需要安装 dateutil，不联网

用法
----
    python -B run.py           # 对照表 + 2000–2399 枚举汇总
    python -B run.py --test    # 断言，全部通过退出码 0
    python -B run.py --json out.json

两版各自跑在 `python -I -B -S` 子进程里，`vendor/<版>` 插到 `sys.path`
最前面；父进程不 import 任何一版。

对照
----
1. `date(2000,1,1) + relativedelta(yearday=366)`：修前是 `2000-12-30`，与
   `yearday=365` 相同；修后是 `2000-12-31`。修前的 repr 是
   `relativedelta(leapdays=-1, month=12, day=32)`，修后是
   `relativedelta(month=12, day=32)`。
2. 平年的 366（1999、1900）：两版都返回 12-31。`day=32` 被
   `min(月末, day)` 压到 31，而 `leapdays` 只在闰年应用。
3. 59/60 边界（2000、2001）：两版一致，修复不碰 366 之前的日号。
4. 367：两版都抛 `ValueError: invalid year day (367)`。
5. 2000–2399 逐日枚举：400 年、97 个闰年、146,097 个日期用例。修前 97
   个失配，全是闰年的第 366 天；修后 0 个。
