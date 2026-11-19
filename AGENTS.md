# AGENTS.md

## Records

- `data/wikipedia.json` is a supplemental discovery snapshot. Refresh it with `scripts/harvest_wikipedia.py`; do not curate its entries by hand.
- `data/inventory.json` is the canonical source union. It is not defined by the Wikipedia list; rebuild it with `scripts/build_inventory.py` after source changes.
- Run only one harvest/build sequence at a time; these commands share generated files.
- `data/sources.json` records source roles, terms, filters, and monitoring methods. `data/source_state.json` records generated revisions, validators, content digests, and counts. Check upstream changes with `scripts/monitor_sources.py` before refreshing.
- `data/discovery_candidates.json` preserves Wikipedia candidates that link to, conflict with, or are not represented in the canonical union.
- `data/adapters.json` is the registry for adapter commands and tested pairings. Record a pairing as tested only after a real handshake and tool request succeed.
- Join source records only through stable identifiers, published crosswalks, exact page links, exact names, or source-published aliases. Leave ambiguous joins unresolved.
- Keep source provenance, revision or retrieval time, license, match rule, and counts with the generated records.
- Keep installation identifiers separate from live availability checks. A listed identifier, tool, runtime, or compiler is not proof that it installs, is current, or is present on a machine.
- Do not promote source descriptions into compatibility claims. Preserve each source's own terms.

## MCP

- `mcp/server.py` reads the generated JSON under `data/` and remains read-only.
- Keep output bounded and paginated. Reject unknown names and invalid filters as tool errors.
- Do not install packages or launch language servers from the catalogue server.
- Label a route as tested only when the exact adapter and language-server pair is recorded in `data/adapters.json`.
- `check_tools` checks `PATH` only; it does not prove that an isolated package manager or coding client is configured.

## Architecture and verification

- Review `ARCHITECTURE.md` whenever sources, records, scripts, server behavior, data flow, or runtime boundaries change. Update its editable diagram source and generated views in the same change.
- Before staging, run the inventory verifier, the unit-test suite, and an official Python MCP SDK client that calls all the listed tools. Keep client scripts and downloaded probes outside the repo.
- The inventory builder uses the `catalog` dependency group; the MCP server stays standard-library-only.
- Keep probes and downloaded working files outside the repo. Keep tests focused on source joins, monitoring behavior, and the refresh workflow.
- Check links, attribution, secrets, staged whitespace, branch, commits, and remotes before handoff.
- Keep personal names and home-directory paths out of tracked files. Do not use em-dashes in authored prose.
