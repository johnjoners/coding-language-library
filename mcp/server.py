#!/usr/bin/env python3
"""Read-only MCP access to the source-linked language catalogue."""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__:
    from .task_matching import compare_candidates, get_suitability_evidence, recommend_stack
else:
    from task_matching import compare_candidates, get_suitability_evidence, recommend_stack

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROTOCOL = "2024-11-05"


def load_inventory() -> dict[str, Any]:
    return json.loads((DATA / "inventory.json").read_text(encoding="utf-8"))


def load_adapters() -> dict[str, Any]:
    return json.loads((DATA / "adapters.json").read_text(encoding="utf-8"))


def load_suitability_profiles() -> dict[str, Any]:
    return json.loads((DATA / "suitability_profiles.json").read_text(encoding="utf-8"))


def norm(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum() or ch in "+#")


def identifiers(row: dict[str, Any]) -> list[str]:
    values = [row["id"], row["name"], *row.get("aliases", [])]
    for source, details in row.get("sources", {}).items():
        values.append(str(details.get("id", "")))
        if source == "github_linguist" and details.get("language_id") is not None:
            values.append(str(details["language_id"]))
        values.extend(details.get("aliases", []))
    return [str(value) for value in values if value]


def get_language(query: str) -> dict[str, Any]:
    key = norm(query)
    exact = [row for row in load_inventory()["languages"]
             if query == row["id"] or any(norm(value) == key for value in identifiers(row))]
    if not exact:
        raise ValueError(f"'{query}' is not in the source-linked inventory")
    if len(exact) > 1:
        raise ValueError(f"'{query}' matches multiple records: {', '.join(row['id'] for row in exact)}")
    return exact[0]


def flatten(value: Any) -> list[str]:
    if isinstance(value, str): return [value]
    if isinstance(value, dict): return [item for child in value.values() for item in flatten(child)]
    if isinstance(value, list): return [item for child in value for item in flatten(child)]
    return []


def package_summary(row: dict[str, Any]) -> dict[str, Any]:
    categories = Counter(category for tool in row["tools"] for category in tool["categories"])
    return {"id": row["id"], "name": row["name"], "aliases": row["aliases"],
            "sources": sorted(row["sources"]), "readiness": row["readiness"],
            "tool_counts": dict(sorted(categories.items())), "tools": [p["name"] for p in row["tools"]],
            "package_identifiers": row["package_identifiers"],
            "homebrew_formulas": [p["name"] for p in row["homebrew_formulas"]]}


