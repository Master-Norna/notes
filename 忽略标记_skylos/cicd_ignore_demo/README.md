# cicd_ignore_demo

同一个 GitHub Actions workflow，交给三版 skylos 扫描，看它报不报。差别只在一件事：忽略标记 `skylos: ignore[规则号]` 只该从真正的 YAML 注释里读，还是从任意文本里读。

需要 PyYAML（skylos 的运行时依赖，本机测于 6.0.3）。其余只用标准库。

```bash
python -B run.py --test     # 断言下表
python -B run.py --table    # 打出下表
python -B run.py --json     # 原始结果
```

| 用例 | v5.6.0 | 父版 `a5024d7` | 合并版 `1a105bd` |
| --- | --- | --- | --- |
| `d340_quoted_name_oneline` | 未报出 | 未报出 | 第 7 行 |
| `d340_quoted_name_block` | 第 8 行 | 未报出 | 第 7 行 |
| `d327_quoted_name_oneline` | 未报出 | 未报出 | 第 7 行 |
| `d340_comment_above_run` | 第 9 行 | 未报出 | 未报出 |
| `d340_trailing_comment` | 未报出 | 未报出 | 未报出 |
| `d327_trailing_comment` | 未报出 | 未报出 | 未报出 |
| `d327_name_repeats_command` | 未报出 | 未报出 | 第 7 行 |
| `d327_env_repeats_command` | 未报出 | 未报出 | 第 9 行 |
| `d327_escaped_run` | 未报出 | 未报出 | 第 8 行 |
| `d327_two_identical_steps` | 第 7 行 | 第 7 行 | 第 7 行、第 9 行 |
| `d327_alias_run` | 第 7 行 | 第 7 行 | 第 7 行、第 9 行 |
| `d327_ignore_first_of_two` | 未报出 | 未报出 | 第 9 行 |

只看 `SKY-D340`（发布命令，HIGH）和 `SKY-D327`（把环境变量或本地机密送到外部地址，CRITICAL），其余规则的输出不参与比对。

## 目录

- `cases/*.yml`：每份 workflow 一个文件。扫描时复制成临时目录里的 `.github/workflows/ci.yml`，再用整目录入口 `scan_github_actions()` 扫。
- `vendor/v560`、`vendor/parent`、`vendor/merge`：三版源码里 `skylos` 包的一个子集，见下。
- `scan_one.py`：单个版本的扫描器。它把对应的 vendor 目录插到 `sys.path` 最前，再断言 `skylos.__path__` 落在里面。
- `run.py`：三个版本各起一个子进程（`scan_one.py`），汇总成表，`--test` 与 `EXPECTED` 逐格比对。

三个版本不共用一个进程，是因为 `skylos` 的模块在第一次 import 时就定住了；同一进程里换 `sys.path` 拿不到另一份。

## 快照来源

| 版本 | 提交 | tarball 字节 | SHA-256 |
| --- | --- | --- | --- |
| `v560` | `v5.6.0` | 56,561,812 | `92BCA79DBAA53232B7A2FAF4050823A58C90FDB03631F020ECCA35B695C4E0E0` |
| `parent` | `a5024d78565de6ed5840fa3e0c96c8ab6db27c00` | 56,626,794 | `EFAEA183ECD5BA932B537CA69AD254585AC25E739A73EEDDC2BA12D82AAE3EEA` |
| `merge` | `1a105bdc3227b0dce8507a19da9f69fcf90eade2` | 56,628,181 | `9A35D29C8632BCBCCE617F912DBB7829B5DBABA6E606765188485F438FC1D1DD` |

三个包都取自 `https://codeload.github.com/duriantaco/skylos/tar.gz/<ref>`。

`vendor/<版>/` 只保留 `skylos/rules/config/cicd/github_actions.py` 的 skylos 内部导入闭包：v5.6.0 51 个文件、父版与合并版各 52 个。`skylos/rules/config/__init__.py` 连同它拉进来的规则注册表也在里面——少了它，`skylos.rules.config.cicd` 的循环导入会在导入时报错。每个 vendor 目录下的 `provenance.json` 记着每个文件的 SHA-256，与上游 tarball 里的成员逐字节相同；没有改写过任何一行。

上游 Apache-2.0 许可见 [LICENSE](LICENSE)。
