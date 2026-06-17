"""PostgreSQL fact repository for SpecRAG."""

from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any, Dict, List, Optional


class PostgresUnitRepository:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.environ.get("KB_POSTGRES_DSN") or ""
        if not self.dsn:
            raise RuntimeError("KB_POSTGRES_DSN is required when KB_STORAGE_MODE=enterprise")

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
            conn.commit()

    def get_document_hash(self, doc_id: str) -> Optional[str]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT content_hash FROM kb_documents WHERE doc_id = %s", (doc_id,))
                row = cur.fetchone()
        return row[0] if row else None

    def delete_document(self, doc_id: str) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kb_documents WHERE doc_id = %s", (doc_id,))
            conn.commit()

    def upsert_document_with_units(self, data: Dict[str, Any], source_json_path: str) -> Dict[str, Any]:
        self.ensure_schema()
        document = data.get("document") or {}
        units = data.get("units") or []
        doc_id = str(document.get("doc_id") or "")
        if not doc_id:
            raise ValueError("document.doc_id is required")
        now = datetime.utcnow()
        content_hash = _content_hash(data)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kb_documents (
                        doc_id, tenant_id, title, product_id, product_line, module,
                        version, version_time, change_type, source_type, source_uri,
                        summary, schema_version, content_hash, status, created_at, updated_at
                    ) VALUES (
                        %(doc_id)s, %(tenant_id)s, %(title)s, %(product_id)s, %(product_line)s,
                        %(module)s, %(version)s, %(version_time)s, %(change_type)s,
                        %(source_type)s, %(source_uri)s, %(summary)s, %(schema_version)s,
                        %(content_hash)s, 'active', %(now)s, %(now)s
                    )
                    ON CONFLICT (doc_id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        title = EXCLUDED.title,
                        product_id = EXCLUDED.product_id,
                        product_line = EXCLUDED.product_line,
                        module = EXCLUDED.module,
                        version = EXCLUDED.version,
                        version_time = EXCLUDED.version_time,
                        change_type = EXCLUDED.change_type,
                        source_type = EXCLUDED.source_type,
                        source_uri = EXCLUDED.source_uri,
                        summary = EXCLUDED.summary,
                        schema_version = EXCLUDED.schema_version,
                        content_hash = EXCLUDED.content_hash,
                        status = 'active',
                        updated_at = EXCLUDED.updated_at
                    """,
                    {
                        "doc_id": doc_id,
                        "tenant_id": str(document.get("tenant_id") or "default"),
                        "title": str(document.get("title") or doc_id),
                        "product_id": str(document.get("product_id") or document.get("product") or "unknown"),
                        "product_line": _optional_str(document.get("product_line") or document.get("product")),
                        "module": _optional_str(document.get("module")),
                        "version": str(document.get("version") or "unknown"),
                        "version_time": _optional_datetime(document.get("version_time")),
                        "change_type": _optional_str(document.get("change_type")),
                        "source_type": str(document.get("source_type") or "cleaned_json"),
                        "source_uri": str(source_json_path or document.get("source_uri") or ""),
                        "summary": _optional_str(document.get("summary")),
                        "schema_version": str(data.get("schema_version") or ""),
                        "content_hash": content_hash,
                        "now": now,
                    },
                )
                cur.execute("DELETE FROM kb_requirement_units WHERE doc_id = %s", (doc_id,))
                for unit in units:
                    unit_id = str(unit.get("unit_id") or "")
                    if not unit_id:
                        continue
                    unit_pk = f"{doc_id}:{unit_id}"
                    cur.execute(
                        """
                        INSERT INTO kb_requirement_units (
                            unit_pk, tenant_id, doc_id, unit_id, title, unit_type, scope,
                            change_type, content, rules, source, retrieval_meta, keywords,
                            unit_json, content_hash, effective_from, effective_to, status,
                            created_at, updated_at
                        ) VALUES (
                            %(unit_pk)s, %(tenant_id)s, %(doc_id)s, %(unit_id)s,
                            %(title)s, %(unit_type)s, %(scope)s, %(change_type)s,
                            %(content)s, %(rules)s, %(source)s, %(retrieval_meta)s,
                            %(keywords)s, %(unit_json)s, %(content_hash)s,
                            %(effective_from)s, %(effective_to)s, 'active', %(now)s, %(now)s
                        )
                        """,
                        {
                            "unit_pk": unit_pk,
                            "tenant_id": str(document.get("tenant_id") or "default"),
                            "doc_id": doc_id,
                            "unit_id": unit_id,
                            "title": _optional_str(unit.get("title")),
                            "unit_type": _optional_str(unit.get("unit_type")),
                            "scope": _optional_str(unit.get("scope")),
                            "change_type": _optional_str(unit.get("change_type") or document.get("change_type")),
                            "content": _optional_str(unit.get("content")),
                            "rules": _json(unit.get("rules") or []),
                            "source": _json(unit.get("source") or {}),
                            "retrieval_meta": _json(unit.get("retrieval_meta") or {}),
                            "keywords": _json(unit.get("keywords") or []),
                            "unit_json": _json(unit),
                            "content_hash": _content_hash(unit),
                            "effective_from": _optional_datetime(unit.get("effective_from")),
                            "effective_to": _optional_datetime(unit.get("effective_to")),
                            "now": now,
                        },
                    )
            conn.commit()
        return {"doc_id": doc_id, "unit_count": len(units), "content_hash": content_hash}

    def replace_embedding_records(self, doc_id: str, records: List[Dict[str, Any]]) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kb_embedding_records WHERE doc_id = %s", (doc_id,))
                for record in records:
                    self._insert_embedding_record(cur, record)
            conn.commit()

    def add_embedding_record(self, record: Dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._insert_embedding_record(cur, record)
            conn.commit()

    def add_feedback_hint(self, doc_id: str, unit_id: str, query_text: str) -> Dict[str, Any]:
        import hashlib

        self.ensure_schema()
        unit_pk = f"{doc_id}:{unit_id}"
        query = str(query_text or "").strip()
        if not query:
            raise ValueError("query_text is required")
        feedback_id = hashlib.sha256(f"{unit_pk}:{query}".encode("utf-8")).hexdigest()[:32]
        now = datetime.utcnow()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tenant_id FROM kb_requirement_units WHERE unit_pk = %s", (unit_pk,))
                row = cur.fetchone()
                if row is None:
                    raise ValueError(f"Unit not found: {unit_pk}")
                cur.execute(
                    """
                    INSERT INTO kb_feedback_hints (
                        feedback_id, tenant_id, unit_pk, doc_id, unit_id, query_text,
                        source, status, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'user', 'active', %s, %s)
                    ON CONFLICT (feedback_id) DO UPDATE SET
                        query_text = EXCLUDED.query_text,
                        status = 'active',
                        updated_at = EXCLUDED.updated_at
                    """,
                    (feedback_id, row[0], unit_pk, doc_id, unit_id, query, now, now),
                )
            conn.commit()
        return {"feedback_id": feedback_id, "unit_pk": unit_pk}

    def list_feedback_hints(self, doc_id: str, unit_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure_schema()
        sql = """
            SELECT feedback_id, unit_pk, doc_id, unit_id, query_text, source, status,
                   created_at, updated_at
            FROM kb_feedback_hints
            WHERE doc_id = %s
        """
        params: List[Any] = [doc_id]
        if unit_id:
            sql += " AND unit_id = %s"
            params.append(unit_id)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                cols = [desc.name for desc in cur.description]
        return [_row_dict(cols, row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM kb_documents")
                documents = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM kb_requirement_units")
                units = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM kb_embedding_records")
                vectors = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM kb_feedback_hints")
                feedback_hints = cur.fetchone()[0]
        return {
            "documents": documents,
            "units": units,
            "vectors": vectors,
            "feedback_hints": feedback_hints,
        }

    def list_documents(self) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.doc_id, d.title, d.product_id AS product, d.version, d.module,
                           d.summary, d.source_uri AS source_json_path, d.updated_at,
                           COUNT(DISTINCT u.unit_pk) AS unit_count,
                           COUNT(DISTINCT e.embedding_id) AS vector_count
                    FROM kb_documents d
                    LEFT JOIN kb_requirement_units u ON u.doc_id = d.doc_id
                    LEFT JOIN kb_embedding_records e ON e.doc_id = d.doc_id
                    GROUP BY d.doc_id
                    ORDER BY d.updated_at DESC
                    """
                )
                rows = cur.fetchall()
                cols = [desc.name for desc in cur.description]
        return [_row_dict(cols, row) for row in rows]

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.doc_id, d.title, d.product_id AS product, d.version, d.module,
                           d.summary, d.schema_version, d.source_uri AS source_json_path,
                           d.content_hash, d.created_at, d.updated_at,
                           COUNT(DISTINCT u.unit_pk) AS unit_count,
                           COUNT(DISTINCT e.embedding_id) AS vector_count
                    FROM kb_documents d
                    LEFT JOIN kb_requirement_units u ON u.doc_id = d.doc_id
                    LEFT JOIN kb_embedding_records e ON e.doc_id = d.doc_id
                    WHERE d.doc_id = %s
                    GROUP BY d.doc_id
                    """,
                    (doc_id,),
                )
                row = cur.fetchone()
                cols = [desc.name for desc in cur.description] if cur.description else []
        if row is None:
            raise ValueError(f"Document not found: {doc_id}")
        return _row_dict(cols, row)

    def get_units(self, doc_id: str) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT unit_json
                    FROM kb_requirement_units
                    WHERE doc_id = %s
                    ORDER BY unit_id
                    """,
                    (doc_id,),
                )
                rows = cur.fetchall()
        return [_loads(row[0]) for row in rows]

    def get_unit(self, doc_id: str, unit_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        unit_pk = f"{doc_id}:{unit_id}"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT unit_json FROM kb_requirement_units WHERE unit_pk = %s", (unit_pk,))
                row = cur.fetchone()
        if row is None:
            raise ValueError(f"Unit not found: {unit_pk}")
        return _loads(row[0])

    def list_units_by_pks(self, unit_pks: List[str]) -> List[Dict[str, Any]]:
        self.ensure_schema()
        if not unit_pks:
            return []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.unit_pk, u.doc_id, u.unit_id, u.unit_json,
                           d.title AS doc_title, d.product_id AS product,
                           d.version, d.module
                    FROM kb_requirement_units u
                    JOIN kb_documents d ON d.doc_id = u.doc_id
                    WHERE u.unit_pk = ANY(%s)
                    """,
                    (unit_pks,),
                )
                rows = cur.fetchall()
                cols = [desc.name for desc in cur.description]
        by_pk = {_row_dict(cols, row)["unit_pk"]: _row_dict(cols, row) for row in rows}
        return [by_pk[unit_pk] for unit_pk in unit_pks if unit_pk in by_pk]

    def _insert_embedding_record(self, cur, record: Dict[str, Any]) -> None:
        cur.execute(
            """
            INSERT INTO kb_embedding_records (
                embedding_id, tenant_id, unit_pk, doc_id, unit_id, vector_type,
                vector_index, embedding_model, embedding_version, qdrant_collection,
                qdrant_point_id, embedding_text_hash, content_hash, status,
                created_at, updated_at
            ) VALUES (
                %(embedding_id)s, %(tenant_id)s, %(unit_pk)s, %(doc_id)s, %(unit_id)s,
                %(vector_type)s, %(vector_index)s, %(embedding_model)s,
                %(embedding_version)s, %(qdrant_collection)s, %(qdrant_point_id)s,
                %(embedding_text_hash)s, %(content_hash)s, %(status)s, %(now)s, %(now)s
            )
            ON CONFLICT (embedding_id) DO UPDATE SET
                qdrant_point_id = EXCLUDED.qdrant_point_id,
                embedding_text_hash = EXCLUDED.embedding_text_hash,
                content_hash = EXCLUDED.content_hash,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            {**record, "now": datetime.utcnow()},
        )

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required for KB_STORAGE_MODE=enterprise") from exc
        return psycopg.connect(self.dsn)


