#!/usr/bin/env python3
"""Harvest the programming-language index from Wikipedia into data/wikipedia.json.

Reads the wikitext of "List of programming languages" through the MediaWiki API, keeps
the bulleted entries under the A-Z sections, and writes one record per entry. Stdlib only.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAGE = "List of programming languages"
API = "https://en.wikipedia.org/w/api.php"
UA = "coding-language-library/0.3 (https://github.com/johnjoners/coding-language-library)"
OUT = Path(__file__).resolve().parent.parent / "data" / "wikipedia.json"

LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
COMMENT = re.compile(r"<!--.*?-->", re.S)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
REF = re.compile(r"<ref[^>]*?(?:/>|>.*?</ref>)", re.S)


def fetch_wikitext() -> tuple[str, int]:
    query = urllib.parse.urlencode({
        "action": "parse", "page": PAGE, "prop": "wikitext|revid",
        "format": "json", "formatversion": 2,
    })
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)["parse"]
    return data["wikitext"], data["revid"]


def clean(text: str) -> str:
    text = COMMENT.sub("", text)
    text = REF.sub("", text)
    text = TEMPLATE.sub("", text)
    text = LINK.sub(lambda m: m.group(2) or m.group(1), text)
    text = text.replace("''", "")
    return re.sub(r"\s+", " ", text).strip()


def parse(wikitext: str) -> list[dict[str, str]]:
    section = None
    entries = []
    for raw in wikitext.split("\n"):
        heading = re.match(r"^==\s*(.+?)\s*==\s*$", raw)
        if heading:
            section = heading.group(1)
            continue
        if section is None or section.lower() in {"see also", "references", "external links", "notes"}:
            continue
        if not raw.lstrip().startswith("*") or raw.lstrip().startswith("*["):
            continue
        body = COMMENT.sub("", raw).strip().lstrip("*").strip()
        first = LINK.search(body)
        if not body or first is None:
            continue
        article = first.group(1).strip()
        if article.startswith(("Wikibooks", "Wikipedia:")):
            continue
        display = clean(first.group(2) or first.group(1))
        note = clean(body[first.end():].lstrip(" –-").strip())
        entries.append({
            "name": display,
            "article": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(article.replace(' ', '_'))}",
            "section": section,
            "note": note,
        })
    return entries


def main() -> int:
    wikitext, revid = fetch_wikitext()
    entries = parse(wikitext)
    seen, unique = set(), []
    for e in entries:
        key = (e["name"].lower(), e["article"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    if len(unique) < 500:
        print(f"refusing to write: only {len(unique)} entries parsed", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": f"https://en.wikipedia.org/wiki/{PAGE.replace(' ', '_')}",
        "revision": revid,
        "license": "CC BY-SA 4.0 (Wikipedia text; attribution to the linked articles)",
        "count": len(unique),
        "entries": unique,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(unique)} entries (revision {revid}) to {OUT.relative_to(OUT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
