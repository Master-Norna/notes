<div align="center">

# Norna 的笔记

读开源项目时写下的笔记，原稿和复现代码都先放在这里

<a href="https://juejin.cn/user/2433681778278539"><img alt="掘金" src="https://img.shields.io/badge/%E6%8E%98%E9%87%91-1E80FF?style=flat-square&logo=juejin&logoColor=white" height="26"></a>
<a href="https://www.zhihu.com/people/50-96-91-56-89"><img alt="知乎" src="https://img.shields.io/badge/%E7%9F%A5%E4%B9%8E-0084FF?style=flat-square&logo=zhihu&logoColor=white" height="26"></a>
<a href="https://blog.csdn.net/MsterNZ"><img alt="CSDN" src="https://img.shields.io/badge/CSDN-FC5531?style=flat-square&logo=csdn&logoColor=white" height="26"></a>

</div>

我读开源项目的 bug 修复时，会把想不通的地方写下来，攒成了这里的笔记。这些补丁大多很短：一个 `+1`、删掉的五行、一层 `try/finally`。可要讲清它为什么非这样改不可，往往得绕一大圈，翻论文、写复现、找反例。我也写错过，错了就在原文后面补上更正。

## 文章

<table>
<tr>
<td width="88" align="center" valign="top"><a href="日期差_nushell_datetime/nushell_负天数消失以后_中文版.md"><img src="日期差_nushell_datetime/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[负天数消失以后，review 又找到了一个问题](日期差_nushell_datetime/nushell_负天数消失以后_中文版.md)**

1 月 31 日到 3 月 1 日，Nushell 算出「1 个月 −2 天」。我的初稿消掉了负号，review 却发现它把原来正确的「28 天」换成了「1 个月」。我把修复前、送审版和最终版一起留下，看一个补丁如何既修正错误，又不改掉原来的约定。

