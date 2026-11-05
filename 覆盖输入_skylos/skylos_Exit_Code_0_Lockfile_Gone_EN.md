# Exit code 0, and the lockfile is gone

```console
$ cargo generate-lockfile
     Locking 7 packages to latest compatible versions
$ skylos sbom . -o Cargo.lock
Wrote CycloneDX 1.6 SBOM with 7 packages to Cargo.lock
$ echo $?
0
```

`Cargo.lock` was 1817 bytes for seven packages. It is 13633 bytes now, and what sits there is a CycloneDX JSON document: `$schema`, `bomFormat`, `components`. The `[[package]]` list is gone.

`skylos sbom` is the dependency-inventory command: it reads the lockfiles and manifests in a project and writes a CycloneDX or SPDX JSON document. `-o` takes the output path, `-` means standard output. The output may be a new file or a file that is already part of the project — including one the command just read from. skylos itself is a code scanner; `sbom` is its dependency-inventory subcommand, and it runs offline by default.

After `Cargo.lock` is overwritten, `cargo build` resolves from `Cargo.toml` again and writes a new lockfile, possibly with versions other than the pinned ones. If the lockfile is in version control, `git diff` shows the whole file replaced. Manifests are heavier: `serde = "1"` in `Cargo.toml`, `<dependency>` in `pom.xml`, `install_requires` in `setup.py` are written by hand, and no command turns an SBOM back into them.

## The guard knows 11 names

Before the fix, `run_sbom_command` ran a check before writing the file:

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

`Path(args.output).name` keeps only the file name and `casefold()` ignores case: if the name is in the set, neither `sub/Cargo.lock` nor `CARGO.LOCK` gets through. `.csproj` is checked by suffix instead, because its file name is the project name (`App.csproj`, `MyLib.csproj`) and cannot be listed.

There is nothing wrong with the check itself. The problem is the list: eleven names, maintained by hand.

## The collector knows 24

The dependency collector in the same code base keeps a longer list. From `vulnerability_scanner.py`:

