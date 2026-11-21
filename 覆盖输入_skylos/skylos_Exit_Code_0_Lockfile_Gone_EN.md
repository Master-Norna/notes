# skylos sbom -o Cargo.lock exits 0, and the lockfile is now an SBOM

```console
$ cargo generate-lockfile
     Locking 7 packages to latest compatible versions
$ skylos sbom . -o Cargo.lock
Wrote CycloneDX 1.6 SBOM with 7 packages to Cargo.lock
$ echo $?
0
```

`Cargo.lock` was 1817 bytes for seven packages. It is 13633 bytes now, and what sits there is a CycloneDX JSON document: `$schema`, `bomFormat`, `components`. The `[[package]]` list is gone.

`skylos sbom` is the dependency-inventory command: it reads the lockfiles and manifests in a project and writes a CycloneDX or SPDX JSON document. `-o` takes the output path, `-` means standard output. The output may be a new file or a file that is already part of the project — including one the command just read from. skylos is a code scanner; `sbom` is its dependency-inventory subcommand, and it runs offline by default.

After `Cargo.lock` is overwritten, `cargo build` resolves from `Cargo.toml` again and writes a new lockfile, possibly with versions other than the pinned ones. If the lockfile is in version control, `git diff` shows the whole file replaced. Manifests are heavier: `serde = "1"` in `Cargo.toml`, `<dependency>` in `pom.xml`, `install_requires` in `setup.py` are written by hand, and no command turns an SBOM back into them.

