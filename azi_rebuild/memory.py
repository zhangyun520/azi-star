from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from typing import Any


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_memory_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_fact_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_key TEXT NOT NULL UNIQUE,
            claim_text TEXT NOT NULL,
            subject TEXT,
            predicate TEXT,
            object_text TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            support_count INTEGER NOT NULL DEFAULT 1,
            conflict_count INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            first_seen_event_id INTEGER NOT NULL DEFAULT 0,
            last_seen_event_id INTEGER NOT NULL DEFAULT 0,
            first_seen_ts TEXT NOT NULL,
            last_seen_ts TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'warm',
            lifecycle_score REAL NOT NULL DEFAULT 0.0,
            meta_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_fact_memory_last_event ON azi_fact_memory(last_seen_event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_fact_memory_tier ON azi_fact_memory(tier)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_fact_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            claim_key TEXT NOT NULL,
            existing_fact_id INTEGER NOT NULL,
            incoming_claim TEXT NOT NULL,
            existing_claim TEXT NOT NULL,
            source TEXT NOT NULL,
            note TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_fact_conflicts_key ON azi_fact_conflicts(claim_key)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_memory_vectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            norm REAL NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            tier TEXT NOT NULL DEFAULT 'short',
            ts TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_memory_vectors_event ON azi_memory_vectors(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_memory_vectors_ts ON azi_memory_vectors(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_memory_vectors_tier ON azi_memory_vectors(tier)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_source_trust (
            source TEXT PRIMARY KEY,
            trust_score REAL NOT NULL DEFAULT 0.5,
            sample_count INTEGER NOT NULL DEFAULT 0,
            updated_ts TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_causal_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_text TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 0.5,
            source TEXT NOT NULL,
            last_event_id INTEGER NOT NULL DEFAULT 0,
            updated_ts TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_causal_subject ON azi_causal_edges(subject)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_causal_last_event ON azi_causal_edges(last_event_id)")
    conn.commit()


def ingest_event_memory(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    source: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, int]:
    text = str(content or "").strip()
    if not text:
        return {"facts": 0, "vectors": 0, "conflicts": 0, "edges": 0}

    claims = extract_claims(text)
    inserted = 0
    for claim in claims[:24]:
        inserted += 1 if upsert_fact(conn, event_id=event_id, source=source, claim=claim, meta=meta or {}) else 0

    conflicts = int(
        conn.execute(
            "SELECT COUNT(1) AS c FROM azi_fact_conflicts WHERE source=? AND ts>=?",
            (str(source), now_iso()[:10]),
        ).fetchone()["c"]
        or 0
    )

    index_vector(conn, event_id=event_id, source=source, content=text)
    edges = upsert_causal_edges(conn, event_id=event_id, source=source, text=text)
    update_source_trust(conn, source=source, quality_signal=_source_quality(source))
    run_memory_lifecycle(conn)
    conn.commit()
    return {"facts": inserted, "vectors": 1, "conflicts": conflicts, "edges": edges}


def extract_claims(text: str) -> list[str]:
    parts = re.split(r"[。！？?!;\n]+", str(text or ""))
    out: list[str] = []
    for part in parts:
        s = str(part).strip()
        if len(s) < 6:
            continue
        if len(s) > 400:
            s = s[:400]
        out.append(s)
    return out


def upsert_fact(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    source: str,
    claim: str,
    meta: dict[str, Any],
) -> bool:
    ts = now_iso()
    subject, predicate, obj = split_claim_triplet(claim)
    claim_key = _fact_key(subject, predicate, obj)
    row = conn.execute(
        "SELECT id, claim_text, support_count, conflict_count FROM azi_fact_memory WHERE claim_key=?",
        (claim_key,),
    ).fetchone()
    confidence = _claim_confidence(claim)
    if row is None:
        conn.execute(
            """
            INSERT INTO azi_fact_memory(
                claim_key, claim_text, subject, predicate, object_text, confidence,
                support_count, conflict_count, source, first_seen_event_id, last_seen_event_id,
                first_seen_ts, last_seen_ts, tier, lifecycle_score, meta_json
            ) VALUES(?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, 'warm', 0.0, ?)
            """,
            (
                claim_key,
                claim,
                subject,
                predicate,
                obj,
                confidence,
                str(source),
                int(event_id),
                int(event_id),
                ts,
                ts,
                json.dumps(meta, ensure_ascii=False),
            ),
        )
        return True

    existing_text = str(row["claim_text"] or "")
    support_count = int(row["support_count"] or 0)
    conflict_count = int(row["conflict_count"] or 0)
    if normalize_claim(existing_text) != normalize_claim(claim):
        conn.execute(
            """
            INSERT INTO azi_fact_conflicts(ts, claim_key, existing_fact_id, incoming_claim, existing_claim, source, note)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, claim_key, int(row["id"]), claim, existing_text, str(source), "same key but different text"),
        )
        conflict_count += 1

    new_conf = _blend(float(confidence), float(conflict_count))
    conn.execute(
        """
        UPDATE azi_fact_memory
        SET claim_text=?, confidence=?, support_count=?, conflict_count=?,
            source=?, last_seen_event_id=?, last_seen_ts=?, meta_json=?
        WHERE claim_key=?
        """,
        (
            claim if len(claim) >= len(existing_text) else existing_text,
            new_conf,
            support_count + 1,
            conflict_count,
            str(source),
            int(event_id),
            ts,
            json.dumps(meta, ensure_ascii=False),
            claim_key,
        ),
    )
    return False


def split_claim_triplet(claim: str) -> tuple[str, str, str]:
    s = str(claim or "").strip()
    if "->" in s:
        a, b = s.split("->", 1)
        return a.strip()[:80], "leads_to", b.strip()[:200]
    if "导致" in s:
        a, b = s.split("导致", 1)
        return a.strip()[:80], "causes", b.strip()[:200]
    if "因为" in s and "所以" in s:
        a, b = s.split("所以", 1)
        return a.replace("因为", "").strip()[:80], "therefore", b.strip()[:200]
    if "是" in s:
        a, b = s.split("是", 1)
        return a.strip()[:80], "is", b.strip()[:200]
    tokens = tokenize(s)
    if len(tokens) >= 3:
        return tokens[0][:80], tokens[1][:32], " ".join(tokens[2:])[:200]
    return s[:80], "states", s[:200]


def _fact_key(subject: str, predicate: str, object_text: str) -> str:
    raw = f"{normalize_claim(subject)}|{normalize_claim(predicate)}|{normalize_claim(object_text)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def normalize_claim(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    t = re.sub(r"[^\w\u4e00-\u9fff ]+", "", t)
    return t[:400]


def _claim_confidence(claim: str) -> float:
    base = 0.52
    length_bonus = min(len(str(claim or "")) / 500.0, 0.18)
    hedge_penalty = 0.08 if any(k in str(claim) for k in ("可能", "大概", "maybe", "perhaps")) else 0.0
    return max(0.1, min(0.95, base + length_bonus - hedge_penalty))


def _blend(confidence: float, conflict_count: float) -> float:
    penalty = min(conflict_count * 0.05, 0.35)
    return max(0.1, min(0.95, confidence - penalty))


def index_vector(conn: sqlite3.Connection, *, event_id: int, source: str, content: str) -> None:
    vec = text_to_vector(content, dim=64)
    norm = math.sqrt(sum(x * x for x in vec))
    conn.execute(
        """
        INSERT INTO azi_memory_vectors(event_id, source, content, vector_json, norm, score, tier, ts)
        VALUES(?, ?, ?, ?, ?, 0.0, 'short', ?)
        """,
        (
            int(event_id),
            str(source),
            str(content)[:2000],
            json.dumps(vec, ensure_ascii=False),
            float(norm),
            now_iso(),
        ),
    )


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", str(text or "").lower())


def text_to_vector(text: str, dim: int = 64) -> list[float]:
    vec = [0.0] * dim
    tokens = tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = -1.0 if ((h >> 1) & 1) else 1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def fact_first_retrieve(conn: sqlite3.Connection, *, query: str, top_k: int = 8) -> list[dict[str, Any]]:
    q_tokens = set(tokenize(query))
    rows = conn.execute(
        """
        SELECT f.id, f.claim_text, f.confidence, f.support_count, f.conflict_count,
               f.source, f.last_seen_event_id, COALESCE(s.trust_score, 0.5) AS trust_score
        FROM azi_fact_memory AS f
        LEFT JOIN azi_source_trust AS s ON s.source=f.source
        WHERE f.tier IN ('hot','warm','cold')
        ORDER BY f.last_seen_event_id DESC
        LIMIT 800
        """
    ).fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        claim = str(row["claim_text"] or "")
        t = set(tokenize(claim))
        overlap = 0.0
        if q_tokens and t:
            overlap = len(q_tokens & t) / max(1.0, len(q_tokens))
        trust = float(row["trust_score"] or 0.5)
        conf = float(row["confidence"] or 0.5)
        score = 0.50 * overlap + 0.30 * conf + 0.20 * trust
        scored.append(
            (
                score,
                {
                    "id": int(row["id"]),
                    "claim_text": claim,
                    "confidence": conf,
                    "source": str(row["source"]),
                    "support_count": int(row["support_count"] or 0),
                    "conflict_count": int(row["conflict_count"] or 0),
                    "last_seen_event_id": int(row["last_seen_event_id"] or 0),
                    "trust_score": trust,
                    "score": score,
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[: max(1, int(top_k))]]


def vector_retrieve(conn: sqlite3.Connection, *, query: str, top_k: int = 8) -> list[dict[str, Any]]:
    q = text_to_vector(query, dim=64)
    rows = conn.execute(
        """
        SELECT id, event_id, source, content, vector_json, norm, tier
        FROM azi_memory_vectors
        WHERE tier IN ('short','mid','long','crystal')
        ORDER BY id DESC
        LIMIT 1000
        """
    ).fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        try:
            vec = json.loads(str(row["vector_json"] or "[]"))
        except Exception:
            vec = []
        if not isinstance(vec, list):
            continue
        sim = cosine(q, [float(v) for v in vec[:64]])
        scored.append(
            (
                sim,
                {
                    "id": int(row["id"]),
                    "event_id": int(row["event_id"] or 0),
                    "source": str(row["source"] or ""),
                    "content": str(row["content"] or ""),
                    "tier": str(row["tier"] or "short"),
                    "score": sim,
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[: max(1, int(top_k))]]


def hybrid_retrieve(conn: sqlite3.Connection, *, query: str, top_k: int = 8) -> dict[str, Any]:
    facts = fact_first_retrieve(conn, query=query, top_k=top_k)
    vecs = vector_retrieve(conn, query=query, top_k=top_k)
    return {"facts": facts, "vectors": vecs}


def update_source_trust(conn: sqlite3.Connection, *, source: str, quality_signal: float) -> None:
    ts = now_iso()
    row = conn.execute("SELECT trust_score, sample_count FROM azi_source_trust WHERE source=?", (str(source),)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO azi_source_trust(source, trust_score, sample_count, updated_ts) VALUES(?, ?, 1, ?)",
            (str(source), float(max(0.0, min(1.0, quality_signal))), ts),
        )
        return
    old = float(row["trust_score"] or 0.5)
    samples = int(row["sample_count"] or 0)
    alpha = 1.0 / max(3.0, min(50.0, samples + 1))
    new = (1.0 - alpha) * old + alpha * float(max(0.0, min(1.0, quality_signal)))
    conn.execute(
        "UPDATE azi_source_trust SET trust_score=?, sample_count=?, updated_ts=? WHERE source=?",
        (float(new), samples + 1, ts, str(source)),
    )


def _source_quality(source: str) -> float:
    low = str(source or "").lower()
    if low.startswith(("manual", "brain", "deep-worker", "health")):
        return 0.80
    if "web" in low:
        return 0.55
    if "social" in low:
        return 0.52
    if "device" in low:
        return 0.50
    return 0.60


def upsert_causal_edges(conn: sqlite3.Connection, *, event_id: int, source: str, text: str) -> int:
    lines = extract_claims(text)
    count = 0
    for line in lines[:16]:
        if "导致" in line:
            a, b = line.split("导致", 1)
            s = a.strip()[:120]
            o = b.strip()[:180]
            p = "causes"
        elif "->" in line:
            a, b = line.split("->", 1)
            s = a.strip()[:120]
            o = b.strip()[:180]
            p = "leads_to"
        elif "因为" in line and "所以" in line:
            a, b = line.split("所以", 1)
            s = a.replace("因为", "").strip()[:120]
            o = b.strip()[:180]
            p = "therefore"
        else:
            continue
        conn.execute(
            """
            INSERT INTO azi_causal_edges(subject, predicate, object_text, weight, source, last_event_id, updated_ts)
            VALUES(?, ?, ?, 0.5, ?, ?, ?)
            """,
            (s, p, o, str(source), int(event_id), now_iso()),
        )
        count += 1
    return count


def run_memory_lifecycle(conn: sqlite3.Connection) -> None:
    max_event_row = conn.execute("SELECT MAX(id) AS m FROM azi_memory_vectors").fetchone()
    max_id = int(max_event_row["m"] or 0) if max_event_row else 0
    if max_id <= 0:
        return

    rows = conn.execute("SELECT id, score FROM azi_memory_vectors").fetchall()
    for row in rows:
        idx = int(row["id"])
        age = max_id - idx
        if age <= 30:
            tier = "short"
        elif age <= 200:
            tier = "mid"
        elif age <= 1200:
            tier = "long"
        else:
            tier = "crystal"
        conn.execute("UPDATE azi_memory_vectors SET tier=? WHERE id=?", (tier, idx))

    fact_rows = conn.execute(
        "SELECT id, support_count, conflict_count, last_seen_event_id FROM azi_fact_memory"
    ).fetchall()
    max_fact_event = conn.execute("SELECT MAX(last_seen_event_id) AS m FROM azi_fact_memory").fetchone()
    max_fact_id = int(max_fact_event["m"] or 0) if max_fact_event else 0
    for row in fact_rows:
        support = float(row["support_count"] or 0)
        conflict = float(row["conflict_count"] or 0)
        age = max_fact_id - int(row["last_seen_event_id"] or 0)
        lifecycle = support - 0.6 * conflict - 0.002 * float(max(0, age))
        if lifecycle >= 3.0:
            tier = "hot"
        elif lifecycle >= 1.0:
            tier = "warm"
        elif lifecycle >= -0.5:
            tier = "cold"
        else:
            tier = "archive"
        conn.execute(
            "UPDATE azi_fact_memory SET tier=?, lifecycle_score=? WHERE id=?",
            (tier, float(lifecycle), int(row["id"])),
        )
