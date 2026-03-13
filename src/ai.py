from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from src.kb import NOTES_DIR, DOCS_DIR, read_note, list_notes, _normalize_tags
from src.retrieval import RetrievalConfig, HybridRetriever, build_bm25_index

# --- Asetukset ---
AI_DATA_DIR = Path("data/ai")
DB_PATH = AI_DATA_DIR / "embeddings.sqlite"

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini"

CHUNK_MAX_CHARS = 2500
CHUNK_OVERLAP = 300
TOP_K = 40
MIN_SCORE = 0.22

# Kuinka paljon liitteiden tekstiä otetaan mukaan / liite
ATTACHMENT_MAX_CHARS = 200000

# Kuinka paljon kontekstia annetaan mallille yhteensä (rajaus varmuuden vuoksi)
MAX_CONTEXT_CHARS = 35000
MAX_CONTEXT_TOKENS = 4000

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_DOC_TYPES = {"law", "instruction", "manual", "note"}

# Hybrid retrieval config
TOP_K_VECTOR = 60
TOP_K_BM25 = 60
WEIGHT_VECTOR = 0.55
WEIGHT_BM25 = 0.45
MAX_CHUNKS_PER_DOC = 4
USE_MMR = True
USE_RERANK = True
RERANK_TOP_K = 50
FINAL_TOP_N = 14
DEBUG_RETRIEVAL = False

BM25_PATH = AI_DATA_DIR / "bm25.pkl"

_index_version = 0
_last_sync_info: Dict[str, object] = {}


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
    con.execute("PRAGMA foreign_keys = ON")
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
        chunk_text TEXT NOT NULL,
        doc_key TEXT,
        keywords TEXT,
        entities TEXT
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        chunk_id INTEGER PRIMARY KEY,
        vec BLOB NOT NULL,
        FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS docs (
        doc_key TEXT PRIMARY KEY,
        doc_hash TEXT NOT NULL
    )
    """)
    _ensure_schema(con)
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_note_id ON chunks(note_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_system ON chunks(system)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source_type ON chunks(source_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_key ON chunks(doc_key)")
    con.commit()
    return con

def _ensure_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(chunks)").fetchall()]
    if "doc_key" not in cols:
        cur.execute("ALTER TABLE chunks ADD COLUMN doc_key TEXT")
    if "keywords" not in cols:
        cur.execute("ALTER TABLE chunks ADD COLUMN keywords TEXT")
    if "entities" not in cols:
        cur.execute("ALTER TABLE chunks ADD COLUMN entities TEXT")
    con.commit()


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

def _hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()

def _extract_entities(text: str) -> List[str]:
    import re
    t = text or ""
    patterns = [
        r"\b\d+(?:\.\d+){1,3}\b",
        r"\b0x[0-9A-Fa-f]+\b",
        r"\bERROR[_ -]?\d+\b",
        r"\bHTTP\s?\d{3}\b",
        r"[A-Za-z]:\\[^\s\"']+",
        r"/[^\s\"']+",
        r"https?://[^\s\"']+",
        r"\b[A-Z]{2,6}\b",
    ]
    out: List[str] = []
    for p in patterns:
        for m in re.findall(p, t):
            if m not in out:
                out.append(m)
    return out[:30]

def _extract_keywords(text: str, top_n: int = 8) -> List[str]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(
            stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z0-9][a-zA-Z0-9_-]{2,}\b",
            max_features=200,
        )
        tf = vec.fit_transform([text or ""])
        scores = tf.toarray()[0]
        feats = vec.get_feature_names_out()
        pairs = sorted(zip(feats, scores), key=lambda x: x[1], reverse=True)
        return [w for w, _s in pairs[:top_n]]
    except Exception:
        import re
        words = re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]{2,}\b", (text or "").lower())
        freq: Dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _n in ranked[:top_n]]

def get_current_doc_keys(include_attachments: bool = True) -> set[str]:
    current: set[str] = set()
    notes = list_notes(limit=100000)
    for m in notes:
        meta, body = read_note(m.id)
        if not meta:
            continue
        current.add(f"{meta.id}::note")
        if include_attachments and meta.linked_files:
            for lf in meta.linked_files:
                rel = Path(lf.replace("\\", "/"))
                full = Path("data") / rel
                if full.exists() and full.is_file():
                    current.add(f"{meta.id}::att::{rel.name}")
    return current

def sync_index(include_attachments: bool = True, verbose: bool = False) -> None:
    rebuild_index(include_attachments=include_attachments, verbose=verbose)

def get_last_sync_info() -> Dict[str, object]:
    return dict(_last_sync_info)

def infer_note_metadata(title: str, body: str) -> Tuple[str, List[str]]:
    client = _openai_client()
    prompt = f"""You will infer metadata for a Finnish knowledge base note.
