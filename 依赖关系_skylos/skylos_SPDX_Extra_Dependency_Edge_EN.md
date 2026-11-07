# SPDX says app depends on child; it only reaches it

A Yarn Berry workspace exported to SPDX 2.3, with three edges in `relationships`:

```json
{"spdxElementId": "SPDXRef-RootPackage", "relationshipType": "DEPENDS_ON",
 "relatedSpdxElement": "SPDXRef-Package-npm-parent-1.0.0-db4b09d612"},
{"spdxElementId": "SPDXRef-Package-npm-parent-1.0.0-db4b09d612", "relationshipType": "DEPENDS_ON",
 "relatedSpdxElement": "SPDXRef-Package-npm-child-2.0.0-4c33f08f2a"},
{"spdxElementId": "SPDXRef-RootPackage", "relationshipType": "DEPENDS_ON",
 "relatedSpdxElement": "SPDXRef-Package-npm-child-2.0.0-4c33f08f2a"}
```

The third one does not add up. In `yarn.lock`, `app`'s dependencies list only `parent`; `child` is an optional dependency of `parent`, and the workspace never declared it. Yet SPDX says the root package depends on it.

A root-level `DEPENDS_ON` is the machine-readable form of "direct dependency". Checking licence policy and answering "which packages do we depend on directly" both start from these edges. One extra edge means a package that only exists in the dependency tree gets counted as one we picked ourselves.

