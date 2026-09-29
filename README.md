# notes

技术笔记原稿仓库：**论文对照真实实现**系列。每篇笔记的断言都尽量落到可运行的代码上——
笔记里有 claim，专题文件夹里就有复现它的工程。

> 博客版（掘金 / dev.to）从这里长出来；仓库是原稿，博客是发布物。

## 结构约定

每个专题一个文件夹，笔记、配图、验证代码都放在里面：

```
<专题名>/
├── xxx.md          # 笔记原稿（中英双语）
├── assets/         # 配图
└── <工程名>/       # 验证工程（可运行）
```

## 专题

### 时间轮：从 SOSP '87 到 tokio

`时间轮_timing_wheel/`

- 博客：[《时间轮里那行凭空出现的 +1》](https://juejin.cn/post/7690596943454437427)（掘金，2026-09-29 首发）
- 笔记：[中文版](时间轮_timing_wheel/时间轮_论文对照_tokio_中文版.md) / [English](时间轮_timing_wheel/Timing_Wheels_From_SOSP_1987_to_tokio_EN.md)
- 验证工程：[`时间轮_timing_wheel/wheel_demo/`](时间轮_timing_wheel/wheel_demo/)

内容要点：
- Varghese & Lauck 1987 SOSP 时间轮 → BSD 内核落地 → Soft timers → Lawn → Carousel 的谱系，逐篇核实
- tokio-util 时间轮 `next_occupied_slot` 里 `+1` 偏移的完整剖析：顶层伪环形缓冲（pseudo-ring buffer）问题
- `+1` 修的是哪个 bug（对应 [tokio PR #8519](https://github.com/tokio-rs/tokio/pull/8519)），去掉它会怎样

## 运行验证代码

```sh
cd 时间轮_timing_wheel/wheel_demo
cargo test        # 5 个测试：fixed 版行为 + buggy 版反例（含 pgdog 场景复现）
cargo run --release --example demo    # 打印三个场景的实测时间线
```

依赖 Rust 工具链。`wheel_fixed/` 是 tokio-util 当前修复版代码（原样搬运），
`wheel_buggy/` 是去掉 `+1` 的对照版，两者共用同一套测试场景，行为差异即 bug 本身。

## 约定

- 笔记里的每个数字（触发时刻、推迟量、层级放置）都来自 `cargo` 实测输出，不手算
- 论文引用标证据级别：【全文读过】/【摘要】/【仅引用关系】
- 没把握的断言（如 GD-Wheel 的元数据疑点）显式标注存疑，不硬写