- `_LOCKFILE_ECOSYSTEMS` has 14 lockfiles: `uv.lock`, `poetry.lock`, `Pipfile.lock`, `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `Cargo.lock`, `composer.lock`, `Gemfile.lock`, `pubspec.lock`, `gradle.lockfile`, `packages.lock.json`.
- `_MANIFEST_ECOSYSTEMS` has 6 manifests: `package.json`, `go.mod`, `pom.xml`, `Cargo.toml`, `composer.json`, `pubspec.yaml`.
- Python has its own: `requirements.txt`, `pyproject.toml`, `setup.cfg`, `setup.py`. The first two go through the Python parser; `setup.cfg` and `setup.py` are marked by `SETUPTOOLS_MANIFEST_NAMES`, which reads `install_requires` statically without executing `setup.py`.

The union is 24. The guard protects 11. The difference is 13.

Those 13 fall into two kinds:

| Kind | Files | After being overwritten |
| --- | --- | --- |
| Lockfiles (7) | `bun.lock`, `Cargo.lock`, `composer.lock`, `Gemfile.lock`, `pubspec.lock`, `gradle.lockfile`, `packages.lock.json` | The package manager can resolve again, but not necessarily to the pinned versions |
| Manifests (6) | `Cargo.toml`, `composer.json`, `pubspec.yaml`, `pom.xml`, `setup.py`, `setup.cfg` | The hand-written declarations are gone; no command rebuilds them |

**The second row is the worse one.** A lost lockfile can be regenerated with `cargo generate-lockfile`; a lost manifest can only come back from version control, and if it was never committed, it is simply gone.

## Running it

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

The 13 names that get through are exactly the difference listed above. A few extra cases ran as their own group:

| Case | Before | After | Note |
| --- | --- | --- | --- |
| `sub/Cargo.lock` | overwrites | refuses | the guard only looks at the basename |
| `CARGO.LOCK` | lets through | refuses | `casefold()` ignores case |
| `Composer.JSON` | lets through | refuses | same, in another ecosystem |
| `App.csproj` | refuses | refuses | the `.csproj` suffix rule was already there |
| `App.CSPROJ` | refuses | refuses | the suffix check ignores case too |
| `sbom.json` | writes | writes | an ordinary output name |
| `report/bom.json` | writes | writes | an ordinary output name in a subdirectory |
| `pins.txt` | writes | writes | pulled in by `requirements.txt`; a known leftover |

"Lets through" means the guard did not stop it. On Windows the case variants land on the same file; on Linux they create a new file with upper-case letters, and the guard should refuse that too.

The table above is the extracted guard, not the full CLI. So I ran the real thing as well: `cargo generate-lockfile` produced a lockfile with 7 packages and 1817 bytes; skylos was installed from the parent commit `b529347` (`pip install --no-deps --force-reinstall <snapshot zip>`). I used the parent commit rather than PyPI because 5.4.0's collector reads 0 packages from this Cargo project, which hides the full consequence of "it read the dependency and then overwrote it".

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

The bytes do not change. `-o Cargo.toml` also exits 2; `-o sbom.json` writes normally on both versions.

The three numbers together:

| Version | `-o Cargo.lock` | Exit | File |
| --- | --- | --- | --- |
| Parent `b529347` | writes 7 packages | 0 | 1817 B → 13633 B |
| Merge `7eff6a5` | refuses | 2 | 1817 B → 1817 B |
| PyPI 5.4.0 | writes 0 packages | 0 | 1817 B → 3270 B |

The third row deserves its own sentence: 5.4.0 also overwrites, but its SBOM contains no Cargo packages — the collector returns 0 packages for this Cargo project. **Overwriting and "what was read" are two separate things**: the guard runs before collection, so whether the collector saw anything does not change whether the file gets written.

## Why extend the list

The most direct idea is "run the collector first and see whether the output path is one of the files it read". That walks the project twice, and the collector may fail to read a file because of permissions or a symlink; when it cannot read a file it cannot rule it out, so the guard misses it. The output may also sit outside the project, go through a symlink, or point into a directory that does not exist yet — a dynamic check would have to cover all of that.

Another idea is "refuse if the output file already exists". That is too broad: an SBOM is routinely written over the previous one, and `-o sbom.json` should not fail on the second run.

So the guard uses a static list: cheap, and aligned with the collector's supported names. The cost is that two lists have to stay in sync — and this bug is a sync that was missed. The fix adds the 13 names to the set without changing how the check works. The production change is 13 lines; the tests add 28 lines and change 3.

## The edge

In review the maintainer pointed out one hole that remains: custom files pulled in by `requirements.txt` through `-r pins.txt` or `-c constraints.txt` can still be overwritten by `-o`. Those files are read from `requirements.txt` at run time, so they are not in any static list, and they are outside this PR's scope.

> Custom files included by `requirements.txt`, such as `pins.txt`, can be overwritten. This is outside this pr's scope and should be fixed separately.

That is the boundary of a static list in general: it knows "conventional file names", not "file names referenced by another file".

## Who is affected

- The fix is in the repository's Unreleased section; at the time of writing the latest release on PyPI is 5.4.0 (2026-11-02), which does not contain the check.
- On 5.4.0, `-o Cargo.lock` also exits 0 and overwrites the file; the SBOM just contains no Cargo packages (3270 bytes, 0 packages), because the collector returns 0 packages for this Cargo project.
- On the parent commit `b529347` of the main branch, the collector already reads these files: `-o Cargo.lock` writes 7 packages into the JSON (1817 B → 13633 B), and `-o Cargo.toml` does the same. That is exactly the gap the fix closes: the collector was extended first, the guard followed later.
- Trigger: the basename of `-o` (case-insensitively) equals one of those 13 names; `-o -` is unaffected. CI scripts commonly run `-o "$OUT"` with `$OUT` assembled from an environment variable or a matrix parameter; any combination that lands on one of these names triggers it.
- When the lockfile is not in version control, `cargo build` rebuilds it immediately after the overwrite, which makes the problem quieter; only a tracked lockfile shows the diff. Manifests have no such automatic rebuild to fall back on.
- After the fix: stderr prints `SBOM error: output must not overwrite a dependency input.`, the exit code is 2, and the original file is untouched.

The PR reports its own test results: the final regression cases fail 26 and pass 8 on an unmodified main, and pass 34 after the fix; the SBOM tests pass 88 (one symlink case excluded for Windows permissions). What this post re-ran is the guard and the write itself; the real-CLI comparison above was run separately.

To check it yourself: in a project with a `Cargo.lock`, run `skylos sbom . -o Cargo.lock` and look at the exit code; then try `-o sbom.json` to confirm the SBOM can still be written. After upgrading, the first should become 2. If `-o` in a CI script comes from a variable, take a look at which names that variable can take.

## Sources

- PR: [duriantaco/skylos#1168](https://github.com/duriantaco/skylos/pull/1168), merge commit [7eff6a5](https://github.com/duriantaco/skylos/commit/7eff6a519ed6c7fdec9263672203ad07902905a5), parent [b529347](https://github.com/duriantaco/skylos/commit/b52934735471f61ef5b813ff88c38c6be0a8533c).
- Collector lists: [`_LOCKFILE_ECOSYSTEMS`, `_MANIFEST_ECOSYSTEMS`, `SETUPTOOLS_MANIFEST_NAMES` in vulnerability_scanner.py](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/skylos/rules/sca/vulnerability_scanner.py#L191-L214).
- Output guard: [`run_sbom_command` in sbom_cmd.py](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/skylos/commands/sbom_cmd.py#L75-L104).
- CHANGELOG: the [Unreleased entry](https://github.com/duriantaco/skylos/blob/7eff6a519ed6c7fdec9263672203ad07902905a5/CHANGELOG.md) rejecting output paths named after Bun, Cargo, Composer, RubyGems, Pub, Gradle, NuGet, Maven and setuptools dependency inputs.
- PyPI: [skylos 5.4.0](https://pypi.org/project/skylos/5.4.0/).
