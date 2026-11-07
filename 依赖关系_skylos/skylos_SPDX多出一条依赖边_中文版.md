# SPDX 说 app 依赖 child，其实只是「够得着」

一份 Yarn Berry 工作区导出成 SPDX 2.3，`relationships` 里有三条边：

```json
{"spdxElementId": "SPDXRef-RootPackage", "relationshipType": "DEPENDS_ON",
 "relatedSpdxElement": "SPDXRef-Package-npm-parent-1.0.0-db4b09d612"},
{"spdxElementId": "SPDXRef-Package-npm-parent-1.0.0-db4b09d612", "relationshipType": "DEPENDS_ON",
 "relatedSpdxElement": "SPDXRef-Package-npm-child-2.0.0-4c33f08f2a"},
{"spdxElementId": "SPDXRef-RootPackage", "relationshipType": "DEPENDS_ON",
 "relatedSpdxElement": "SPDXRef-Package-npm-child-2.0.0-4c33f08f2a"}
```

第三条对不上。`yarn.lock` 里 `app` 的 dependencies 只有 `parent`，`child` 是 `parent` 的可选依赖，工作区从没直接声明过它。可 SPDX 说根包依赖它。

root 的 `DEPENDS_ON` 是「直接依赖」的机读版本。查许可证政策、回答「我们直接依赖了哪些包」，都从这条边出发。多一条，等于把一个只在依赖树里的包算成了我们自己挑的。

