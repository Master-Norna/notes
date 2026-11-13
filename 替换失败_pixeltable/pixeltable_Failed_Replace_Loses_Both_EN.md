# After a failed replace, the old table and the new one are both gone

Exporting to Iceberg with `if_exists='replace'`, the worst outcome on failure is not "the replace did not happen":

```text
before:  target table, 1 row
failed:  target table absent
         temp table absent
```

None of the three rows written into the temp table can be read back. The error only says `failed to write Iceberg table 'demo.t': synthetic rename failure`, and says nothing about where the data went — because the cleanup deleted it.

This is what [pixeltable #1889](https://github.com/pixeltable/pixeltable/pull/1889) fixes. The patch is small, but it redefines what is left behind after a failure.

The problem was first filed as [issue #1885](https://github.com/pixeltable/pixeltable/issues/1885). That report reproduced it on pixeltable 0.7.16, Python 3.14.4, Ubuntu 24.04: inject one catalog IO error into `rename_table` and nothing is left in the namespace, neither the old table nor the new data. The reproduction here moves to 0.7.24, Python 3.12, Windows, and on three of five scenes the parent ends with an empty namespace.

## A temp table first, to keep the old one

The replace path in `export_iceberg()` does not rewrite in place. It creates a temp table first, named after the target plus a random suffix:

```python
temp_name = f'{table_name}__pxt_tmp_{uuid.uuid4().hex[:8]}'
```

The whole dataset is written there, and only then is the target touched: `drop_table(table_name)`, then `rename_table(temp_name, table_name)`. The comment in the code states the intent plainly ([parent `iceberg.py:174-176`](https://github.com/pixeltable/pixeltable/blob/2eca8e44e31dc4ad6eee2c602615cb35e5d89dcc/pixeltable/io/iceberg.py#L174-L176)):

> Write to a temp table and swap on success so a mid-stream failure leaves any existing original untouched. Drop-then-rename is two catalog calls and not truly atomic; a crash between them leaves the original gone but the data preserved under the temp name.

The second half of that is the whole story: the author knew the two catalog calls are not atomic, and knew the old table disappears first inside that window. The designed fallback is "the data survives under the temp name". The data does survive — until `finally` deletes it.

## Which copy the finally deletes

The parent's cleanup ([`iceberg.py:199-205`](https://github.com/pixeltable/pixeltable/blob/2eca8e44e31dc4ad6eee2c602615cb35e5d89dcc/pixeltable/io/iceberg.py#L199-L205)):

```python
finally:
    # Drop temp if it still exists; covers mid-stream errors and BaseException paths
    # like KeyboardInterrupt. On success, rename consumed temp_name, so swallow NoSuchTableError.
    try:
        catalog.drop_table(temp_name)
    except NoSuchTableError:
        pass
```

For two situations it does the right thing:

- A failure in the middle of the write: the temp table holds half a dataset, dropping it is right, and the old table was never touched.
- Success: `rename` has already turned the temp table into the target, the old name is gone, `NoSuchTableError` is swallowed.

But there is a third:

- A failure in the middle of the swap: the temp table is **the only complete copy**, and the old table has already been dropped. Deleting it now empties both sides.

That is the flaw: `finally` cannot tell "the temp table is garbage" from "the temp table is the last copy left". All it knows is that the name might still exist.

With the failure stopped inside the swap window, what sits under the two names:

![The swap window: after drop and before rename the target name is already empty and the temp name holds the only copy of the three-row export; the parent's finally deletes it unconditionally, while the merged version deletes only a temp table it created itself and does not need for recovery](assets/swap-window.png)

## Where the failure lands changes the outcome

`drop_table` and `rename_table` are two separate catalog calls. The failure can land:

1. `drop_table` raises but did not take effect — the target is still there, the temp table should go. This is what `finally` was written for.
2. `drop_table` raises after taking effect — the target is gone, the temp table is the complete export.
3. `rename_table` raises — the target was deleted in the previous step, the temp table is the complete export.
4. Checking the target after the swap, `table_exists` itself fails — nothing can be assumed about the target.

Case 2 is not a theoretical corner. The PR body says it in so many words: "a catalog operation may take effect before reporting failure" — a call can land on the server and still report a failure on the way back. The error message after the fix asks the caller to "inspect both identifiers rather than assuming the temporary table still exists".

## Two flags and one more question

The merged version ([`iceberg.py`](https://github.com/pixeltable/pixeltable/blob/b76619839123f2f4402fb78ee8348adcc6f87f2f/pixeltable/io/iceberg.py#L179-L224)) adds two booleans:

```python
temp_created = False
preserve_temp = False

try:
    temp_tbl = catalog.create_table(temp_name, schema=arrow_schema)
    temp_created = True
    ...
    preserve_temp = True
    if existing_tbl is not None:
        catalog.drop_table(table_name)
    catalog.rename_table(temp_name, table_name)
    preserve_temp = False
except ...
```

- `temp_created` is true only once **this call really created the temp table** — so a failure elsewhere does not delete somebody else's table.
- `preserve_temp` is set before the swap starts and cleared after `rename` succeeds. Any failure inside the window defaults to keeping.

The exception handler then asks about the target once more:

```python
if preserve_temp:
    try:
        preserve_temp = not catalog.table_exists(table_name)
    except Exception:
        # If the catalog is unavailable, keep the possible recovery copy.
        pass
```

If the target is already there (say the drop did not take effect), the temp table is redundant and gets cleaned up; if the target is absent, or the question itself fails, the copy stays. The `finally` then deletes only when `temp_created and not preserve_temp`:

```python
finally:
    # Clean up only a temp table we know this call created and do not need for recovery.
    if temp_created and not preserve_temp:
        try:
            catalog.drop_table(temp_name)
        except NoSuchTableError:
            pass
```

When the copy is preserved, the error message gains a sentence naming the target and the temp identifier, so the caller knows where the data is. The identifier is the target name plus `__pxt_tmp_` and eight hex characters, e.g. `demo.t__pxt_tmp_1a2b3c4d`; the real name differs every time, and the message is what counts.

```text
...; the catalog swap may be incomplete. Inspect 'demo.t' and temporary
identifier 'demo.t__pxt_tmp_1a2b3c4d' before retrying.
```

## Five scenes, both versions

The project `替换失败_pixeltable/iceberg_swap_demo/` vendors both `iceberg.py` versions unchanged, loads them by file and patches them over `pixeltable.io.export_iceberg`; the rest is pixeltable 0.7.24, whose copy of that file is byte-identical to the parent commit. The catalog is a local SQLite `SqlCatalog` wrapped in a `FailingCatalog` that injects a failure at a chosen step of the swap:

| scene | injection | before the fix | after the fix |
| --- | --- | --- | --- |
| `rename-fails/no-target` | no target table, `rename` raises | temp 0 / target missing | temp 1 (3 rows) / target missing / named in the error |
| `drop-applied-then-raises` | `drop` takes effect, then raises | temp 0 / target missing | temp 1 (3 rows) / target missing / named in the error |
| `drop-fails-before-effect` | `drop` raises before taking effect | temp 0 / target 1 row | temp 0 / target 1 row |
| `target-check-fails` | `drop` takes effect and raises, `table_exists` raises too | temp 0 / target missing | temp 1 (3 rows) / target missing / named in the error |
| `replace-succeeds` | nothing injected | temp 0 / target 3 rows | temp 0 / target 3 rows |

In one line:

```text
parent left no copy after 3/5 failed swaps; merged failed 0/5 expectations
```

Before the fix, three of the five scenes end with "target table absent, temp table absent" — not one row of what was written can be read back. After the fix those three each leave a complete temp table whose name the error gives out, readable as three rows with `load_table`; the scene where `drop` did not take effect cleans up as before, the target still there, nothing piling up; the success path leaves nothing either.

When the target is still there, cleanup works as usual: the upstream regression test runs this path three times in a row and both the target table and the temp table list stay clean — which is what the tests added during the PR revision are there to guard.

One environment snag while reproducing: pixeltable bundles PostgreSQL 16, and on this machine with a Chinese locale the bundled `initdb` fails to build a UTF-8 cluster, reporting `invalid byte sequence for encoding "UTF8"` during post-bootstrap. The demo creates the cluster with `-E SQL_ASCII --locale=C` first, then rebuilds the `postgres` and `pixeltable` databases from `template0` as UTF-8. On a machine with a normal locale the step is unnecessary.

## What you get back: data, not an atomic swap

The patch does not wrap the two calls in a transaction and does not restore the old target: what it prevents is the temp table being deleted as well after a failed swap.

So after a failed replace the caller still has work to do: the target table may be gone, the old data does not come back by itself; what can be recovered is **the new export**, under the temp name, with the full row count. For an export job whose first concern is getting the data landed and only then deciding what to do, that is a lot better than two empty names.

There is also a deliberate conservative choice: keep the temp table when `table_exists` fails. The cost is a table left behind in the worst case; the benefit is never deleting the only copy while not knowing whether the target exists. The error names it, so the operator can choose between recovering and dropping.

Upstream: `pixeltable/pixeltable`, [#1889](https://github.com/pixeltable/pixeltable/pull/1889), parent commit [`2eca8e44`](https://github.com/pixeltable/pixeltable/commit/2eca8e44e31dc4ad6eee2c602615cb35e5d89dcc), merge commit [`b7661983`](https://github.com/pixeltable/pixeltable/commit/b76619839123f2f4402fb78ee8348adcc6f87f2f).
