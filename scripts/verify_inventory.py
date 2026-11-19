#!/usr/bin/env python3
"""Validate the generated multi-source inventory and its provenance."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATEGORIES = {"LSP", "DAP", "Formatter", "Linter", "Runtime", "Compiler"}


def load(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main() -> int:
    inventory = load("inventory.json")
    sources = load("sources.json")["sources"]
    state = load("source_state.json")["sources"]
    candidates = load("discovery_candidates.json")["entries"]
    unresolved = load("unresolved_matches.json")
    adapters = load("adapters.json")
    errors: list[str] = []
    rows = inventory.get("languages", [])
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate canonical record ID")
    if inventory.get("schema") != 2:
        errors.append("inventory schema is not 2")
    if set(state) != set(sources):
        errors.append("source state keys do not match the source registry")

    source_counts = Counter()
    for row in rows:
        if not row.get("id") or not row.get("name"):
            errors.append(f"record lacks stable id or name: {row}")
            continue
        members = row.get("sources", {})
        if not members:
            errors.append(f"record has no source evidence: {row['id']}")
        for key, source_row in members.items():
            if key not in {"pldb", "wikidata", "github_linguist"}:
                errors.append(f"unexpected identity source {key}: {row['id']}")
            source_counts[key] += 1
            if not isinstance(source_row, dict):
                errors.append(f"invalid {key} source evidence: {row['id']}")
        for match in row.get("matches", []):
            if match.get("method") not in {"wikidata-pldb-id", "exact-wikipedia-sitelink",
                    "pldb-githubLanguage", "exact-name-or-published-alias"}:
                errors.append(f"unknown match method for {row['id']}: {match}")
        for tool in row.get("tools", []):
            if not set(tool.get("categories", [])).issubset(CATEGORIES):
                errors.append(f"unknown tool category for {row['id']}: {tool.get('categories')}")
            if not tool.get("name") or not tool.get("install"):
                errors.append(f"tool lacks name or install command: {row['id']}")
        expected = []
        categories = {c for tool in row.get("tools", []) for c in tool.get("categories", [])}
        if "LSP" in categories: expected.append("language-server-catalogued")
        if categories & {"Runtime", "Compiler"}: expected.append("runtime-or-compiler-catalogued")
        if row.get("tools"): expected.append("development-tools-catalogued")
        if row.get("package_identifiers"): expected.append("package-manager-identifiers-recorded")
        if "github_linguist" in members: expected.append("github-language-identified")
        if "wikidata" in members: expected.append("wikidata-linked")
        if "pldb" in members: expected.append("pldb-listed")
        if len(members) == 1: expected.append("single-source")
        if row.get("readiness") != expected:
            errors.append(f"readiness mismatch for {row['id']}: {row.get('readiness')} != {expected}")

    if inventory.get("counts", {}).get("languages") != len(rows):
        errors.append("language total does not match records")
    for key, count in (("pldb_records", source_counts["pldb"]),
                       ("wikidata_items", source_counts["wikidata"]),
                       ("github_linguist_languages", source_counts["github_linguist"])):
        if inventory.get("counts", {}).get(key) != count:
            errors.append(f"source count {key}: stored {inventory.get('counts', {}).get(key)}; found {count}")
    if inventory.get("counts", {}).get("unresolved_identity_matches") != unresolved.get("count"):
        errors.append("unresolved match count disagrees with the report")
    if len(candidates) != inventory.get("counts", {}).get("wikipedia_candidates"):
        errors.append("Wikipedia discovery candidate count disagrees")
    if any(entry.get("status") not in {"linked", "ambiguous", "discovery-only"} for entry in candidates):
        errors.append("unknown Wikipedia candidate status")
    if not adapters.get("adapters") or not any(a.get("verification", {}).get("status") == "tested" for a in adapters["adapters"]):
        errors.append("no tested MCP adapter pairing recorded")

    actual = {
        "languages": len(rows),
        "with_multiple_identity_sources": sum(len(row["sources"]) > 1 for row in rows),
        "with_mason_tools": sum(bool(row["tools"]) for row in rows),
        "with_homebrew_formula": sum(any(f["available"] for f in row["homebrew_formulas"]) for row in rows),
        "wikipedia_candidates": len(candidates),
        "wikipedia_linked_candidates": sum(row["status"] == "linked" for row in candidates),
        "wikipedia_only_candidates": sum(row["status"] == "discovery-only" for row in candidates),
        "unresolved_identity_matches": unresolved.get("count", -1),
        "mason_packages_associated": sum(len(row["tools"]) for row in rows),
    }
    for category in ("LSP", "DAP", "Formatter", "Linter", "Runtime", "Compiler"):
        actual[f"mason_{category.lower()}_packages"] = sum(category in p["categories"] for r in rows for p in r["tools"])
    for key, value in actual.items():
        if inventory.get("counts", {}).get(key) != value:
            errors.append(f"summary count {key}: stored {inventory.get('counts', {}).get(key)}; calculated {value}")

    print(json.dumps({"records": len(rows), "identity_source_members": dict(source_counts),
                      "counts": actual, "problems": errors}, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
