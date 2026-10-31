# PDM #3964：同一 ZIP 的 fresh-read metadata 对照

使用未修改的 PDM 上游源码，串起 requirements 导入 → 初次 metadata → `PyLockConverter.convert()` → TOML 写出/解析 → **全新 `LockedRepository`、Candidate、PreparedCandidate** → 重新解包并读取 metadata。终点是项目定位与元数据，不是安装。

## 固定版本

| 对照 | PDM 源码提交 |
| --- | --- |
| before：#3964 的实际直接父提交 | `7aaeb992092d827dee173e60e82cfffa0a5b9676` |
| after：#3964 合并提交 | `f01b85810baacec4c8a22168da3f9e54550adb14` |

来源：[PR #3964](https://github.com/pdm-project/pdm/pull/3964)、[父提交](https://github.com/pdm-project/pdm/commit/7aaeb992092d827dee173e60e82cfffa0a5b9676)、[合并提交](https://github.com/pdm-project/pdm/commit/f01b85810baacec4c8a22168da3f9e54550adb14)。两版都已包含 #3954 的入口解析和 #3956 的 archive 哈希读取修复。

`vendor/before/`、`vendor/after/` 各保存对应提交的完整 `src/pdm/` 包、原始 `pyproject.toml` 和 MIT `LICENSE`，不含测试与全仓库归档。`provenance.json` 记录 tarball 地址/哈希、源码 SHA 与每个文件的 SHA-256；每次运行先检查源码字节。`.gitattributes` 防止 Git 自动转换快照换行后破坏校验。根部 `LICENSE.pdm` 也附同一许可。

## 环境与准备

已验证：Windows、Python **3.12.14**。`requirements.lock` 是本实验的完整固定依赖清单，其中 unearth **0.19.0**、hishel **1.4.0**、httpx2 **2.16.0**。这两份源码已经要求 unearth >=0.19 / hishel >=1.4，不能直接复用旧文章的 unearth 0.18.2 环境。本实验未声称验证其他 Python/操作系统组合。

清单中的 `pdm==2.29.4` 只供应已安装 distribution 的版本元数据及通用依赖；真正执行的 `pdm.*` 模块由每个独立子进程的 `sys.path` 优先指向固定 `vendor` 源码，JSON 会记录 converter 路径。不能把安装包的版本号当成本修复的发布版本。

`run.py` **不会安装依赖或联网补依赖**，缺失/版本不符会直接报出清单。下面命令在仓库根目录用 PowerShell 执行；路径按需改，但不要把 venv、wheelhouse 或运行证据提交到公开工程。

### 一次联网准备，随后离线安装与运行

```powershell
# 明确的联网准备步骤；为当前 Python 3.12/平台下载锁定的 wheels。
python 子目录定位_pdm/subdirectory_demo/prepare.py --download-to .yan/pdm-subdirectory/wheelhouse

# 不访问索引；核对本地 SHA256SUMS，再从 wheelhouse 安装固定清单。
python 子目录定位_pdm/subdirectory_demo/prepare.py --venv .yan/pdm-subdirectory/venv-offline --wheelhouse .yan/pdm-subdirectory/wheelhouse

# 测试本身离线。
& .yan/pdm-subdirectory/venv-offline/Scripts/python.exe -B -X utf8 子目录定位_pdm/subdirectory_demo/run.py --test --json .yan/pdm-subdirectory/runs/comparison.json
```

也可显式联网创建环境：

```powershell
python 子目录定位_pdm/subdirectory_demo/prepare.py --venv .yan/pdm-subdirectory/venv --allow-network
& .yan/pdm-subdirectory/venv/Scripts/python.exe -B -X utf8 子目录定位_pdm/subdirectory_demo/run.py --test
```

已有正确环境则直接 `python run.py --test`。`--test` 和默认运行都执行全部断言，`--json` 额外保存完整证据。Python 的 `-B` 避免生成快照旁的 `__pycache__`，`-X utf8` 兼容中文路径。脚本只对 findpython 的隔离解释器探针补 `-X utf8`，不改 PDM converter、reader、candidate、finder 或 unearth 实现。

## 实验与预期

标准库只造 **一个 ZIP**，固定条目时间与内容：

- 归档内 `bundle/` 为根项目 `parent`，依赖 `parent-dep`。
- `bundle/src/child/` 与 `bundle/src/a&b/` 是两个目标，项目均为 `child`、依赖 `child-dep`。
- `bundle/src/a/` 为截断诱饵 `decoy`，依赖 `decoy-dep`。

ZIP SHA-256 固定为：

```text
b032cb18c9d87b1d2a7d9ed762ad649ed9c1f02f890671e9191c7a2d6698b587
```

两种 source 表示 × 三种 selector（缺省、`src/child`、`src/a&b`）× before/after，合计 **12 个 fresh-read metadata 场景（6 对对照）**，另有两版各一个直接读取 `src/a` 的 **2 个 decoy 正控制**。最初导入后的 metadata 也逐一读取，确认在导出前确实选择了目标。

| source | selector | 两版导出名称 | before fresh metadata | after fresh metadata |
| --- | --- | --- | --- | --- |
| URL / path | 缺省 | parent | parent / parent-dep | parent / parent-dep |
| URL / path | src/child | child | parent / parent-dep | child / child-dep |
| URL / path | src/a&b | child | parent / parent-dep | child / child-dep |

URL 组输入 `https://archives.invalid/bundle-1.0.zip`，通过 **httpx2.MockTransport 进程内 fixture** 返回同一 ZIP 字节，不开 HTTP 服务、不创建 socket，不代表真实公网访问；path 组输入指向同一 ZIP 的 `file:` URI，由 PDM 自己识别为本地路径。没有手工改写 requirement 的路径/selector 字段。两组都先调用真实 `pdm.formats.requirements.convert()`，含 `&` 的输入 fragment 是 `src/a%26b`。

每版 URL 组共有 6 次 ZIP fixture 请求（3 个场景各初读、fresh-read 一次），有断言保证不是命中了旧 metadata。关闭 PDM wheel/HTTP cache，初读与 fresh-read 前都清空上游 `_build_dir_cache`，让新 candidate 真正重新解包。reader 从重新解析的 TOML 构造，不复用已被 `pop(name)` 修改的输入字典。

导出 TOML 的 **`lock-version = "1.0"`**。所有组都核对导出名称不变、ZIP 的实际 SHA-256 与 `archive.hashes` 相符、reader 恢复的 hash 值相符。父/合并版去掉唯一预期差异 `archive.subdirectory` 后，整个 `archive` 字典必须相等，包括 URL、可选 path、hashes。修后写实际目录字符串 `src/a&b`，不是 `%26` 编码串；缺省目录两版都不写 selector。

JSON 包含每个场景的导入行、初读 metadata、普通 PDM lock entry、**完整导出 TOML**、archive 字段、fresh-read requirement/hash、candidate 名称、metadata 名称/依赖与相对解包目录，以及 fixture 请求记录。

## 验证边界

- 本实验执行真实 requirements 导入器、Candidate/PreparedCandidate、整个 `PyLockConverter.convert()`、TOML 序列化、整个 `LockedRepository` reader 与 unearth 解包逻辑；没有用手写模型模拟这些生产函数。
- 为隔离序列化边界，第一次读出 metadata 后直接用真实 `Package` / `LockedRepository.add_package()` 建单包 repository，再调用 converter。hash 值由标准库对 ZIP 字节计算后填入 Candidate；普通锁 entry 由真实 `Candidate.as_lockfile_entry()` 产生，但不经过 CLI/resolver 写完整普通锁。
- **未运行 `pdm add/export/sync` CLI、依赖解析、构建或安装**；占位依赖只作 metadata 观察，不从索引查找。`lock.format=pdm/pylock` 两条 CLI 路线没有在这里分别复跑，不能把 12 个场景冒充上游那套 12 个 CLI 回归参数。
- `PreparedCandidate.prepare_metadata()` 的真实代码会调用 **`_unpack(validate_hashes=False)`**。`sys.setprofile` 只读观察真实函数入口，不替换方法：每版记录到 13 次 `_unpack`（6 次初读＋6 次 fresh-read＋1 次 decoy），全部为 `False`，原始记录在 JSON 的 `unpack_calls`。所以本实验证明的是“真实 ZIP SHA 与导出/读回哈希字段一致，selector 决定 metadata 来源”，**不证明安装时哈希校验通过**。也没有证明安装错包、静默装成 parent，或安装一定成功。
- 父版 fresh candidate 的名字仍是 `child`，但 `metadata.metadata['Name']` 是 `parent`，依赖是 `parent-dep`；记录的是两者不一致，不把 candidate 自动更名成 parent。
- driver 与 PDM worker 安装 Python audit hook，禁止 socket 创建、解析与网络操作；允许只读本机 `gethostname`，并实测 `socket.socket()` 会被拒绝。URL 请求只进入本地 MockTransport。解释器探针子进程负责读取版本与环境标签，不运行构建后端；本实验不是操作系统级防火墙隔离。