Return strict JSON only:
{{"system": "short system name or empty", "tags": ["tag1", "tag2"]}}

Guidelines:
- "system" should be a short lowercase keyword like sap, jira, zebra, windows, printer, excel. Empty if unknown.
- "tags" should be 2-6 short lowercase tags; no duplicates.
- Use only information from the title/body.

Title: {title.strip()}
Body: {body.strip()}
"""
    resp = client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )
    text = getattr(resp, "output_text", None)
    if not text:
        text = str(resp)

    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "", []

    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return "", []

    system = str(data.get("system", "") or "").strip().lower()
    tags = data.get("tags", []) or []
    if not isinstance(tags, list):
        tags = []

    tags_norm = _normalize_tags(",".join(str(t) for t in tags))
    return system, tags_norm


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
            text = (page.extract_text() or "").strip()
            if not text:
                images = getattr(page, "images", []) or []
                ocr_parts = []
                for img in images:
                    data = getattr(img, "data", None)
                    name = getattr(img, "name", "") or ""
                    if not data:
                        continue
                    ocr_parts.append(_read_image_bytes_text(data, name))
                text = "\n".join([p for p in ocr_parts if p])
            parts.append(text)
        return "\n".join(parts)
    except Exception:
        return ""

def _read_pdf_pages(path: Path) -> List[tuple[int, str]]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            t = (page.extract_text() or "").strip()
            if not t:
                images = getattr(page, "images", []) or []
                ocr_parts = []
                for img in images:
                    data = getattr(img, "data", None)
                    name = getattr(img, "name", "") or ""
                    if not data:
                        continue
                    ocr_parts.append(_read_image_bytes_text(data, name))
                t = "\n".join([p for p in ocr_parts if p]).strip()
            if t:
                pages.append((i, t))
        return pages
    except Exception:
        return []

def extract_attachment_pages(rel_path: str) -> List[tuple[int, str]]:
    rel = Path(rel_path.replace("\\", "/"))
    full = Path("data") / rel
    if not full.exists() or not full.is_file():
        return []

    ext = full.suffix.lower()
    if ext == ".pdf":
        return _read_pdf_pages(full)

    # muille tyypeille palautetaan “yksi sivu”
    if ext in {".txt", ".md", ".log", ".csv"}:
        return [(1, _read_text_file(full))]
    if ext in {".docx", ".doc"}:
        return [(1, _read_docx(full))]
    if ext in IMAGE_EXTS:
        text = _read_image_text(full)
        return [(1, text)] if text else []

    return []


def _read_docx(path: Path) -> str:
    try:
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text]
        return "\n".join(parts)
    except Exception:
        return ""

def _read_image_bytes_text(data: bytes, name: str = "") -> str:
    try:
        import base64
        import mimetypes

        mime = mimetypes.guess_type(name)[0] or "image/png"
        encoded = base64.b64encode(data).decode("ascii")
        client = _openai_client()
        resp = client.responses.create(
            model=CHAT_MODEL,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Extract all text from this image. Return only the text."},
                    {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"},
                ],
            }],
        )
        text = getattr(resp, "output_text", None)
        if not text:
            text = str(resp)
        return (text or "").strip()
    except Exception:
        return ""

def _read_image_text(path: Path) -> str:
    return _read_image_bytes_text(path.read_bytes(), path.name)

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
    if ext in IMAGE_EXTS:
        return _read_image_text(full)

    # kuvat yms: ei vielä (OCR myöhemmin)
    return ""


# -------------------------
# Indeksointi (A+B)
# -------------------------

def rebuild_index(include_attachments: bool = True, verbose: bool = True) -> None:
    """
    Rakentaa embeddings-indeksin:
    - muistiinpanojen body chunkkeina
    - (valinnainen) liitteiden teksti sivuittain
    """
    con = _db()
    cur = con.cursor()

    existing_docs = dict(cur.execute("SELECT doc_key, doc_hash FROM docs").fetchall())
    updated_docs: Dict[str, str] = {}
    current_doc_keys: set[str] = set()
    all_chunk_rows = []
    changed = False
    deleted_doc_keys: List[str] = []
    deleted_chunks = 0

    notes = list_notes(limit=100000)
    if verbose:
        print(f"Indeksoidaan {len(notes)} muistiinpanoa...")

    for m in notes:
        meta, body = read_note(m.id)
        if not meta:
            continue

        tags = ",".join(meta.tags or [])

        # --- 1) Muistiinpanon teksti ---
        doc_key = f"{meta.id}::note"
        current_doc_keys.add(doc_key)
        doc_text = f"{meta.title}\n{meta.system}\n{meta.device}\n{body or ''}".strip()
        doc_hash = _hash_text(doc_text)
        if existing_docs.get(doc_key) != doc_hash:
            changed = True
            cur.execute("DELETE FROM chunks WHERE doc_key = ?", (doc_key,))
            doc_keywords = _extract_keywords(doc_text)
            doc_entities = _extract_entities(doc_text)
            header = meta.title.strip()
            body_chunks = _chunk_text(doc_text)
            for idx, ch in enumerate(body_chunks):
                text_for_chunk = f"{header}\n{ch}".strip() if header else ch
                kw = list(dict.fromkeys(doc_keywords + _extract_keywords(text_for_chunk, top_n=4)))
                ent = list(dict.fromkeys(doc_entities + _extract_entities(text_for_chunk)))
                all_chunk_rows.append(
                    (meta.id, meta.title, meta.system, meta.device, tags,
                     "note", "", idx, text_for_chunk, doc_key,
                     json.dumps(kw, ensure_ascii=True),
                     json.dumps(ent, ensure_ascii=True))
                )
            updated_docs[doc_key] = doc_hash

        # --- 2) Liitteet (PDF/DOCX/TXT/MD/CSV/kuvat) ---
        if include_attachments and meta.linked_files:
            for lf in meta.linked_files:
                pages = extract_attachment_pages(lf)
                if not pages:
                    continue

                source_name = Path(lf).name
                doc_key = f"{meta.id}::att::{source_name}"
                current_doc_keys.add(doc_key)

                full_text = "\n".join([p[1] for p in pages if p[1]]).strip()
                full_text = full_text[:ATTACHMENT_MAX_CHARS]
                doc_text = f"{meta.title}\n{source_name}\n{full_text}".strip()
                doc_hash = _hash_text(doc_text)
                if existing_docs.get(doc_key) == doc_hash:
                    continue

                changed = True
                cur.execute("DELETE FROM chunks WHERE doc_key = ?", (doc_key,))
                doc_keywords = _extract_keywords(doc_text)
                doc_entities = _extract_entities(doc_text)
                header = f"{meta.title} | {source_name}".strip(" |")

                for page_no, page_text in pages:
                    if not page_text:
                        continue
                    page_text = page_text.strip()[:ATTACHMENT_MAX_CHARS]
                    att_chunks = _chunk_text(page_text)
                    for idx, ch in enumerate(att_chunks):
                        chunk_idx = page_no * 1000 + idx
                        text_for_chunk = f"{header}\n{ch}".strip() if header else ch
                        kw = list(dict.fromkeys(doc_keywords + _extract_keywords(text_for_chunk, top_n=4)))
                        ent = list(dict.fromkeys(doc_entities + _extract_entities(text_for_chunk)))
                        all_chunk_rows.append(
                            (meta.id, meta.title, meta.system, meta.device, tags,
                             "attachment", source_name, chunk_idx, text_for_chunk, doc_key,
                             json.dumps(kw, ensure_ascii=True),
                             json.dumps(ent, ensure_ascii=True))
                        )
                updated_docs[doc_key] = doc_hash

    # Poista poistuneet dokumentit
    stale = set(existing_docs.keys()) - current_doc_keys
    for doc_key in stale:
        changed = True
        cnt = cur.execute("SELECT COUNT(1) FROM chunks WHERE doc_key = ?", (doc_key,)).fetchone()[0]
        deleted_chunks += int(cnt or 0)
        cur.execute("DELETE FROM chunks WHERE doc_key = ?", (doc_key,))
        cur.execute("DELETE FROM docs WHERE doc_key = ?", (doc_key,))
        deleted_doc_keys.append(doc_key)

    if verbose:
        print(f"Luotu {len(all_chunk_rows)} tekstipalaa (chunks).")

    if all_chunk_rows:
        cur.executemany(
            """INSERT INTO chunks
               (note_id, note_title, system, device, tags,
                source_type, source_name, chunk_index, chunk_text, doc_key, keywords, entities)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            all_chunk_rows,
        )
        con.commit()

    if updated_docs:
        cur.executemany(
            "INSERT OR REPLACE INTO docs(doc_key, doc_hash) VALUES (?, ?)",
            list(updated_docs.items()),
        )
        con.commit()

    if not changed and not all_chunk_rows:
        _last_sync_info.clear()
        _last_sync_info.update({
            "changed": False,
            "deleted_doc_keys": [],
            "deleted_chunks": 0,
            "created_chunks": 0,
            "index_version": _index_version,
        })
        if verbose:
            print("Ei muutoksia indeksiin.")
        con.close()
        return

    # Laske embeddingit vain uusille chunkeille
    rows = cur.execute("""
        SELECT id, chunk_text
        FROM chunks
        WHERE id NOT IN (SELECT chunk_id FROM embeddings)
        ORDER BY id
    """).fetchall()
    chunk_ids = [r[0] for r in rows]
    chunk_texts = [r[1] for r in rows]
    created_chunks = len(chunk_ids)

    BATCH = 64
    if verbose:
        print("Lasketaan embeddingit...")

    for i in range(0, len(chunk_texts), BATCH):
        batch_texts = chunk_texts[i:i + BATCH]
        vecs = embed_texts(batch_texts)
        batch_ids = chunk_ids[i:i + BATCH]

        cur.executemany(
            "INSERT OR REPLACE INTO embeddings(chunk_id, vec) VALUES (?, ?)",
            [(cid, _serialize_vec(v)) for cid, v in zip(batch_ids, vecs)],
        )
        con.commit()

        if verbose:
            print(f"  {min(i + BATCH, len(chunk_texts))}/{len(chunk_texts)} valmiina")

    con.close()

    build_bm25_index(DB_PATH, BM25_PATH)
    if changed:
        _bump_index_version()
        _reset_retriever_cache()
    _last_sync_info.clear()
    _last_sync_info.update({
        "changed": changed,
        "deleted_doc_keys": deleted_doc_keys,
        "deleted_chunks": deleted_chunks,
        "created_chunks": created_chunks,
        "index_version": _index_version,
    })
    if verbose:
        if deleted_doc_keys:
            print(f"Poistettuja dokumentteja: {len(deleted_doc_keys)}")
            print(f"Poistettuja chunkeja: {deleted_chunks}")
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
    doc_key: str
    keywords: str
    entities: str
    score: float
