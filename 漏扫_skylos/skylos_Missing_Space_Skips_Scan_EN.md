# `MATCH(` one space short, and skylos skips the security scan

```python
def find(graph, name):
    return graph.query(f"MATCH(p:Person {{name: '{name}'}}) RETURN p")
```

`name` goes straight into the Cypher quotes. One single quote in the input and the shape of the query changes. skylos has a rule for this, `SKY-D211`, MEDIUM, and its message opens with "a value is interpolated inside a quoted string of the Cypher text, so a quote or backslash in it changes the query".

On 2026-11-13 06:37 UTC, [#1227](https://github.com/duriantaco/skylos/pull/1227) merged it into `main`. On the code above, it does not fire.

Change `MATCH(` to `MATCH (` and the same rule fires. The difference is one space.

Eight hours later, [#1228](https://github.com/duriantaco/skylos/pull/1228) arrived to add that space.

## The word list at the door

[`scan_file_with_tree()`](https://github.com/duriantaco/skylos/blob/311cfdf30ce4f92983a8a880fdc5fea88e056047/skylos/rules/danger/danger.py#L654-L679) in `skylos/rules/danger/danger.py` is handed a parsed AST, but first it looks at the source text to decide whether `scan_python_security_gaps()` runs at all:

```python
if source is None or _has_any(
    source.lower(),
    (
        "jinja", "requests", "httpx", "urllib", "importlib", "__import__",
        "gradio", "/tmp/", "makedirs", "mkdir", "url_for", "subprocess",
        "shlex", "match (", "merge (", "create (",
    ),
):
    scan_python_security_gaps(tree, file_path, findings, project_root=project_root)
```

Sixteen words. Thirteen are general danger words; the last three are Cypher literals, each carrying a space. Those three were written the same day `SKY-D211` was added, in #1227, in a different file from the rule itself.

The rule lives elsewhere. [`_CYPHER_PATTERN`](https://github.com/duriantaco/skylos/blob/311cfdf30ce4f92983a8a880fdc5fea88e056047/skylos/rules/danger/python_security_gaps.py#L42-L47) reads:

```python
_CYPHER_PATTERN = re.compile(
    r"\b(?:MATCH|MERGE|CREATE)\s*\(\s*\w*\s*(?::|\)|\{)", re.IGNORECASE
)
_CYPHER_START = re.compile(
    r"\s*(?:OPTIONAL\s+MATCH|MATCH|MERGE|CREATE|UNWIND|WITH|CALL)\b", re.IGNORECASE
)
```

`\s*` takes any amount of whitespace: none, one, two, or a line break. **The list at the door accepts exactly one space; the pattern inside accepts everything.** Two word lists, written independently, one in the prefilter in `danger.py`, one in the regexes in the rule file.

If the prefilter does not match, `scan_python_security_gaps()` is never called. That function holds eight rule IDs: `SKY-D211`, `D212`, `D348`, and `D355` through `D359`. They all go quiet together — not one finding missing, the whole branch skipped.

What the prefilter saves is the AST walk: `scan_python_security_gaps()` walks each file once and runs eight groups of checks, and a substring search can turn most files away first. Five of the rules on that branch are HIGH: command arguments built by concatenation (D212), shared temp directories (D348), Jinja with autoescape off (D355), untrusted input selecting a module (D357), Gradio bound to every interface (D358). None of them has anything to do with Cypher, but they ride in the same boat as D211.

## Ten spellings that cannot get through the door

Same snippet, different Cypher spellings. Does the parent prefilter let it through, and does the rule itself report:

| Spelling | Parent prefilter | First PR version | Merged | Rule reports D211 |
|---|---|---|---|---|
| `MATCH (` | yes | yes | yes | 1 |
| `MATCH(` | blocked | yes | yes | 1 |
| `MATCH  (` | blocked | yes | yes | 1 |
| `MATCH` then a line break, then `(` | blocked | yes | yes | 1 |
| `OPTIONAL MATCH(` | blocked | yes | yes | 1 |
| `MERGE(` | blocked | yes | yes | 1 |
| `CREATE(` | blocked | yes | yes | 1 |
| `f"""MATCH(` | blocked | yes | yes | 1 |
| triple quote, line break, `MATCH(` | blocked | yes | yes | 1 |
| `WITH 1 AS one`, line break, `MATCH(` | blocked | **blocked** | yes | 1 |
| `\nMATCH(` written in the source | blocked | **blocked** | yes | 1 |

The first row is the standard spelling, there for reference.

The last column comes from handing the source straight to `python_security_gaps.scan()`, bypassing the prefilter. All eleven rows say 1: the rule knows every spelling. The only variable is the door.

Whether you get missed also depends on what else the file mentions. A service that only queries a graph imports the neo4j driver and none of `requests`, `subprocess`, and the rest, so the whole file looks like nothing to the prefilter. Add one line `import requests` to such a file and the parent lets it through at once — not because of the Cypher, because of `requests`.

## Handing the word list back to the rule

The merged version pulls the keywords out into one place:

```python
_CYPHER_KEYWORDS = "MATCH|MERGE|CREATE"
```

The hint lives in the rule file, next to the two regexes:

```python
_SOURCE_HINT = re.compile(
    rf"(?:(?<![\w.])|(?<=\\[nrt]))(?<!def )"
    rf"(?:{_CYPHER_KEYWORDS})(?:\s|\\[nrt])*\(",
    re.IGNORECASE,
)

def mentions_graph_query(source: str) -> bool:
    return _SOURCE_HINT.search(source) is not None
```

On the `danger.py` side the three literals are gone, replaced by `or mentions_graph_query(source)`.

With the keywords shared, `_CYPHER_PATTERN` and `_CYPHER_START` in the rule file are now assembled from the same `_CYPHER_KEYWORDS`, so a new spelling only touches that one line.

Why not reuse `_CYPHER_PATTERN` directly? Because the prefilter holds source text and the rule holds a string dug out of the AST. In the source you write `f"MATCH(p:Person {{name: ...}})"` and the quotes, the `f` prefix, the doubled braces, the `\n` escapes are all still there; in the AST none of that survives. Two regexes facing two kinds of input. The vocabulary can be shared; the shape cannot.

This is the recurring flaw of coarse-filter-then-fine-check: the coarse filter wants speed and writes a few literals; the fine check wants precision and writes a full regex. The two evolve on their own, and nothing in between guarantees they mean the same thing.

## Two holes in the first hint

The first version anchored the hint on an opening quote, and the comment says why: `require a string quote first, so ordinary code such as re.match(pattern) or create(...) does not start the scan`. The direction was right — `re.match(` should not start a scan — and the price was every spelling not sitting directly behind a quote:

```python
["']{1,3}\s*[^"'\n]*\b(?:MATCH|MERGE|CREATE)\s*\(
```

Of the ten non-standard spellings, the first version lets eight through and blocks two. One is `WITH 1 AS one`, line break, `MATCH(`: `\s*` eats the line break, `[^"'\n]*` can only reach the next line break, and `\bMATCH` never connects. The other is `\nMATCH(` in the source, where `\n` is two characters and `n` is a word character, so `\b` does not hold.

The second problem is not a miss but a slowdown. `\s*` and `[^"'\n]*` both eat spaces, so on a long run of spaces the engine tries every split:

![Time for the first hint and the merged hint on `label = '<N spaces>'`](assets/backtrack.png)

8000 spaces: about 0.7 s for the first version, under 0.5 ms for the merged one; each doubling of the input quadruples the time. These are three runs on one machine, keeping the fastest, so the order of magnitude does not depend on a single measurement. This code runs once for every Python file that misses the first thirteen words.

The second version drops the anchor and looks for a keyword followed by a paren anywhere, using two lookbehinds to rule out ordinary calls:

- `(?<![\w.])`: the character before cannot be a word character or a dot, so `re.match(` and `db.create(` do not fire;
- `(?<!def )`: `def create (` does not fire;
- `(?<=\\[nrt])`: when the preceding text is a `\n`, `\r`, or `\t` escape, allow it to fire, since there is no word boundary there to begin with.

`(?:\s|\\[nrt])*` only eats whitespace and those three escapes; there is no second repetition for it to overlap with, so backtracking stays linear.

## Lookalikes and precision

| A snippet in the source | Parent prefilter | Merged |
|---|---|---|
| `re.match (name, pattern)` | yes | no |
| `re.match(name, pattern)` | no | no |
| `db.create(obj)` | no | no |
| `def create (name):` | yes | no |
| `def create(name):` | no | no |

`re.match (` and `def create (` both pass the parent: `"match ("` and `"create ("` are plain substrings, blind to what precedes them. The old list did not only miss, it also scanned for nothing.

Would a wider pattern scan too much? Run `\b(?:MATCH|MERGE|CREATE)\s*\(` with no anchor over skylos' own `skylos/` package (1042 `.py` files): 162 files hit. The final hint hits 10. Of the 152 extra, 144 start with a method call like `_CONVERTER_RE.match(...)`, 8 with `merge(...)`, and none is Cypher. Handing those 10 files to the rule itself yields zero `SKY-D211`. The parent's three literals hit 2 files in the same tree.

Those numbers are the output of `python -B run.py --measure <skylos source tree>/skylos` in the reproduction: `files 1042`, `merged hint 10`, `wide \b hint 162`, `parent literals 2`.

## Which versions carry it

- 5.6.0 (released 2026-11-11) and everything before it: `python_security_gaps.py` has no `SKY-D211`, and the prefilter has none of the three Cypher literals. The snippet at the top is silent on 5.6.0 because the rule has not arrived yet, not because the prefilter stopped it.
- #1227 and #1228 both landed on 2026-11-13, less than eight hours apart; the latest on PyPI is still 5.6.0, so this window did not go out with any release. The next one will carry both, and the prefilter and the rule will agree.
- What the window skipped is the eight rule IDs of `scan_python_security_gaps()`, five of them HIGH. The scan does not fail, the exit code is unchanged; that one branch simply produces nothing.

To tell whether a tree is in this window, look at the prefilter tuple in `skylos/rules/danger/danger.py`: `"match ("` alongside the thirteen general words and no `mentions_graph_query` is the shape between #1227 and #1228. The 5.6.0 tuple has no `"match ("`.

The reproduction is in the repository under `漏扫_skylos/prefilter_demo/`: `python -B run.py --test` prints the tables above and the timings of both hints, standard library only; `--measure <dir>` counts how many files in any Python source tree each of the three patterns hits.

Upstream: `duriantaco/skylos`, [#1228](https://github.com/duriantaco/skylos/pull/1228), parent commit [`311cfdf3`](https://github.com/duriantaco/skylos/commit/311cfdf30ce4f92983a8a880fdc5fea88e056047), merge commit [`017365e6`](https://github.com/duriantaco/skylos/commit/017365e64b19109199fc9d037c80b7f795e2087b).
