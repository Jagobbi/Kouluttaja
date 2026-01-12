from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from src.kb import NOTES_DIR, DOCS_DIR, read_note, list_notes

# --- Asetukset ---
AI_DATA_DIR = Path("data/ai")
DB_PATH = AI_DATA_DIR / "embeddings.sqlite"

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini"

CHUNK_MAX_CHARS = 1500
CHUNK_OVERLAP = 200
TOP_K = 16

# Kuinka paljon liitteiden tekstiä otetaan mukaan / liite
ATTACHMENT_MAX_CHARS = 20000

# Kuinka paljon kontekstia annetaan mallille yhteensä (rajaus varmuuden vuoksi)
MAX_CONTEXT_CHARS = 25000


def _cosine(a: List[float], b: List[float]) -> float:
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
        source_type TEXT NOT NULL,   -- "note" or "attachment"
        source_name TEXT,           -- attachment filename if source_type="attachment"
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
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source_type ON chunks(source_type)")
    con.commit()
    return con


def _serialize_vec(vec: List[float]) -> bytes:
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


def _deserialize_vec(blob: bytes) -> List[float]:
    import struct
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _openai_client():
    from openai import OpenAI
    return OpenAI()


def embed_texts(texts: List[str]) -> List[List[float]]:
    client = _openai_client()
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in resp.data]


# -------------------------
# Liitteiden tekstin lukeminen (B)
# -------------------------

def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        return ""

def _read_docx(path: Path) -> str:
    try:
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text]
        return "\n".join(parts)
    except Exception:
        return ""

def extract_attachment_text(rel_path: str) -> str:
    """
    rel_path on muotoa "docs/xxxx.pdf"
    Palauttaa liitteen tekstin (jos tuettu).
    """
    rel = Path(rel_path.replace("\\", "/"))
    full = Path("data") / rel  # data/docs/...
    if not full.exists() or not full.is_file():
        return ""

    ext = full.suffix.lower()
    if ext in {".txt", ".md", ".log", ".csv"}:
        return _read_text_file(full)
    if ext == ".pdf":
        return _read_pdf(full)
    if ext in {".docx", ".doc"}:
        return _read_docx(full)

    # kuvat yms: ei vielä (OCR myöhemmin)
    return ""


# -------------------------
# Indeksointi (A+B)
# -------------------------

