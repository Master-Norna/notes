# 来源与哈希

## 合并提交

- 仓库：<https://github.com/nushell/nushell>
- PR：<https://github.com/nushell/nushell/pull/19127>
- 合并提交：`73f0a8983aa2f99b1e9e9383c983caf9244fadce`
- 合并父提交：`65a22bfa4512e061ef7142914d032e2ad4a5d2ae`（#19107 的合并提交）
- 源码归档：`nushell-73f0a8983aa2f99b1e9e9383c983caf9244fadce.tar.gz`
  （核验用副本在 `.yan/math-log/`，不进公开提交）
- 归档 SHA-256：`3EA7408434D3F3D8B85BE6EB92423F4E8177CB9C15518929806B7CE30790A15C`

## `upstream/<标签>/log.rs`

所有文件都取自 `crates/nu-command/src/math/log.rs`：

| 标签 | 提交 | SHA-256 |
| --- | --- | --- |
| `parent` | `65a22bfa4512e061ef7142914d032e2ad4a5d2ae` | `7def04504676f4cc6868f809842cb65344731f00f6df91fd856f2be1e16d21ec` |
| `first` | `8af57986e3d6c10b451baba5a5199c79b644b0fd` | `90f98a5c230a0a81891fcbe9e55e416f0374c897c354987775234337614524e6` |
| `merge` | `73f0a8983aa2f99b1e9e9383c983caf9244fadce` | `badd980751f26a5e7e23f85257f1cb5ca3b66225a67acd89a557371b92d90abd` |

`merge` 与 review 后的重写提交 `3fc3526caa1babd5caf7a1c5f594c6d394d390ed`
的哈希相同：合并没有再改这个文件。

标签 `0.116.1`（提交 `b632ef0994e07b5176ec45171e8cee2c127c5563`，2026-10-04）
的同一文件哈希也是 `7def0450…`，所以 0.116.1 的行为就是 `parent` 的行为；
`cargo test` 里的 `the_parent_matches_the_official_0_116_1_binary` 记录了
从官方 0.116.1 二进制上抄下来的十条命令输出。

## 提取方式

`build.rs` 从每个文件里按名字定位 `fn require_positive_base(` /
`fn require_valid_base(` 与 `fn operate(`，按花括号配对截取完整函数体，只把
`fn` 改成 `pub fn`，生成到 `OUT_DIR/extracted.rs`。其余类型来自 `src/lib.rs`
的最小代用品；`Value` 多留了 `String` 与 `Nothing` 两个变体，好让 `operate`
里「非数字输入」那条分支仍然可达。

## 上游许可

`upstream/LICENSE` 取自合并提交的 `LICENSE`，SHA-256
`ff5dcaaba6140ec57cafdd4f707cd0d329e727477cf7d5b9ba7a244ec2678b79`。
