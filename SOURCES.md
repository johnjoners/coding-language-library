# Sources and refresh

The catalogue is the union of maintained language and tooling sources. A source
entry means that source lists or classifies a record; it does not establish that
the language is current, widely used, or compatible with a tool.

| Source | Use | Limits | Change signal | Cadence |
| --- | --- | --- | --- | --- |
| [PLDB](https://pldb.info/pldb.json) | Broad language discovery; published `id`, `aka`, Wikipedia, and Linguist crosswalks | Curated dataset, not a census. The public-domain statement is in its upstream README. | conditional HTTP validator; if it rotates, compare downloaded content SHA-256 with the snapshot | Weekly |
| [Wikidata](https://query.wikidata.org/sparql) | Stable QIDs, labels, aliases, language-class membership, and package identifiers | Community-edited claims can be incomplete or wrong. Membership uses `P31/P279* Q9143`. | Hash of distinct QIDs and each entity's `schema:dateModified` value; WDQS has no usable validator for this query | Weekly |
| [GitHub Linguist](https://github.com/github-linguist/linguist/blob/main/lib/linguist/languages.yml) | GitHub-recognized language names, aliases, IDs, and extensions | GitHub detection scope, not a global usage ranking | conditional HTTP validator; compare content SHA-256 if it rotates | Weekly |
| [Mason Registry](https://github.com/mason-org/mason-registry) | Explicit language-tool package declarations and executables | Package listing does not prove installability or language compatibility | conditional HTTP validator; compare content SHA-256 if it rotates | Weekly |
| [Homebrew Core](https://formulae.brew.sh/api/formula.json) | Check formula names published by Wikidata and record executable names | Formula presence is not proof that a formula works on a particular host | conditional HTTP validator; compare content SHA-256 if it rotates | Weekly |
| [Wikipedia list](https://en.wikipedia.org/wiki/List_of_programming_languages) | Supplemental discovery candidates and recall check | Never creates canonical inventory records by itself | MediaWiki revision ID and timestamp | Weekly |

`data/sources.json` is the source registry. `data/source_state.json` records generated validators, revisions, content digests,
counts, and Wikidata entity IDs that the entity API did not return. The individual data
records retain source IDs and the matching rule. Exact identifiers, exact page
links, exact names, and source-published aliases are used; ambiguous matches are
kept separate and counted in `data/unresolved_matches.json`.

## Review cycle

A weekly workflow checks conditional HTTP validators, source content digests, page revisions, and Wikidata entity digests. If any source content changes, it harvests Wikipedia as a supplemental seed, rebuilds snapshots, runs tests, and opens a pull request from `automated/source-refresh`. Review data changes, counts, unresolved joins, and license notices before merging. The workflow stops on check failure and never merges to `main`; unchanged content leaves snapshots untouched.

For a manual refresh:

```sh
uv run --locked --group catalog python scripts/monitor_sources.py
uv run --locked --group catalog python scripts/harvest_wikipedia.py
uv run --locked --group catalog python scripts/build_inventory.py
uv run --locked --group catalog python scripts/verify_inventory.py
```
