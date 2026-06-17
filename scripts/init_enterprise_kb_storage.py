#!/usr/bin/env python3
"""Initialize enterprise SpecRAG storage.

Requires:
  KB_POSTGRES_DSN=postgresql://...
  optional KB_QDRANT_URL=http://localhost:6333
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from services.kb.storage.postgres_store import PostgresUnitRepository


def main() -> int:
    repo = PostgresUnitRepository()
    repo.ensure_schema()
    print(json.dumps({
        "status": "ok",
        "postgres": "schema_ready",
        "dsn_configured": bool(os.environ.get("KB_POSTGRES_DSN")),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