[skylos #1179](https://github.com/duriantaco/skylos/pull/1179) 修的就是这一条，改动是删掉一个 `or` 分支。

## 收集器记了两个字段，回答的是两个问题

Yarn 收集器读 `yarn.lock` 后，从每个 workspace 根出发做一遍遍历。每走到一条边，就往两个地方各记一笔：

```python
usage[target].add((root, target_optional))
kinds[target].add("direct" if direct else "transitive")
```

`direct` 是「这一跳直接从 workspace 根发出」，`root` 是「从哪个 workspace 根走到这里」。遍历时这个标志在入队后就被固定成 `False`（`queue.append((target, root, target_optional, False))`）：第一跳算声明，第二跳往后都算传递，`kinds` 只会给 workspace 自己写进 `dependencies` 的包加上 `direct`。遍历完，`dependency_kind` 由 `kinds` 归并，`dependency_roots` 由 `usage` 归并：

```python
"dependency_kind": "direct" if "direct" in kinds[key] else "transitive" if kinds[key] else "unknown",
"dependency_roots": sorted({root for root, _ in usage[key]}),
```

对 `child` 来说，`kinds` 里只有 `transitive`，`usage` 里却有根 `""`——`parent` 是从根出发的，`child` 又从 `parent` 走到，于是「根能到达它」。两个字段都没错：一个说它没被直接声明，一个说它够得着。`roots` 描述的是可达性，`kind` 描述的才是声明。

`roots` 不是没人要的中间量。导出成 CycloneDX 时，每条 occurrence 都写进组件的 `properties`，`roots` 一起带过去，回答的是「这个包被哪个 workspace 拉进来的」。单仓库里它区分不出什么，monorepo 里 `packages/a` 和 `packages/b` 各依赖一版同名包时，这条信息就是唯一的出处。删掉导出器里的一个条件，不等于删掉这个字段。

## 导出器把「够得着」当成了「直接」

修前 `spdx.py:67` 的判断：

```python
def _is_direct(occurrence: dict) -> bool:
    return (
        occurrence.get("dependency_kind") == "direct"
        or "lockfile_version" not in occurrence
        or bool(occurrence.get("dependency_roots"))
    )
```

三个条件取或。前两个各有分工：`dependency_kind == "direct"` 认直接声明，`"lockfile_version" not in occurrence` 认没有锁文件的清单条目——`requirements.txt` 里写死版本的那种，没有图可走，只能按声明算。第三个把 `roots` 非空也当成直接，而在 yarn 收集器里，这个字段对每一个被遍历到的包都非空。

`child` 于是进了 `direct` 集合，`_relationships()` 给它挂上一条从根发出的边；而 `parent -> child` 那条本来就由 `_graph()` 产生，一真一假叠在一起。

两条边指向的 `SPDXID` 由 purl 算出来：`_package_id()` 把 `pkg:npm/child@2.0.0` 里的不安全字符换掉，再拼上 purl 的 sha256 前十位。同一个包在任何一次导出里都是同一个 ID，`SPDXRef-Package-npm-child-2.0.0-4c33f08f2a` 里的后缀就是那个摘要——所以拿两份文档 diff，多出来的边一眼能看出来，不用先解析包名。

## 三组对照

复现工程把上游测试里的 Yarn 夹具原样拿来（`test/test_sbom_lockfiles.py` 的 `_berry()`），只改 `app` 的声明做出一组差异，各跑合并前后两版：

```text
== transitive_child
  before parent -> child, root -> child, root -> parent
  after  parent -> child, root -> parent

== also_direct
  before parent -> child, root -> child, root -> parent
  after  parent -> child, root -> child, root -> parent

== incomplete_graph
  before root -> child, root -> parent
  after  root -> parent, root .. child (OTHER)
```

第一组是症状：修前多一条 `root -> child`，修后只剩 `parent -> child`。第二组把 `child` 也写进 `app` 的 dependencies，两版的边完全相同——真声明本来就该有那条边。第三组见下一节。

上游的回归测试是同一份夹具配一个参数（`child_is_direct`）跑两遍，断言两边都只有 `root -> parent` 与 `parent -> child`，声明了才多一条根边。本文的工程把这两组照搬，另加一组把图标成不完整。

## 删掉一项，另外两项还站得住

`also_direct` 说明 `dependency_kind == "direct"` 这一支仍然在起作用：只要有一处声明，`kinds` 里就同时有 `direct` 和 `transitive`，归并后是 `direct`，根边保留。

没有 `lockfile_version` 那一支管的是清单条目。这类记录没有锁定版本、没有依赖图，第二个条件先返回真，第三个对它们没有意义。PR 描述里把它叫作 existing fallback for manifest pins without lockfile metadata。

删掉的那一支，能加进来的只有一种包：**被遍历到、但没被声明**。正是要清掉的那一类。

## 图不完整时，它换了个说法

`_relationships()` 末尾还有一段：既不在直接依赖里、也没被任何图边连上的包，会挂一条 `OTHER`，注释写明原因。

第三组把记录的图标记为不完整（`receipt["complete"] = False`），`_graph()` 因此返回空，`parent -> child` 这条边不出现。修前，`child` 靠那条假边混进「根依赖」；修后它落到兜底分支：

```json
{"spdxElementId": "SPDXRef-RootPackage", "relationshipType": "OTHER",
 "relatedSpdxElement": "SPDXRef-Package-npm-child-2.0.0-4c33f08f2a",
 "comment": "Recorded in the inventory; dependency path from the root was not recorded."}
```

「清单里记了它，但从根出发的路径没记下来」——这句话是实情。比「根依赖它」准确。

`_graph()` 这边也有同样的取舍：缺节点算「依赖未知」，不写成「没有依赖」；只有锁定记录、且图标记为完整时，才发包与包之间的边。图不完整时它返回空列表，一条包边都不发，宁可少说。

`--strict` 管不到这里。它的语义是「清单不完整就退出 2」：`requirements.txt` 没锁版本、某个 lockfile 读不懂，才拦下来。这次的清单是完整的，命令退出 0，错的是关系本身——完整性检查和关系正确性是两件事。

## 哪些 lockfile 会碰到

不是每个收集器都给 `dependency_roots` 填值。cargo、composer、gemfile、gradle、nuget、pipfile、poetry、pubspec 的实现里，这个字段固定写 `[]`，删掉那一支对它们没有任何影响。npm 只在包被直接声明时才写 `roots`（`npm_lockfile.py:514`），这类包本来就靠 `kind` 判成直接。会给可达但未声明的包也记上根的，是 yarn、pnpm、uv 三条——也只有这三条会多出那条边。

CycloneDX 不走这段代码。`roots` 作为 occurrence 属性仍写进 CycloneDX 的 `properties`，信息没丢，只是不再被当成「直接声明」的证据。

PR 里另有一段验证记录，是作者机器上的数：`test_licenses.py`、`test_sbom.py`、`test_sbom_lockfiles.py` 三个文件 144 passed；新增的两条参数化用例套在旧判断上 1 failed / 1 passed，失败的那条正是多出来的根边；扩到 12 个文件的 SBOM、许可证与 lockfile 选择集，642 passed、1 skipped、6 deselected——被 deselect 的六条要建符号链接，Windows 上 `WinError 1314` 建不了。本文的三组只覆盖导出这一段，不重复那批数字。

## 复现

工程在 `依赖关系_skylos/spdx_demo/`，两版 `skylos` 包（父 `4481fea7`、合并 `bf6215f0`）原样放在 `vendor/`，只保留 SPDX 导出 import 得到的模块，附 Apache-2.0 许可证；提交号、`spdx.py` 与 `sbom.py` 的 SHA-256、上游 tarball 的哈希都记在 `provenance.json`。需要 Python 3.11+ 和 PyYAML：

```text
python -m venv venv
venv/Scripts/python -m pip install pyyaml
venv/Scripts/python -B run.py --test
```

用例里的 `yarn.lock` 用上游夹具的同一份内容生成，两版各起一个子进程，`sys.path` 只指向其中一版，`parse_yarn_lock` 与 `spdx_document` 都是上游原码。三组结果在 `--test` 里逐条断言；`--json` 会把两版关系与提交号一起写出。

## 参考

- skylos PR [#1179](https://github.com/duriantaco/skylos/pull/1179)；父提交 [`4481fea7`](https://github.com/duriantaco/skylos/commit/4481fea70b5a7ccab9e4b362a42c2ebb4f3608ea)、合并提交 [`bf6215f0`](https://github.com/duriantaco/skylos/commit/bf6215f02f27d58c9c07ac57731505e65f76f8ad)。
- 改动文件：[`skylos/reporting/spdx.py`](https://github.com/duriantaco/skylos/blob/bf6215f02f27d58c9c07ac57731505e65f76f8ad/skylos/reporting/spdx.py)、[`test/test_sbom_lockfiles.py`](https://github.com/duriantaco/skylos/blob/bf6215f02f27d58c9c07ac57731505e65f76f8ad/test/test_sbom_lockfiles.py)。
- 收集器：[`yarn_lockfile.py`](https://github.com/duriantaco/skylos/blob/bf6215f02f27d58c9c07ac57731505e65f76f8ad/skylos/rules/sca/yarn_lockfile.py) 的遍历与字段写入；规范：[SPDX 2.3 relationships](https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/)。
