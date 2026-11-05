# 退出码 0，Cargo.lock 没了

```console
$ cargo generate-lockfile
     Locking 7 packages to latest compatible versions
$ skylos sbom . -o Cargo.lock
Wrote CycloneDX 1.6 SBOM with 7 packages to Cargo.lock
$ echo $?
0
```

`Cargo.lock` 原来 1817 字节（这个项目有 7 个包），现在 13633 字节。打开一看，是一份 CycloneDX JSON：`$schema`、`bomFormat`、`components`。原来的 `[[package]]` 列表没了。

`skylos sbom` 是依赖清单导出命令：读项目里的锁文件与清单，写一份 CycloneDX 或 SPDX JSON。`-o` 指定输出路径，`-` 表示写到标准输出。输出可以是一个新文件，也可以是项目里已经存在的文件——包括它刚读过的依赖文件。skylos 本身是一个代码扫描工具，`sbom` 是它的依赖清单子命令，默认离线运行。

`Cargo.lock` 被覆盖后，`cargo build` 会按 `Cargo.toml` 重新解析，生成一份新的锁文件，版本可能和原来锁定的不同。如果锁文件在版本库里，`git diff` 会显示整份被替换。清单更重：`Cargo.toml` 里的 `serde = "1"`、`pom.xml` 里的 `<dependency>`、`setup.py` 里的 `install_requires` 是人写的，没有命令能把它们从一份 SBOM 变回来。

## 守卫认识 11 个名字

修前的 `run_sbom_command` 在写文件之前有一段检查：

```python
if args.output != "-" and (
    Path(args.output).name.casefold()
    in {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "go.mod",
        "uv.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "yarn.lock",
        "pipfile.lock",
        "npm-shrinkwrap.json",
    }
    or Path(args.output).suffix.casefold() == ".csproj"
):
    print("SBOM error: output must not overwrite a dependency input.", file=sys.stderr)
    return 2
```

`Path(args.output).name` 只取文件名，`casefold()` 忽略大小写：名字只要在集合里，`sub/Cargo.lock` 和 `CARGO.LOCK` 都躲不过。`.csproj` 单独按后缀判断，因为它的文件名是项目名（`App.csproj`、`MyLib.csproj`），列不完。

这段代码本身没有问题。问题在名单：十一个名字，是手工维护的。

## 收集器认识 24 个

同一份代码里，依赖收集器的清单更长。`vulnerability_scanner.py` 里：

- `_LOCKFILE_ECOSYSTEMS` 有 14 个锁文件：`uv.lock`、`poetry.lock`、`Pipfile.lock`、`package-lock.json`、`npm-shrinkwrap.json`、`pnpm-lock.yaml`、`yarn.lock`、`bun.lock`、`Cargo.lock`、`composer.lock`、`Gemfile.lock`、`pubspec.lock`、`gradle.lockfile`、`packages.lock.json`。
- `_MANIFEST_ECOSYSTEMS` 有 6 个清单：`package.json`、`go.mod`、`pom.xml`、`Cargo.toml`、`composer.json`、`pubspec.yaml`。
- Python 侧另有 `requirements.txt`、`pyproject.toml`、`setup.cfg`、`setup.py`。`requirements.txt` 与 `pyproject.toml` 走 Python 侧的解析器；`setup.cfg`、`setup.py` 由 `SETUPTOOLS_MANIFEST_NAMES` 标记，静态读 `install_requires`，不执行 `setup.py`。

并集 24 个。守卫保护 11 个，差 13 个。

这 13 个分两类：

| 类型 | 文件 | 被覆盖之后 |
| --- | --- | --- |
| 锁文件（7） | `bun.lock`、`Cargo.lock`、`composer.lock`、`Gemfile.lock`、`pubspec.lock`、`gradle.lockfile`、`packages.lock.json` | 包管理器能重新解析，但结果可能不是原来锁定的版本 |
| 清单（6） | `Cargo.toml`、`composer.json`、`pubspec.yaml`、`pom.xml`、`setup.py`、`setup.cfg` | 手写的依赖声明没了，没有命令能重建 |

