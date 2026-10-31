# 拦住了 1 和 NaN，却漏掉 ∞

```nushell
> 2 | math log 1
inf
> 1 | math log 1
NaN
> 2 | math log inf
0.0
```

这是 Nu 0.116.1 上的三条真实命令，没有一条报错。同一个命令对 `2 | math log 0` 是会拒绝的，错误信息里写着 `Base has to be greater 0`。所以「底数不合法」这件事，它管；它只是不认为 1 和 ∞ 不合法。

`math log` 算的是 `f64::log`。按定义 `log_b(x) = ln x / ln b`：底数为 1 时 `ln 1 = 0`，分母为零，结果只能是 ±∞ 或 `0 / 0` 的 NaN；底数为 ∞ 时 `ln ∞ = ∞`，任何有限输入除以它都得 0。这些答案都能打印出来，看起来都像数。

输入那一侧还有一处，形状一样：

```nushell
> NaN | math log 2
NaN
```

## 守卫写成了「坏的就不让进」

修复前，底数的检查长这样（[`log.rs` @ `65a22bf`](https://github.com/nushell/nushell/blob/65a22bfa4512e061ef7142914d032e2ad4a5d2ae/crates/nu-command/src/math/log.rs#L140-L150)，也就是 0.116.1 里那一份）：

```rust
fn require_positive_base(base: Spanned<f64>, head: Span) -> Result<f64, ShellError> {
    if base.item <= 0.0f64 {
        return Err(ShellError::UnsupportedInput {
            msg: "Base has to be greater 0".into(),
            ..
        });
    }
    Ok(base.item)
}
```

读起来像一道完整的检查：坏值是「≤ 0」。可 1 是正数，+∞ 是正数，两个都从判据正中间走了过去。NaN 更特殊——**它跟任何值比较都为假**，`NaN <= 0.0` 是假，所以这个 `if` 根本没有看见它。这道守卫漏掉的是三样东西：判据没想到的两个正数（1、+∞），和判据没法比较的那个值（NaN）。

输入侧是同一句话换了个主语：

```rust
if val <= 0.0 {
    return Value::error(
        ShellError::UnsupportedInput { msg: "'math log' undefined for values outside the open interval (0, Inf).".into(), .. },
        span,
    );
}
```

`NaN <= 0.0` 同样是假，于是 `NaN | math log 2` 一路走到 `val.log(2)`，返回 NaN。

守卫的形状是「如果坏，就报错」。这个形状默认了一件事：坏值都答得出「我 ≤ 0 吗」。NaN 答不出任何比较，它不是坏在数值上，而是根本不在数轴上。

## 首稿补了 1 和 NaN

第一版提交（[`8af5798`](https://github.com/nushell/nushell/commit/8af57986e3d6c10b451baba5a5199c79b644b0fd)）换了判据，也换了措辞：

```rust
// A logarithm is only defined for a base in the open interval (0, 1) union (1, Inf):
// the base must be positive and not equal to 1. `NaN` is rejected as well, since it
// satisfies neither `> 0` nor `== 1`.
if base.item.is_nan() || base.item <= 0.0f64 || base.item == 1.0f64 {
```

`is_nan()` 把 NaN 点了名，`== 1.0` 补上那个洞，报错信息改成 `Base has to be greater than 0 and not equal to 1`。测试加了六条：三条拒绝（底数 1、1.0，以及用 `inf - inf` 造出来的 NaN），三条接受（底数 2、10、e）。

`+inf` 还站在门里。`2 | math log inf` 仍然返回 `0.0`。

## 评审在同一轮里点了两处

八天后，fdncred 的评审在两处停下（[review](https://github.com/nushell/nushell/pull/19127#pullrequestreview-5470451175)）。行内那一条说的是 `+inf`：

> `+inf` still gets through. The comment above says the domain is the open interval `(0, 1) ∪ (1, Inf)`, but this condition accepts `inf`... That is the same silent-garbage result this PR fixes for `1` and `NaN`.

评审正文里的那一条，说的是另一侧——不在这个 diff 里、但同一个函数里的输入检查：

> It's the same class of bug on the input side.

两条其实是两种漏法。`+inf` 是判据写窄了：`is_nan()` 只挡 NaN，没管无穷，而正无穷和负无穷在这个函数里的命运并不一样——`-inf` 被 `<= 0` 挡下，`+inf` 没有。输入侧的 NaN 则是同一个形状又出现了一次：又一个「如果坏就报错」，又一次看不见 NaN。

## 合并版把一侧补全，把另一侧翻过来

底数那一侧继续补判据，用一次 `is_finite()` 把 NaN 和两个无穷一起挡住（[合并版 `log.rs`](https://github.com/nushell/nushell/blob/73f0a8983aa2f99b1e9e9383c983caf9244fadce/crates/nu-command/src/math/log.rs#L140-L153)）：

```rust
if !base.item.is_finite() || base.item <= 0.0f64 || base.item == 1.0f64 {
    return Err(ShellError::UnsupportedInput {
        msg: "Base has to be a finite number greater than 0 and not equal to 1".into(),
        ..
    });
}
```

输入那一侧不再列举坏值，改成要求好值：

```rust
// A positive test keeps `NaN` out of the log: `NaN > 0.0` is false, so it
// reaches the error branch instead of silently returning `NaN`.
if val > 0.0 {
    // Specialize for better precision/performance
    let val = if base == 10.0 {
        val.log10()
    } else if base == 2.0 {
        val.log2()
    } else {
        val.log(base)
    };

    Value::float(val, span)
} else {
    Value::error(
        ShellError::UnsupportedInput { msg: "'math log' undefined for values outside the open interval (0, Inf).".into(), .. },
        span,
    )
}
```

**从「坏的进不来」改成「好的才放行」**，NaN 就无处可藏：`NaN > 0.0` 为假，它自然落进 else。作者在回复里说，这个写法是同目录的 `math ln` 已经在用的。

输入侧这一改，对轴上的每一个点都没有影响。`-inf`、`0`、`-1` 在旧写法里被拒绝，在新写法里同样被拒绝；`0.5`、`2`、`+inf` 在两边得到同一个值。变的只有轴外那一个 NaN。

![底数与输入两根轴：青色的区间是合并版放行的，红底是两版都拒绝的，红圈是这次新拦下的 1 与 ∞，灰虚线框里的 NaN 不落在任何一根轴上](assets/fig_domain.png)

底数一侧其实也可以写成正向的（`if base.item > 0.0 && base.item != 1.0 && base.item.is_finite()`）；合并版保留了「列举坏值」的形状，只是把列举写全。

## 无穷作输入留着，作底数不留

合并版有一个有意的不对称：`inf | math log 2` 仍然返回 `inf`，`2 | math log inf` 报错。

理由在数学那边。输入趋于无穷时，`log₂` 趋于无穷，`inf` 是这个极限；底数取无穷时，函数变成恒等于 0 的常数，任何输入都得不到信息。作者在[回复](https://github.com/nushell/nushell/pull/19127#discussion_r4235789344)里写得很清楚：`inf | math log 2` 还是 `inf`，"which is the correct limit"，所以他把 PR 标题改成「reject invalid bases and a NaN input value」，没有顺手宣称拒绝了所有非有限输入。

## 测试里还有三件事

首稿的测试里有一条精确浮点断言：`16 | math log 2.718281828459045` 应当等于 `2.772588722239781`。这台机器上它确实等于——逐位相同，`0x40062e42fefa39ef`。但等式两边都不是凭空的数：分母是 `ln(2.718281828459045)`，这个值只是四舍五入到 1，并不正好是 1；Rust 自己的文档就写着 [`f64::log`](https://doc.rust-lang.org/std/primitive.f64.html#method.log) 的精度"varies by platform, Rust version, and can even differ within the same execution from one invocation to the next"。

把分母换成 1 下面一个 ulp 的 `0.9999999999999999`，同一个式子给出 `2.7725887222397816`，断言当场翻掉。这不是说哪个平台真的算错过，而是说这条断言把正确性押在了 libm 的最后一个比特上。评审的建议是换成有精确结果的底数：`16 | math log 4` 得 `2.0`，`8 | math log 0.5` 得 `-3.0`。

第二件事是覆盖：首稿的测试全在 `b > 1` 那一半，`(0, 1)` 这一半一次都没跑过——而那正是 PR 自己说合法的另一半定义域。

第三件事是重复：`16 | math log 2` 已经有 `const_log` 覆盖，`100 | math log 10` 是 `examples()` 的第一条，`test_examples` 会执行它。另外 `NaN` 在 nushell 里是字面量，不必用 `inf - inf` 去造。

合并后的测试把前两组折进 `#[rstest]`：七个非法底数（`1`、`1.0`、`0`、`-2`、`NaN`、`inf`、`-inf`）、四个合法底数（`2`、`10`、`4`、`0.5`），加一个 `NaN` 输入，加上原有的三条，一共 15 个 case。

## 三版跑同一个矩阵

复现在 `对数定义域_nushell_math_log/math_log_demo/`：`build.rs` 从三份固定的 `log.rs` 里按花括号配对取出 `require_*` 与 `operate`，配上最小的 `Value`、`Span`、`Spanned`、`ShellError` 代用品编译。算法与判据不是手抄的，改动只在可见性。

三版是：父提交 `65a22bf`（与 0.116.1 的同一文件逐字节相同）、首稿 `8af5798`、合并 `73f0a89`。取 12 个底数乘 12 个输入，共 144 对：

| 版本 | 域外仍被回答 | 其中答案是 NaN 或 ±inf | 域内被拒绝 |
| --- | --- | --- | --- |
| 父提交 | 29 | 23 | 0 |
| 首稿 | 13 | 7 | 0 |
| 合并版 | 0 | 0 | 0 |

29 里，24 对是「底数 1、NaN、∞」乘上各种输入，其余 5 对是五个合法底数配 NaN 输入。首稿把 1 和 NaN 那 16 对清掉了，剩下的 13 对里，8 对来自 `b = ∞`，5 对来自 NaN 输入。

两个版本都回答的 35 对（5 个合法底数 × 7 个合法输入），逐位相同 35 对。这次修复没有碰正常算术。

同一套判定，拿去和官方 0.116.1 二进制对了一遍：十条命令的输出与提取出来的父提交版逐条相同，包括 `2 | math log 1` 的 `inf` 和 `2 | math log inf` 的 `0.0`。

范围要说清楚：这是三个版本的函数提取运行，不是 Nushell 构建，没有解析器、管道和 const 求值；`run_const` 调用的是同一个 `require_*`，但没在 demo 里跑。浮点部分只在本机 Windows 上跑过，别的平台的 libm 没有测。至于这个修复进了哪个发行版——合并是 2026-10-10，0.116.1 是 2026-10-04 发的，查的时候（2026-10-31）仓库里最新的标签还是 0.116.1。

顺带一提，这次合并的父提交正好是同一仓库里 bytes remove 那次修复的合并提交，两次合并相隔 46 秒。

## 两种漏法

`1` 和 `∞` 是判据写得窄：`<= 0` 把「坏」定义得太小，补条件就能补齐。NaN 是判据的方向反了：它默认每个值都答得出「我坏吗」，而 NaN 对所有比较都答「否」。前者靠加一个 `== 1.0` 和一个 `is_finite()` 解决；后者得把句子翻过来，先说「好的长什么样」。

翻过来之后还有个好处：下一个浮点的怪值出现时，它也会落进 else，而不是从某个 `<=` 的缝里漏过去。

[离线复现工程](math_log_demo/)保存父提交、首稿和合并三版的固定 `log.rs`，构建时自动提取 `require_*` 与 `operate`，附上游 MIT 许可证、来源 SHA 与哈希；运行方法、数字和适用范围见[工程 README](math_log_demo/README.md)。它直接编译提取出的函数，不需要完整 Nushell，也不需要联网。

本文依据的最终实现已随 [#19127 合并](https://github.com/nushell/nushell/commit/73f0a8983aa2f99b1e9e9383c983caf9244fadce)。
