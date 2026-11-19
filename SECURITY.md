# Security Policy

## Supported version

The latest commit on `main` is supported. There are no tagged releases.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/johnjoners/coding-language-library/security/advisories/new). Do not report security issues in public issues or discussions. Include the affected version, steps to reproduce, and impact. No response-time guarantee is offered.

## Runtime boundary

The MCP server reads committed JSON, serves stdio requests, and does not make network calls, write files, install packages, or launch language servers. `check_tools` calls `PATH` lookup and returns executable names and absolute paths; use it only with a trusted local MCP client.

The refresh workflow runs only from the default branch on a schedule or manual dispatch. It checks public upstream sources, rebuilds snapshots, runs verification, and opens a review pull request. It does not merge or publish data directly to `main`. Its repository token is limited to writing a refresh branch and pull request.
