# Architecture

[Interactive diagram](architecture/coding-language-library.architecture.html) · [Editable diagram source](architecture/coding-language-library.architecture.json)

![Coding language catalogue architecture](architecture/coding-language-library.architecture.png)

`harvest_wikipedia.py` records the MediaWiki list as a discovery seed only.
`build_inventory.py` joins PLDB and Wikidata identity records with GitHub Linguist,
Mason, and Homebrew metadata; Wikipedia entries do not determine inventory membership.
`verify_inventory.py` checks the generated snapshot. The stdio MCP server reads
the committed files. It does not install tools or launch language servers.

A catalogue match is not a compatibility check. Python with Pyright is the only
adapter pairing marked tested.
