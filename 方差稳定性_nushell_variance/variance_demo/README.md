# variance_demo

`nushell #19108`（`math variance` 数值稳定性修复）的验证工程，只依赖 Rust 标准库。

六个变体分别复刻了实际实现的计算形状：

| 函数 | 说明 |
|---|---|
| `naive` | 旧实现：单遍恒等式 `Σx² − (Σx)²/n`，运算顺序与 `sum_of_squares` 一致 |
| `two_pass_plain` | 普通两遍：先均值，再偏差平方和 |
| `mean_div_n` | 均值改成 `Σ(x/n)` 的两遍法 |
| `corrected_two_pass` | Björck 修正两遍：`ss − (Σd)²/n` |
| `welford` | Welford 在线更新 |
| `shifted` | 合并后的修复：`r = x − min`，`m = Σr/n`，`Σ(r − m)²/denom` |

```sh
cargo test --release    # 7 个测试：合并后的行为、各候选方案的反例、两个边界
cargo run --release     # 打印文中表格与扫描数据，并写出 out/*.csv
python plot_fig1.py     # 从 out/curve.csv 生成 ../assets/fig1_variance_error.png
```

输出里的 `## Cases` 表就是文章第三节那张对比表；`out/curve.csv` 是第四节
256 组样本（64 个值、16 个尾数 × 16 个数量级）的原始数据。