def rebuild_index(include_attachments: bool = True, verbose: bool = True) -> None:
    """
    Rakentaa embeddings-indeksin:
    - muistiinpanojen body chunkkeina
    - (valinnainen) liitteiden teksti chunkkeina
    """
    con = _db()
    cur = con.cursor()

    cur.execute("DELETE FROM embeddings")
    cur.execute("DELETE FROM chunks")
    con.commit()

    notes = list_notes(limit=100000)
    if verbose:
        print(f"Indeksoidaan {len(notes)} muistiinpanoa...")

    all_chunk_rows: List[Tuple[str, str, str, str, str, str, str, int, str]] = []
    # columns: note_id, title, system, device, tags, source_type, source_name, chunk_index, chunk_text

    for m in notes:
        meta, body = read_note(m.id)
        if not meta:
            continue

        tags = ",".join(meta.tags or [])

        # 1) note body
        body_chunks = _chunk_text(body or "")
        for idx, ch in enumerate(body_chunks):
            all_chunk_rows.append((meta.id, meta.title, meta.system, meta.device, tags, "note", "", idx, ch))

        # 2) attachments
        if include_attachments and meta.linked_files:
            for lf in meta.linked_files:
                att_text = extract_attachment_text(lf)
                if not att_text:
                    continue
                att_text = att_text.strip()[:ATTACHMENT_MAX_CHARS]
                att_chunks = _chunk_text(att_text)
                source_name = Path(lf).name
                for idx, ch in enumerate(att_chunks):
                    all_chunk_rows.append((meta.id, meta.title, meta.system, meta.device, tags, "attachment", source_name, idx, ch))

    if verbose:
        print(f"Luotu {len(all_chunk_rows)} tekstipalaa (chunks).")

    if not all_chunk_rows:
        if verbose:
            print("Ei indeksoitavaa tekstiä.")
        return

    cur.executemany(
        """INSERT INTO chunks(note_id, note_title, system, device, tags, source_type, source_name, chunk_index, chunk_text)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        all_chunk_rows,
    )
    con.commit()

    rows = cur.execute("SELECT id, chunk_text FROM chunks ORDER BY id").fetchall()
    chunk_ids = [r[0] for r in rows]
    chunk_texts = [r[1] for r in rows]

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


# -------------------------
# Haku + vastaus (A + jatkokysymykset)
# -------------------------

@dataclass
class RetrievedChunk:
    note_id: str
    note_title: str
    system: str
    device: str
    tags: str
    source_type: str      # "note" / "attachment"
    source_name: str      # filename if attachment
    chunk_index: int
    chunk_text: str
    score: float


def retrieve(question: str, system_filter: str = "", top_k: int = TOP_K) -> List[RetrievedChunk]:
    con = _db()
    cur = con.cursor()

    qvec = embed_texts([question])[0]

    if system_filter:
        rows = cur.execute("""
            SELECT c.note_id, c.note_title, c.system, c.device, c.tags, c.source_type, c.source_name,
                   c.chunk_index, c.chunk_text, e.vec
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.id
            WHERE c.system = ?
        """, (system_filter.lower().strip(),)).fetchall()
    else:
        rows = cur.execute("""
            SELECT c.note_id, c.note_title, c.system, c.device, c.tags, c.source_type, c.source_name,
                   c.chunk_index, c.chunk_text, e.vec
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.id
        """).fetchall()

    scored: List[RetrievedChunk] = []
    for note_id, title, system, device, tags, stype, sname, cidx, ctext, vec_blob in rows:
        vec = _deserialize_vec(vec_blob)
        s = _cosine(qvec, vec)
        scored.append(RetrievedChunk(
            note_id=note_id,
            note_title=title,
            system=system,
            device=device,
            tags=tags,
            source_type=stype,
            source_name=sname or "",
            chunk_index=int(cidx),
            chunk_text=ctext,
            score=float(s),
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def _build_context(chunks: List[RetrievedChunk]) -> str:
    parts = []
    total = 0
    for ch in chunks:
        header = f"[{ch.note_id}] title={ch.note_title} system={ch.system} device={ch.device} tags={ch.tags} source={ch.source_type}"
        if ch.source_type == "attachment" and ch.source_name:
            header += f":{ch.source_name}"
        block = header + "\n" + ch.chunk_text.strip() + "\n"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n---\n".join(parts) if parts else "(Ei löytynyt kontekstia.)"


def answer_with_gpt(
    question: str,
    system_filter: str = "",
    history: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[str, List[RetrievedChunk]]:
    """
    history: lista (user_question, assistant_answer) tämän session ajalta.
    Tämä mahdollistaa jatkokysymykset.
    """
    chunks = retrieve(question, system_filter=system_filter, top_k=TOP_K)
    context = _build_context(chunks)

    # Tiivis keskusteluhistoria (ei liian pitkä)
    hist_txt = ""
    if history:
        last = history[-6:]  # pidä viimeiset 6 vuoroparia
        lines = []
        for uq, aa in last:
            lines.append(f"Käyttäjä: {uq}\nAvustaja: {aa}")
        hist_txt = "\n\n".join(lines)

    prompt = f"""Olet tietopankin tekninen avustaja. Vastaat AINOASTAAN annetun kontekstin perusteella.
Jos kontekstissa ei ole tarvittavaa tietoa, sano se selvästi ("En löydä tästä tietopankista varmaa vastausta") ja kysy 1–2 täsmäkysymystä.

TYYLI:
- Vastaa suomeksi.
- Jos kysymys pyytää ohjeita tai ongelmanratkaisua, anna SELKEÄT step-by-step vaiheet.
- Jos asiaan liittyy riskejä (esim. tuotantojärjestelmä), lisää varoitus ja turvallinen tapa testata.
- Älä keksi nimiä, asetuksia tai komentoja, joita et näe kontekstissa.

KYSYMYS:
{question}

KESKUSTELUHISTORIA (viimeisimmät, jos jatkokysymyksiä):
{hist_txt if hist_txt else "(ei historiaa)"}

KONTEKSTI (muistiinpanopalat, lähde note_id hakasuluissa; liitteet merkitty source=attachment):
{context}

PALAUTUSFORMAATTI:
1) Vastaus
2) Jos hyödyllistä: Step-by-step
3) Lähteet: listaa käytetyt note_id:t (uniikit). Jos käytit liitteitä, mainitse myös liitteen nimi.
"""

    client = _openai_client()
    resp = client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )

    text = getattr(resp, "output_text", None)
    if not text:
        text = str(resp)

    return text, chunks
def debug_retrieve(question: str, system_filter: str = ""):
    chunks = retrieve(question, system_filter=system_filter, top_k=TOP_K)
    print("\nTOP CHUNKS:")
    for ch in chunks:
        print("="*60)
        print(f"score={ch.score:.3f} note_id={ch.note_id} source={ch.source_type} name={ch.source_name}")
        print(ch.chunk_text[:500])
