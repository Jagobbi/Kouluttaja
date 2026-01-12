from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

from src.kb import NOTES_DIR, read_note, list_notes

# --- Asetukset (voit muuttaa myöhemmin) ---
AI_DATA_DIR = Path("data/ai")
DB_PATH = AI_DATA_DIR / "embeddings.sqlite"

# Embedding-malli (OpenAI)
EMBED_MODEL = "text-embedding-3-small"  # edullinen & hyvä hakuun :contentReference[oaicite:4]{index=4}
# Chat-malli (OpenAI) - voit vaihtaa myöhemmin
CHAT_MODEL = "gpt-4.1-mini"

CHUNK_MAX_CHARS = 1500  # yksinkertainen chunkkaus merkkimäärällä
CHUNK_OVERLAP = 200
TOP_K = 8


def _cosine(a: List[float], b: List[float]) -> float:
    # käsin, ei numpy-riippuvuutta
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(i + max_chars, n)
        chunks.append(text[i:j])
        if j >= n:
            break
        i = max(0, j - overlap)
    return chunks


def _db() -> sqlite3.Connection:
    AI_DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id TEXT NOT NULL,
        note_title TEXT,
        system TEXT,
        device TEXT,
        tags TEXT,
        chunk_index INTEGER NOT NULL,
        chunk_text TEXT NOT NULL
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        chunk_id INTEGER PRIMARY KEY,
        vec BLOB NOT NULL,
        FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
    )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_note_id ON chunks(note_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_system ON chunks(system)")
    con.commit()
    return con


def _serialize_vec(vec: List[float]) -> bytes:
    # Tallennetaan 32-bit floateiksi ilman riippuvuuksia
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


def _deserialize_vec(blob: bytes) -> List[float]:
    import struct
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _openai_client():
    # lazy import, jotta ohjelma toimii ilman openai-asennusta listausmoodissa
    from openai import OpenAI
    return OpenAI()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Kutsuu OpenAI Embeddings APIa. :contentReference[oaicite:5]{index=5}
    """
    client = _openai_client()
    # SDK palauttaa data-listan, jossa embedding-kenttä
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in resp.data]


def rebuild_index(verbose: bool = True) -> None:
    """
    Rakentaa embeddings-indeksin kaikista muistiinpanoista:
    - pilkkoo body-tekstin chunkkeihin
    - tallentaa chunkit sqliteen
    - laskee embeddingit ja tallentaa ne
    """
    con = _db()
    cur = con.cursor()

    # Tyhjennä vanha indeksi (helpoin & varmin MVP:ssä)
    cur.execute("DELETE FROM embeddings")
    cur.execute("DELETE FROM chunks")
    con.commit()

    notes = list_notes(limit=100000)
    if verbose:
        print(f"Indeksoidaan {len(notes)} muistiinpanoa...")

    all_chunk_rows: List[Tuple[str, str, str, str, str, int, str]] = []
    for m in notes:
        meta, body = read_note(m.id)
        if not meta:
            continue
        chunks = _chunk_text(body or "")
        if not chunks:
            continue
        tags = ",".join(meta.tags or [])
        for idx, ch in enumerate(chunks):
            all_chunk_rows.append((meta.id, meta.title, meta.system, meta.device, tags, idx, ch))

    if verbose:
        print(f"Luotu {len(all_chunk_rows)} tekstipalaa (chunks).")

    # Insert chunks
    cur.executemany(
        "INSERT INTO chunks(note_id, note_title, system, device, tags, chunk_index, chunk_text) VALUES (?,?,?,?,?,?,?)",
        all_chunk_rows,
    )
    con.commit()

    # Hae chunkit takaisin id:n kanssa
    rows = cur.execute("SELECT id, chunk_text FROM chunks ORDER BY id").fetchall()
    chunk_ids = [r[0] for r in rows]
    chunk_texts = [r[1] for r in rows]

    # Embed batcheissa
    BATCH = 64
    if verbose:
        print("Lasketaan embeddingit...")
    for i in range(0, len(chunk_texts), BATCH):
        batch_texts = chunk_texts[i:i+BATCH]
        vecs = embed_texts(batch_texts)
        batch_ids = chunk_ids[i:i+BATCH]
        cur.executemany(
            "INSERT INTO embeddings(chunk_id, vec) VALUES (?, ?)",
            [(cid, _serialize_vec(v)) for cid, v in zip(batch_ids, vecs)],
        )
        con.commit()
        if verbose:
            print(f"  {min(i+BATCH, len(chunk_texts))}/{len(chunk_texts)} valmiina")

    if verbose:
        print(f"✅ Indeksi valmis: {DB_PATH}")


@dataclass
class RetrievedChunk:
    note_id: str
    note_title: str
    system: str
    device: str
    tags: str
    chunk_index: int
    chunk_text: str
    score: float


def retrieve(question: str, system_filter: str = "", top_k: int = TOP_K) -> List[RetrievedChunk]:
    con = _db()
    cur = con.cursor()

    qvec = embed_texts([question])[0]

    if system_filter:
        rows = cur.execute("""
            SELECT c.note_id, c.note_title, c.system, c.device, c.tags, c.chunk_index, c.chunk_text, e.vec
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.id
            WHERE c.system = ?
        """, (system_filter.lower().strip(),)).fetchall()
    else:
        rows = cur.execute("""
            SELECT c.note_id, c.note_title, c.system, c.device, c.tags, c.chunk_index, c.chunk_text, e.vec
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.id
        """).fetchall()

    scored: List[RetrievedChunk] = []
    for note_id, title, system, device, tags, cidx, ctext, vec_blob in rows:
        vec = _deserialize_vec(vec_blob)
        s = _cosine(qvec, vec)
        scored.append(RetrievedChunk(
            note_id=note_id,
            note_title=title,
            system=system,
            device=device,
            tags=tags,
            chunk_index=int(cidx),
            chunk_text=ctext,
            score=float(s),
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def answer_with_gpt(question: str, system_filter: str = "") -> Tuple[str, List[RetrievedChunk]]:
    """
    RAG:
    1) hae top-k palat
    2) anna ne kontekstiksi Responses API:lle :contentReference[oaicite:6]{index=6}
    """
    chunks = retrieve(question, system_filter=system_filter, top_k=TOP_K)

    context_lines = []
    used_notes = []
    for ch in chunks:
        context_lines.append(
            f"[{ch.note_id}] title={ch.note_title} system={ch.system} device={ch.device} tags={ch.tags}\n"
            f"{ch.chunk_text}\n"
        )
        used_notes.append(ch.note_id)

    context = "\n---\n".join(context_lines) if context_lines else "(Ei löytynyt kontekstia.)"

    prompt = f"""Olet tietopankin avustaja. Vastaa käyttäjän kysymykseen käyttäen vain annettua kontekstia.
Jos kontekstissa ei ole riittävästi tietoa, sano se suoraan ja kerro mitä puuttuu.

KYSYMYS:
{question}

KONTEKSTI (muistiinpanopalat, lähde note_id hakasuluissa):
{context}

OHJE:
- Vastaa suomeksi.
- Lopuksi listaa "Lähteet:" ja note_id:t, joihin vastaus perustui (uniikit).
"""

    client = _openai_client()
    resp = client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )

    # SDK: resp.output_text on tyypillinen helppo tapa
    text = getattr(resp, "output_text", None)
    if not text:
        # fallback: yritä kaivaa kentistä
        text = str(resp)

    return text, chunks