def _json(value: Any) -> str:
    try:
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    except Exception:
        return json.dumps(value, ensure_ascii=False)


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _optional_str(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _optional_datetime(value: Any):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_dict(cols: List[str], row) -> Dict[str, Any]:
    return {col: _loads(value) for col, value in zip(cols, row)}


def _content_hash(payload: Any) -> str:
    import hashlib

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb_documents (
  doc_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  title TEXT NOT NULL,
  product_id TEXT NOT NULL DEFAULT 'unknown',
  product_line TEXT,
  module TEXT,
  version TEXT NOT NULL DEFAULT 'unknown',
  version_time TIMESTAMPTZ,
  change_type TEXT,
  source_type TEXT NOT NULL,
  source_uri TEXT,
  summary TEXT,
  schema_version TEXT,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_product_version
  ON kb_documents (tenant_id, product_id, version, status);

CREATE INDEX IF NOT EXISTS idx_kb_documents_module
  ON kb_documents (tenant_id, module, status);

CREATE TABLE IF NOT EXISTS kb_requirement_units (
  unit_pk TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  doc_id TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
  unit_id TEXT NOT NULL,
  title TEXT,
  unit_type TEXT,
  scope TEXT,
  change_type TEXT,
  content TEXT,
  rules JSONB NOT NULL DEFAULT '[]'::jsonb,
  source JSONB NOT NULL DEFAULT '{}'::jsonb,
  retrieval_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  unit_json JSONB NOT NULL,
  content_hash TEXT NOT NULL,
  effective_from TIMESTAMPTZ,
  effective_to TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (doc_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_units_doc
  ON kb_requirement_units (doc_id);

CREATE INDEX IF NOT EXISTS idx_kb_units_filter
  ON kb_requirement_units (tenant_id, status, unit_type);

CREATE INDEX IF NOT EXISTS idx_kb_units_retrieval_meta_gin
  ON kb_requirement_units USING GIN (retrieval_meta);

CREATE TABLE IF NOT EXISTS kb_embedding_records (
  embedding_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  unit_pk TEXT NOT NULL REFERENCES kb_requirement_units(unit_pk) ON DELETE CASCADE,
  doc_id TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  vector_type TEXT NOT NULL,
  vector_index INTEGER NOT NULL DEFAULT 1,
  embedding_model TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  qdrant_collection TEXT NOT NULL,
  qdrant_point_id TEXT NOT NULL,
  embedding_text_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (qdrant_collection, qdrant_point_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_embedding_records_unit
  ON kb_embedding_records (unit_pk);

CREATE INDEX IF NOT EXISTS idx_kb_embedding_records_model
  ON kb_embedding_records (embedding_model, embedding_version, vector_type, status);

CREATE TABLE IF NOT EXISTS kb_feedback_hints (
  feedback_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  unit_pk TEXT NOT NULL REFERENCES kb_requirement_units(unit_pk) ON DELETE CASCADE,
  doc_id TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  query_text TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_feedback_hints_unit
  ON kb_feedback_hints (unit_pk, status);

CREATE TABLE IF NOT EXISTS kb_import_jobs (
  job_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  doc_id TEXT,
  source_type TEXT NOT NULL,
  source_uri TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  stage TEXT,
  progress INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_kb_import_jobs_status
  ON kb_import_jobs (tenant_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS kb_retrieval_audits (
  audit_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  question TEXT NOT NULL,
  product_id TEXT,
  module TEXT,
  version TEXT,
  answerable BOOLEAN,
  answer TEXT,
  reason TEXT,
  sources JSONB NOT NULL DEFAULT '[]'::jsonb,
  tool_trace JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_call_trace JSONB NOT NULL DEFAULT '[]'::jsonb,
  usage_stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  duration_seconds NUMERIC,
  status TEXT NOT NULL DEFAULT 'success',
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_retrieval_audits_created
  ON kb_retrieval_audits (tenant_id, created_at DESC);
"""