**第二行更麻烦。** 锁文件丢了还能 `cargo generate-lockfile`，清单丢了只能从版本库恢复；如果它还没提交，就真的没了。

## 跑一遍

工程 `覆盖输入_skylos/overwrite_demo/` 把两版的守卫摘出来，对 24 个输入名逐个跑一遍：守卫放行时真的写一份 SBOM，再用 SHA-256 看原文件的字节有没有变。只用标准库，`-B -S` 离线运行。

```console
$ python -B -S 覆盖输入_skylos/overwrite_demo/run.py
...
parent   overwrites 13/24 dependency inputs (6 manifests, 7 lockfiles)
merged   overwrites 0/24 dependency inputs (0 manifests, 0 lockfiles)
```

`--test` 把同样的对照变成断言：

```console
$ python -B -S 覆盖输入_skylos/overwrite_demo/run.py --test
PASS parent overwrites 13/24 inputs, merged 0/24; extras and byte checks pass
```

13 个放行的名字与上面的差集一致。额外情形单独跑了一组：

| 情形 | 修复前 | 修复后 | 说明 |
| --- | --- | --- | --- |
| `sub/Cargo.lock` | 覆盖 | 拒绝 | 守卫只看 basename |
| `CARGO.LOCK` | 放行 | 拒绝 | `casefold()` 忽略大小写 |
| `Composer.JSON` | 放行 | 拒绝 | 同上，换成另一个生态 |
| `App.csproj` | 拒绝 | 拒绝 | `.csproj` 后缀规则原本就有 |
| `App.CSPROJ` | 拒绝 | 拒绝 | 后缀判断也忽略大小写 |
| `sbom.json` | 写入 | 写入 | 正常输出名 |
| `report/bom.json` | 写入 | 写入 | 子目录里的正常输出名 |
| `pins.txt` | 写入 | 写入 | `requirements.txt` 引入的文件；已知残余 |

表里的“放行”指守卫没有拦。在 Windows 上，大小写变体落到同一个文件；在 Linux 上会新建一个大写名的文件，守卫同样应该拒绝它。

上面的表是摘出来的守卫，不是完整 CLI。再用真项目跑一遍：`cargo generate-lockfile` 生成 7 个包、1817 字节的锁文件；skylos 从仓库的父提交 `b529347` 装（`pip install --no-deps --force-reinstall <快照 zip>`）。选父提交而不是 PyPI，是因为 5.4.0 的收集器对这份 Cargo 项目读出 0 个包，看不到“读到了依赖又被覆盖”的完整后果。

```console
$ skylos sbom . -o Cargo.lock
Wrote CycloneDX 1.6 SBOM with 7 packages to Cargo.lock
$ echo $?
0
```

覆盖后的文件 13633 字节，SHA-256 从 `14946046…` 变成 `c3b076a8…`。同一版上 `-o Cargo.toml` 也一样：133 字节的清单变成 13633 字节的 JSON，退出 0。

换到合并提交 `7eff6a5`：

```console
$ skylos sbom . -o Cargo.lock
SBOM error: output must not overwrite a dependency input.
$ echo $?
2
```

文件字节不变。`-o Cargo.toml` 同样退出 2；`-o sbom.json` 两个版本都正常写。

三组数字放在一起：

| 版本 | `-o Cargo.lock` | 退出码 | 文件 |
| --- | --- | --- | --- |
| 父提交 `b529347` | 写入 7 个包 | 0 | 1817 B → 13633 B |
| 合并提交 `7eff6a5` | 拒绝 | 2 | 1817 B → 1817 B |
| PyPI 5.4.0 | 写入 0 个包 | 0 | 1817 B → 3270 B |

第三行值得单独说：5.4.0 也覆盖，但那份 SBOM 里没有 Cargo 的包——收集器对这份 Cargo 项目返回 0 个包。**覆盖与“读到了什么”是两件事**：守卫在收集之前运行，收集器读没读到，都不影响它把文件写掉。

## 为什么是加名单

最直接的想法是“写之前先跑一遍收集器，看输出路径是不是它读过的某个文件”。这要多遍历一次项目，而且收集器可能因为权限或符号链接读不到某个文件；读不到就判不出来，反而漏掉。输出还可能在项目外、经过符号链接，或指向一个还没创建的目录，动态判断要把这些情况都算进来。

