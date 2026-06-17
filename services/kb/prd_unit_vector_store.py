"""Knowledge-unit vector store for SpecRAG question answering."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.kb.embedding_provider import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    cosine_similarity,
)
from services.kb.prd_answerability_gate import PRDAnswerabilityGate, LLMEvidenceSynthesizerGate


class PRDUnitVectorStore:
    def __init__(
        self,
        db_path: str = "data/specrag.db",
        embedding_provider: Optional[EmbeddingProvider] = None,
        answerability_gate: Optional[PRDAnswerabilityGate] = None,
    ):
        self.db_path = db_path
        self.embedding_provider = embedding_provider or SentenceTransformerEmbeddingProvider()
        self.answerability_gate = answerability_gate or PRDAnswerabilityGate()
        self.answer_synthesizer = LLMEvidenceSynthesizerGate()

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS kb_prd_unit_documents (
              doc_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              product TEXT,
              version TEXT,
              module TEXT,
              summary TEXT,
              schema_version TEXT,
              source_json_path TEXT,
              content_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_prd_units (
              unit_pk TEXT PRIMARY KEY,
              doc_id TEXT NOT NULL,
              unit_id TEXT NOT NULL,
              title TEXT,
              unit_type TEXT,
              scope TEXT,
              content TEXT,
              rules TEXT,
              source TEXT,
              retrieval_meta TEXT,
              keywords TEXT,
              unit_json TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_prd_unit_vectors (
              vector_id TEXT PRIMARY KEY,
              unit_pk TEXT NOT NULL,
              doc_id TEXT NOT NULL,
              unit_id TEXT NOT NULL,
              vector_type TEXT NOT NULL,
              vector_index INTEGER NOT NULL DEFAULT 0,
              embedding_model TEXT NOT NULL,
              embedding_version TEXT NOT NULL,
              embedding_text TEXT NOT NULL,
              embedding TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_prd_unit_feedback_hints (
              feedback_id TEXT PRIMARY KEY,
              unit_pk TEXT NOT NULL,
              doc_id TEXT NOT NULL,
              unit_id TEXT NOT NULL,
              query_text TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_kb_prd_unit_docs_product_version
              ON kb_prd_unit_documents(product, version);
            CREATE INDEX IF NOT EXISTS idx_kb_prd_units_doc
              ON kb_prd_units(doc_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_prd_units_doc_unit
              ON kb_prd_units(doc_id, unit_id);
            CREATE INDEX IF NOT EXISTS idx_kb_prd_unit_vectors_unit
              ON kb_prd_unit_vectors(unit_pk);
            CREATE INDEX IF NOT EXISTS idx_kb_prd_unit_vectors_type
              ON kb_prd_unit_vectors(vector_type);
            CREATE INDEX IF NOT EXISTS idx_kb_prd_unit_feedback_unit
              ON kb_prd_unit_feedback_hints(unit_pk);
            """)

    def import_cleaned_json(self, cleaned_json_path: str, *, rebuild: bool = False) -> Dict[str, Any]:
        self.ensure_schema()
        path = Path(cleaned_json_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        document = data.get("document") or {}
        units = data.get("units") or []
        if not units:
            raise ValueError(f"No units found in {path}")

        doc_id = str(document.get("doc_id") or path.stem)
        now = datetime.utcnow().isoformat()
        content_hash = _content_hash(data)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT content_hash FROM kb_prd_unit_documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if existing and existing["content_hash"] == content_hash and not rebuild:
                unit_count = conn.execute("SELECT COUNT(*) FROM kb_prd_units WHERE doc_id = ?", (doc_id,)).fetchone()[0]
                vector_count = conn.execute("SELECT COUNT(*) FROM kb_prd_unit_vectors WHERE doc_id = ?", (doc_id,)).fetchone()[0]
                return {
                    "doc_id": doc_id,
                    "status": "skipped",
                    "unit_count": unit_count,
                    "vector_count": vector_count,
                }

        unit_rows: List[Tuple[Any, ...]] = []
        vector_payloads: List[Dict[str, Any]] = []
        for unit in units:
            unit_id = str(unit.get("unit_id") or "")
            if not unit_id:
                continue
            unit_pk = f"{doc_id}:{unit_id}"
            unit_hash = _content_hash(unit)
            unit_rows.append((
                unit_pk,
                doc_id,
                unit_id,
                str(unit.get("title") or ""),
                str(unit.get("unit_type") or ""),
                str(unit.get("scope") or ""),
                str(unit.get("content") or ""),
                json.dumps(unit.get("rules") or [], ensure_ascii=False),
                json.dumps(unit.get("source") or {}, ensure_ascii=False),
                json.dumps(unit.get("retrieval_meta") or {}, ensure_ascii=False),
                json.dumps(unit.get("keywords") or [], ensure_ascii=False),
                json.dumps(unit, ensure_ascii=False),
                unit_hash,
                now,
                now,
            ))
            vector_payloads.extend(build_unit_vector_payloads(data, unit, unit_pk=unit_pk, doc_id=doc_id))

        embeddings = self.embedding_provider.embed_texts([payload["embedding_text"] for payload in vector_payloads])

        with self._connect() as conn:
            conn.execute("DELETE FROM kb_prd_unit_vectors WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM kb_prd_unit_feedback_hints WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM kb_prd_units WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM kb_prd_unit_documents WHERE doc_id = ?", (doc_id,))

            conn.execute("""
                INSERT INTO kb_prd_unit_documents (
                    doc_id, title, product, version, module, summary, schema_version,
                    source_json_path, content_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                str(document.get("title") or doc_id),
                str(document.get("product") or ""),
                str(document.get("version") or ""),
                str(document.get("module") or ""),
                str(document.get("summary") or ""),
                str(data.get("schema_version") or ""),
                str(path),
                content_hash,
                now,
                now,
            ))

            for row in unit_rows:
                conn.execute("""
                    INSERT INTO kb_prd_units (
                        unit_pk, doc_id, unit_id, title, unit_type, scope, content,
                        rules, source, retrieval_meta, keywords, unit_json,
                        content_hash, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)

            for payload, embedding in zip(vector_payloads, embeddings):
                vector_hash = _content_hash({
                    "unit_pk": payload["unit_pk"],
                    "vector_type": payload["vector_type"],
                    "vector_index": payload["vector_index"],
                    "embedding_text": payload["embedding_text"],
                })
                vector_id = (
                    f"{payload['unit_pk']}:{payload['vector_type']}:{payload['vector_index']}:"
                    f"{self.embedding_provider.model_name}:{self.embedding_provider.version}"
                )
                conn.execute("""
                    INSERT INTO kb_prd_unit_vectors (
                        vector_id, unit_pk, doc_id, unit_id, vector_type, vector_index,
                        embedding_model, embedding_version, embedding_text, embedding,
                        content_hash, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    vector_id,
                    payload["unit_pk"],
                    payload["doc_id"],
                    payload["unit_id"],
                    payload["vector_type"],
                    payload["vector_index"],
                    self.embedding_provider.model_name,
                    self.embedding_provider.version,
                    payload["embedding_text"],
                    json.dumps(embedding, separators=(",", ":")),
                    vector_hash,
                    now,
                    now,
                ))

        return {
            "doc_id": doc_id,
            "status": "rebuilt" if existing else "imported",
            "unit_count": len(units),
            "vector_count": len(vector_payloads),
            "embedding_model": self.embedding_provider.model_name,
        }

    def add_feedback_hint(self, doc_id: str, unit_id: str, query_text: str) -> Dict[str, Any]:
        self.ensure_schema()
        unit_pk = f"{doc_id}:{unit_id}"
        query = str(query_text or "").strip()
        if not query:
            raise ValueError("query_text is required")
        with self._connect() as conn:
            unit_row = conn.execute("SELECT unit_json FROM kb_prd_units WHERE unit_pk = ?", (unit_pk,)).fetchone()
            if unit_row is None:
                raise ValueError(f"Unit not found: {unit_pk}")
            unit = json.loads(unit_row["unit_json"])
            document = self._load_document(conn, doc_id)
            feedback_id = _content_hash({"unit_pk": unit_pk, "query_text": query})[:32]
            now = datetime.utcnow().isoformat()
            hint_text = build_feedback_hint_text(document, unit, query)
            embedding = self.embedding_provider.embed_texts([hint_text])[0]
            vector_index = self._next_vector_index(conn, unit_pk, "feedback_hint")
            vector_id = f"{unit_pk}:feedback_hint:{vector_index}:{self.embedding_provider.model_name}:{self.embedding_provider.version}"
            vector_hash = _content_hash({
                "unit_pk": unit_pk,
                "vector_type": "feedback_hint",
                "vector_index": vector_index,
                "embedding_text": hint_text,
            })
            conn.execute("""
                INSERT OR REPLACE INTO kb_prd_unit_feedback_hints (
                    feedback_id, unit_pk, doc_id, unit_id, query_text, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """, (feedback_id, unit_pk, doc_id, unit_id, query, now, now))
            conn.execute("""
                INSERT OR REPLACE INTO kb_prd_unit_vectors (
                    vector_id, unit_pk, doc_id, unit_id, vector_type, vector_index,
                    embedding_model, embedding_version, embedding_text, embedding,
                    content_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vector_id,
                unit_pk,
                doc_id,
                unit_id,
                "feedback_hint",
                vector_index,
                self.embedding_provider.model_name,
                self.embedding_provider.version,
                hint_text,
                json.dumps(embedding, separators=(",", ":")),
                vector_hash,
                now,
                now,
            ))
        return {"feedback_id": feedback_id, "unit_pk": unit_pk, "vector_id": vector_id}

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        product: Optional[str] = None,
        version: Optional[str] = None,
        vector_types: Optional[List[str]] = None,
        candidate_k: Optional[int] = None,
        evidence_k: Optional[int] = None,
        module: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        self.ensure_schema()
        query_vector = _embed_query(self.embedding_provider, query)
        sql = """
            SELECT v.embedding, v.vector_type, v.vector_index, v.embedding_text,
                   u.unit_pk, u.doc_id, u.unit_id, u.unit_json,
                   d.title AS doc_title, d.product, d.version, d.module
            FROM kb_prd_unit_vectors v
            JOIN kb_prd_units u ON u.unit_pk = v.unit_pk
            JOIN kb_prd_unit_documents d ON d.doc_id = u.doc_id
            WHERE 1 = 1
        """
        params: List[Any] = []
        if product:
            sql += " AND d.product = ?"
            params.append(product)
        if version:
            sql += " AND d.version = ?"
            params.append(version)
        if module:
            sql += " AND d.module = ?"
            params.append(module)
        if vector_types:
            placeholders = ",".join("?" for _ in vector_types)
            sql += f" AND v.vector_type IN ({placeholders})"
            params.extend(vector_types)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        best_by_unit: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            score = cosine_similarity(query_vector, json.loads(row["embedding"]))
            unit_pk = row["unit_pk"]
            if unit_pk not in best_by_unit or score > best_by_unit[unit_pk]["score"]:
                unit = json.loads(row["unit_json"])
                best_by_unit[unit_pk] = {
                    "score": round(float(score), 6),
                    "vector_type": row["vector_type"],
                    "vector_index": row["vector_index"],
                    "unit_pk": unit_pk,
                    "doc_id": row["doc_id"],
                    "unit_id": row["unit_id"],
                    "doc_title": row["doc_title"],
                    "product": row["product"],
                    "version": row["version"],
                    "module": row["module"],
                    "unit": unit,
                }
        results = list(best_by_unit.values())
        if min_score is not None:
            results = [item for item in results if float(item.get("score") or 0) >= min_score]
        results.sort(key=lambda item: item["score"], reverse=True)
        limit = int(evidence_k or top_k or candidate_k or 5)
        return results[:max(1, limit)]

    def ask(self, question: str, *, top_k: int = 5, product: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        results = self.search(question, top_k=top_k, product=product, version=version)
        if not results:
            return {
                "question": question,
                "answerable": False,
                "answerability": {"should_answer": False, "reason": "no retrieved units", "intents": [], "missing_intents": [], "evidence_hits": []},
                "answer": "未找到明确的知识单元。",
                "sources": [],
            }

        units = [item["unit"] for item in results]
        try:
            answerability = self.answerability_gate.judge(question, units)
        except Exception as exc:
            return {
                "question": question,
                "answerable": False,
                "answerability": {
                    "should_answer": False,
                    "reason": f"answerability judge failed: {exc}",
                    "intents": [],
                    "missing_intents": ["judge_error"],
                    "evidence_hits": [],
                },
                "answer": "答案充分性判断失败，当前不返回推断答案。",
                "sources": self._source_payloads(results),
            }
        if not answerability.get("should_answer"):
            return {
                "question": question,
                "answerable": False,
                "answerability": answerability,
                "answer": "当前知识单元中未明确说明该问题，不能仅根据相近内容推断答案。",
                "sources": self._source_payloads(results),
            }

        answer_results = self._supported_results(results, answerability)

        try:
            synthesis = self.answer_synthesizer.synthesize(question, units, answerability)
        except Exception as exc:
            synthesis = {
                "synthesized_answer": "",
                "unsatisfied_points": [f"synthesis_failed: {exc}"],
            }

        answer_lines = []
        synthesized_answer = (synthesis.get("synthesized_answer") or "").strip()
        if synthesized_answer:
            answer_lines.append(synthesized_answer)
            answer_lines.append("")
        else:
            answer_lines.append("以下内容来自知识单元，不能直接视为当前线上最新规则：")
            answer_lines.append("")
            for index, item in enumerate(answer_results, 1):
                unit = item["unit"]
                answer_lines.append(f"{index}. {item['doc_title']} / {item['version']} / {unit.get('unit_id')} {unit.get('title')}")
                answer_lines.append(f"   {self._excerpt(unit.get('content', ''), 260)}")
        return {
            "question": question,
            "answerable": True,
            "answerability": answerability,
            "answer": "\n".join(answer_lines).strip(),
            "answer_synthesis": synthesis,
            "sources": self._source_payloads(answer_results),
        }

    def stats(self) -> Dict[str, Any]:
        self.ensure_schema()
        with self._connect() as conn:
            return {
                "documents": conn.execute("SELECT COUNT(*) FROM kb_prd_unit_documents").fetchone()[0],
                "units": conn.execute("SELECT COUNT(*) FROM kb_prd_units").fetchone()[0],
                "vectors": conn.execute("SELECT COUNT(*) FROM kb_prd_unit_vectors").fetchone()[0],
                "feedback_hints": conn.execute("SELECT COUNT(*) FROM kb_prd_unit_feedback_hints").fetchone()[0],
            }

    def list_documents(self) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT d.doc_id, d.title, d.product, d.version, d.module, d.summary,
                       d.source_json_path, d.updated_at,
                       COUNT(DISTINCT u.unit_pk) AS unit_count,
                       COUNT(DISTINCT v.vector_id) AS vector_count
                FROM kb_prd_unit_documents d
                LEFT JOIN kb_prd_units u ON u.doc_id = d.doc_id
                LEFT JOIN kb_prd_unit_vectors v ON v.doc_id = d.doc_id
                GROUP BY d.doc_id
                ORDER BY d.updated_at DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT d.doc_id, d.title, d.product, d.version, d.module, d.summary,
                       d.schema_version, d.source_json_path, d.content_hash,
                       d.created_at, d.updated_at,
                       COUNT(DISTINCT u.unit_pk) AS unit_count,
                       COUNT(DISTINCT v.vector_id) AS vector_count
                FROM kb_prd_unit_documents d
                LEFT JOIN kb_prd_units u ON u.doc_id = d.doc_id
                LEFT JOIN kb_prd_unit_vectors v ON v.doc_id = d.doc_id
                WHERE d.doc_id = ?
                GROUP BY d.doc_id
            """, (doc_id,)).fetchone()
        if row is None:
            raise ValueError(f"Document not found: {doc_id}")
        return dict(row)

    def get_units(self, doc_id: str) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT unit_json
                FROM kb_prd_units
                WHERE doc_id = ?
                ORDER BY unit_id
            """, (doc_id,)).fetchall()
        return [json.loads(row["unit_json"]) for row in rows]

    def get_unit(self, doc_id: str, unit_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        unit_pk = f"{doc_id}:{unit_id}"
        with self._connect() as conn:
            row = conn.execute("""
                SELECT unit_json
                FROM kb_prd_units
                WHERE unit_pk = ?
            """, (unit_pk,)).fetchone()
        if row is None:
            raise ValueError(f"Unit not found: {unit_pk}")
        return json.loads(row["unit_json"])

    def list_feedback_hints(self, doc_id: str, unit_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure_schema()
        sql = """
            SELECT feedback_id, unit_pk, doc_id, unit_id, query_text, status, created_at, updated_at
            FROM kb_prd_unit_feedback_hints
            WHERE doc_id = ?
        """
        params: List[Any] = [doc_id]
        if unit_id:
            sql += " AND unit_id = ?"
            params.append(unit_id)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _load_document(self, conn: sqlite3.Connection, doc_id: str) -> Dict[str, Any]:
        row = conn.execute(
            "SELECT doc_id, title, product, version, module, summary FROM kb_prd_unit_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Document not found: {doc_id}")
        return dict(row)

    def _next_vector_index(self, conn: sqlite3.Connection, unit_pk: str, vector_type: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(vector_index), 0) + 1 FROM kb_prd_unit_vectors WHERE unit_pk = ? AND vector_type = ?",
            (unit_pk, vector_type),
        ).fetchone()
        return int(row[0] or 1)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _source_payloads(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources = []
        for item in results:
            unit = item["unit"]
            source = unit.get("source") or {}
            sources.append({
                "doc_id": item.get("doc_id"),
                "doc_title": item.get("doc_title"),
                "version": item.get("version"),
                "unit_id": item.get("unit_id"),
                "unit_title": unit.get("title"),
                "heading_path": source.get("heading_path"),
                "score": item.get("score"),
                "vector_type": item.get("vector_type"),
                "start_line": source.get("start_line"),
                "end_line": source.get("end_line"),
                "evidence": source.get("evidence"),
            })
        return sources

    @staticmethod
    def _supported_results(results: List[Dict[str, Any]], answerability: Dict[str, Any]) -> List[Dict[str, Any]]:
        supporting_unit_ids = answerability.get("supporting_unit_ids") or []
        supporting_set = {str(unit_id) for unit_id in supporting_unit_ids if str(unit_id).strip()}
        if not supporting_set:
            return results
        supported = [
            item for item in results
            if str((item.get("unit") or {}).get("unit_id") or item.get("unit_id") or "") in supporting_set
        ]
        return supported or results

    @staticmethod
    def _excerpt(content: str, max_chars: int) -> str:
        text = " ".join(str(content or "").split())
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."


def build_unit_vector_payloads(data: Dict[str, Any], unit: Dict[str, Any], *, unit_pk: str, doc_id: str) -> List[Dict[str, Any]]:
    payloads = [
        {
            "unit_pk": unit_pk,
            "doc_id": doc_id,
            "unit_id": str(unit.get("unit_id") or ""),
            "vector_type": "body",
            "vector_index": 1,
            "embedding_text": str(unit.get("embedding_text") or fallback_embedding_text(data, unit)),
        }
    ]
    hint_text = fallback_query_hints_text(data, unit)
    if not hint_text:
        hint_text = str(unit.get("query_hints_embedding_text") or "").strip()
    if hint_text:
        payloads.append({
            "unit_pk": unit_pk,
            "doc_id": doc_id,
            "unit_id": str(unit.get("unit_id") or ""),
            "vector_type": "agent_hint_bundle",
            "vector_index": 1,
            "embedding_text": hint_text,
        })
    return payloads


def build_feedback_hint_text(document: Dict[str, Any], unit: Dict[str, Any], query_text: str) -> str:
    retrieval_meta = unit.get("retrieval_meta") or {}
    key_terms = retrieval_meta.get("key_terms") or []
    lines = [
        f"产品：{document.get('product') or ''}",
        f"版本：{document.get('version') or ''}",
        f"模块：{document.get('module') or ''}",
        f"文档：{document.get('title') or ''}",
        f"知识单元：{unit.get('title') or ''}",
        f"用户反馈问法：{query_text}",
    ]
    if key_terms:
        lines.append("关键证据词：")
        lines.extend(f"- {term}" for term in key_terms)
    return "\n".join(lines).strip()


def fallback_query_hints_text(data: Dict[str, Any], unit: Dict[str, Any]) -> str:
    retrieval_meta = unit.get("retrieval_meta") or {}
    query_hints = retrieval_meta.get("query_hints") or []
    if not query_hints:
        return ""
    document = data.get("document") or {}
    lines = [
        f"产品：{document.get('product') or ''}",
        f"版本：{document.get('version') or ''}",
        f"模块：{document.get('module') or ''}",
        f"文档：{document.get('title') or ''}",
        f"知识单元：{unit.get('title') or ''}",
        "用户可能问：",
    ]
    lines.extend(f"- {hint}" for hint in query_hints)
    key_terms = retrieval_meta.get("key_terms") or []
    if key_terms:
        lines.append("关键证据词：")
        lines.extend(f"- {term}" for term in key_terms)
    return "\n".join(lines).strip()


def fallback_embedding_text(data: Dict[str, Any], unit: Dict[str, Any]) -> str:
    document = data.get("document") or {}
    source = unit.get("source") or {}
    lines = [
        f"产品：{document.get('product') or ''}",
        f"版本：{document.get('version') or ''}",
        f"模块：{document.get('module') or ''}",
        f"变更类型：{document.get('change_type') or ''}",
        f"文档：{document.get('title') or ''}",
        f"章节：{' > '.join(source.get('heading_path') or [])}",
        f"知识单元：{unit.get('title') or ''}",
        f"类型：{unit.get('unit_type') or ''}",
        "内容：",
        str(unit.get("content") or ""),
    ]
    rules = unit.get("rules") or []
    if rules:
        lines.append("规则：")
        lines.extend(f"- {rule}" for rule in rules)
    return "\n".join(lines)


def _embed_query(provider: EmbeddingProvider, query: str) -> List[float]:
    if hasattr(provider, "embed_query"):
        return provider.embed_query(query)  # type: ignore[attr-defined]
    return provider.embed_texts([query])[0]


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
