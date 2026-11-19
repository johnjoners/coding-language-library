# Data terms

`LICENSE` covers the project code and authored documentation. It does not grant
rights to generated catalogue data or third-party material.

`data/inventory.json` is an attributed union of source records. Each record names
its upstream sources and the exact join methods used. No new blanket license is
applied to those source-derived fields. Follow the terms named in `data/sources.json`
and the notices below when reusing them.

| Data | Source and terms |
| --- | --- |
| `data/wikipedia.json`, `data/discovery_candidates.json` | The list text is generally available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) and [GFDL](https://www.gnu.org/licenses/fdl-1.3.en.html), except where a page history or notice states otherwise. The harvest is a discovery seed, not the authority for inventory membership. The committed snapshot records the page revision. Attribute the page and revision when reusing its material. |
| Wikidata fields in `data/inventory.json` | Wikidata data is released under CC0 1.0. |
| PLDB fields in `data/inventory.json` | PLDB states in its upstream README that its data is dedicated to the public domain. Attribution is included here although the README says it is not required. |
| GitHub Linguist fields in `data/inventory.json` | MIT. The upstream license is retained in `licenses/GitHub-Linguist-MIT.txt`. |
| Mason package fields in `data/inventory.json` | Apache-2.0. The upstream license is retained in `licenses/Apache-2.0.txt`. Package software licenses listed in each record are separate from the registry license. |
| Homebrew formula fields in `data/inventory.json` | Formula metadata comes from Homebrew Core, whose repository is BSD-2-Clause. Formula software licenses are separate values. The upstream license is retained in `licenses/Homebrew-BSD-2-Clause.txt`. |

Sources and terms can change. Check `data/sources.json`, `data/source_state.json`,
and `THIRD_PARTY_NOTICES.md` before redistribution. This notice does not replace
the upstream licenses.