[skylos #1179](https://github.com/duriantaco/skylos/pull/1179) fixes that one edge, and the change is deleting one `or` branch.

## The collector records two fields, answering two questions

After reading `yarn.lock`, the Yarn collector walks outward from each workspace root. Every edge it traverses writes to two places:

```python
usage[target].add((root, target_optional))
kinds[target].add("direct" if direct else "transitive")
```

`direct` means "this hop leaves the workspace root", `root` means "which workspace root reached here". During traversal that flag is pinned to `False` right after enqueueing (`queue.append((target, root, target_optional, False))`): the first hop counts as declared, every hop after it counts as transitive, so `kinds` only marks a package `direct` if a workspace listed it in `dependencies`. When the walk finishes, `dependency_kind` folds down from `kinds` and `dependency_roots` folds down from `usage`:

```python
"dependency_kind": "direct" if "direct" in kinds[key] else "transitive" if kinds[key] else "unknown",
"dependency_roots": sorted({root for root, _ in usage[key]}),
```

For `child`, `kinds` holds only `transitive`, while `usage` holds the root `""` — `parent` was reached from the root, `child` was reached from `parent`, so "the root can reach it". Neither field is wrong: one says it was never declared, the other says it is reachable. `roots` describes reachability; `kind` describes declaration.

`roots` is not an unwanted intermediate. When exporting to CycloneDX, every occurrence writes its properties onto the component, and `roots` travels along, answering "which workspace pulled this package in". In a single-repo layout it distinguishes nothing; in a monorepo, where `packages/a` and `packages/b` each depend on a different version of the same name, that information is the only place to find out. Deleting one condition in the exporter is not the same as deleting this field.

## The exporter treats reachable as declared

The check before the fix, `spdx.py:67`:

```python
def _is_direct(occurrence: dict) -> bool:
    return (
        occurrence.get("dependency_kind") == "direct"
        or "lockfile_version" not in occurrence
        or bool(occurrence.get("dependency_roots"))
    )
```

Three conditions or-ed together. The first two have their jobs: `dependency_kind == "direct"` recognises a direct declaration, and `"lockfile_version" not in occurrence` recognises a manifest entry without a lockfile — the kind of `requirements.txt` that pins versions by hand, where there is no graph to walk and a declaration is all there is. The third treats a non-empty `roots` as direct too, and in the Yarn collector that field is non-empty for every package the walk touches.

So `child` lands in the `direct` set, `_relationships()` hangs a root edge on it, and the `parent -> child` edge that `_graph()` produces anyway sits next to it — one real, one invented.

The `SPDXID`s on both edges are derived from the purl: `_package_id()` replaces unsafe characters in `pkg:npm/child@2.0.0` and appends the first ten hex digits of the purl's sha256. The same package gets the same ID in every export, so the suffix in `SPDXRef-Package-npm-child-2.0.0-4c33f08f2a` is that digest — which means diffing two documents shows the extra edge at a glance, without parsing package names first.

## Three comparisons

The demo takes the Yarn fixture from the upstream tests as is (`_berry()` in `test/test_sbom_lockfiles.py`), changes only `app`'s declarations to make a set of variations, and runs both versions on each:

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

The first is the symptom: one extra `root -> child` before the fix, only `parent -> child` after. The second also lists `child` in `app`'s dependencies, and both versions produce identical edges — a real declaration deserves that edge. The third is the next section.

The upstream regression test is the same fixture with one parameter (`child_is_direct`) run twice, asserting that both runs have only `root -> parent` and `parent -> child`, and that only the declared case gains a root edge. The project here copies those two and adds one more that marks the graph incomplete.

## Remove one clause and the other two still hold

`also_direct` shows the `dependency_kind == "direct"` branch still works: one declaration anywhere puts both `direct` and `transitive` into `kinds`, the fold yields `direct`, and the root edge stays.

The branch without `lockfile_version` covers manifest entries. Those records have no pinned versions and no dependency graph; the second condition returns true first, and the third means nothing for them. The PR description calls it the existing fallback for manifest pins without lockfile metadata.

The clause that was removed could only ever admit one kind of package: **reached by the walk, never declared**. Exactly the kind that needed cleaning out.

## When the graph is incomplete it says something else

There is one more stretch at the end of `_relationships()`: a package that is neither in the direct set nor connected by any graph edge gets an `OTHER` relationship, with the reason in a comment.

The third comparison marks the recorded graph as incomplete (`receipt["complete"] = False`), so `_graph()` returns nothing and `parent -> child` never appears. Before the fix, the fake edge smuggled `child` into "root dependencies"; after it, `child` lands in the fallback branch:

```json
{"spdxElementId": "SPDXRef-RootPackage", "relationshipType": "OTHER",
 "relatedSpdxElement": "SPDXRef-Package-npm-child-2.0.0-4c33f08f2a",
 "comment": "Recorded in the inventory; dependency path from the root was not recorded."}
```

"Recorded in the inventory, but the path from the root was not recorded" — that is the truth, and more accurate than "the root depends on it".

`_graph()` makes the same trade elsewhere: a missing node counts as "dependency unknown" rather than "no dependencies", and package-to-package edges are emitted only when there is a locked record and the graph is marked complete. With an incomplete graph it returns nothing at all, one package edge short rather than one too many.

`--strict` cannot reach this. Its meaning is "exit 2 if the inventory is incomplete": `requirements.txt` without pins, a lockfile that will not parse. This inventory was complete, the command exited 0, and what was wrong was the relationship itself — completeness checking and relationship correctness are two different things.

## Which lockfiles are affected

Not every collector fills in `dependency_roots`. The implementations for cargo, composer, gemfile, gradle, nuget, pipfile, poetry and pubspec write `[]` there unconditionally, so removing that clause changes nothing for them. npm writes `roots` only when a package is declared directly (`npm_lockfile.py:514`), and those packages were already counted direct through `kind`. The collectors that also record a root for reachable-but-undeclared packages are yarn, pnpm and uv — and those three are also the only ones that produced the extra edge.

CycloneDX does not go through this code. `roots` still travels into CycloneDX as an occurrence property, so the information is not lost; it just stops counting as evidence of a direct declaration.

The PR carries another verification record, numbers from the author's machine: 144 passed across `test_licenses.py`, `test_sbom.py` and `test_sbom_lockfiles.py`; the two new parameterised cases against the old check give 1 failed / 1 passed, and the failure is exactly the extra root edge; widening to 12 files covering SBOM, licences and lockfile selection gives 642 passed, 1 skipped, 6 deselected — the six deselected ones need symlinks, and Windows refuses with `WinError 1314`. The three comparisons here cover only the export, and do not repeat those numbers.

## Reproducing

The project lives in `依赖关系_skylos/spdx_demo/`, with both `skylos` packages (parent `4481fea7`, merge `bf6215f0`) untouched in `vendor/`, keeping only the modules the SPDX export imports, plus the Apache-2.0 licence; commit hashes, the SHA-256 of `spdx.py` and `sbom.py`, and the hash of the upstream tarball are all recorded in `provenance.json`. It needs Python 3.11+ and PyYAML:

```text
python -m venv venv
venv/Scripts/python -m pip install pyyaml
venv/Scripts/python -B run.py --test
```

Each case builds the same `yarn.lock` content as the upstream fixture and starts one subprocess per version, with `sys.path` pointing at exactly one of them; `parse_yarn_lock` and `spdx_document` are upstream code. All three results are asserted case by case in `--test`; `--json` writes both versions' relationships along with the commit hashes.

## References

- skylos PR [#1179](https://github.com/duriantaco/skylos/pull/1179); parent commit [`4481fea7`](https://github.com/duriantaco/skylos/commit/4481fea70b5a7ccab9e4b362a42c2ebb4f3608ea), merge commit [`bf6215f0`](https://github.com/duriantaco/skylos/commit/bf6215f02f27d58c9c07ac57731505e65f76f8ad).
- Changed files: [`skylos/reporting/spdx.py`](https://github.com/duriantaco/skylos/blob/bf6215f02f27d58c9c07ac57731505e65f76f8ad/skylos/reporting/spdx.py), [`test/test_sbom_lockfiles.py`](https://github.com/duriantaco/skylos/blob/bf6215f02f27d58c9c07ac57731505e65f76f8ad/test/test_sbom_lockfiles.py).
- The collector: the walk and field writes in [`yarn_lockfile.py`](https://github.com/duriantaco/skylos/blob/bf6215f02f27d58c9c07ac57731505e65f76f8ad/skylos/rules/sca/yarn_lockfile.py); the spec: [SPDX 2.3 relationships](https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/).