The same command exits 2 and leaves the file alone on 5.5.0 and later. On earlier versions — tested back to 4.50.1, through 5.4.0 — it exits 0 and replaces the file. `pip install -U skylos` to 5.5.0 or newer (the latest is [5.7.0](https://github.com/duriantaco/skylos/releases/tag/v5.7.0)) and the problem is gone.

## The guard knows 11 names

Before the fix, `run_sbom_command` ran a check before writing the file:

```python
if args.output != "-" and (
    Path(args.output).name.casefold() in {
        "requirements.txt", "pyproject.toml", "package.json", "go.mod",
        "uv.lock", "package-lock.json", "pnpm-lock.yaml", "poetry.lock",
        "yarn.lock", "pipfile.lock", "npm-shrinkwrap.json",
    }
    or Path(args.output).suffix.casefold() == ".csproj"
):
    print("SBOM error: output must not overwrite a dependency input.", file=sys.stderr)
    return 2
```

`Path(args.output).name` keeps only the file name and `casefold()` ignores case: if the name is in the set, neither `sub/Cargo.lock` nor `CARGO.LOCK` gets through. `.csproj` is checked by suffix instead, because its file name is the project name (`App.csproj`, `MyLib.csproj`) and cannot be listed.

There is nothing wrong with the check itself. The problem is the list: eleven names, maintained by hand.

## The collector knows 24

In the same repository, the list the dependency collector reads is longer. `vulnerability_scanner.py` keeps it in three places:

- `_LOCKFILE_ECOSYSTEMS` has 14 lockfiles: `uv.lock`, `poetry.lock`, `Pipfile.lock`, `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `Cargo.lock`, `composer.lock`, `Gemfile.lock`, `pubspec.lock`, `gradle.lockfile`, `packages.lock.json`.
- `_MANIFEST_ECOSYSTEMS` has 6 manifests: `package.json`, `go.mod`, `pom.xml`, `Cargo.toml`, `composer.json`, `pubspec.yaml`.
- Python has four more: `requirements.txt`, `pyproject.toml`, `setup.cfg`, `setup.py`. The first two go through the Python parser; `setup.cfg` and `setup.py` are marked by `SETUPTOOLS_MANIFEST_NAMES`, which reads `install_requires` statically without executing `setup.py`.

The union is 24. The guard protects 11, so 13 are left over. They come in two kinds:

| Kind | Files | After being overwritten |
| --- | --- | --- |
| Lockfiles (7) | `bun.lock`, `Cargo.lock`, `composer.lock`, `Gemfile.lock`, `pubspec.lock`, `gradle.lockfile`, `packages.lock.json` | The package manager can resolve again, but not necessarily to the pinned versions |
| Manifests (6) | `Cargo.toml`, `composer.json`, `pubspec.yaml`, `pom.xml`, `setup.py`, `setup.cfg` | The hand-written declarations are gone; no command rebuilds them |

A lost lockfile can be regenerated with `cargo generate-lockfile`; a lost manifest can only come back from version control, and if it was never committed it is simply gone. The guard returns before the collector runs, so whether the collector read those files, or how many packages it found, has no bearing on whether the output gets written.

The two lists do not even live in the same file: the guard is in `skylos/commands/sbom_cmd.py`, the collector's lists are in `skylos/rules/sca/vulnerability_scanner.py`. Each carries its own literals, with no shared constant between them and no script that generates one from the other. Adding an ecosystem means remembering both places.

## Running it against 24 names

The demo in `覆盖输入_skylos/overwrite_demo/` extracts the guard from both versions and runs it against all 24 input names: when the guard lets a name through, the demo actually writes an SBOM and then compares SHA-256 of the original bytes. Standard library only, offline under `-B -S`.

```console
$ python -B -S 覆盖输入_skylos/overwrite_demo/run.py
...
parent   overwrites 13/24 dependency inputs (6 manifests, 7 lockfiles)
merged   overwrites 0/24 dependency inputs (0 manifests, 0 lockfiles)
```

`--test` turns the same comparison into assertions:

```console
$ python -B -S 覆盖输入_skylos/overwrite_demo/run.py --test
PASS parent overwrites 13/24 inputs, merged 0/24; extras and byte checks pass
```

The 13 names that get through are exactly the difference listed above. A second group covers the extra cases:

| Case | Before | After | Note |
| --- | --- | --- | --- |
| `sub/Cargo.lock` | overwrites | refuses | the guard only looks at the basename |
| `CARGO.LOCK` | lets through | refuses | `casefold()` ignores case |
| `Composer.JSON` | lets through | refuses | same, in another ecosystem |
| `App.csproj` | refuses | refuses | the `.csproj` suffix rule was already there |
| `App.CSPROJ` | refuses | refuses | the suffix check ignores case too |
| `sbom.json` | writes | writes | an ordinary output name |
| `report/bom.json` | writes | writes | an ordinary output name in a subdirectory |
| `pins.txt` | writes | writes | pulled in by `requirements.txt` with `-r` |

"Lets through" means the guard did not stop it. On Windows the case variants land on the same file; on Linux they create a new file with upper-case letters, and the guard should refuse that too.

## Again on a real project

The table above is the extracted guard, not the full CLI. So I ran the real thing as well: `cargo generate-lockfile` produced a lockfile with 7 packages and 1817 bytes; skylos was installed from the parent commit `b529347` (`pip install --no-deps --force-reinstall` from the snapshot). I used the parent commit rather than PyPI because 5.4.0's collector reads 0 packages from this Cargo project, which hides the full consequence of "it read the dependency and then overwrote it".

```console
$ skylos sbom . -o Cargo.lock
Wrote CycloneDX 1.6 SBOM with 7 packages to Cargo.lock
$ echo $?
0
```

The file after the overwrite is 13633 bytes, its SHA-256 going from `14946046…` to `c3b076a8…`. On the same version `-o Cargo.toml` behaves the same way: a 133-byte manifest becomes 13633 bytes of JSON, exit 0.

On the merge commit `7eff6a5`:

```console
$ skylos sbom . -o Cargo.lock
SBOM error: output must not overwrite a dependency input.
$ echo $?
2
```

The bytes do not change. `-o Cargo.toml` also exits 2; `-o sbom.json` writes normally on both versions. The three runs side by side:

| Version | `-o Cargo.lock` | Exit | File |
| --- | --- | --- | --- |
| Parent `b529347` | writes 7 packages | 0 | 1817 B → 13633 B |
| Merge `7eff6a5` | refuses | 2 | 1817 B → 1817 B |
| PyPI 5.4.0 | writes 0 packages | 0 | 1817 B → 3270 B |

The third row deserves its own sentence: 5.4.0 also overwrites, but its SBOM contains no Cargo packages — the collector returns 0 packages for this Cargo project and prints an `SBOM incomplete` warning. **Overwriting and "what was read" are two separate things**: the guard runs before collection, so what the collector found does not change whether the file gets written.

## Why extend the list

The most direct idea is "run the collector first and see whether the output path is one of the files it read". That walks the project twice, and the collector may fail to read a file because of permissions or a symlink; when it cannot read a file it cannot rule it out, so the guard misses it. The output may also sit outside the project, go through a symlink, or point into a directory that does not exist yet — a dynamic check would have to cover all of that.

Another idea is "refuse if the output file already exists". That is too broad: an SBOM is routinely written over the previous one, and `-o sbom.json` should not fail on the second run.

So the guard uses a static list: cheap, and aligned with the collector's supported names. The cost is that two lists have to stay in sync — and this bug is a sync that was missed. The fix adds the 13 names to the set without changing how the check works. The production change is 13 lines; the tests add 28 lines and change 3.

A static list knows conventional file names, not file names referenced by another file. The maintainer named that branch in review:

> Custom files included by `requirements.txt`, such as `pins.txt`, can be overwritten. This is outside this pr's scope and should be fixed separately.

The PR's own test results show how the surface changed: the regression group parameterizes 17 names × 2 formats, 34 cases in all; on the unmodified main 26 fail and 8 pass, and after the fix all 34 pass. The SBOM group has another 88 passes, one symlink case excluded because the link cannot be created on Windows.

## When it arrived, when it was fixed

The eleven names did not grow in a day. From [4.50.1](https://github.com/duriantaco/skylos/releases/tag/v4.50.1) (10-15) through [5.4.0](https://github.com/duriantaco/skylos/releases/tag/v5.4.0), `sbom_cmd.py` carried the same set of eleven names; 5.5.0 has 24.

| Time (UTC) | Event | Guard list |
| --- | --- | --- |
| 10-15 10:01 | v4.50.1 released | 11 |
| 11-02 15:33 | v5.4.0 released | 11 |
| 11-05 00:34 | [#1168](https://github.com/duriantaco/skylos/pull/1168) merged | 24 |
| 11-10 08:27 | [v5.5.0](https://github.com/duriantaco/skylos/releases/tag/v5.5.0) released | 24 |
| 11-19 14:04 | v5.7.0 released | 24 |

5.4.0 to 5.5.0 is 7 days and 16 hours. Anyone who installed a new version from PyPI in that window got 5.4.0, where `-o Cargo.lock` exits 0 and the file is replaced; install after 5.5.0 and the same command exits 2.

## Which projects it hits

These 13 names span nine ecosystems — Bun, Cargo, Composer, RubyGems, Pub, Gradle, NuGet, Maven and setuptools. Any project that carries one of these dependency files and runs an SBOM step in CI can run into it.

- **Rust**: `Cargo.lock` sits in version control, so after the overwrite `git diff` is the whole file, yet `cargo build` still succeeds — it resolves from `Cargo.toml` again, with versions that need not match the pinned ones. In review that diff is easy to wave through as "a lockfile update"; the cost is a build against a different dependency graph.
- **PHP / Dart / Java / .NET**: `composer.lock`, `composer.json`, `pubspec.lock`, `pubspec.yaml`, `gradle.lockfile`, `packages.lock.json`, `pom.xml`. Every one of these names looks like an ordinary output file name, so appending it to `$OUT` meets almost no friction.
- **Python packaging**: `setup.py` and `setup.cfg` are hand-written; once overwritten, no command reconstructs `install_requires` from the SBOM. Only version control brings them back, and if they were never committed they are gone.

To tell whether it hits you, you do not need the ecosystem list — look at what sits to the right of `-o` in the CI script. A literal like `sbom.json` or `report/bom.json` is fine; a variable shared across an ecosystem matrix is the case worth a second look.

## Checking your own install

First, which version is installed: the `Version` line in `pip show skylos`. 5.4.0 and below need attention; 5.5.0 and later carry the full list. Then, without reading any code, ask the installed guard whether it knows `cargo.lock`:

```console
$ python -c "import inspect, skylos.commands.sbom_cmd as m; print('cargo.lock' in inspect.getsource(m.run_sbom_command))"
```

5.4.0 prints `False`, 5.5.0 prints `True`. The blunter way is to run it once in a project that has a `Cargo.lock`:

```powershell
skylos sbom . -o Cargo.lock; echo "exit=$LASTEXITCODE"
```

`exit=2` with the bytes unchanged means the fixed version; `exit=0` with the file turned into JSON means you hit it. Restore the lockfile afterwards — a rebuild may pin different versions, and `git diff` will tell you.

CI scripts often use `-o "$OUT"`, with `$OUT` assembled from an environment variable or a matrix parameter. Any combination that lands on one of those 24 names turns the dependency file into an SBOM on 5.4.0 and earlier; the more ecosystems the matrix spreads over, the easier it is to hit one.

## Sources

- PR: [duriantaco/skylos#1168](https://github.com/duriantaco/skylos/pull/1168), merge commit [7eff6a5](https://github.com/duriantaco/skylos/commit/7eff6a519ed6c7fdec9263672203ad07902905a5), parent [b529347](https://github.com/duriantaco/skylos/commit/b52934735471f61ef5b813ff88c38c6be0a8533c).
- Collector lists: [`_LOCKFILE_ECOSYSTEMS`, `_MANIFEST_ECOSYSTEMS`, `SETUPTOOLS_MANIFEST_NAMES` in vulnerability_scanner.py](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/skylos/rules/sca/vulnerability_scanner.py#L191-L214).
- Output guard: [`run_sbom_command` in sbom_cmd.py](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/skylos/commands/sbom_cmd.py#L75-L104).
- CHANGELOG: the [5.5.0 entry](https://github.com/duriantaco/skylos/blob/v5.5.0/CHANGELOG.md) records this as "sbom: protect additional dependency input filenames".
- CycloneDX spec: [cyclonedx.org](https://cyclonedx.org/); what a Cargo lockfile is for: [Cargo Book](https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html).
- PyPI: [5.4.0](https://pypi.org/project/skylos/5.4.0/), [5.5.0](https://pypi.org/project/skylos/5.5.0/).

Upstream: `duriantaco/skylos`, [#1168](https://github.com/duriantaco/skylos/pull/1168), parent commit [`b5293473`](https://github.com/duriantaco/skylos/commit/b52934735471f61ef5b813ff88c38c6be0a8533c), merge commit [`7eff6a51`](https://github.com/duriantaco/skylos/commit/7eff6a519ed6c7fdec9263672203ad07902905a5).