def _tokens(q: str) -> List[str]:
    import re
    t = re.findall(r"[\w]{3,}", (q or "").lower())
    # pidä uniikit
    out = []
    for x in t:
        if x not in out:
            out.append(x)
    return out

def _boilerplate_penalty(text: str) -> float:
    t = (text or "").lower()
    bad = ["legal notice", "index", "liable for any loss", "original instruction"]
    return 0.6 if any(b in t for b in bad) else 1.0

def _keyword_boost(q: str, text: str) -> float:
    toks = _tokens(q)
    if not toks:
        return 1.0
    t = (text or "").lower()
    hits = sum(1 for tok in toks if tok in t)
    # pieni boost, ei liian aggressiivinen
    return 1.0 + min(0.30, hits * 0.08)

def _keyword_hits(q: str, text: str) -> int:
    toks = _tokens(q)
    if not toks:
        return 0
    t = (text or "").lower()
    return sum(1 for tok in toks if tok in t)


def retrieve(question: str, system_filter: str = "", top_k: int = TOP_K) -> List[RetrievedChunk]:
    con = _db()
    cur = con.cursor()

    qvec = embed_texts([question])[0]

    if system_filter:
        rows = cur.execute("""
            SELECT c.note_id, c.note_title, c.system, c.device, c.tags, c.source_type, c.source_name,
                   c.chunk_index, c.chunk_text, c.doc_key, c.keywords, c.entities, e.vec
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.id
            WHERE c.system = ?
        """, (system_filter.lower().strip(),)).fetchall()
    else:
        rows = cur.execute("""
            SELECT c.note_id, c.note_title, c.system, c.device, c.tags, c.source_type, c.source_name,
                   c.chunk_index, c.chunk_text, c.doc_key, c.keywords, c.entities, e.vec
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.id
        """).fetchall()

    scored: List[RetrievedChunk] = []
    toks = _tokens(question)
    for note_id, title, system, device, tags, stype, sname, cidx, ctext, dkey, kw, ent, vec_blob in rows:
        vec = _deserialize_vec(vec_blob)
        base = _cosine(qvec, vec)
        if toks:
            meta_text = " ".join([title or "", system or "", tags or "", sname or ""])
            hits = _keyword_hits(question, ctext + " " + meta_text)
            if hits == 0 and base < 0.25:
                continue
        s = base * _boilerplate_penalty(ctext) * _keyword_boost(question, ctext)
        if s < MIN_SCORE:
            continue
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
            doc_key=dkey or note_id,
            keywords=kw or "[]",
            entities=ent or "[]",
            score=float(s),
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def _build_context(chunks: List[RetrievedChunk]) -> str:
    parts = []
    total_chars = 0
    total_tokens = 0
    per_doc: Dict[str, int] = {}

    def _est_tokens(s: str) -> int:
        return max(1, len(s) // 4)

    def _doc_type_from_tags(tags: str, source_type: str) -> str:
        # Doc type is read only from metadata tags; default to "note" to avoid guessing.
        for raw in (tags or "").split(","):
            t = raw.strip().lower()
            if not t:
                continue
            if t in ALLOWED_DOC_TYPES:
                return t
            if ":" in t:
                _k, v = t.split(":", 1)
                if v in ALLOWED_DOC_TYPES:
                    return v
            if "=" in t:
                _k, v = t.split("=", 1)
                if v in ALLOWED_DOC_TYPES:
                    return v
        if source_type == "note":
            return "note"
        return "note"

    for ch in chunks:
        doc_key = ch.doc_key or ch.note_id
        per_doc[doc_key] = per_doc.get(doc_key, 0) + 1
        if per_doc[doc_key] > 2:
            continue

        page_hint = ""
        if ch.source_type == "attachment" and ch.chunk_index >= 1000:
            page_hint = f", page={ch.chunk_index//1000}"

        doc_id = ch.doc_key or ch.note_id
        doc_name = ch.note_title or ch.note_id
        if ch.source_type == "attachment" and ch.source_name:
            doc_name = ch.source_name

        doc_type = _doc_type_from_tags(ch.tags or "", ch.source_type or "")
        block = (
            f"[LÄHDE {len(parts) + 1}]\n"
            f"- Dokumentin nimi: {doc_name} (id={doc_id}{page_hint})\n"
            f"- Dokumenttityyppi: {doc_type}\n"
            f"- Sisältö:\n{ch.chunk_text.strip()}\n"
        )
        block_tokens = _est_tokens(block)
        if total_chars + len(block) > MAX_CONTEXT_CHARS or total_tokens + block_tokens > MAX_CONTEXT_TOKENS:
            break
        parts.append(block)
        total_chars += len(block)
        total_tokens += block_tokens

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
    sync_index(include_attachments=True, verbose=False)
    sync_info = get_last_sync_info()
    if history and sync_info.get("deleted_doc_keys"):
        history = None
    chunks: List[RetrievedChunk] = []
    try:
        retriever = _get_retriever()
        raw = retriever.retrieve(question, system_filter=system_filter)
        active_docs = get_current_doc_keys(include_attachments=True)
        chunks = [
            RetrievedChunk(
                note_id=str(r.get("note_id", "")),
                note_title=str(r.get("note_title", "")),
                system=str(r.get("system", "")),
                device=str(r.get("device", "")),
                tags=str(r.get("tags", "")),
                source_type=str(r.get("source_type", "")),
                source_name=str(r.get("source_name", "")),
                chunk_index=int(r.get("chunk_index", 0)),
                chunk_text=str(r.get("chunk_text", "")),
                doc_key=str(r.get("doc_key", "")),
                keywords=str(r.get("keywords", "")),
                entities=str(r.get("entities", "")),
                score=float(r.get("score", 0.0)),
            )
            for r in raw
            if str(r.get("doc_key", "")) in active_docs
        ]
    except Exception:
        chunks = retrieve(question, system_filter=system_filter, top_k=TOP_K)
    context = _build_context(chunks)
    if not chunks or context.startswith("(Ei"):
        msg = (
            "1) Yhteenveto\n"
            "Materiaaleista ei löytynyt vastausta tähän kysymykseen.\n\n"
            "2) Toimintaohjeet (Step-by-step)\n"
            "1. Lisää aiheeseen liittyvä dokumentti tai muistiinpano tietopankkiin.\n"
            "2. Kokeile kysymystä uudelleen tarkemmilla hakusanoilla.\n\n"
            "3) Vianrajaus / huomioitavaa\n"
            "Jos tiedosto on uusi, varmista että indeksi on ajan tasalla.\n\n"
            "4) Lähteet: -"
        )
        return msg, []

    # Tiivis keskusteluhistoria (ei liian pitkä)
    hist_txt = ""
    if history:
        last = history[-6:]  # pidä viimeiset 6 vuoroparia
        lines = []
        for uq, aa in last:
            lines.append(f"Käyttäjä: {uq}\nAvustaja: {aa}")
        hist_txt = "\n\n".join(lines)

    # Säännöt vähentävät väärän lähdetyypin käyttöä ja ylitulkintaa.
    prompt = f"""Olet käytännönläheinen tekninen tuki ja kouluttaja. Vastaat käyttäjän kysymykseen HYÖDYLLISESTI ja SUORAAN käyttäen annettua kontekstia.

TÄRKEÄ PERIAATE:
- ÄLÄ sano “katso manuaalista/lähteestä”. Sinun tehtävä on nimenomaan POIMIA ja TIIVISTÄÄ relevantti tieto kontekstista ja muotoilla siitä vastaus.
- Saat käyttää vain sitä sisältöä, joka löytyy kontekstista. Voit kuitenkin selittää askeleet selkeämmin (järjestää ne, nimetä vaiheet), kunhan et keksi uusia toimintoja tai asetuksia.
- Jos konteksti ei sisällä vastausta, kerro selkeästi että materiaaleista ei löytynyt vastausta.

ENNEN VASTAAMISTA:
1) Määrittele, koskeeko kysymys ensisijaisesti lakia, sisäistä ohjetta vai teknistä käyttöä.
2) Tarkista, sisältävätkö annetut lähteet tämän tyyppistä aineistoa (Dokumenttityyppi-kenttä).
3) Jos sopivaa lähdettä ei ole, sano selkeästi: "Tietoa ei löydy annetusta aineistosta." ÄLÄ sovella muun tyyppistä aineistoa.

YLITULKINNAN ESTO:
- ÄLÄ tee oletuksia tai analogioita lähteiden ulkopuolelta.
- ÄLÄ sovella ohjetta toiseen kontekstiin kuin mihin se on tarkoitettu.
- ÄLÄ täydennä puuttuvaa tietoa yleisellä tiedolla.
- Jos tieto puuttuu, vastaa että tietoa ei löydy annetusta aineistosta.

RAJAUS:
Vastaa kysymykseen VAIN annettujen lähteiden perusteella.
Jos vastaus vaatii ulkopuolista tietoa, ilmoita ettei aineisto riitä.

DETERMINISTINEN VASTAUS:
- Käytä vain väitelauseita, joille löytyy suora tuki lähteistä.
- Liitä jokaisen pääväitteen perään lähdeviite (doc_id tai nimi).
- ÄLÄ käytä sanoja kuten "yleensä", "tyypillisesti", "todennäköisesti".

TYYLI:
- Vastaa suomeksi.
- Jos kysymys pyytää ohjeita tai ongelmanratkaisua, kirjoita aina selkeät step-by-step vaiheet numeroituna.
- Jos tarvitset tarkennuksen (esim. versio/valikkopolku puuttuu), kysy lopussa 1–2 täsmäkysymystä, mutta anna silti paras mahdollinen ohje jo nyt.
- Jos löydät relevantit UI-termit (valikon nimet, napit), säilytä ne alkuperäisessä muodossa.

KYSYMYS:
{question}

KESKUSTELUHISTORIA (viimeisimmät, jos jatkokysymyksiä):
{hist_txt if hist_txt else "(ei historiaa)"}

KONTEKSTI (muotoiltu [LÄHDE i] -lohkoina; Dokumenttityyppi on metadata):
{context}

PALAUTUS:
Kirjoita vastaus rakenteella:
1) Yhteenveto (1–3 lausetta)
2) Toimintaohjeet (Step-by-step)
3) Vianrajaus / huomioitavaa (vain jos relevanttia)
4) Lähteet: listaa käytetyt doc_id:t tai dokumentin nimet
5) Luotettavuusarvio:
- Perustuuko vastaus suoraan lähteisiin: kyllä/ei
- Puuttuuko oleellista tietoa: kyllä/ei
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

_retriever: Optional[HybridRetriever] = None

def _bump_index_version() -> None:
    global _index_version
    _index_version += 1
    if _retriever is not None:
        _retriever.set_index_version(_index_version)

def _reset_retriever_cache() -> None:
    global _retriever
    _retriever = None

def _get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        cfg = RetrievalConfig(
            top_k_vector=TOP_K_VECTOR,
            top_k_bm25=TOP_K_BM25,
            weight_vector=WEIGHT_VECTOR,
            weight_bm25=WEIGHT_BM25,
            max_chunks_per_doc=MAX_CHUNKS_PER_DOC,
            use_mmr=USE_MMR,
            use_rerank=USE_RERANK,
            rerank_top_k=RERANK_TOP_K,
            final_top_n=FINAL_TOP_N,
            debug=DEBUG_RETRIEVAL,
        )
        _retriever = HybridRetriever(DB_PATH, BM25_PATH, embed_texts, cfg)
        _retriever.set_index_version(_index_version)
    return _retriever
def debug_retrieve(question: str, system_filter: str = ""):
    sync_index(include_attachments=True, verbose=False)
    try:
        retriever = _get_retriever()
        raw = retriever.retrieve(question, system_filter=system_filter)
        active_docs = get_current_doc_keys(include_attachments=True)
        chunks = [
            RetrievedChunk(
                note_id=str(r.get("note_id", "")),
                note_title=str(r.get("note_title", "")),
                system=str(r.get("system", "")),
                device=str(r.get("device", "")),
                tags=str(r.get("tags", "")),
                source_type=str(r.get("source_type", "")),
                source_name=str(r.get("source_name", "")),
                chunk_index=int(r.get("chunk_index", 0)),
                chunk_text=str(r.get("chunk_text", "")),
                doc_key=str(r.get("doc_key", "")),
                keywords=str(r.get("keywords", "")),
                entities=str(r.get("entities", "")),
                score=float(r.get("score", 0.0)),
            )
            for r in raw
            if str(r.get("doc_key", "")) in active_docs
        ]
    except Exception:
        chunks = retrieve(question, system_filter=system_filter, top_k=TOP_K)
    print("\nTOP CHUNKS:")
    for ch in chunks:
        print("="*60)
        print(f"score={ch.score:.3f} note_id={ch.note_id} source={ch.source_type} name={ch.source_name}")
        print(ch.chunk_text[:500])
