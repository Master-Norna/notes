# notes

从真实的 bug 出发，读源码、对照论文，再用小程序把问题跑出来。

这里收录中英文技术笔记、配图和复现代码。博客版发布在掘金；原稿和后续更正在这里保留。

## 时间轮：那行 `+1`，后来怎么样了？

一个 PostgreSQL 代理运行约 12 天后，周期任务开始不再触发。追到时间轮里，修复看起来只是把扫描起点往后挪一格。

但这个 `+1` 不能加在每一层。维护者用 `64ms / 65ms` 和 `4096ms / 4160ms` 两组定时器，找到了初稿没覆盖的级联错误。

|文章|中文|English|
|---|---|---|
|首篇 · 时间轮里那行凭空出现的 `+1`|[阅读](时间轮_timing_wheel/时间轮_论文对照_tokio_中文版.md)|[Read](时间轮_timing_wheel/Timing_Wheels_From_SOSP_1987_to_tokio_EN.md)|
|续篇 · 时间轮的 `+1`，为什么最后只留在顶层|[阅读](时间轮_timing_wheel/时间轮_续篇_只在顶层加一_中文版.md)|[Read](时间轮_timing_wheel/Timing_Wheel_Followup_Top_Level_Only_EN.md)|

首篇从顶层伪环讲到时间轮的论文谱系；续篇接着讲 review 中发现的两组反例、漏掉的级联写入路径，以及 runtime 与 tokio-util 不同的级联方式。**首篇已补更正，建议连同续篇一起读。**

- 已发布：[首篇博客](https://juejin.cn/post/7690596943454437427)（2026-09-29）
- 对应修复：[tokio #8519](https://github.com/tokio-rs/tokio/pull/8519)（2026-10-11 合并）
- 复现：[三版本时间轮对照](时间轮_timing_wheel/wheel_demo/)，包含原实现、首篇初稿和最终修复

## 方差：两个相差 1 的数，怎么算出 −32？

对 `506250000` 和 `506250001` 求总体方差，正确结果是 `0.25`。Nushell 的旧实现却能算出 `−32`。

普通两遍法修好了这个输入，又在大数常数序列上引入新问题。文章沿着修复过程，比较六种算法，也保留了最终方案仍然存在的数值边界。

- 原稿：[中文版](方差稳定性_nushell_variance/nushell_math_variance_中文版.md) / [English](方差稳定性_nushell_variance/Nushell_Math_Variance_EN.md)
- 已发布：[博客](https://juejin.cn/post/7699685792612679715)（2026-10-23）
- 对应修复：[nushell #19108](https://github.com/nushell/nushell/pull/19108)
- 复现：[六种算法与量级扫描](方差稳定性_nushell_variance/variance_demo/)

## 跑一遍

两个工程都使用 Rust。下面的命令在各自工程目录运行，详细说明见工程内的 README。

**时间轮**

```sh
cd 时间轮_timing_wheel/wheel_demo
cargo test
cargo test --release
cargo run --release --example followup
```

`followup` 打印顶层伪环与两组级联反例的三版本对照；不需要等现实中的 12 天过去。debug 模式的断言差异见[工程说明](时间轮_timing_wheel/wheel_demo/README.md)。

**方差**

```sh
cd 方差稳定性_nushell_variance/variance_demo
cargo test --release
cargo run --release
```

运行后会打印文章里的对照表，并输出 CSV。重画曲线另需 Python 与 Matplotlib，见[工程说明](方差稳定性_nushell_variance/variance_demo/README.md)。

## 目录

```text
时间轮_timing_wheel/
├── *.md             中英文首篇与续篇
├── assets/          配图
└── wheel_demo/      三版本复现

方差稳定性_nushell_variance/
├── *.md             中英文笔记
├── assets/          配图
└── variance_demo/   算法对照与数据扫描
```
