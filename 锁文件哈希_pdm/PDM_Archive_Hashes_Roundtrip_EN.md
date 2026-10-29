# The Hashes Are in pylock.toml. Why Does PDM Say They Aren’t?

Open `pylock.toml`, and `archive.hashes` is right there. Ask PDM to export requirements, though, and it says:

```text
Hash is not available for '…', please export with `--no-hashes` option.
```

Export to pylock instead, and the command succeeds. Compare the new file with the old one, and the original `archive.hashes` is gone.

One export refuses to continue; the other silently drops a field. Both start with the same omission: **the hashes are in the file, but never make it into the in-memory object.**

That is the bug I fixed in [PDM #3956](https://github.com/pdm-project/pdm/pull/3956), merged on October 27, 2026. The production change adds just seven lines. Following one round trip—write a lock file, read it back, then export it—shows why those lines belong in the reader, not at the point where the error appears.

## 1. One wheel, two ways to record it

`pylock.toml` is a standard format for exchanging locked dependency information between Python packaging tools, originally defined by [PEP 751](https://github.com/python/peps/blob/fc008c935df169de9b7669d8c22face10af4be4c/peps/pep-0751.rst). Alongside package names and versions, it records where installation files come from and which hashes to check them against.

The affected case is a direct archive reference: give PDM a wheel URL or the path to a local wheel. The relevant part of the generated lock file looks like this, with the hash value omitted:

```toml
[[packages]]
name = "first"
version = "2.0.2"

[packages.archive]
url = "http://fixtures.test/artifacts/first-2.0.2-py2.py3-none-any.whl"

[packages.archive.hashes]
sha256 = "…"
```

A `.whl` extension does not necessarily put the file under `packages.wheels`.

- `packages.archive` records a directly specified archive. That archive can be a wheel.
- `packages.wheels` records the wheels available to choose from for a package.

The first means “install this file”; the second means “choose a suitable wheel from these files.” The specification’s [definition of archive](https://github.com/pypa/packaging.python.org/blob/6a46e9923342d5512167cbc2ca4393928abb8520/source/specifications/pylock-toml.rst#L429-L441) explicitly includes both wheels and sdists. The extension alone cannot tell the reader which table holds the hashes.

PDM could already [write direct file dependencies](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/formats/pylock.py#L52-L67) with their hashes under `archive.hashes`. The loss came later, when PDM read its own correctly written file back in.

## 2. The location comes back; the hashes do not

An export does not simply copy the original TOML. PDM first reads the lock file into internal objects, then passes those objects to an exporter for the target format.

One of those objects is a `Candidate`: a possible installation, carrying a name, version, source, and file hashes. A newly constructed candidate has an [empty `hashes` list by default](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/models/candidates.py#L145-L157).

Before the fix, `_read_pylock()` recognized `archive` and restored its source information. Here is an excerpt from the [direct parent commit](https://github.com/pdm-project/pdm/blob/3b82f5291988aa8d6a5c1f92b695c5b18ce170bd/src/pdm/models/repositories/lock.py#L141-L159):

```python
elif archive := package.get("archive"):
    req_dict["url"] = archive.get("url")
    req_dict["path"] = archive.get("path")
    req_dict["subdirectory"] = archive.get("subdirectory")

req = Requirement.from_req_dict(package_name, req_dict)
# Local paths are also converted to file: URLs here
candidate = Candidate(req=req, name=package_name, version=package.get("version"))
```

A hash-loading loop followed, but it visited only `wheels` and `sdist`:

```python
for artifact in itertools.chain(
    package.get("wheels", []),
    [sdist] if (sdist := package.get("sdist")) else [],
):
    algo, hash_value = next(iter(artifact["hashes"].items()))
    hash_item = {"hash": f"{algo}:{hash_value}"}
    # Add url / file as appropriate for the input
    candidate.hashes.append(hash_item)
```

Direct archive hashes live in a third place: `archive.hashes`. Nothing visited that table.

The resulting object looked almost complete. It had a package name, a version, and a download location, but its hash list was still `[]`. TOML parsing had not failed, and no hashing algorithm had gone wrong. The missing step was the mapping from an external field to its internal representation.

| Stage, starting with the same archive input | Before the fix | After the fix |
| --- | --- | --- |
| Input `archive.hashes` | Contains the recorded hashes | Contains the same hashes |
| Reader constructs the candidate | Restores the location, leaves `candidate.hashes` empty | Restores the location and the `FileHash` records |
| requirements export with hashes enabled | Rejects the candidate for missing hashes | Writes the corresponding `--hash` values |
| pylock export | Writes the archive without `hashes` | Preserves `archive.hashes` |

**Restoring an installation file’s location is not the same as restoring its complete record.**

## 3. Why the exporters behave differently

Both exporters receive the same candidate with missing hashes. What differs is how they handle its empty list.

### requirements: refuse to export

The [requirements exporter](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/formats/requirements.py#L255-L275) checks whether hashes were requested and whether the candidate has any. If they were requested but none are available, it raises an error:

```python
if options.hashes and not candidate.hashes:
    raise PdmUsageError(
        f"Hash is not available for '{req}', "
        "please export with `--no-hashes` option."
    )
```

It does not reopen the lock file to look for `archive.hashes`, nor does it know that an earlier step missed the field. For the object it has been given, “hash is not available” is accurate.

`--no-hashes` bypasses this check by no longer asking for hash output. It does not put the missing values back into the candidate, and the exported requirements no longer contain the corresponding `--hash` options.

### pylock: write the archive, omit the table

The [pylock exporter](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/formats/pylock.py#L60-L67) first creates `archive`, then iterates over the internal hash list:

```python
archive = result["archive"] = {"url": req.get_full_url()}
if req.path:
    archive["path"] = req.str_path
for hash_item in candidate.hashes:
    hash_type, hash_value = hash_item["hash"].split(":", 1)
    archive.setdefault("hashes", tomlkit.inline_table())[hash_type] = hash_value
```

An empty list means the loop never runs, so the `hashes` table is never created. Serialization can finish normally, producing TOML that still parses.

Parseable TOML is not necessarily a valid pylock file. The [specification for `packages.archive.hashes`](https://github.com/pypa/packaging.python.org/blob/6a46e9923342d5512167cbc2ca4393928abb8520/source/specifications/pylock-toml.rst#L499-L510) marks the table as required and states:

> The table MUST contain at least one entry.

When an archive is recorded here, omitting its hash table is not allowed. An empty table is not a substitute, either. A successful command has not necessarily preserved the data or met the format’s requirements.

## 4. Seven lines at the shared entry point

Changing only the requirements error would leave pylock’s silent loss untouched. Making pylock emit `hashes = {}` would restore neither the values nor compliance with the requirement above.

The actual fix goes in `_read_pylock()`, after candidate construction and before the existing wheel/sdist loop. The [merged code](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/models/repositories/lock.py#L148-L166) adds:

```python
if archive := package.get("archive"):
    link = candidate.link
    assert link is not None
    candidate.hashes = [
        {"url": link.url_without_fragment, "file": link.filename, "hash": f"{algo}:{value}"}
        for algo, value in archive.get("hashes", {}).items()
    ]
```

This does not download the file again or recompute a hash. It converts every algorithm and value already recorded in the input into PDM’s existing `FileHash` representation.

Each record has three fields:

| Field | Source | Purpose |
| --- | --- | --- |
| `hash` | Algorithm and value from `archive.hashes` | Combines a TOML key and value into a string such as `sha256:…` for downstream consumers |
| `url` | The candidate link’s `url_without_fragment` | Keeps the file location without treating a fragment such as `#subdirectory=src` as part of that location |
| `file` | The candidate link’s `filename` | Keeps the filename, matching the metadata PDM already uses when obtaining file hashes |

This structure was not invented for the patch. [`BaseRepository.get_hashes()`](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/models/repositories/base.py#L309-L319) already produces records in this shape. The [native lock-file writer](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/src/pdm/project/lockfile/pdmlock.py#L113-L125) also consumes either `url` or `file`, depending on whether static URLs are being saved. Although requirements export mainly needs `hash`, the reader should restore the full internal representation, not insert a string tailored to one immediate consumer.

Using `.items()` preserves multiple algorithms recorded for an archive. For a local path, the patch reuses the candidate link already constructed earlier instead of assembling another address. The existing wheel/sdist reading logic is unchanged.

**The fix belongs at the data entry point shared by both export paths.** Once hashes are restored there, both exporters can keep using their existing output logic.

## 5. “Did the export succeed?” is not enough

The [upstream reader regression tests](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/tests/models/test_locked_repository.py#L219-L243) check the internal representation after reading. They cover URL and relative-path sources, each with one or two hash algorithms, and assert that `url`, `file`, and `hash` match the input. The URL example includes `#subdirectory=src` to check that the internal file location excludes the fragment.

A separate set of [export tests](https://github.com/pdm-project/pdm/blob/adfdb5dccacc0153ad7bf6b14354ad8e46b9801b/tests/test_formats.py#L1214-L1235) starts with a lock file generated by PDM itself:

1. Set `lock.format = "pylock"`, then add a direct wheel URL or local wheel with `--no-sync` so it is not installed.
2. Check that the generated lock file already contains a hash equal to the SHA-256 of the actual test wheel’s contents.
3. Export requirements or pylock, and check that the same value survives.

That separates three questions: Was the hash written in the first place? Did it survive reading? Is it still present after exporting to another format?

For pylock in particular, a test that checked only a zero exit code could pass before the fix. The test needs to parse the exported TOML again and compare `packages[0].archive.hashes`.

On Windows with Python 3.12, I reran these eight regression cases from the merged version against both the direct parent commit and the merge commit: `8 failed` before the fix, `8 passed` after it. The pre-fix export failures split exactly as expected: requirements reported missing hashes; pylock completed, but the test hit a `KeyError` when it accessed `archive["hashes"]`.

## 6. Running the round trip offline

I put the relevant functions from the parent commit, `3b82f529…`, and the merge commit, `adfdb5dc…`, into [hash_demo](hash_demo/). The offline demo uses the Python standard library to run the unchanged, extracted reader functions from both versions, candidate construction, and the output logic for both formats. Minimal stand-ins supply the surrounding requirement and link objects, project environment, and TOML containers. It does not download packages or resolve dependencies; on the pylock side, the output is a package-record dictionary. The project README documents the extracted source, pinned SHAs, and stand-in boundaries.

Run these commands from the repository root:

```powershell
python 锁文件哈希_pdm/hash_demo/run.py
python 锁文件哈希_pdm/hash_demo/run.py --test
```

The question here is whether the hashes from a single input pass through the internal object and reach the requirements text and pylock package record. This run produced the following comparison:

| Observation | Before the fix | After the fix |
| --- | --- | --- |
| Input `archive.hashes` | Contains hashes | Contains the same hashes |
| `candidate.hashes` after reading | Empty | Contains the algorithms and values recorded in the input |
| requirements export with hashes enabled by default | Reports missing hashes | Includes the corresponding `--hash` options |
| pylock export | Succeeds, but lacks `archive.hashes` | Contains the original `archive.hashes` |
| requirements export with `--no-hashes` | Succeeds without hashes | Still omits hashes |

With a single algorithm in the input, the candidate goes from zero hash records before the fix to one after it. With both SHA-256 and SHA-512, it goes from zero to two. URL and local-path sources give the same result, and the exported values match the hashes calculated from the actual bytes of the locally generated wheel.

All five test methods in the offline regression run passed. Together they cover twelve scenarios: four positive archive cases, four wheel/sdist compatibility cases, and four negative cases with missing or empty hashes. Missing and empty archive hashes already violate the specification’s requirements. Those cases stay in the tests to check that the fix restores existing data rather than inventing a hash.

## What the round trip needs to preserve

This bug made me pay closer attention to a quiet kind of failure: the input parses, the main fields are present, and the object is constructed, but a field that is not needed to locate the file never gets carried over.

The omission only becomes visible later. One consumer detects the missing data and stops; another successfully writes out the incomplete record.

What needs protecting is more than an export command’s exit code. It is the meaning of the data after a round trip: given an archive, an algorithm, and a hash value, reading and exporting should preserve the same basis for checking that file. Seven lines reconnect it at the shared entry point. Tests along the full path pin down exactly where it was lost.
