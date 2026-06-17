#!/usr/bin/env python3
"""Run the SpecRAG MCP server."""

from __future__ import annotations

import argparse
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="SpecRAG MCP server")
    parser.add_argument("--db", default=os.environ.get("PRD_UNIT_KB_DB", "data/specrag.db"))
    parser.add_argument("--model", default=os.environ.get("PRD_UNIT_EMBEDDING_MODEL", "runtime/models/qwen3-embedding-0.6b"))
    parser.add_argument("--embedding-provider", choices=["sentence", "hashing"], default=os.environ.get("PRD_UNIT_EMBEDDING_PROVIDER", "sentence"))
    parser.add_argument("--judge", choices=["rule", "llm"], default=os.environ.get("PRD_UNIT_JUDGE_MODE", "rule"))
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    args = parser.parse_args()

    os.environ["PRD_UNIT_KB_DB"] = args.db
    os.environ["PRD_UNIT_EMBEDDING_MODEL"] = args.model
    os.environ["PRD_UNIT_EMBEDDING_PROVIDER"] = args.embedding_provider
    os.environ["PRD_UNIT_JUDGE_MODE"] = args.judge

    from services.kb.mcp_server import create_mcp_server

    server = create_mcp_server()
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
