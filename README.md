# coding-language-library

A programmatic, source-linked union of programming-language identities and tool catalogues. The inventory combines broad discovery, structured identities, language-recognition metadata, and package availability. No one list defines the catalogue.

| Path | Contents |
| --- | --- |
| `data/inventory.json` | Canonical records with source identities, match evidence, package identifiers, and tools |
| `data/sources.json` | Source roles, terms, filters, and monitor endpoints |
| `data/source_state.json` | Last generated upstream revisions, validators, digests, and counts |
| `data/suitability_profiles.json` | Evidence-backed stack profiles linked to canonical language IDs |
| `data/task_profile.schema.json` | JSON Schema for the structured task profile |
| `data/wikipedia.json` | Supplemental discovery seed only |
| `data/discovery_candidates.json` | Seed candidates linked, ambiguous, or still discovery-only |
| `data/unresolved_matches.json` | Exact-key collisions and joins left unresolved |
| `data/adapters.json` | Adapter definition and the one tested pairing |
| `scripts/build_inventory.py` | Rebuilds the source union and snapshots |
| `scripts/monitor_sources.py` | Checks upstream revisions, validators, and content changes |
| `scripts/verify_inventory.py` | Checks identities, source counts, readiness, and generated totals |
| `mcp/server.py` | Read-only MCP interface |
| `mcp/task_matching.py` | Task-profile validation, hard-constraint checks, and weighted ranking |
| `SOURCES.md` | Source roles, monitoring cadence, and review cycle |
| `ARCHITECTURE.md` | System map and editable diagram |
| `DATA-LICENSE.md` | Code and dataset license boundaries |
| `SECURITY.md` | Supported version and private reporting route |
| `THIRD_PARTY_NOTICES.md` | Upstream license notices and bundled materials |

## Use

Run the stdio MCP server from this checkout:

```sh
uv run --python 3.11 --locked python mcp/server.py
```

The server reads committed JSON snapshots. It makes no network requests, installs nothing, and does not launch language servers. Tools are `search_index`, `list_shelf`, `get_language`, `check_tools`, `recommend_stack`, `compare_candidates`, and `get_suitability_evidence`. The PATH check returns the absolute locations of matching executables.

## Task matching

`recommend_stack` turns a request into a structured task profile (`data/task_profile.schema.json`), then filters and ranks recorded language, framework, and runtime combinations from `data/suitability_profiles.json`. Hard requirements eliminate candidates only on recorded evidence; a `supported_with_conditions` claim stays unknown until its conditions are checked. Missing or unevidenced constraints are reported as unknown, never guessed. Ranking adds comparison points for existing project languages, frameworks, team experience, and evidenced priorities; ties share a rank. Every result carries the claims, conditions, HTTPS sources, and a validation step, so a recommendation can be traced back to what a source documented and what remains unmeasured. Profiles are curated, not generated: they cover a small set of common service stacks and grow only with reviewed evidence.

## Identity and matching

The canonical inventory is a source union, not a ranking. PLDB and Wikidata provide broad identity coverage; the language-recognition file adds GitHub-scoped identities; package registries contribute tool availability. Source membership is recorded on each record. Stable IDs, published crosswalks, exact page links, exact names, and published aliases are used for joins. Ambiguous joins remain separate and are reported in `data/unresolved_matches.json`.

The Wikipedia list is kept as a discovery seed. It can reveal candidates or gaps, but entries that have no corroborating identity-source match stay outside `data/inventory.json`.

## Refresh and monitoring

```sh
uv run --locked --group catalog python scripts/monitor_sources.py
uv run --locked --group catalog python scripts/harvest_wikipedia.py
uv run --locked --group catalog python scripts/build_inventory.py
uv run --locked --group catalog python scripts/verify_inventory.py
```

A weekly workflow checks conditional HTTP validators, content hashes, revisions, and entity digests. When source content changes, it rebuilds snapshots and opens a review pull request. A human reviews the data and source terms before merging; the workflow never updates `main` automatically. See [SOURCES.md](SOURCES.md) for the change signals and review process.

## Terms

The root [MIT license](LICENSE) covers project code and authored documentation only. Generated data follows upstream terms. See [DATA-LICENSE.md](DATA-LICENSE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
