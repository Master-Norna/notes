# Norna 的笔记

这里放我读开源代码时写下的一些东西。最近几篇都和 Rust 项目里的 bug 有关：方差算成负数、定时器不再触发、拥塞窗口多砍了一刀。

补丁往往只有几行，弄明白为什么这样改却要绕不少路。我也把这些绕路记下来：试过的算法、没覆盖的反例，还有后来需要更正的地方。能用小程序跑出来的，就把代码一起放进来。

## 文章

### CUBIC：同一个窗口，乘了两遍 0.7

quinn 处理持久拥塞时，把已经削减过的窗口又削了一次，`ssthresh` 从原窗口的 0.7 倍变成了 0.49 倍（未触及最小窗口下限时）。这篇从被删掉的五行代码讲起，看看这条界线为什么会影响窗口恢复，也理一理 `cwnd` 和 `flight_size` 的区别。

[中文](拥塞控制_cubic/cubic_持久拥塞_ssthresh_二次削减_中文版.md) · [English](拥塞控制_cubic/Cubic_Persistent_Congestion_Second_Cut_EN.md) · [掘金](https://juejin.cn/spost/7701604765432545289) · [知乎](https://zhuanlan.zhihu.com/p/2098906464999969780) · [CSDN](https://blog.csdn.net/MsterNZ/article/details/169368038)

修复：[quinn #2903](https://github.com/quinn-rs/quinn/pull/2903)

### 方差怎么会是 −32？

`506250000` 和 `506250001` 的总体方差是 `0.25`，Nushell 的旧实现却算出了 `−32`。换成普通两遍法，这组数对了，另一组又出了问题。沿着这次修复，把六种算法放到相同的输入下试一遍，看看误差从哪里来。

[中文](方差稳定性_nushell_variance/nushell_math_variance_中文版.md) · [English](方差稳定性_nushell_variance/Nushell_Math_Variance_EN.md) · [掘金](https://juejin.cn/post/7699685792612679715) · [知乎](https://zhuanlan.zhihu.com/p/2098926232993846374) · [CSDN](https://blog.csdn.net/MsterNZ/article/details/169368433)

修复：[nushell #19108](https://github.com/nushell/nushell/pull/19108)

### 时间轮里那行凭空出现的 `+1`

一个 PostgreSQL 代理跑了约 12 天，周期任务开始不再触发。追到 tokio-util 的时间轮里，修复看起来只是把扫描起点往后挪一格。为了理解这一格，回头翻了时间轮的论文，也写了一个不用真等 12 天的复现。

[中文](时间轮_timing_wheel/时间轮_论文对照_tokio_中文版.md) · [English](时间轮_timing_wheel/Timing_Wheels_From_SOSP_1987_to_tokio_EN.md) · [掘金](https://juejin.cn/post/7690596943454437427)

### 后来，`+1` 为什么只留在顶层？

首篇写完，review 里又出现了两组反例：`64 / 65ms` 和 `4096 / 4160ms`。它们暴露了初稿漏看的级联写入路径，也改变了最终修复。续篇接着讲这件事；首篇文末已补更正，两篇可以连着读。

[中文](时间轮_timing_wheel/时间轮_续篇_只在顶层加一_中文版.md) · [English](时间轮_timing_wheel/Timing_Wheel_Followup_Top_Level_Only_EN.md) · [掘金](https://juejin.cn/post/7699791664956932150)

修复：[tokio #8519](https://github.com/tokio-rs/tokio/pull/8519)（首篇与续篇对应同一个 PR）

## 复现代码

三个小工程都用 Rust，运行命令和实验设置在各自的 README 里。

| 工程 | 可以跑什么 |
| --- | --- |
| [cubic_demo](拥塞控制_cubic/cubic_demo/) | 同一场持久拥塞事件，比较修复前后的状态与逐 RTT 窗口轨迹 |
| [variance_demo](方差稳定性_nushell_variance/variance_demo/) | 六种方差算法的对照表、反例和数量级扫描 |
| [wheel_demo](时间轮_timing_wheel/wheel_demo/) | 原实现、首篇初稿、最终修复的三版本对照，包含两组级联反例 |

文章有中英文两版，配图和绘图脚本也在对应专题里。博客方便阅读，这里保留原稿、代码和后续更正。