def tool_search_index(args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query: raise ValueError("query is required")
    key = norm(query)
    index = load_inventory()
    matches = [package_summary(row) for row in index["languages"] if any(key in norm(s) for s in flatten(row))]
    offset = max(0, int(args.get("offset", 0)))
    limit = min(100, max(1, int(args.get("limit", 25))))
    return json.dumps({"total": len(matches), "offset": offset, "limit": limit,
        "source_counts": index["counts"], "results": matches[offset:offset + limit]}, ensure_ascii=False, indent=1)


def readiness_match(row: dict[str, Any], category: str) -> bool:
    filters = {"language-server": "language-server-catalogued", "runtime-or-compiler": "runtime-or-compiler-catalogued",
        "development-tools": "development-tools-catalogued", "package-manager": "package-manager-identifiers-recorded",
        "linguist": "github-language-identified", "wikidata": "wikidata-linked", "pldb": "pldb-listed",
        "single-source": "single-source"}
    if category == "all": return True
    if category not in filters: raise ValueError(f"unknown filter '{category}'; use {', '.join([*filters, 'all'])}")
    return filters[category] in row["readiness"]


def tool_list_shelf(args: dict[str, Any]) -> str:
    index = load_inventory()
    category = str(args.get("filter", "all"))
    rows = [package_summary(row) for row in index["languages"] if readiness_match(row, category)]
    offset = max(0, int(args.get("offset", 0)))
    limit = min(100, max(1, int(args.get("limit", 50))))
    return json.dumps({"generated_at": index["generated_at"], "total": len(rows), "offset": offset,
        "limit": limit, "filter": category, "results": rows[offset:offset + limit]}, ensure_ascii=False, indent=1)


def tool_get_language(args: dict[str, Any]) -> str:
    row = get_language(str(args.get("name", "")))
    lsp_tools = [tool for tool in row["tools"] if "LSP" in tool["categories"]]
    adapter = load_adapters()["adapters"][0]
    verification = adapter.get("verification", {})
    candidates = []
    for tool in lsp_tools:
        binaries = tool.get("executables", {})
        executable = (verification.get("executable") if tool["name"] == verification.get("package")
                     and verification.get("executable") in binaries else next(iter(binaries), None))
        if not executable: continue
        tested = tool["name"] == verification.get("package") and executable == verification.get("executable")
        candidates.append({"status": "tested-with-this-pairing" if tested else "candidate-not-yet-tested",
            "adapter": adapter["url"], "adapter_version": adapter["version"], "adapter_install": adapter["install"],
            "language_server_package": tool["name"], "language_server_install": tool["install"],
            "executable": executable, "mcp_command": adapter["name"],
            "mcp_args": ["--workspace", "<absolute project path>", "--lsp", executable,
                *(["--", *verification.get("arguments", [])] if tested else [])],
            "source_id": tool["source_id"], "tested_mcp_tools": verification.get("mcp_tools", []) if tested else []})
    result = dict(row)
    result["mcp_candidates"] = candidates
    result["use_note"] = "Catalogue evidence does not prove installation or compatibility."
    return json.dumps(result, ensure_ascii=False, indent=1)


def tool_check_tools(args: dict[str, Any]) -> str:
    row = get_language(str(args.get("name", "")))
    candidates: set[str] = set()
    for package in row["tools"]:
        if set(package["categories"]) & {"LSP", "Runtime", "Compiler"}:
            candidates.update(package.get("executables", {}))
    for formula in row["homebrew_formulas"]:
        if formula["available"]: candidates.update(formula.get("executables", []))
    limit = min(100, max(1, int(args.get("limit", 40))))
    checked = [{"executable": exe, "found_on_path": shutil.which(exe) is not None,
                "path": shutil.which(exe)} for exe in sorted(candidates)[:limit]]
    return json.dumps({"id": row["id"], "name": row["name"], "checked": len(checked), "limit": limit,
        "note": "PATH check only; absolute paths are returned and isolated environments may not be visible.",
        "executables": checked}, ensure_ascii=False, indent=1)


def tool_recommend_stack(args: dict[str, Any]) -> str:
    result = recommend_stack(args.get("task_profile", {}), load_suitability_profiles(), args.get("limit", 5))
    return json.dumps({"recommendations": result}, ensure_ascii=False, indent=1)


def tool_compare_candidates(args: dict[str, Any]) -> str:
    result = compare_candidates(args.get("candidate_ids", []), args.get("task_profile", {}), load_suitability_profiles())
    return json.dumps({"comparisons": result}, ensure_ascii=False, indent=1)


def tool_get_suitability_evidence(args: dict[str, Any]) -> str:
    result = get_suitability_evidence(args.get("language_id", ""), args.get("capability"), load_suitability_profiles())
    return json.dumps(result, ensure_ascii=False, indent=1)


TASK_PROFILE_SCHEMA = json.loads((DATA / "task_profile.schema.json").read_text(encoding="utf-8"))


TOOLS = {
 "search_index": (tool_search_index, {"description": "Search canonical identities, aliases, extensions, source IDs, package IDs, and linked tools.",
  "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 25}}, "required": ["query"]}}),
 "list_shelf": (tool_list_shelf, {"description": "Page through the source union or filter by source coverage and recorded tooling.",
  "inputSchema": {"type": "object", "properties": {"filter": {"type": "string", "enum": ["all", "language-server", "runtime-or-compiler", "development-tools", "package-manager", "linguist", "wikidata", "pldb", "single-source"], "default": "all"}, "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 50}}}}),
 "get_language": (tool_get_language, {"description": "Get a source-linked record and its tool and adapter evidence.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}),
 "check_tools": (tool_check_tools, {"description": "Check recorded language-tool and Homebrew executable names against PATH.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "limit": {"type": "integer", "default": 40}}, "required": ["name"]}}),
 "recommend_stack": (tool_recommend_stack, {"description": "Rank recorded language stacks for a structured task profile. Unknown constraints remain visible; the tool installs nothing.", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object", "properties": {"task_profile": TASK_PROFILE_SCHEMA, "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20}}, "required": ["task_profile"]}}),
 "compare_candidates": (tool_compare_candidates, {"description": "Compare stack IDs against one structured task profile, including failed and unknown constraints.", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object", "properties": {"candidate_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}, "task_profile": TASK_PROFILE_SCHEMA}, "required": ["candidate_ids", "task_profile"]}}),
 "get_suitability_evidence": (tool_get_suitability_evidence, {"description": "Return documented suitability claims and evidence for a canonical language ID.", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object", "properties": {"language_id": {"type": "string"}, "capability": {"type": "string"}}, "required": ["language_id"]}}),
}


def respond(msg_id: Any, result: Any = None, error: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
    out["error" if error is not None else "result"] = error if error is not None else result
    return out


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method, msg_id = msg.get("method"), msg.get("id")
    if method == "notifications/initialized" or msg_id is None: return None
    if method == "initialize":
        return respond(msg_id, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": {"name": "coding-language-library", "version": "0.3.0"}})
    if method == "ping": return respond(msg_id, {})
    if method == "tools/list": return respond(msg_id, {"tools": [{"name": n, **spec} for n, (_, spec) in TOOLS.items()]})
    if method == "tools/call":
        params = msg.get("params", {}); name = params.get("name")
        if name not in TOOLS: return respond(msg_id, error={"code": -32602, "message": f"unknown tool {name}"})
        try:
            text = TOOLS[name][0](params.get("arguments", {}) or {})
            return respond(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return respond(msg_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
    return respond(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    for line in sys.stdin:
        if not line.strip(): continue
        try: msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(respond(None, error={"code": -32700, "message": "parse error"})) + "\n")
            sys.stdout.flush(); continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n"); sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
