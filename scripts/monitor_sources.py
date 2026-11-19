#!/usr/bin/env python3
"""Check upstream revisions and validators without rewriting snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.build_inventory import fetch_wikidata_ids

DATA = ROOT / "data"
UA = "coding-language-library/0.3 (https://github.com/johnjoners/coding-language-library)"


def check_http(url: str, saved: dict) -> dict:
    headers = {"User-Agent": UA}
    if saved.get("etag"):
        headers["If-None-Match"] = saved["etag"]
    if saved.get("last_modified"):
        headers["If-Modified-Since"] = saved["last_modified"]
    request = Request(url, headers=headers, method="HEAD")
    try:
        with urlopen(request, timeout=60) as response:
            current = {key.lower(): value for key, value in response.headers.items()}
            etag = current.get("etag")
            modified = current.get("last-modified")
            if not etag and not modified:
                raise RuntimeError(f"no validator returned by {url}")
            validator_changed = ((saved.get("etag") and etag != saved["etag"])
                                 or (saved.get("last_modified") and modified != saved["last_modified"])
                                 or (not saved.get("etag") and not saved.get("last_modified")))
            digest = saved.get("sha256")
            content_changed = bool(validator_changed)
            if validator_changed and saved.get("sha256"):
                get_request = Request(url, headers={"User-Agent": UA})
                with urlopen(get_request, timeout=120) as body_response:
                    digest = hashlib.sha256(body_response.read()).hexdigest()
                content_changed = digest != saved["sha256"]
            return {"status": "changed" if content_changed else "unchanged", "http_status": response.status,
                    "etag": etag, "last_modified": modified, "sha256": digest,
                    "validator_changed": bool(validator_changed), "content_changed": content_changed}
    except HTTPError as exc:
        if exc.code == 304:
            return {"status": "unchanged", "http_status": 304}
        raise


def check_wikipedia(saved: dict) -> dict:
    params = urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "ids|timestamp",
        "titles": "List of programming languages", "format": "json", "formatversion": 2})
    request = Request(f"https://en.wikipedia.org/w/api.php?{params}", headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(request, timeout=60) as response:
        data = json.load(response)
    revision = data["query"]["pages"][0]["revisions"][0]
    changed = revision["revid"] != saved.get("revision")
    return {"status": "changed" if changed else "unchanged", "revision": revision["revid"],
            "timestamp": revision["timestamp"]}


def check_wikidata(saved: dict[str, Any]) -> dict[str, Any]:
    ids, qid_digest, modified_digest = fetch_wikidata_ids()
    changed = (qid_digest != saved.get("query_sha256") or
               modified_digest != saved.get("modified_digest"))
    return {"status": "changed" if changed else "unchanged", "qid_count": len(ids),
            "qid_digest": qid_digest, "modified_digest": modified_digest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", help="append changed/sources outputs for a workflow")
    args = parser.parse_args()
    state_path = DATA / "source_state.json"
    if not state_path.exists():
        print("data/source_state.json is missing; run scripts/build_inventory.py first", file=sys.stderr)
        return 1
    state = json.loads(state_path.read_text(encoding="utf-8"))["sources"]
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]
    results: dict[str, dict] = {}
    errors = []
    for key in ("pldb", "github_linguist", "mason_registry", "homebrew"):
        try:
            results[key] = check_http(sources[key]["monitor"]["url"], state[key])
        except Exception as exc:
            results[key] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            errors.append(key)
    for key, check in (("wikipedia_seed", check_wikipedia), ("wikidata", check_wikidata)):
        try:
            results[key] = check(state[key])
        except Exception as exc:
            results[key] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            errors.append(key)
    changed = [key for key, value in results.items() if value["status"] in {"changed", "changed-or-validator-rotated"}]
    report = {"checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "changed": changed, "sources": results, "errors": errors}
    print(json.dumps(report, indent=1))
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as output:
            output.write(f"changed={'true' if changed else 'false'}\n")
            output.write(f"sources={','.join(changed)}\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
