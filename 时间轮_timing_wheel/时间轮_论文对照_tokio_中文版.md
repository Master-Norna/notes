# 时间轮里那行凭空出现的 `+1`

```rust
let now\_slot = ((now / slot\_range(self.level)) % LEVEL\_MULT as u64) as usize + 1;
```

为什么一个成熟的 Rust 库（tokio-util），时间轮里要在这里**凭空 `+1`**？

这个修复 2026 年 9 月先在 runtime 侧合入（[tokio#8334](https://github.com/tokio-rs/tokio/pull/8334)，9 月 7 日）；**tokio-util 侧的同一行修复目前还在等审（[tokio#8519](https://github.com/tokio-rs/tokio/pull/8519)）**——本文引用的代码取自 #8519 分支，不是 tokio-util 的 master。它修的是一个真实生产事故：一个 PostgreSQL 代理 **pgdog 连续运行 12 天后，所有定时任务集体"挂起"**——不报错、不 panic，就是安静地不再触发。

先看图，再给结论。

!\[tokio-util 时间轮：6 层 × 64 槽](assets/fig1\_levels.png)

**去掉这个 `+1`，一个 12 天后到期的定时器，会被推迟到 807 天后才触发。** 整整多睡了两年多。

!\[同一组 timer，两种实现的触发时刻](assets/fig3\_timeline.png)

下面倒着讲：先看清楚它到底修了什么，再回溯时间轮为什么会长成这样，最后放回那篇 1987 年的论文里。

\---

## 一、时间轮：把"谁下一个到期"从 O(n) 降到 O(1)

定时器要回答的核心问题就一个：**下一个谁到期？**

朴素做法是把所有未决定时器按到期时间排序，每次取队头。增删、维护都是 O(n)——定时器越多越慢，内核里扛不住。

时间轮（timing wheel）的思路来自钟表：**把时间切成等宽的格子（槽），每个槽放"在这个时间点到期"的条目。** 指针每走一格，处理那一格的条目。增删就是往某个格子里塞/取，O(1)。

但一个钟表只能覆盖一圈。要覆盖更长的时间，有两个经典扩展（1987 年 SOSP 那篇同时给了）：

1. **哈希进槽**：范围太大，就把大量条目哈希到同一个槽，槽内用链表存；
2. **层级轮**：多个不同粒度的轮叠起来，低层管近处、高层管远处，高层槽到期时把条目"下沉"到低层。

tokio-util 用的是层级轮，6 层 × 64 槽：

|层|槽宽|覆盖范围|
|-|-|-|
|L0|1ms|64ms|
|L1|64ms|\~4s|
|L2|\~4s|\~4min|
|L3|\~4min|\~4hr|
|L4|\~4hr|\~12day|
|L5（顶）|\~12day|\~2yr|

1ms 精度，覆盖约两年。找下一个占用槽靠一个 `occupied` 位图 + `rotate\_right` + `trailing\_zeros`，也是 O(1)。

到这里一切都很美好。问题出在**边界**。

\---

## 二、边界：最远的定时器往哪放？

层级轮不是无限层。一个定时器如果比顶层一圈还远，`level\_for` 没地方放它——于是 tokio 做了两件事：

1. 用 `MAX\_DURATION`（顶层一圈，约 2 年）当上限，再远的直接拒绝；
2. **逻辑上属于"顶层 +1"的定时器，被强行塞进顶层的某个槽。**

代码注释自己把这事说得很直白（`level.rs`）：

> What this means is that the top level's slots act as a \*\*pseudo-ring buffer\*\*, and we rotate around them indefinitely.

翻译过来：**顶层的槽变成了一个"伪环形缓冲"，无限期地绕圈。** 一个槽里，可能同时躺着"逻辑上在很后面、物理上绕了一圈回来"的条目。

这就是 Lawn 论文（2019）通篇在打的 **overflow problem**——层级轮"最远定时器被挤进顶层"的那个问题。

现在把镜头拉到顶层。假设 `now`（已流逝时间）落在顶层的**槽 0**，而槽 0 里恰好躺着一个伪环条目（逻辑上整整一圈之后才到期）：

!\[顶层环扫描对比](assets/fig2\_ring\_scan.png)

找下一个到期槽的逻辑，是"从 `now` 所在的槽开始，顺时针找第一个非空槽"。

**问题就在这：如果从槽 0 开始找，而槽 0 自己是满的（被伪环条目占着），你会立刻命中它。** 但那个条目逻辑上是一圈之后的——它不该被当成"现在"。

`+1` 干的就是这一件事：**扫描起点从 `now` 槽往后挪一格，跳过它。** 因为 `now` 槽里能装的，最多就是"一整圈之后"的那个最远条目，把它跳过，才能看到槽 1 里真正更近的定时器。

对低层来说，`+1` 是个无害的 no-op——`level\_for` 保证条目永远不会落在 `now` 所在的低层槽（那个槽永远是空的），跳不跳都一样。**所以这一行只在顶层生效，而顶层恰恰是唯一会出事的层。**

\---

## 三、去掉 `+1` 会怎样（代码实测）

与其口头推演，我直接把 `tokio-util` 的时间轮代码搬进一个独立 crate，做成 fixed（含 `+1`）/ buggy（去掉 `+1`）两个版本，逐字节相同、只差那一行，然后跑真实行为。三个场景：

### 场景 A：最小复现

顶层槽 0 放一个伪环远端条目（`2^36+1` ms），槽 1 放一个 12 天后到期的条目，`now` 落在槽 0：

```
FAR  = 2^36+1 ms   (≈795 天)   → 顶层槽 0（伪环，与 now 同槽）
NEAR = 2^30+1000 ms (12 天+1秒) → 顶层槽 1

BUGGY  poll\_at = 2^36 (795 天后)      ← 被伪环条目劫持
       fires near @ 2^36+2^30+1000    ← NEAR 被推迟整整一圈，807 天才触发
FIXED  poll\_at = 2^30 (12 天后)
       fires near @ 2^30+1000         ← NEAR 准点（12 天+1 秒）
```

**buggy 把 12 天到期的定时器推迟到了 807 天。** 推的幅度恰好是顶层一整圈（`2^36` ms ≈ 795 天）。

（一个佐证"跑出来的比写下来的可靠"的小细节：移植 commit 的 message 里把推迟幅度写成了 "\~19 days"，但 `2^36 - 2^31 ms` 实际是 770 天——上面是 release 实测值。）

### 场景 B：低层短定时器免疫（对照）

运行 12 天，一个长 sleep 占顶层，一个 5 秒的 interval。预期：buggy 和 fixed 行为一致。

实测**确实一致**——因为 5 秒的 interval 按相对距离落在低层（L2），根本不进顶层，伪环够不着它。

这一条划清了 bug 的边界：**问题只在顶层，低层短定时器天然免疫。** 不是所有定时器都受影响，只有"恰好也落在顶层"的那些。

### 场景 B2：pgdog 的精确机制

那 pgdog 的 interval 为什么中招？关键在 `level\_for` 用的是 **`elapsed ^ when`（异或距离）**，不是简单的 `when - elapsed`。

构造：`elapsed = 2^30 - 1000`（紧贴 12 天边界之下），一个贴近 max 时长的长 sleep，一个 5 秒的 interval：

```
elapsed   = 2^30 - 1000            （12 天 - 1 秒）
MAX\_TIMER = elapsed + 2^36 - 2000  （顶层 now\_slot，伪环条目）
INTERVAL  = elapsed + 5000         （跨过 2^30 边界！）

  → INTERVAL 的 elapsed^when ≈ 2^31（异或距离爆炸）
  → level\_for 把它 fudge 进顶层，槽 1

BUGGY  poll\_at = 2^36 (795 天后)   ← 伪环条目劫持
       fires interval\_5s @ 807 天  ← 5 秒的 interval 挂起 795 天
FIXED  poll\_at = 2^30 (1 秒后)
       fires interval\_5s 准点
```

**触发条件全齐了**：运行时长贴近 12 天边界 + 一个长定时器占住顶层 `now` 槽 + 短定时器恰好跨过 `2^30` 边界（异或距离爆炸、被 `level\_for` 推进顶层）。三者一碰，短定时器就被伪环条目劫持，`poll\_at` 跳到一整圈之后。

pgdog 的 runtime driver 每次 `park` 前只取**一次** `poll\_at`，然后睡到那个时刻、期间没有别的唤醒源——所以 `poll\_at` 被劫持 = driver 睡一整圈 = 所有短周期定时器"挂起"。这正是事故现象。

> 顺带纠正一个流传的说法：#8334 的 PR 描述里写"short sleeps got queued on the top level 5"（短 sleep 被排到顶层）。这话本身没错，但\*\*原因不是"短"，而是"跨边界导致异或距离爆炸"\*\*。场景 B 证明了：不跨边界的短定时器落在低层，完全不受影响。

三个场景 + 移植过去的 9 个单元测试全绿，本地 tokio checkout 里时间轮的 12 个测试也全绿。

\---

## 四、一条三十年的谱系

这行 `+1` 不是凭空冒出来的，它站在这条线的最末端：

|年|论文|出处|一句话|引\*|
|-|-|-|-|-|
|1987|Varghese \& Lauck, *Hashed and hierarchical timing wheels*|SOSP '87（DEC）|奠基：O(1) 哈希轮 + 层级轮|89（期刊版另 51）|
|1998|Costello \& Varghese, *Redesigning the BSD timer facilities*|Softw. Pract. Exper.|时间轮真正落进 NetBSD 内核|3|
|1999/2000|Aron \& Druschel, *Soft timers*|SOSP '99 / TOCS 2000|微秒级软件定时器，为网络处理免中断|103|
|2017|Saeed et al.（Georgia Tech + Google）, *Carousel*|SIGCOMM '17|端侧流量整形，百万级流|104|
|2019|Lev-Libfeld, *Lawn*|arXiv|按 TTL 分桶，去掉层级，攻 overflow 问题|—|
|2026|tokio-util wheel|Rust 用户态|6 层级轮，任意 TTL，`+1` 解顶层伪环|—|

\* 被引数取自 OpenAlex，快照 2026-09-28。

一个容易忽略的事实：**O(1) 的数据结构 1987 年就提出了，但 1998 年才真正进内核。** 之后三十年沿三条轴展开——

* **粒度**：Soft timers 把软件事件调度压到数十微秒，让 TCP 能做按速率的发包调度；
* **结构简化**：Lawn 直接砍掉层级，按 TTL 分桶；
* **应用域**：Carousel 拿它去做端侧流量整形（它的参考文献里确实引了 1987 原文，谱系坐实）。

同一颗时间轮，三种宿主：**1987 的数据结构、1998 内核的中断锁约束、tokio 的用户态单线程**。BSD 1998 那条"关中断时间必须有界"的工程约束，在 tokio-util 里不存在——`DelayQueue` 跑在用户态，它用一个 `tokio::time::Sleep` 等下一个 deadline，被唤醒后再推进自己的时间轮，没有需要关硬件中断的临界区。

\---

## 五、为什么 Lawn 不太适合这个场景

Lawn 的核心思想：**不按"到期时刻"分桶，按 TTL 值分桶。** 每个 TTL 一个队列，队内按入队时间天然有序，每 tick 把各桶队头已过期的"割草"掉。

好处是 overflow 问题在结构上消失了——没有层级，就没有"最远定时器往哪放"。**代价是每 tick 的平均复杂度 O(t)，t = 不同 TTL 的种类数。** 论文自己给的适用前提：`不同 TTL 种类数 ≪ 并发 timer 数`。

拿它和 tokio-util 摆在一起：

||tokio-util（层级轮）|Lawn（TTL 分桶）|
|-|-|-|
|前提假设|TTL 任意（用户 `sleep(Duration)` 随便给）|不同 TTL 种类数 ≪ 并发 timer 数|
|边界处理|顶层伪环 + `+1` 偏移 + `MAX\_DURATION` 上限|无 overflow（结构上消失）|
|代价|边界逻辑微妙、易写错（这次就是）|PerTick O(t)，t = TTL 种类数|
|适用|通用用户态运行时|Redis streams / RDMA 这类 TTL 高度集中的场景|

**Lawn 的核心前提，和通用 `DelayQueue` 的任意 deadline 场景并不天然匹配**：tokio 的 TTL 是用户任意值，不同 TTL 的种类数很容易和并发 timer 数同量级，`O(t)` 的 per-tick 开销就顶不住了。这解释了一个现象——层级轮 + 偏移是**更自然、与当前需求兼容**的选择，它用一行 `+1` 的代价，避开了 Lawn 那个 `O(t)` 前提风险。

反过来说，在 Redis streams 那种 TTL 高度集中的场景里硬套层级轮，才是杀鸡用牛刀。

两个数据结构，两个前提，各管一段。这不是"谁更先进"，也不是"tokio 看了 Lawn 然后拒绝"——工程设计很少能仅凭一组条件证明"唯一正确"，只能说**哪个前提和当前需求对得上**。

\---

## 六、存疑与未决

1. **GD-Wheel（EuroSys '15）**：OpenAlex 给它挂的摘要讲的是 Memcached/Redis 缓存替换策略，与时间轮无关；ACM 页面 403 验证不了。**未列入核心谱系**——要么元数据挂错，要么我对它的假设是错的。
2. **1987 与 Soft timers 全文**：ACM 付费墙（Cloudflare 挑战 + 镜像 401），本文对这两篇止于摘要。
3. **Carousel 的 pacing 内部**：只验证到"它引用了 1987 原文"，"pacing 用时间轮"未读到全文，不作断言。

\---

## 脚注

① 写作中纠正过两处早期误记：1987 的作者（曾误记为 Andersson \& Erlick，实为 Varghese \& Lauck）；"搬进 OS"（曾误归给 1987，实为 1998）。凭印象记作者/年份是常态，下笔前逐条重查是应做的。

② 方法注记：定位/元数据/引文网络/摘要用 OpenAlex REST（无 key）；参考文献用 Crossref（按 DOI）；图谱可视化用 Semantic Scholar 网页；**代码行为用独立 crate 双版本实测**（fixed/buggy 逐字节相同、只差 `+1`，release 模式跑）。每个"论文声称 X"标了来源级别，每个代码断言带行号或实测输出。

③ 代码引用自 PR [#8519](https://github.com/tokio-rs/tokio/pull/8519) 分支的 `tokio-util/src/time/wheel/`（MIT 协议；行号对应本文写作时的本地 checkout）。注意：该 PR 截至本文发布时仍为 open，tokio-util 的 master 上尚无此修复。

