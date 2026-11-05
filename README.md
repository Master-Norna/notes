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
<td width="88" align="center" valign="top"><a href="覆盖输入_skylos/skylos_退出码0锁文件没了_中文版.md"><img src="覆盖输入_skylos/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[退出码 0，Cargo.lock 没了](覆盖输入_skylos/skylos_退出码0锁文件没了_中文版.md)**

`skylos sbom . -o Cargo.lock` 退出 0，把 7 个包的锁文件写成了一份 CycloneDX JSON。守卫认识 11 个依赖文件名，收集器认识 24 个；差的 13 个里有 6 个是手写清单，丢了没有命令能重建。

<sub>2026-11-05 · [English](覆盖输入_skylos/skylos_Exit_Code_0_Lockfile_Gone_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="百分号解码_epub_start/epub_中文封面404_中文版.md"><img src="百分号解码_epub_start/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[中文封面为什么 404](百分号解码_epub_start/epub_中文封面404_中文版.md)**

`OEBPS/图片/封面.png` 在 ZIP 里是 23 个字节，浏览器发来的请求路径是 47 个 ASCII 字符；处理器拿这串字符去按字面找，找不到。解码要放在入口、要走在路径校验前面，而且只能做一次——`save_book_image` 那一层收到的，已经是解好的名字。

<sub>2026-11-03 · [English](百分号解码_epub_start/epub_Why_the_Chinese_Cover_404s_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="零阈值_scrapling/scrapling_零阈值仍过滤_中文版.md"><img src="零阈值_scrapling/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[阈值写 0，过滤为什么没关](零阈值_scrapling/scrapling_零阈值仍过滤_中文版.md)**

参考链接没有属性、候选多一个 `class`，`checks` 停在 0；旧代码把「没有可比的属性」当成「不相似」，直接返回。修复只把 `return False` 换成了 `0 >= similarity_threshold`，14 行对照里只有两行变了。

<sub>2026-11-03 · [English](零阈值_scrapling/scrapling_Zero_Threshold_Still_Filters_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="第366天_dateutil/dateutil_第366天_中文版.md"><img src="第366天_dateutil/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[第 366 天，落回了 12 月 30 日](第366天_dateutil/dateutil_第366天_中文版.md)**

从 2000 年 1 月 1 日取第 366 天，dateutil 返回的还是 12 月 30 日，和第 365 天同一个日期。`yearday` 先被换算成 12 月 32 日，clamp 把它压回月末，闰年的补偿又减了一天；2000–2399 逐日枚举，97 个闰年全错在这一天。

<sub>2026-11-03 · [English](第366天_dateutil/dateutil_Day_366_Lands_on_Dec_30_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="负指针_pypdf/pypdf_负指针_中文版.md"><img src="负指针_pypdf/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[报错是 −257，文件里写的是 −256](负指针_pypdf/pypdf_负指针_中文版.md)**

把 PDF 末尾的 `startxref` 改成 `-256`，pypdf 报的是 `negative seek value -257`。差的那 1 来自 `seek(startxref - 1)`；我顺着这个值看它流向的三个去处，2025 年那道守卫只装在其中一处，而且只认 0。

<sub>2026-11-01 · 2026-11-04 扩写 · [English](负指针_pypdf/pypdf_Negative_Startxref_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="旋转丢元素_pottery/pottery_旋转丢元素_中文版.md"><img src="旋转丢元素_pottery/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[转四步，少了一个元素](旋转丢元素_pottery/pottery_旋转丢元素_中文版.md)**

`[1, 2, 3]` 转 −4 步，标准库给 `[2, 3, 1]`，`RedisDeque` 给 `[2, 3]`；转 −6 步直接清空。切片会夹住越界的端点，裁切却按原步数算。我把长度 0–8、步数 −20–20 的 369 格逐格跑完，红格正好落在 `|n| > len`。

<sub>2026-11-01 · [English](旋转丢元素_pottery/Pottery_Rotate_Long_Steps_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="本地时间_tomlkit/tomlkit_本地时间没有时区_中文版.md"><img src="本地时间_tomlkit/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[tomlkit 写出的 07:32:00+02:00，为什么自己读不回来](本地时间_tomlkit/tomlkit_本地时间没有时区_中文版.md)**

`item(time(7, 32, tzinfo=+02:00))` 写出 `07:32:00+02:00`，交给它自己的 `parse()` 却抛 `InvalidTimeError`。TOML 的 Local Time 没有那六个字符的位置；修复只动了写出端，解析器照旧拒绝偏移。

<sub>2026-11-01 · 2026-11-04 扩写 · 2026-11-05 改写 · [English](本地时间_tomlkit/TOML_tomlkit_Local_Time_No_Offset_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="对数定义域_nushell_math_log/nushell_math_log_中文版.md"><img src="对数定义域_nushell_math_log/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[拦住了 1 和 NaN，却漏掉 ∞](对数定义域_nushell_math_log/nushell_math_log_中文版.md)**

`2 | math log 1` 返回 `inf`，`2 | math log inf` 返回 `0.0`，两条都不报错。我的首稿补上了 1 和 NaN，review 却指出同一个判据还漏着正无穷；输入那一侧的 NaN 漏法相同，只是守卫的方向反了。我把三版提取出来跑完 144 对。

<sub>2026-10-31 · [English](对数定义域_nushell_math_log/Nushell_Math_Log_Domain_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="字节删除_nushell_bytes/nushell_bytes_remove_中文版.md"><img src="字节删除_nushell_bytes/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[panic 消失以后，字节却少了](字节删除_nushell_bytes/nushell_bytes_remove_中文版.md)**

`0x[10 11 12 13] | bytes remove --end 0x[AA BB]` 没找到模式，返回的却是 `0x[11 12 13]`：第一个字节没了。两年前那次修复只挡住了 panic，没有把扫描跳过的前缀补回来。我的首稿把结果修对了，review 却要求把那条已经出过两次问题的游标整个换掉。

<sub>2026-10-31 · [English](字节删除_nushell_bytes/Nushell_Bytes_Remove_Prefix_Loss_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="子目录定位_pdm/pdm_锁文件叫child打开却是parent_中文版.md"><img src="子目录定位_pdm/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[锁文件里叫 child，打开却是 parent](子目录定位_pdm/pdm_锁文件叫child打开却是parent_中文版.md)**

锁文件里的名字还是 `child`，归档哈希也没变；把它重新读进来，元数据却来自同一个 ZIP 根目录的 `parent`。十月最后一周，这条导出路线上补了三处——入口、读入端的哈希、写出端的目录。我按它们发生的顺序把真实 PDM 跑了一遍，看那两行补丁接回的是哪一段。

<sub>2026-10-31 · [English](子目录定位_pdm/PDM_Lockfile_Subdirectory_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="PDF注释_pypdf/pypdf_注释不再压垮栈_中文版.md"><img src="PDF注释_pypdf/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[注释不再压垮栈，为什么普通对象又多绕了一次？](PDF注释_pypdf/pypdf_注释不再压垮栈_中文版.md)**

前面多放一些注释，pypdf 连后面的 42 都读不到。我的初稿用循环修好了递归，按 review 抽出公共工具后，却碰到了另一份优化留下的调用预算。我把三版放在一起，追到函数入口和流指针，看两份改动怎样把各自的理由都留在代码里。

<sub>2026-10-31 · [English](PDF注释_pypdf/pypdf_注释不再压垮栈_EN.md)</sub>

</td>
</tr>
<tr>
<td width="88" align="center" valign="top"><a href="后端参数_pathspec/pathspec_装了加速库规则却不认了_中文版.md"><img src="后端参数_pathspec/assets/icon.svg" width="64"></a></td>
<td valign="top">

**[装了加速库，同一条规则却不认了](后端参数_pathspec/pathspec_装了加速库规则却不认了_中文版.md)**

同一条忽略大小写的正则，装上原生加速库后，匹配反而从 True 变成 False。我的初稿靠退回 Python 修好了答案，维护者却要求让能表达的参数继续走原生后端；改版期间，另一份补丁又先合入了重叠的加固。我把三版放在一起，不只看答案，也看它究竟选了哪个引擎。

<sub>2026-10-31 · [English](后端参数_pathspec/pathspec_装了加速库规则却不认了_EN.md)</sub>

</td>
</tr>
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
| [overwrite_demo](覆盖输入_skylos/overwrite_demo/) | 两版输出守卫对 24 个依赖输入名逐个跑一遍，看修前哪 13 个被安静覆盖、修后是否全部拒绝，另比对大小写、子目录、`.csproj` 与 `pins.txt` 的字节 |
| [percent_decode_demo](百分号解码_epub_start/percent_decode_demo/) | 两版协议处理器读同一份含中文、空格、`#`、`?`、`%` 条目名的 EPUB，9 个请求在哪一版是 404，解码与路径校验的先后如何把一次穿越从 404 变成 403 |
| [threshold_demo](零阈值_scrapling/threshold_demo/) | 两版 `parser.py` 跑 7 个页面 × 2 个阈值，看 0 阈值下「参考无属性、候选有属性」那一格修前修后差在哪里 |
| [yearday_demo](第366天_dateutil/yearday_demo/) | 两份固定源码快照对照 `yearday=366` 的返回日期与 `relativedelta` 字段，并逐日枚举 2000–2399 的 146,097 个日期 |
| [negative_startxref_demo](负指针_pypdf/negative_startxref_demo/) | 两份完整 pypdf 源码读同一份把 `startxref` 改成负数的 PDF，看修前在哪一处 `seek` 抛 `ValueError`、合并版如何归一化后重建 xref；`--emit` 存下四份样例，`scan_startxref.py` 只读末尾 1 KiB 报两个指针的落点 |
| [rotate_demo](旋转丢元素_pottery/rotate_demo/) | 两版 pottery 在 fakeredis 上跑 369 组旋转，对照最终列表和实际发出的 `LPUSH`/`RPUSH`/`LTRIM` 参数 |
| [local_time_demo](本地时间_tomlkit/local_time_demo/) | 两版 tomlkit 序列化同一个带时区的 `time`，看写出的文本、自己的解析器能否读回，以及不带时区时是否逐字节不变；`--emit` 写出两版样例，`scan_local_times.py` 扫目录里带偏移的 Local Time |
| [math_log_demo](对数定义域_nushell_math_log/math_log_demo/) | 从三个固定提交里提取 `math log` 的底数检查与输入判断，看 1、NaN 与 ∞ 各在哪一版被拦下，域内算术是否逐位不变 |
| [bytes_demo](字节删除_nushell_bytes/bytes_demo/) | 从五个固定提交里提取 `remove_impl`，看未命中时丢了哪几个字节、panic 在哪一版消失，以及首稿与最终版在 882 组输入上是否逐字相同 |
| [subdirectory_demo](子目录定位_pdm/subdirectory_demo/) | 同一份含三个项目的 ZIP 交给两版 PDM 走完导入、导出、重新读入，看子目录在哪一版没写进 archive 表，新 candidate 的元数据来自哪个目录 |
| [comments_demo](PDF注释_pypdf/comments_demo/) | 真实三版 pypdf 解析同一组对象字节，对照连续注释边界、流位置和无注释数组的函数调用预算 |
| [flags_demo](后端参数_pathspec/flags_demo/) | 三份固定源码交给真实 RE2 / Hyperscan，对照编译参数丢失、初稿回退和最终映射，同时检查匹配结果与实际后端 |
| [datetime_demo](日期差_nushell_datetime/datetime_demo/) | 三份固定源码交给同一个真实 Nu 执行，对照负天数、初稿的语义变化与最终兼容拆分，并独立检查闰日输入解析 |
| [hash_demo](锁文件哈希_pdm/hash_demo/) | 同一份归档哈希经过两版 PDM 读入函数，再导出 requirements / pylock，看它在哪一步丢失或保留 |
| [backpressure_demo](取消与背压_anyio/backpressure_demo/) | 修复前后两版 AnyIO 各连一条真实的 TCP，看取消之后数据有没有继续堆进队列，连接还能不能接着用 |
| [cubic_demo](拥塞控制_cubic/cubic_demo/) | 同一次持久拥塞，修复前后的 `ssthresh`，以及之后每个 RTT 的窗口变化 |
| [variance_demo](方差稳定性_nushell_variance/variance_demo/) | 六种方差算法在同一批输入上的误差，包括反例和数量级扫描 |
| [wheel_demo](时间轮_timing_wheel/wheel_demo/) | 原实现、首篇引用的初稿、最终修复，三版放在一起跑，也包括那两组级联反例 |
| [isort_demo](导入排序语义_isort/isort_demo/) | 同一份带 noqa 的导入交给修复前后两版 isort 快照，看注释在哪一版丢失、flake8 如何当场翻脸，折行与无注释场景两版逐字一致 |
| [tomlkit_demo](转义往返_tomlkit/tomlkit_demo/) | 同一组追加操作喂给修复前后两版 tomlkit 快照，看引号与反斜杠在哪一版把源文本拼坏、文档级往返哪一版当场翻车，String 拼 String 与追加普通文本两版逐字一致 |
