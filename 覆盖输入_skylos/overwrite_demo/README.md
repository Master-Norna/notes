# skylos SBOM 输出守卫对照

`skylos sbom . -o Cargo.lock` 在修复前会退出 0，并把 `Cargo.lock` 写成一份 CycloneDX JSON。
这个工程把 `sbom_cmd.py` 里的输出守卫摘出来，对 24 个依赖输入名和 8 个额外情形逐个跑一遍：
守卫放行时真的写一份 SBOM，再用字节哈希看原文件有没有被替换。

## 来源

- 仓库：<https://github.com/duriantaco/skylos>
- 父提交：`b52934735471f61ef5b813ff88c38c6be0a8533c`
- 合并提交：`7eff6a519ed6c7fdec9263672203ad07902905a5`（PR #1168）
- 许可证：Apache-2.0，见 `LICENSE`

`snapshots/guard_parent.py`、`snapshots/guard_merged.py` 是
`skylos/commands/sbom_cmd.py` 中 `run_sbom_command` 的守卫条件摘录（`args.output`
换成函数参数），集合、`casefold()` 与 `.csproj` 后缀判断原样保留。
`upstream/` 下是两版完整文件，可逐行对照。
“依赖输入”的 24 个名字取自 `skylos/rules/sca/vulnerability_scanner.py`：
`_LOCKFILE_ECOSYSTEMS`（14 个锁文件）、`_MANIFEST_ECOSYSTEMS`（6 个清单）、
`SETUPTOOLS_MANIFEST_NAMES` 与 Python 的 `requirements.txt` / `pyproject.toml`（4 个）。

## 跑

```console
python -B -S run.py            # 对照表
python -B -S run.py --json     # 机器可读结果
python -B -S run.py --test     # 断言；失败时退出码 1
```

只用标准库，不联网，不建 socket。每个用例在独立临时目录里写入原文件，
守卫放行时再写一份 SBOM；表里的 `overwritten` 表示原文件字节已被替换。

## 读数

- 24 个依赖输入名里，修复前有 11 个受保护，13 个放行：6 个手写清单
  （`Cargo.toml`、`composer.json`、`pubspec.yaml`、`pom.xml`、`setup.py`、`setup.cfg`）
  和 7 个锁文件。
- 修复后 24 个全部拒绝；子目录与大小写变体也拒绝；`.csproj` 两版都拒绝。
- `pins.txt` 这类由 `requirements.txt` 的 `-r` / `-c` 引入的文件不在守卫里，
  两版都会放行。这是 PR review 里维护者说明的范围外缺口。

## 边界

工程验证的是守卫函数加写入这一步，不是完整 CLI 的参数解析、依赖收集与 SBOM 生成；
需要完整 CLI 时用发布版跑真实命令，版本与输出另记在 `.yan/skylos-overwrite/记录.md`（内部记录，不随公开提交）。
