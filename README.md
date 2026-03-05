# ICICLE AI Component MCP

ICICLE AI Component MCP lets developers use AI-powered IDEs to explore ICICLE components and then
implement, experiment, and iterate directly from chat inside the IDE. It exposes
tools for listing, searching, and retrieving component metadata over MCP.

Tags: Software

## Acknowledgements

*National Science Foundation (NSF) funded AI institute for Intelligent Cyberinfrastructure with Computational Learning in the Environment (ICICLE) (OAC 2112606)*

## Issue reporting

[TODO: <GITHUB_ISSUES / EMAIL / OTHER>]

---

# Tutorials

## Get started

Prerequisites:
- Python 3.10+
- Internet access to fetch the catalog YAML

Steps:
1) Create and activate a virtual environment.
```bash
python3 -m venv .venv
source .venv/bin/activate
```
2) Install dependencies.
```bash
pip install -r requirements.txt
```
3) Run the MCP server.
```bash
python server.py
```
4) Connect your MCP client to the stdio server (Cursor MCP settings).

Expected results:
- MCP tools like `list_components` and `search_components` return catalog data.

## Connect from Cursor or Claude Desktop

Prerequisites:
- The server is installed and runnable with `python server.py`.

Steps (Cursor):
1) Create a local MCP config file at `.cursor/mcp.json`.
```json
{
  "mcpServers": {
    "icicle-catalog": {
      "command": "./.venv/bin/python",
      "args": ["./server.py"]
    }
  }
}
```
2) In Cursor, open MCP settings and enable the `icicle-catalog` server.
3) In chat, ask a question like: "List components in release 2025-07."

Steps (Claude Desktop):
1) Create a local MCP config file at `.claude/mcp.json`.
```json
{
  "mcpServers": {
    "icicle-catalog": {
      "command": "./.venv/bin/python",
      "args": ["./server.py"]
    }
  }
}
```
2) Enable the server in Claude Desktop MCP settings.
3) Ask: "Search components for Foundation AI."

Expected results:
- The IDE can call tools like `list_components` and `search_components` directly from chat.

Example chat request and response:
```
User: Show me ICICLE components related to Foundation AI.
Assistant: I found 7 components. Here are the top 3: [component list...]
```

---

# How-To Guides

## Search by keyword

Problem:
- Find components matching a query string.

Steps:
1) Ask the IDE chat to search the catalog.

Example:
```
User: Find ICICLE components related to Foundation AI.
Assistant: I found 7 components. Here are the top 3: [component list...]
```
JSON tool call (advanced):
```json
{"tool": "search_components", "args": {"query": "Foundation AI"}}
```

Tips:
- Use broader terms to increase recall.

Troubleshooting:
- If results are empty, verify network access and catalog URL.

## Filter by release

Problem:
- List components for a target release.

Steps:
1) Ask the IDE chat to list components for a release.

Example:
```
User: List all ICICLE components in release 2025-07.
Assistant: I found 42 components in 2025-07. Here are the first 10: [component list...]
```
JSON tool call (advanced):
```json
{"tool": "list_components", "args": {"target_release": "2025-07"}}
```

Tips:
- Combine `primary_thrust` and `public_access` for narrower results.

Troubleshooting:
- If the request times out, retry or increase `CATALOG_TIMEOUT`.

---

# Explanation

## Overview

Core concepts:
- The server fetches a YAML catalog over HTTPS and exposes MCP tools and resources.
- Tools return compact summaries, while resources expose full component records.

Architecture:
- `server.py` defines the FastMCP server and tool handlers.
- An HTTP session handles retries and timeouts for the catalog fetch.
- Transport is stdio; messages are JSON-RPC 2.0 between the client and server.

Design decisions:
- stdio transport keeps integration simple for IDE-based MCP clients.
- Compact list/search responses reduce payload size and latency.

Conceptual flow:
```
[MCP Client] <-> stdio/JSON-RPC 2.0 <-> [FastMCP Server] -> HTTPS -> [Catalog YAML]
```
