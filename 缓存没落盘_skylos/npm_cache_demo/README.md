# npm 镜像身份缓存复现工程

复现 duriantaco/skylos #1224：npm 镜像身份缓存把数据文件名交给了按目录处理的锁，缓存文件从没写出来过；主机没有 home 目录时，取缓存目录还会先抛 `RuntimeError`。

两版源码裁到导入链所需的最小集合，放在 `vendor/`：

| 目录 | 来源 | 说明 |
| --- | --- | --- |
| `vendor/base/` | duriantaco/skylos @ `3f47e36da352caae19acd789690094ce9e372fd0` | 修复前 |
| `vendor/merge/` | duriantaco/skylos @ `89b88730c8c2c6fe952c8d61d06975f8422a9925` | #1224 合并后 |

只保留 `skylos/__init__.py`、`core/`、`commands/hook_parallel.py` 与 `rules/sca/` 下相关模块。`skylos.commands.hook_locked_packages`（内部包判定）由脚本注入一个恒返回 `False` 的桩：它和缓存无关，却会把所有 lockfile 解析器拉进来。改动只落在 `npm_mirrors.py` 一个文件，其余模块两版逐字节相同。

上游许可证见 `LICENSE`（Apache-2.0）。

## 跑法

只需要 Python 3.11 以上，无第三方依赖：

```text
python -B run.py --test
```

两个快照各在一个隔离子进程里跑，各自使用临时目录中的 `XDG_CACHE_HOME` 与项目目录。脚本用一个记账的假 HTTP 传输层喂固定元数据，因此不联网。

## 三个场景

1. **连续两次扫描。** 同一个依赖 `left-pad@1.3.0` 跑两遍 `verify_npm_mirrors()`，读回执里的 `metadata_requests`、`cache_hits`，再看缓存文件是否存在、里面有几条。
2. **锁拿到的路径。** 包一层 `project_cache_lock` 记录调用参数，再调 `_save_cache()`；进入锁时看数据路径是什么，退出后看文件有没有落盘。
3. **没有 home 目录。** 把 `Path.home` 换成抛 `RuntimeError`，调用 `_cache_directory()`，记录异常还是返回 `None`。

## 预期输出

修复前：

- 第二次扫描仍然 `metadata_requests=1 / cache_hits=0`，两次共 2 次请求；
- 跑完之后缓存路径不存在（两次扫描之间锁在自己那把「锁目录」上 `mkdir`，数据文件名成了目录，保存函数看到非常规文件就返回 `False`，调用方不看返回值）；
- 锁拿到的参数就是 `npm-mirror-identities.json`，持有期间它是一个目录；
- 没有 home 时 `_cache_directory()` 直接抛 `RuntimeError`。

修复后：

- 第二次扫描 `metadata_requests=0 / cache_hits=1`，总共 1 次请求；
- 缓存文件存在，1 条记录；
- 锁拿到的是 `npm-mirror-identities.json.lock`，数据路径在持有期间还不存在；
- 没有 home 时返回 `None`，缓存停用，扫描继续。

文中数字均出自 `--test` 的输出，存档在 `../.yan/skylos-npm-cache/runs/`。