另一个做法是“输出文件已存在就拒绝”。这太宽：SBOM 本来就经常覆盖上一份，`-o sbom.json` 跑第二次不该失败。

所以守卫用了静态名单：成本低，与收集器的支持清单对齐。代价是两份清单要同步——这次的 bug 就是同步漏了。修法是把 13 个名字补进集合，没有改判断方式。生产改动 13 行，测试新增 28 行、改写 3 行。

## 边界

维护者在 review 里指出了一处没盖住的：`requirements.txt` 用 `-r pins.txt` 或 `-c constraints.txt` 引入的自定义文件，仍然可以被 `-o` 覆盖。这类文件是运行期从 `requirements.txt` 里读出来的，不在静态名单里，属于这个 PR 的范围之外。

> Custom files included by `requirements.txt`, such as `pins.txt`, can be overwritten. This is outside this pr's scope and should be fixed separately.

这也是静态名单的边界：它认识“约定俗成的文件名”，不认识“被另一个文件引用的文件名”。

## 影响面

- 修复在仓库的 Unreleased；写稿时 PyPI 上的最新版是 5.4.0（2026-11-02），不含这个检查。
- 在 5.4.0 上，`-o Cargo.lock` 同样退出 0 并覆盖文件，只是那份 SBOM 里没有 Cargo 的包（3270 字节、0 个包）——收集器对这份 Cargo 项目返回 0 个包。
- 在仓库主干的父提交 `b529347` 上，收集器已经读这些文件：`-o Cargo.lock` 会把 7 个包写进 JSON（1817 字节 → 13633 字节），`-o Cargo.toml` 也一样。修复补的正是这一段：收集器先扩展，守卫后跟上。
- 触发条件：`-o` 的 basename（忽略大小写）等于那 13 个名字之一；`-o -` 不受影响。CI 里常见 `-o "$OUT"`，`$OUT` 由环境变量或矩阵参数拼出来；只要某个组合落到这些名字上就会触发。
- 锁文件不在版本库里时，覆盖后 `cargo build` 会立刻重建，问题更隐蔽；在版本库里时才会看到 diff。清单没有这个“自动重建”的兜底。
- 修复后的行为：stderr 打 `SBOM error: output must not overwrite a dependency input.`，退出码 2，原文件不动。

PR 自述的测试结果：最终回归用例在未修改的主干上 26 失败、8 通过，修复后 34 通过；SBOM 测试 88 通过（一个符号链接用例因 Windows 权限被排除）。这里复跑的是守卫与写入，上面的真实 CLI 对照另外跑。

如果要自己验：在一个有 `Cargo.lock` 的项目里跑 `skylos sbom . -o Cargo.lock`，看退出码；再换 `-o sbom.json` 确认 SBOM 仍能写。升级后前者应该变成 2。CI 脚本里 `-o` 来自变量时，先看一眼变量可能取到的名字。

## 来源

- PR：[duriantaco/skylos#1168](https://github.com/duriantaco/skylos/pull/1168)，合并提交 [7eff6a5](https://github.com/duriantaco/skylos/commit/7eff6a519ed6c7fdec9263672203ad07902905a5)，父提交 [b529347](https://github.com/duriantaco/skylos/commit/b52934735471f61ef5b813ff88c38c6be0a8533c)。
- 收集器清单：[vulnerability_scanner.py](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/skylos/rules/sca/vulnerability_scanner.py#L191-L214) 的 `_LOCKFILE_ECOSYSTEMS`、`_MANIFEST_ECOSYSTEMS`、`SETUPTOOLS_MANIFEST_NAMES`。
- 输出守卫：[sbom_cmd.py](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/skylos/commands/sbom_cmd.py#L75-L104) 的 `run_sbom_command`。
- CHANGELOG 的 [Unreleased 条目](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/CHANGELOG.md)：拒绝以 Bun、Cargo、Composer、RubyGems、Pub、Gradle、NuGet、Maven、setuptools 依赖输入命名的输出路径。
- PyPI：[skylos 5.4.0](https://pypi.org/project/skylos/5.4.0/)。
