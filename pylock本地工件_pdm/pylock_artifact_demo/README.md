# PDM #3975：pylock 里的本地工件路径与显式文件名

用未修改的 PDM 上游源码，对照「读取 pylock → 构造候选 → 准备本地工件」这条链，观察 `path` 与 `name` 两个字段的去向。终点是 `PreparedCandidate._obtain()`，不是完整安装。

## 固定版本

| 对照 | PDM 源码提交 |
| --- | --- |
| before：#3975 的实际直接父提交 | `dc1f476a53043ec36c83df104a73a6e86a4d4e64` |
| after：#3975 合并提交 | `a4965a8f116dc51d961cdd6b1e0d55aabb0abd2e` |

来源：[PR #3975](https://github.com/pdm-project/pdm/pull/3975)、[父提交](https://github.com/pdm-project/pdm/commit/dc1f476a53043ec36c83df104a73a6e86a4d4e64)、[合并提交](https://github.com/pdm-project/pdm/commit/a4965a8f116dc51d961cdd6b1e0d55aabb0abd2e)。

`vendor/before/pdm`、`vendor/after/pdm` 各是两版 `src/pdm/` 的完整副本，附 MIT `LICENSE.pdm`。`provenance.json` 记录 tarball 地址与 SHA-256、每个源码文件的 SHA-256；`fixtures/` 里的 wheel 与 sdist 取自 PDM 测试夹具，同样列入 provenance。

## 环境与准备

已在 Windows、Python 3.12.14 上验证。运行前按 `requirements.lock` 准备固定依赖（`unearth==0.19.0`、`findpython==0.9.0`、`hishel==1.4.0` 等）；其中 `pdm==2.29.4` 只供应已安装 distribution 的元数据，真正执行的 `pdm.*` 模块来自 `vendor/`，由每个子进程的 `sys.path` 优先指向。

`run.py` 不会安装依赖，也不会联网；缺失或版本不符会直接报错。

## 运行

```powershell
python run.py --test
```

每组用例各起两个独立子进程（before/after），socket 由 audit hook 拒绝。`--json results.json` 可把原始结果写到文件。

## 预期结果

| 用例 | before | after |
| --- | --- | --- |
| `path_only_wheel` | 去索引，离线失败（`socket.getaddrinfo`） | 用本地路径，成功 |
| `path_and_url_wheel` | 用 `url`，离线失败 | `path` 优先，成功 |
| `named_local_wheel` | 物理名不是 wheel，`CandidateNotFound` | 按逻辑名成功 |
| `named_local_sdist` | 物理名不是 sdist，`CandidateNotFound` | 按逻辑名解包 |

`named_local_sdist` 的 before 停在候选匹配，没有走到解压；这正说明名字问题发生在更早的一层。

## 说明

`findpython` 在 `-Ic` 下调用解释器，输出用 OEM 码页；本实验在 UTF-8 locale 的主机上以 `-X utf8` 重跑该探测脚本，属于环境适配，不改上游逻辑。该适配写在 `run.py` 的 worker 里。

本工程只验证 `LockedRepository` + `PreparedCandidate._obtain()` 这一条读路径，不声称覆盖 `pdm install` 的全部 CLI 行为、构建后端或安装落盘；PR 描述里的 36 个 CLI 场景是作者记录，不是本工程的输出。
