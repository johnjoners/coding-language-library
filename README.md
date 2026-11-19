# coding-language-library

A source-linked union of programming-language identities and tool catalogues: broad discovery, structured identities, language-recognition metadata, and package availability. No one list defines the catalogue.

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

Without a checkout, run the packaged entry point from the git repository, or install the wheel and run `coding-language-library`:

```sh
uvx --from git+https://github.com/johnjoners/coding-language-library coding-language-library
```

Pin a tagged release when you want a fixed catalogue snapshot; the wheel bundles the data at build time:

```sh
uvx --from git+https://github.com/johnjoners/coding-language-library@v0.3.0 coding-language-library
```

The server reads the committed JSON snapshots under `data/`, which are also bundled into the package. It makes no network requests, installs nothing, and does not launch language servers.

| Tool | Does |
| --- | --- |
| `search_index` | Searches identities, aliases, extensions, source IDs, package IDs, and linked tools |
| `list_shelf` | Pages the union, filtered by source coverage or recorded tooling |
| `get_language` | Returns one source-linked record with its tool and adapter evidence |
| `check_tools` | Checks recorded tool and Homebrew executable names against `PATH` |
| `recommend_stack` | Ranks recorded stacks against a caller-supplied task profile |
| `compare_candidates` | Compares chosen stack IDs against one profile, failed constraints included |
| `get_suitability_evidence` | Returns documented suitability claims and evidence for a language ID |

## Task matching

`recommend_stack` and `compare_candidates` rank the recorded stacks in `data/suitability_profiles.json` against a task profile the caller fills in (`data/task_profile.schema.json`). The matcher never reads the `task` string, so a requirement left in prose is invisible to it.

| Profile field | Effect |
| --- | --- |
| `task` | Request text, validated for presence only; constraint terms named in it without a structured field are echoed in `unstructured_terms` on every result |
| `existing_project.languages` | +100 when a stack language matches |
| `existing_project.frameworks` | +60 when a stack framework matches |
| `team_experience` | +20 on a language or framework match |
| `priorities` | Position-weighted points, capped at 60, only where the profile records a supported signal with evidence |
| `target.platform` | Hard filter against the `platform.*` capability |
| `target.deployment` | Hard filter against the `deployment.*` capability |
| `requirements.required_integrations` | Hard filter per integration against `integration.*` |
| `requirements.memory_limit_mb` | Hard filter against the recorded `resources.memory_peak_mb` |
| `requirements.native_dependencies_allowed` | `false` fails a stack whose `dependencies.native` claim is `required` |

A stack is eliminated only by a recorded, contradicting claim. Constraints that are missing, unevidenced, or `supported_with_conditions` are listed as unknown in the result. Constraint terms named in the `task` text but not placed in a structured field are never parsed or applied; they are echoed in `unstructured_terms` so the caller can move them into the profile. `recommend_stack` drops failed stacks; `compare_candidates` keeps them so the failure stays visible. Ties share a rank. Each result carries its claims, conditions, HTTPS sources, a suggested next validation, and the profile's `unknowns` echoed as open questions.

Profiles are curated by hand: a small set of service stacks, grown only with reviewed evidence.

## Identity and matching

Joins use stable IDs, published crosswalks, exact page links, exact names, and source-published aliases. Ambiguous joins stay separate and are counted in `data/unresolved_matches.json`. The Wikipedia list seeds discovery only; a candidate with no identity-source match never enters `data/inventory.json`.

## Refresh and monitoring

```sh
uv run --locked --group catalog python scripts/monitor_sources.py
uv run --locked --group catalog python scripts/harvest_wikipedia.py
uv run --locked --group catalog python scripts/build_inventory.py
uv run --locked --group catalog python scripts/verify_inventory.py
```

A weekly workflow checks validators, content hashes, revisions, and entity digests. On a source change it rebuilds snapshots and opens a review pull request; a human reviews the data and source terms before merging, and the workflow never updates `main`. See [SOURCES.md](SOURCES.md) for the change signals and review process.

## Terms

The root [MIT license](LICENSE) covers project code and authored documentation only. Generated data follows upstream terms. See [DATA-LICENSE.md](DATA-LICENSE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).