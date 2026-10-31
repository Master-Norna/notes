# 来源与哈希

## 合并提交

- 仓库：<https://github.com/nushell/nushell>
- PR：<https://github.com/nushell/nushell/pull/19107>
- 合并提交：`65a22bfa4512e061ef7142914d032e2ad4a5d2ae`
- 合并父提交：`8696b5246f7a920156a0be08f29ce7fefe16d885`
- 源码归档：`nushell-65a22bfa4512e061ef7142914d032e2ad4a5d2ae.tar.gz`
  （核验用副本在 `.yan/bytes-remove/upstream/`，不进公开提交）
- 归档 SHA-256：`9F1A2E5B5B9DC30A321D7FD8E6D9CD040B5585FDF314F1BFA592019E2115443F`

## `upstream/<标签>/remove.rs`

所有文件都取自 `crates/nu-command/src/bytes/remove.rs`：

| 标签 | 提交 | SHA-256 |
| --- | --- | --- |
| `old-parent` | `95220520639910c77d79c31bece37c468d54aeec` | `cc7fb2b59592a638b6bd670e841f8b1ff18634a5dd8c9df1a52ea874cf2deec7` |
| `old-merge` | `15421dc45e6b8b831b6cacebe80b37eda46fbcd9` | `97e6ba0f0529205376cd592e528c18457d4134f1eb83bd303e7c594df3ed3584` |
| `merge-parent` | `8696b5246f7a920156a0be08f29ce7fefe16d885` | `99b8866c381cca4ad7a3e2ab619aa82f24a961eabf0dd4f81543fdf62ff5be02` |
| `first` | `9e99b50de7dd8cb37b5b8b4187d3972afe6e291c` | `8c00a5bf9c4329e8402f1b94e39600c868e12cabc14291ee3f143f1f78eee06c` |
| `merge` | `65a22bfa4512e061ef7142914d032e2ad4a5d2ae` | `39acb1ff68624d9d2881b83c81390424822f6bd6d0077cade7facfa50ee32587` |

`old-merge` 与 `merge-parent` 的哈希相同：两次提交之间这个文件没有变化。
`merge` 与 review 后重写提交 `bb2c7f5a748c6ca21a415dcf681b17b7302d4b7e`
的哈希也相同。

## 提取方式

`build.rs` 从每个文件里定位 `fn remove_impl(`，按花括号配对截取完整函数体，
只把 `fn` 改成 `pub fn`，生成到 `OUT_DIR/extracted.rs`。其余类型来自
`src/lib.rs` 的最小代用品。

## 上游许可

`upstream/LICENSE` 取自合并提交的 `LICENSE`，SHA-256
`ff5dcaaba6140ec57cafdd4f707cd0d329e727477cf7d5b9ba7a244ec2678b79`。
