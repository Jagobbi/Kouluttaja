from __future__ import annotations

import json
import math
import pickle
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class RetrievalConfig:
    top_k_vector: int = 60
    top_k_bm25: int = 60
    weight_vector: float = 0.55
    weight_bm25: float = 0.45
    max_chunks_per_doc: int = 4
    use_mmr: bool = True
    mmr_lambda: float = 0.7
    use_rerank: bool = False
    rerank_top_k: int = 50
    final_top_n: int = 14
    debug: bool = False


class _LRUCache:
    def __init__(self, max_size: int = 256):
        self.max_size = max_size
        self._data: OrderedDict[str, object] = OrderedDict()

    def get(self, key: str):
        if key not in self._data:
            return None
        val = self._data.pop(key)
        self._data[key] = val
        return val

    def set(self, key: str, value: object) -> None:
        if key in self._data:
            self._data.pop(key)
        self._data[key] = value
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)


def _tokenize(text: str) -> List[str]:
    import re
    tokens = re.findall(r"[A-Za-z0-9_./:\\-]{2,}", (text or "").lower())
    stop = {
        "the", "and", "for", "with", "this", "that", "from", "into", "your",
        "you", "are", "was", "were", "how", "what", "when", "where", "which",
        "tai", "että", "voi", "mitä", "mikä", "miksi", "kuinka", "joka",
        "joten", "kuten", "sekä", "että", "vielä", "näin", "tämä", "tuo",
        "they", "them", "then", "than", "has", "have", "had",
    }
    return [t for t in tokens if t not in stop]


def _deserialize_vec(blob: bytes) -> List[float]:
    import struct
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


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


def build_bm25_index(db_path: Path, bm25_path: Path) -> bool:
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        return False

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    rows = cur.execute("SELECT id, chunk_text FROM chunks ORDER BY id").fetchall()
    con.close()

    chunk_ids: List[int] = []
    tokenized: List[List[str]] = []
    for cid, text in rows:
        toks = _tokenize(text)
        chunk_ids.append(int(cid))
        tokenized.append(toks)

    bm25 = BM25Okapi(tokenized)
    bm25_path.parent.mkdir(parents=True, exist_ok=True)
    with bm25_path.open("wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": chunk_ids}, f)
    return True


