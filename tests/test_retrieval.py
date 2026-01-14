import sqlite3
import struct
from pathlib import Path

import pytest

from src.retrieval import HybridRetriever, RetrievalConfig, build_bm25_index


def _serialize_vec(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "embeddings.sqlite"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""
    CREATE TABLE chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id TEXT NOT NULL,
        note_title TEXT,
        system TEXT,
        device TEXT,
        tags TEXT,
        source_type TEXT NOT NULL,
        source_name TEXT,
        chunk_index INTEGER NOT NULL,
        chunk_text TEXT NOT NULL,
        doc_key TEXT,
        keywords TEXT,
        entities TEXT
    )
    """)
    con.execute("""
    CREATE TABLE embeddings (
        chunk_id INTEGER PRIMARY KEY,
        vec BLOB NOT NULL,
        FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
    )
    """)
    con.commit()

    rows = [
        ("n1", "VPN guide", "network", "", "", "note", "", 0, "VPN setup steps", "n1::note", "[]", "[]"),
        ("n2", "Printer help", "hardware", "", "", "note", "", 0, "Printer error 0x900", "n2::note", "[]", "[]"),
    ]
    con.executemany("""
        INSERT INTO chunks
        (note_id, note_title, system, device, tags, source_type, source_name,
         chunk_index, chunk_text, doc_key, keywords, entities)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    con.commit()

    ids = [r[0] for r in con.execute("SELECT id FROM chunks ORDER BY id").fetchall()]
    vectors = [
        _serialize_vec([1.0, 0.0, 0.0]),
        _serialize_vec([0.0, 1.0, 0.0]),
    ]
    con.executemany(
        "INSERT INTO embeddings(chunk_id, vec) VALUES (?, ?)",
        list(zip(ids, vectors)),
    )
    con.commit()
    con.close()
    return db_path


def test_hybrid_retrieval_returns_expected_doc(tmp_path: Path):
    pytest.importorskip("rank_bm25")
    db_path = _make_db(tmp_path)
    bm25_path = tmp_path / "bm25.pkl"
    build_bm25_index(db_path, bm25_path)

    def embed_fn(texts):
        out = []
        for t in texts:
            if "vpn" in t.lower():
                out.append([1.0, 0.0, 0.0])
            else:
                out.append([0.0, 1.0, 0.0])
        return out

    cfg = RetrievalConfig(
        top_k_vector=10,
        top_k_bm25=10,
        use_mmr=False,
        use_rerank=False,
        final_top_n=1,
    )
    retriever = HybridRetriever(db_path, bm25_path, embed_fn, cfg)
    results = retriever.retrieve("vpn")
    assert results
    assert results[0]["note_id"] == "n1"
