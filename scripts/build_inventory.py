#!/usr/bin/env python3
"""Build a provenance-first union from language and tooling registries."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
USER_AGENT = "coding-language-library/0.3 (https://github.com/johnjoners/coding-language-library)"
WDQS = "https://query.wikidata.org/sparql"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
BATCH = 50
PROPERTIES = {
    "pldb": "P11410", "homebrew": "P8443", "repology": "P6931",
    "pypi": "P5568", "npm": "P8262", "debian_source": "P9128",
    "arch_linux": "P3454", "fedora": "P3463", "chocolatey": "P10766",
    "nixpkgs": "P12433", "macports": "P13706", "github_topic": "P9100",
    "official_site": "P856", "source_repository": "P1324",
    "programming_paradigm": "P3966", "typing_discipline": "P7078",
    "implemented_in": "P277", "instance_of": "P31", "subclass_of": "P279",
}
PACKAGE_FIELDS = {"homebrew", "repology", "pypi", "npm", "debian_source", "arch_linux", "fedora", "chocolatey", "nixpkgs", "macports"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_resource(url: str, *, accept: str = "application/json", method: str = "GET", timeout: int = 120) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept}, method=method)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read(), {k.lower(): v for k, v in response.headers.items()}
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise
            try:
                delay = min(120, int(exc.headers.get("Retry-After", "0"))) or 2 ** (attempt + 1)
            except ValueError:
                delay = 2 ** (attempt + 1)
            print(f"HTTP {exc.code}; retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 4:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def get_json(url: str, *, accept: str = "application/json") -> tuple[Any, dict[str, str], bytes]:
    raw, headers = fetch_resource(url, accept=accept)
    return json.loads(raw), headers, raw


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).casefold().strip().replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return "".join(ch for ch in value if ch.isalnum() or ch in "+#")


def article_key(value: str | None) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    title = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1]).replace("_", " ")
    return norm(title)


def stable_digest(values: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def fetch_pldb() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]["pldb"]
    raw, headers = fetch_resource(config["data_url"], accept="application/json")
    rows = json.loads(raw)
    programming = []
    for row in rows:
        if "pl" not in str(row.get("tags", "")).split():
            continue
        programming.append({key: row[key] for key in ("id", "name", "aka", "wikipedia", "githubLanguage") if row.get(key)})
    state = {"etag": headers.get("etag"), "last_modified": headers.get("last-modified"),
             "sha256": hashlib.sha256(raw).hexdigest(), "records": len(rows),
             "programming_languages": len(programming), "retrieved_at": now_utc()}
    return programming, state


def fetch_wikidata_ids() -> tuple[list[str], str, str]:
    query = "SELECT DISTINCT ?item ?modified WHERE { ?item wdt:P31/wdt:P279* wd:Q9143 . OPTIONAL { ?item schema:dateModified ?modified } }"
    url = f"{WDQS}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    result, _, _ = get_json(url, accept="application/sparql-results+json")
    rows = result["results"]["bindings"]
    revisions = {row["item"]["value"].rsplit("/", 1)[-1]: row.get("modified", {}).get("value", "") for row in rows}
    ids = sorted(revisions)
    return ids, stable_digest(ids), stable_digest([f"{qid}:{revisions[qid]}" for qid in ids])


def entity_value(claim: dict[str, Any]) -> str | None:
    value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("id", "text", "amount", "time", "url"):
            if key in value:
                return str(value[key])
    return None


def fetch_wikidata(ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    revisions: list[str] = []
    for start in range(0, len(ids), BATCH):
        part = ids[start:start + BATCH]
        query = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(part),
            "props": "info|labels|aliases|descriptions|claims|sitelinks", "languages": "en",
            "sitefilter": "enwiki", "format": "json", "maxlag": "120"})
        result, _, _ = get_json(f"{WD_API}?{query}")
        if "error" in result:
            if result["error"].get("code") == "maxlag" and start + BATCH < len(ids):
                time.sleep(5)
                result, _, _ = get_json(f"{WD_API}?{query}")
            if "error" in result:
                raise RuntimeError(f"Wikidata API: {result['error'].get('code')}: {result['error'].get('info')}")
        for qid, entity in result.get("entities", {}).items():
            if entity.get("missing") is not None:
                continue
            labels = entity.get("labels", {}).get("en", {})
            aliases = [item["value"] for item in entity.get("aliases", {}).get("en", []) if item.get("value")]
            claims: dict[str, list[str]] = {}
            for key, prop in PROPERTIES.items():
                values = [value for claim in entity.get("claims", {}).get(prop, [])
                          if (value := entity_value(claim)) is not None]
                if values:
                    claims[key] = sorted(set(values))
            sitelink = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
            rows.append({"id": qid, "name": labels.get("value", qid), "aliases": sorted(set(aliases)),
                "description": entity.get("descriptions", {}).get("en", {}).get("value", ""),
                "enwiki": sitelink, "claims": claims, "lastrevid": entity.get("lastrevid")})
            revisions.append(f"{qid}:{entity.get('lastrevid', 0)}")
        print(f"Wikidata entities: {min(start + BATCH, len(ids))}/{len(ids)}", file=sys.stderr)
        time.sleep(0.25)
    missing_ids = sorted(set(ids) - {row["id"] for row in rows})
    return rows, {"items": len(rows), "requested_ids": len(ids), "missing_ids": missing_ids,
                  "qid_digest": stable_digest(ids), "revision_digest": stable_digest(revisions),
                  "retrieved_at": now_utc()}


def fetch_linguist() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]["github_linguist"]["data_url"]
    raw, headers = fetch_resource(url, accept="text/plain")
    languages = yaml.safe_load(raw)
    rows = []
    for name, details in languages.items():
        if details.get("type") != "programming":
            continue
        rows.append({"name": name, "aliases": details.get("aliases", []),
            "extensions": details.get("extensions", []), "language_id": details.get("language_id"),
            "group": details.get("group")})
    return rows, {"etag": headers.get("etag"), "sha256": hashlib.sha256(raw).hexdigest(),
        "entries": len(languages), "programming_languages": len(rows), "retrieved_at": now_utc()}


def fetch_mason() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]["mason_registry"]
    raw, headers = fetch_resource(config["data_url"], accept="application/zip")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = [name for name in archive.namelist() if name.endswith("registry.json")]
        if len(members) != 1:
            raise ValueError("Mason archive must contain exactly one registry.json")
        packages = json.loads(archive.read(members[0]))
    return packages, {"etag": headers.get("etag"), "last_modified": headers.get("last-modified"),
        "sha256": hashlib.sha256(raw).hexdigest(), "packages": len(packages), "retrieved_at": now_utc()}


def fetch_homebrew() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    config = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]["homebrew"]
    raw, headers = fetch_resource(config["data_url"])
    formulae = json.loads(raw)
    return {str(row["name"]): row for row in formulae}, {"etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"), "sha256": hashlib.sha256(raw).hexdigest(),
        "formulae": len(formulae), "retrieved_at": now_utc()}


def record_aliases(source: str, row: dict[str, Any]) -> list[str]:
    aliases = list(row.get("aliases", []))
    if source == "pldb" and row.get("aka"):
        aliases.append(row["aka"])
    return list(dict.fromkeys(str(x) for x in [row.get("name", ""), *aliases] if x))


def merge_source_records(pldb_rows: list[dict[str, Any]], wikidata_rows: list[dict[str, Any]],
                         linguist_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_rows = {"pldb": pldb_rows, "wikidata": wikidata_rows, "github_linguist": linguist_rows}
    nodes: dict[str, dict[str, Any]] = {}
    by_source: dict[str, list[str]] = defaultdict(list)
    for source, rows in source_rows.items():
        for row in rows:
            raw_id = row.get("id") or row.get("language_id") or norm(row.get("name", ""))
            ident = f"{source}:{raw_id}"
            if ident in nodes:
                raise ValueError(f"duplicate source identity {ident}")
            nodes[ident] = {"id": ident, "source": source, "record": row,
                            "name": row.get("name", str(raw_id)), "aliases": record_aliases(source, row)}
            by_source[source].append(ident)

    edges: list[tuple[int, str, str, str, str]] = []
    unresolved: list[dict[str, Any]] = []
    priority = {"wikidata-pldb-id": 0, "exact-wikipedia-sitelink": 1,
                "pldb-githubLanguage": 2, "exact-name-or-published-alias": 3}

    def add_unique(left: list[str], right: list[str], method: str, key: str) -> None:
        if len(left) == 1 and len(right) == 1:
            edges.append((priority[method], left[0], right[0], method, key))
        elif left and right:
            unresolved.append({"method": method, "key": key, "candidates": sorted(set(left + right)),
                               "reason": "ambiguous-exact-name" if "name" in method or "alias" in method else "ambiguous-crosswalk"})

    # Stable PLDB identifiers published in Wikidata.
    pl_by_id = {str(nodes[i]["record"]["id"]): i for i in by_source["pldb"]}
    for wid in by_source["wikidata"]:
        for value in nodes[wid]["record"].get("claims", {}).get("pldb", []):
            pid = pl_by_id.get(str(value))
            if pid:
                edges.append((priority["wikidata-pldb-id"], wid, pid, "wikidata-pldb-id", str(value)))

    # Exact article sitelinks are crosswalks, not language-name guesses.
    pldb_articles: dict[str, list[str]] = defaultdict(list)
    wd_articles: dict[str, list[str]] = defaultdict(list)
    for ident in by_source["pldb"]:
        key = article_key(nodes[ident]["record"].get("wikipedia"))
        if key:
            pldb_articles[key].append(ident)
    for ident in by_source["wikidata"]:
        title = nodes[ident]["record"].get("enwiki")
        if title:
            wd_articles[norm(title)].append(ident)
    for key in pldb_articles.keys() & wd_articles.keys():
        add_unique(pldb_articles[key], wd_articles[key], "exact-wikipedia-sitelink", key)

    # PLDB publishes GitHub Linguist names as a cross-reference field.
    linguist_keys: dict[str, list[str]] = defaultdict(list)
    for ident in by_source["github_linguist"]:
        for key in record_aliases("github_linguist", nodes[ident]["record"]):
            linguist_keys[norm(key)].append(ident)
    for ident in by_source["pldb"]:
        value = nodes[ident]["record"].get("githubLanguage")
        if value:
            add_unique([ident], linguist_keys.get(norm(str(value)), []), "pldb-githubLanguage", str(value))

    # Exact canonical names and source-published aliases are secondary joins.
    for left_source, right_source in (("pldb", "wikidata"), ("pldb", "github_linguist"), ("wikidata", "github_linguist")):
        left_index: dict[str, list[str]] = defaultdict(list)
        right_index: dict[str, list[str]] = defaultdict(list)
        for ident in by_source[left_source]:
            for key in record_aliases(left_source, nodes[ident]["record"]):
                if norm(key): left_index[norm(key)].append(ident)
        for ident in by_source[right_source]:
            for key in record_aliases(right_source, nodes[ident]["record"]):
                if norm(key): right_index[norm(key)].append(ident)
        for key in left_index.keys() & right_index.keys():
            add_unique(sorted(set(left_index[key])), sorted(set(right_index[key])),
                       "exact-name-or-published-alias", key)

    parent = {ident: ident for ident in nodes}
    members = {ident: {nodes[ident]["source"]} for ident in nodes}
    matches: dict[str, list[dict[str, str]]] = {ident: [] for ident in nodes}
    def root(ident: str) -> str:
        while parent[ident] != ident:
            parent[ident] = parent[parent[ident]]
            ident = parent[ident]
        return ident
    for _, left, right, method, key in sorted(edges):
        a, b = root(left), root(right)
        match = {"method": method, "key": key, "sources": sorted({nodes[left]["source"], nodes[right]["source"]})}
        if a == b:
            matches[a].append(match)
            continue
        if members[a] & members[b]:
            unresolved.append({"method": method, "key": key, "candidates": sorted([left, right]),
                               "reason": "same-source-collision"})
            continue
        parent[b] = a
        members[a] |= members[b]
        matches[a] = matches[a] + matches.pop(b) + [match]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ident, node in nodes.items():
        grouped[root(ident)].append(node)
    result = []
    for group in grouped.values():
        group.sort(key=lambda row: (row["source"], row["id"]))
        sources = {row["source"]: row["record"] for row in group}
        primary = next((row for source in ("pldb", "wikidata", "github_linguist")
                        for row in group if row["source"] == source), group[0])
        canonical = next((row["id"] for source in ("wikidata", "pldb", "github_linguist")
                          for row in group if row["source"] == source), group[0]["id"])
        all_names = sorted({alias for row in group for alias in row["aliases"]}, key=str.casefold)
        result.append({"id": canonical, "name": primary["name"],
                       "aliases": [name for name in all_names if norm(name) != norm(primary["name"])],
                       "sources": sources, "matches": sorted(matches[root(group[0]["id"])], key=lambda m: (m["method"], m["key"]))})
    result.sort(key=lambda row: (row["name"].casefold(), row["id"]))
    unique_unresolved = {json.dumps(row, sort_keys=True): row for row in unresolved}
    return result, [unique_unresolved[key] for key in sorted(unique_unresolved)]


def build() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_config = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]
    pldb, pldb_state = fetch_pldb()
    wikidata_ids, qid_query_digest, modified_digest = fetch_wikidata_ids()
    wikidata, wd_state = fetch_wikidata(wikidata_ids)
    wikidata_items_count = len(wikidata)
    wd_state["query_sha256"] = qid_query_digest
    wd_state["modified_digest"] = modified_digest
    linguist, linguist_state = fetch_linguist()
    mason, mason_state = fetch_mason()
    brew, brew_state = fetch_homebrew()
    groups, unresolved = merge_source_records(pldb, wikidata, linguist)

    language_lookup: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(groups):
        for value in [row["name"], *row["aliases"]]:
            if norm(value): language_lookup[norm(value)].append(index)
    mason_for: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    unresolved_mason = 0
    for package in mason:
        for language in package.get("languages", []):
            hits = set(language_lookup.get(norm(language), []))
            if len(hits) == 1:
                mason_for[next(iter(hits))][package["name"]] = package
            elif len(hits) > 1:
                unresolved_mason += 1
    inventory = []
    for index, group in enumerate(groups):
        tools = []
        for package in mason_for[index].values():
            tools.append({"name": package["name"], "categories": package.get("categories", []),
                "languages": package.get("languages", []), "homepage": package.get("homepage", ""),
                "licenses": package.get("licenses", []), "source_id": package.get("source", {}).get("id", ""),
                "executables": package.get("bin", {}), "install": f"MasonInstall {package['name']}"})
        tools.sort(key=lambda p: (p["categories"], p["name"]))
        wd_source = group["sources"].get("wikidata", {})
        claims = wd_source.get("claims", {})
        identifiers = {key: values for key, values in claims.items() if key in PACKAGE_FIELDS and values}
        formulas = []
        for formula_name in claims.get("homebrew", []):
            row = brew.get(formula_name)
            formulas.append({"name": formula_name, "available": row is not None,
                "version": row.get("versions", {}).get("stable") if row else None,
                "executables": row.get("executables", []) if row else [],
                "homepage": row.get("homepage", "") if row else "",
                "program_license": row.get("license") if row else None})
        readiness = []
        categories = {category for tool in tools for category in tool["categories"]}
        if "LSP" in categories: readiness.append("language-server-catalogued")
        if categories & {"Runtime", "Compiler"}: readiness.append("runtime-or-compiler-catalogued")
        if tools: readiness.append("development-tools-catalogued")
        if identifiers: readiness.append("package-manager-identifiers-recorded")
        if "github_linguist" in group["sources"]: readiness.append("github-language-identified")
        if "wikidata" in group["sources"]: readiness.append("wikidata-linked")
        if "pldb" in group["sources"]: readiness.append("pldb-listed")
        if len(group["sources"]) == 1: readiness.append("single-source")
        inventory.append({**group, "readiness": readiness, "package_identifiers": identifiers,
                          "homebrew_formulas": formulas, "tools": tools})

    # Wikipedia contributes candidates for discovery only; it never creates inventory rows.
    wiki = json.loads((DATA / "wikipedia.json").read_text(encoding="utf-8"))
    wiki_url_index: dict[str, set[str]] = defaultdict(set)
    for row in inventory:
        for source in row["sources"].values():
            if source.get("wikipedia"):
                wiki_url_index[article_key(source["wikipedia"])].add(row["id"])
            if source.get("enwiki"):
                wiki_url_index[norm(source["enwiki"])].add(row["id"])
    wiki_names: dict[str, set[str]] = defaultdict(set)
    for row in inventory:
        for value in [row["name"], *row["aliases"]]: wiki_names[norm(value)].add(row["id"])
    candidates = []
    for entry in wiki.get("entries", []):
        ids = set(wiki_url_index.get(article_key(entry.get("article")), set()))
        ids |= set(wiki_names.get(norm(entry.get("name", "")), set()))
        candidates.append({"name": entry["name"], "article": entry["article"],
                           "section": entry.get("section", ""), "status": "linked" if len(ids) == 1 else ("ambiguous" if ids else "discovery-only"),
                           "inventory_ids": sorted(ids)})

    counts = {"languages": len(inventory), "pldb_records": len(pldb), "wikidata_items": wikidata_items_count,
        "github_linguist_languages": len(linguist), "with_multiple_identity_sources": sum(len(r["sources"]) > 1 for r in inventory),
        "with_mason_tools": sum(bool(r["tools"]) for r in inventory),
        "with_homebrew_formula": sum(any(f["available"] for f in r["homebrew_formulas"]) for r in inventory),
        "wikipedia_candidates": len(candidates), "wikipedia_linked_candidates": sum(r["status"] == "linked" for r in candidates),
        "wikipedia_only_candidates": sum(r["status"] == "discovery-only" for r in candidates),
        "unresolved_identity_matches": len(unresolved), "unresolved_mason_language_names": unresolved_mason,
        "mason_packages_associated": sum(len(r["tools"]) for r in inventory)}
    for category in ("LSP", "DAP", "Formatter", "Linter", "Runtime", "Compiler"):
        counts[f"mason_{category.lower()}_packages"] = sum(category in p["categories"] for r in inventory for p in r["tools"])
    generated_at = now_utc()
    source_state = {"schema": 1, "generated_at": generated_at, "sources": {
        "pldb": pldb_state, "wikidata": wd_state, "github_linguist": linguist_state,
        "mason_registry": mason_state, "homebrew": brew_state,
        "wikipedia_seed": {"revision": wiki.get("revision"), "retrieved_at": wiki.get("retrieved_at"),
                            "entries": len(wiki.get("entries", [])), "sha256": hashlib.sha256((DATA / "wikipedia.json").read_bytes()).hexdigest()}}}
    inventory_data = {"schema": 2, "generated_at": generated_at, "sources": source_config,
                      "source_state": {key: {k: v for k, v in value.items() if k not in {"sha256", "query_sha256", "revision_digest", "modified_digest"}}
                                       for key, value in source_state["sources"].items()},
                      "counts": counts, "languages": inventory}
    discovery_data = {"schema": 1, "source": source_config["wikipedia_seed"], "revision": wiki.get("revision"),
                      "retrieved_at": wiki.get("retrieved_at"), "entries": candidates}
    unresolved_data = {"schema": 1, "generated_at": generated_at, "count": len(unresolved), "matches": unresolved}
    return inventory_data, discovery_data, unresolved_data, source_state


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    inventory, discovery, unresolved, source_state = build()
    write_json(DATA / "inventory.json", inventory)
    write_json(DATA / "discovery_candidates.json", discovery)
    write_json(DATA / "unresolved_matches.json", unresolved)
    write_json(DATA / "source_state.json", source_state)
    print(json.dumps(inventory["counts"], indent=1))
    print(f"wrote {len(inventory['languages'])} canonical records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