def _load_bm25(bm25_path: Path):
    if not bm25_path.exists():
        return None
    try:
        with bm25_path.open("rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _minmax(scores: Dict[int, float]) -> Dict[int, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    mn = min(vals)
    mx = max(vals)
    if mx == mn:
        return {k: 0.0 for k in scores}
    return {k: (v - mn) / (mx - mn) for k, v in scores.items()}


def _mmr_select(
    items: List[int],
    scores: Dict[int, float],
    vectors: Dict[int, List[float]],
    top_n: int,
    lamb: float,
) -> List[int]:
    if not items:
        return []
    selected: List[int] = []
    candidates = items[:]
    while candidates and len(selected) < top_n:
        best_id = None
        best_val = -1e9
        for cid in candidates:
            rel = scores.get(cid, 0.0)
            if not selected:
                mmr = rel
            else:
                sims = []
                for sid in selected:
                    if cid in vectors and sid in vectors:
                        sims.append(_cosine(vectors[cid], vectors[sid]))
                max_sim = max(sims) if sims else 0.0
                mmr = lamb * rel - (1.0 - lamb) * max_sim
            if mmr > best_val:
                best_val = mmr
                best_id = cid
        if best_id is None:
            break
        selected.append(best_id)
        candidates.remove(best_id)
    return selected


class HybridRetriever:
    def __init__(
        self,
        db_path: Path,
        bm25_path: Path,
        embed_fn,
        config: RetrievalConfig,
        query_cache_size: int = 256,
        embedding_cache_size: int = 256,
    ):
        self.db_path = Path(db_path)
        self.bm25_path = Path(bm25_path)
        self.embed_fn = embed_fn
        self.config = config
        self._query_cache = _LRUCache(max_size=query_cache_size)
        self._embed_cache = _LRUCache(max_size=embedding_cache_size)

        self._reranker = None
        if self.config.use_rerank:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            except Exception:
                self._reranker = None
        self._index_version = 0

    def set_index_version(self, version: int) -> None:
        self._index_version = int(version)

    def _embed_query(self, q: str) -> List[float]:
        key = q.strip().lower()
        cached = self._embed_cache.get(key)
        if cached is not None:
            return cached
        vec = self.embed_fn([q])[0]
        self._embed_cache.set(key, vec)
        return vec

    def retrieve(self, question: str, system_filter: str = "") -> List[Dict[str, object]]:
        cache_key = f"{self._index_version}||{question.strip().lower()}||{system_filter.strip().lower()}"
        cached = self._query_cache.get(cache_key)
        if cached is not None:
            return cached

        con = sqlite3.connect(self.db_path)
        cur = con.cursor()

        qvec = self._embed_query(question)
        q_tokens = _tokenize(question)

        bm25_data = _load_bm25(self.bm25_path)
        bm25_scores: Dict[int, float] = {}
        if bm25_data is not None:
            bm25 = bm25_data.get("bm25")
            chunk_ids = bm25_data.get("chunk_ids") or []
            if bm25 and chunk_ids:
                scores = bm25.get_scores(q_tokens)
                scored = sorted(
                    zip(chunk_ids, scores), key=lambda x: x[1], reverse=True
                )[: self.config.top_k_bm25]
                bm25_scores = {int(cid): float(s) for cid, s in scored}

        if system_filter:
            rows = cur.execute("""
                SELECT c.id, c.note_id, c.note_title, c.system, c.device, c.tags,
                       c.source_type, c.source_name, c.chunk_index, c.chunk_text,
                       c.doc_key, c.keywords, c.entities, e.vec
                FROM chunks c
                JOIN embeddings e ON e.chunk_id = c.id
                WHERE c.system = ?
            """, (system_filter.lower().strip(),)).fetchall()
        else:
            rows = cur.execute("""
                SELECT c.id, c.note_id, c.note_title, c.system, c.device, c.tags,
                       c.source_type, c.source_name, c.chunk_index, c.chunk_text,
                       c.doc_key, c.keywords, c.entities, e.vec
                FROM chunks c
                JOIN embeddings e ON e.chunk_id = c.id
            """).fetchall()

        vec_scores: Dict[int, float] = {}
        vectors: Dict[int, List[float]] = {}
        meta: Dict[int, Dict[str, object]] = {}
        for row in rows:
            (cid, note_id, title, system, device, tags, stype, sname, cidx,
             ctext, doc_key, kw, ent, vec_blob) = row
            vec = _deserialize_vec(vec_blob)
            score = _cosine(qvec, vec)
            vec_scores[int(cid)] = float(score)
            vectors[int(cid)] = vec
            meta[int(cid)] = {
                "note_id": note_id,
                "note_title": title,
                "system": system,
                "device": device,
                "tags": tags,
                "source_type": stype,
                "source_name": sname or "",
                "chunk_index": int(cidx),
                "chunk_text": ctext,
                "doc_key": doc_key or note_id,
                "keywords": kw,
                "entities": ent,
            }

        if vec_scores:
            vec_scores = dict(sorted(vec_scores.items(), key=lambda x: x[1], reverse=True)[: self.config.top_k_vector])

        candidate_ids = set(vec_scores.keys()) | set(bm25_scores.keys())
        if not candidate_ids:
            con.close()
            self._query_cache.set(cache_key, [])
            return []

        missing_ids = [cid for cid in candidate_ids if cid not in meta]
        if missing_ids:
            qmarks = ",".join(["?"] * len(missing_ids))
            extra = cur.execute(f"""
                SELECT c.id, c.note_id, c.note_title, c.system, c.device, c.tags,
                       c.source_type, c.source_name, c.chunk_index, c.chunk_text,
                       c.doc_key, c.keywords, c.entities
                FROM chunks c
                WHERE c.id IN ({qmarks})
            """, missing_ids).fetchall()
            for row in extra:
                (cid, note_id, title, system, device, tags, stype, sname, cidx,
                 ctext, doc_key, kw, ent) = row
                meta[int(cid)] = {
                    "note_id": note_id,
                    "note_title": title,
                    "system": system,
                    "device": device,
                    "tags": tags,
                    "source_type": stype,
                    "source_name": sname or "",
                    "chunk_index": int(cidx),
                    "chunk_text": ctext,
                    "doc_key": doc_key or note_id,
                    "keywords": kw,
                    "entities": ent,
                }

        con.close()

        vec_norm = _minmax(vec_scores)
        bm25_norm = _minmax(bm25_scores)

        query_entities = set(q_tokens)
        combined: Dict[int, float] = {}
        for cid in candidate_ids:
            vs = vec_norm.get(cid, 0.0)
            bs = bm25_norm.get(cid, 0.0)
            base = self.config.weight_vector * vs + self.config.weight_bm25 * bs

            ent_boost = 0.0
            ent_raw = meta.get(cid, {}).get("entities") or "[]"
            kw_raw = meta.get(cid, {}).get("keywords") or "[]"
            try:
                ents = set(json.loads(ent_raw))
            except Exception:
                ents = set()
            try:
                kws = set(json.loads(kw_raw))
            except Exception:
                kws = set()
            if query_entities and (query_entities & ents or query_entities & kws):
                ent_boost = 0.08
            combined[cid] = base + ent_boost

        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        limited: List[int] = []
        per_doc: Dict[str, int] = {}
        for cid, _score in ranked:
            doc_key = str(meta.get(cid, {}).get("doc_key") or "")
            per_doc[doc_key] = per_doc.get(doc_key, 0) + 1
            if per_doc[doc_key] > self.config.max_chunks_per_doc:
                continue
            limited.append(cid)

        if self.config.use_mmr and limited:
            mmr_ids = _mmr_select(
                limited,
                combined,
                vectors,
                top_n=min(self.config.final_top_n, len(limited)),
                lamb=self.config.mmr_lambda,
            )
            limited = mmr_ids + [cid for cid in limited if cid not in mmr_ids]

        top_ids = limited[: max(self.config.rerank_top_k, self.config.final_top_n)]
        if self._reranker and top_ids:
            pairs = [(question, meta[cid]["chunk_text"]) for cid in top_ids]
            try:
                scores = self._reranker.predict(pairs)
                reranked = sorted(zip(top_ids, scores), key=lambda x: x[1], reverse=True)
                top_ids = [cid for cid, _ in reranked]
            except Exception:
                pass

        final_ids = top_ids[: self.config.final_top_n]
        results = []
        for cid in final_ids:
            item = meta.get(cid, {}).copy()
            item["chunk_id"] = cid
            item["score"] = float(combined.get(cid, 0.0))
            results.append(item)

        if self.config.debug:
            print(
                f"[retrieval] vec={len(vec_scores)} bm25={len(bm25_scores)} "
                f"candidates={len(candidate_ids)} final={len(results)}"
            )

        self._query_cache.set(cache_key, results)
        return results
