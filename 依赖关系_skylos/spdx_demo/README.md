# SPDX 依赖关系对照（skylos #1179）

同一份 Yarn Berry 工作区清单，交给合并提交前后的两版 `skylos`，比较 SPDX 2.3 JSON 里的
`DEPENDS_ON` 关系。

工作区固定为 `app -> parent -> child`，`yarn.lock` 里的三组输入：

| 用例 | 输入差异 | 看什么 |
| --- | --- | --- |
| `transitive_child` | child 只被 parent 依赖 | 修前多出 `root -> child`，修后没有 |
| `also_direct` | app 自己也声明了 child | 两版都保留 `root -> child` |
| `incomplete_graph` | 同第一组，但记录的图标记为不完整 | 修后 child 从 `DEPENDS_ON` 变成 `OTHER` |

## 跑

需要 Python 3.11+ 和 PyYAML（`yaml_lockfile` 之外的 `pnpm_lockfile` 在导入时就要 `yaml`）：

```text
python -m venv venv
venv/Scripts/python -m pip install pyyaml
venv/Scripts/python -B run.py --test
```

`--json <路径>` 把两版结果与提交号写成一份 JSON。

## 目录

- `vendor/before/`、`vendor/after/`：上游 `skylos` 包在父提交 `4481fea7` 与合并提交 `bf6215f0` 的原样源码，
  只保留 SPDX 导出实际 import 的模块（`reporting/spdx.py`、`reporting/sbom.py`、`rules/sca/`、`core/safe_cache_io.py` 等），
  其余文件未改。`pyproject.toml` 只写版本号，让 `skylos.__version__` 可复现。
- `provenance.json`：两个提交、`spdx.py` / `sbom.py` 的 SHA-256、上游 tarball 的 SHA-256。
- `LICENSE`：上游 Apache-2.0。

## 边界

- 只比较 SPDX 导出；CycloneDX 不在这条代码路径上。
- 用例由上游测试的 Yarn Berry 夹具改写（`test/test_sbom_lockfiles.py` 的 `_berry()`），
  只加了 `also_direct` 与 `incomplete_graph` 两组差异。
- 不覆盖 manifest-only 依赖（无 `lockfile_version` 的记录）、其他生态的 lockfile 与真实 CLI。
- 两版代码都是固定提交的源码，不随上游继续变化。