<sub>2026-10-30 · [English](日期差_nushell_datetime/nushell_负天数消失以后_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="转义往返_tomlkit/tomlkit_自己写的TOML读不回_中文版.md"><img src="转义往返_tomlkit/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[追加一个引号，自己写出的 TOML 自己读不回](转义往返_tomlkit/tomlkit_自己写的TOML读不回_中文版.md)**

tomlkit 为保真给每个字符串存两份：逻辑值和源文本。给值追加一个引号，值是对的，序列化出来却成了它自己的解析器都读不回的 TOML。2022 年那行拼接保住了左半边，右半边这一洞开了四年，直到 #612 把普通文本也领过转义那道刷子。

<sub>2026-10-29 · [English](转义往返_tomlkit/TOML_tomlkit_Cannot_Read_Back_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="导入排序语义_isort/isort_noqa去哪了_中文版.md"><img src="导入排序语义_isort/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[isort 格式化一遍，两条 F401 回来了](导入排序语义_isort/isort_noqa去哪了_中文版.md)**

一行挂着 `# noqa: F401` 的导入，过一遍 isort 注释就没了，flake8 当场报出两条 F401。我沿着注释在 isort 内部走的路找到了那个出口：十来种折行模式里，只有 grid 的注释全靠折行分支接住，语句不超宽就没人管它。

<sub>2026-10-29 · [English](导入排序语义_isort/Isort_Two_F401s_Are_Back_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="锁文件哈希_pdm/pdm_锁文件里的哈希去哪了_中文版.md"><img src="锁文件哈希_pdm/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[锁文件里明明有哈希，PDM 为什么说没有？](锁文件哈希_pdm/pdm_锁文件里的哈希去哪了_中文版.md)**

`pylock.toml` 里有哈希，导出 requirements 却说没有；换成导出 pylock，命令成功了，哈希却丢了。我沿着“写出 → 读入 → 再导出”跑了一遍，发现两种结果都从同一个空列表开始。七行修复补在读入处，而不是两个出口。

<sub>2026-10-29 · [English](锁文件哈希_pdm/PDM_Archive_Hashes_Roundtrip_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="取消与背压_anyio/anyio_取消接收与背压_中文版.md"><img src="取消与背压_anyio/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[receive 取消了，TCP 为什么还在读？](取消与背压_anyio/anyio_取消接收与背压_中文版.md)**

给 `receive()` 套一个超时，超时后把连接留着下回再用，这是很常见的写法。可在修复前的 AnyIO 里，超时退出的只是这一次等待，底层 transport 还在读，对端发来的数据一直往 Python 的队列里堆。我用真实的 TCP 连接把修复前后两版各跑了一遍，看那 4 MiB 数据分别去了哪里。

<sub>2026-10-28 · [English](取消与背压_anyio/AnyIO_Cancelled_Receive_Backpressure_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="拥塞控制_cubic/cubic_持久拥塞_ssthresh_二次削减_中文版.md"><img src="拥塞控制_cubic/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[CUBIC：同一个窗口，乘了两遍 0.7](拥塞控制_cubic/cubic_持久拥塞_ssthresh_二次削减_中文版.md)**

quinn 遇到持久拥塞时，把已经乘过 0.7 的窗口又乘了一遍，`ssthresh` 成了原窗口的 0.49 倍（没碰到最小窗口下限时）。修复删掉了五行代码。要讲清这五行为什么该删，得先分清 `cwnd` 和 `flight_size`。

<sub>2026-10-27 · [English](拥塞控制_cubic/Cubic_Persistent_Congestion_Second_Cut_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="方差稳定性_nushell_variance/nushell_math_variance_中文版.md"><img src="方差稳定性_nushell_variance/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[方差怎么会是 −32？](方差稳定性_nushell_variance/nushell_math_variance_中文版.md)**

`506250000` 和 `506250001` 的总体方差是 `0.25`，Nushell 的旧实现给出的却是 `−32`。换成教科书上的两遍法，这组数算对了，换一组又不对。于是我把六种算法放在同样的输入上挨个跑，看误差是从哪一步冒出来的。

<sub>2026-10-23 · [English](方差稳定性_nushell_variance/Nushell_Math_Variance_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="时间轮_timing_wheel/时间轮_论文对照_tokio_中文版.md"><img src="时间轮_timing_wheel/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[时间轮里那行凭空出现的 `+1`](时间轮_timing_wheel/时间轮_论文对照_tokio_中文版.md)**

PostgreSQL 代理 pgdog 连续跑了 12 天以后，定时任务全都不再触发了，既不报错，也不 panic。问题出在 tokio-util 的时间轮里，修复只是把扫描起点往后挪了一格。为了弄懂这一格，我回头读了 1987 年那篇时间轮论文。

<sub>2026-09-29 · [English](时间轮_timing_wheel/Timing_Wheels_From_SOSP_1987_to_tokio_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="时间轮_timing_wheel/时间轮_续篇_只在顶层加一_中文版.md"><img src="时间轮_timing_wheel/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[后来，`+1` 为什么只留在顶层？](时间轮_timing_wheel/时间轮_续篇_只在顶层加一_中文版.md)**

上一篇写完后，review 里又冒出两组反例：`64 / 65ms` 和 `4096 / 4160ms`。它们暴露了初稿漏看的级联写入路径，最终合并的修复也因此变了样。上一篇文末已补上更正，两篇最好连着读。

<sub>2026-10-24 · [English](时间轮_timing_wheel/Timing_Wheel_Followup_Top_Level_Only_EN.md)</sub>

</td>
</tr>
</table>

## 复现代码

能跑的小工程放在各自的专题文件夹里，怎么跑写在它们的 README 里。

| 工程 | 跑出来的是什么 |
| --- | --- |
| [datetime_demo](日期差_nushell_datetime/datetime_demo/) | 三份固定源码交给同一个真实 Nu 执行，对照负天数、初稿的语义变化与最终兼容拆分，并独立检查闰日输入解析 |
| [hash_demo](锁文件哈希_pdm/hash_demo/) | 同一份归档哈希经过两版 PDM 读入函数，再导出 requirements / pylock，看它在哪一步丢失或保留 |
| [backpressure_demo](取消与背压_anyio/backpressure_demo/) | 修复前后两版 AnyIO 各连一条真实的 TCP，看取消之后数据有没有继续堆进队列，连接还能不能接着用 |
| [cubic_demo](拥塞控制_cubic/cubic_demo/) | 同一次持久拥塞，修复前后的 `ssthresh`，以及之后每个 RTT 的窗口变化 |
| [variance_demo](方差稳定性_nushell_variance/variance_demo/) | 六种方差算法在同一批输入上的误差，包括反例和数量级扫描 |
| [wheel_demo](时间轮_timing_wheel/wheel_demo/) | 原实现、首篇引用的初稿、最终修复，三版放在一起跑，也包括那两组级联反例 |
| [isort_demo](导入排序语义_isort/isort_demo/) | 同一份带 noqa 的导入交给修复前后两版 isort 快照，看注释在哪一版丢失、flake8 如何当场翻脸，折行与无注释场景两版逐字一致 |
| [tomlkit_demo](转义往返_tomlkit/tomlkit_demo/) | 同一组追加操作喂给修复前后两版 tomlkit 快照，看引号与反斜杠在哪一版把源文本拼坏、文档级往返哪一版当场翻车，String 拼 String 与追加普通文本两版逐字一致 |
