from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

DATA_DIR = Path("data")
NOTES_DIR = DATA_DIR / "notes"
DOCS_DIR = DATA_DIR / "docs"

ALLOWED_DOC_EXTS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp",
    ".csv", ".xlsx", ".pptx", ".zip", ".log"
}

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "note"

def _normalize_tags(tags_in: str) -> List[str]:
    parts = [t.strip().lower() for t in (tags_in or "").split(",")]
    tags = []
    for t in parts:
        if not t:
            continue
        # keep only safe-ish tag chars
        t2 = re.sub(r"[^a-z0-9åäö\-_ ]", "", t).strip()
        t2 = re.sub(r"\s+", "-", t2)
        if t2 and t2 not in tags:
            tags.append(t2)
    return tags

def _safe_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1F]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def ensure_dirs():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class NoteMeta:
    id: str
    title: str
    system: str
    device: str
    tags: List[str]
    created_at: str
    updated_at: str
    linked_files: List[str]  # relative paths like "docs/20260112_120000_file.pdf"

def _note_path(note_id: str) -> Path:
    return NOTES_DIR / f"{note_id}.md"

def _meta_to_frontmatter(meta: NoteMeta) -> str:
    # YAML-ish frontmatter (no external yaml lib needed)
    tags_str = "[" + ", ".join(meta.tags) + "]"
    files_str = "[" + ", ".join(meta.linked_files) + "]"
    lines = [
        "---",
        f'id: "{meta.id}"',
        f'title: "{meta.title}"',
        f'system: "{meta.system}"',
        f'device: "{meta.device}"',
        f"tags: {tags_str}",
        f'created_at: "{meta.created_at}"',
        f'updated_at: "{meta.updated_at}"',
        f"linked_files: {files_str}",
        "---",
        "",
    ]
    return "\n".join(lines)

def _parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """
    Returns (meta_dict, body).
    Very tolerant:
    - looks for first '---' block
    - parses lines 'key: value'
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    header = parts[1]
    body = parts[2].lstrip("\n")

    meta: Dict[str, str] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = v.strip()
    return meta, body

def _parse_list_value(v: str) -> List[str]:
    """
    Parses values like:
      [a, b, c]
    Returns list of strings.
    """
    if not v:
        return []
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    items = [x.strip().strip('"').strip("'") for x in v.split(",")]
    return [i for i in items if i]

def read_note(note_id: str) -> Tuple[Optional[NoteMeta], Optional[str]]:
    ensure_dirs()
    p = _note_path(note_id)
    if not p.exists():
        return None, None
    text = p.read_text(encoding="utf-8", errors="replace")
    meta_raw, body = _parse_frontmatter(text)

    note_id2 = meta_raw.get("id", "").strip().strip('"').strip("'") or note_id
    title = meta_raw.get("title", "").strip().strip('"').strip("'")
    system = meta_raw.get("system", "").strip().strip('"').strip("'")
    device = meta_raw.get("device", "").strip().strip('"').strip("'")
    tags = _parse_list_value(meta_raw.get("tags", ""))
    created_at = meta_raw.get("created_at", "").strip().strip('"').strip("'") or ""
    updated_at = meta_raw.get("updated_at", "").strip().strip('"').strip("'") or ""
    linked_files = _parse_list_value(meta_raw.get("linked_files", ""))

    meta = NoteMeta(
        id=note_id2,
        title=title,
        system=system,
        device=device,
        tags=[t.lower() for t in tags],
        created_at=created_at,
        updated_at=updated_at,
        linked_files=linked_files,
    )
    return meta, body

def create_note(
    title: str,
    system: str,
    device: str,
    tags: List[str],
    body: str,
) -> NoteMeta:
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _slugify(title)[:40]
    note_id = f"{ts}_{base}"

    now = _now_iso()
    meta = NoteMeta(
        id=note_id,
        title=title.strip(),
        system=system.strip().lower(),
        device=device.strip(),
        tags=tags,
        created_at=now,
        updated_at=now,
        linked_files=[],
    )

    content = _meta_to_frontmatter(meta) + (body or "").strip() + "\n"
    _note_path(note_id).write_text(content, encoding="utf-8")
    return meta

def update_note(meta: NoteMeta, body: str) -> None:
    meta.updated_at = _now_iso()
    content = _meta_to_frontmatter(meta) + (body or "").rstrip() + "\n"
    _note_path(meta.id).write_text(content, encoding="utf-8")

def list_notes(limit: int = 50) -> List[NoteMeta]:
    ensure_dirs()
    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    out: List[NoteMeta] = []
    for p in files[:limit]:
        note_id = p.stem
        meta, _body = read_note(note_id)
        if meta:
            out.append(meta)
    return out

def search_notes(system: str = "", tag: str = "", text_query: str = "", limit: int = 50) -> List[NoteMeta]:
    ensure_dirs()
    system = (system or "").strip().lower()
    tag = (tag or "").strip().lower()
    text_query = (text_query or "").strip().lower()

    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    results: List[NoteMeta] = []

    for p in files:
        note_id = p.stem
        meta, body = read_note(note_id)
        if not meta:
            continue

        if system and meta.system != system:
            continue
        if tag and tag not in [t.lower() for t in meta.tags]:
            continue
        if text_query:
            hay = (meta.title + "\n" + (body or "")).lower()
            if text_query not in hay:
                continue

        results.append(meta)
        if len(results) >= limit:
            break

    return results

def attach_file_to_note(note_id: str, source_path: str) -> Tuple[Optional[NoteMeta], str]:
    """
    Copies source file into data/docs/ with timestamped name, stores relative path in note metadata.
    Returns (updated_meta, message).
    """
    ensure_dirs()
    meta, body = read_note(note_id)
    if not meta:
        return None, f"Muistiinpanoa ei löydy id: {note_id}"

    src = Path(source_path).expanduser()
    if not src.exists() or not src.is_file():
        return None, f"Tiedostoa ei löydy: {src}"

    ext = src.suffix.lower()
    if ext and ext not in ALLOWED_DOC_EXTS:
        # allow unknown extensions too, but warn
        pass

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _safe_filename(src.name)
    dest_name = f"{ts}_{safe_name}"
    dest = DOCS_DIR / dest_name

    shutil.copy2(src, dest)
    rel = str(Path("docs") / dest_name).replace("\\", "/")

    if rel not in meta.linked_files:
        meta.linked_files.append(rel)

    update_note(meta, body or "")
    return meta, f"✅ Liitetty tiedosto: {rel}"

def delete_attachment(rel_path: str) -> Tuple[int, str]:
    """
    Removes attachment file and unlinks it from any notes.
    Returns (notes_updated_count, message).
    """
    ensure_dirs()
    rel = Path(rel_path.replace("\\", "/"))
    if rel.parts and rel.parts[0] == "data":
        rel = Path(*rel.parts[1:])
    if rel.parts and rel.parts[0] != "docs":
        rel = Path("docs") / rel

    full = DATA_DIR / rel
    updated = 0

    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    for p in files:
        note_id = p.stem
        meta, body = read_note(note_id)
        if not meta:
            continue
        if str(rel).replace("\\", "/") in meta.linked_files:
            meta.linked_files = [f for f in meta.linked_files if f != str(rel).replace("\\", "/")]
            update_note(meta, body or "")
            updated += 1

    if full.exists() and full.is_file():
        try:
            full.unlink()
        except Exception:
            return updated, f"Liitteen poisto epäonnistui: {full}"

    return updated, f"Poistettu liite: {rel}"

def delete_note(note_id: str, remove_files: bool = True) -> str:
    """
    Removes a note and optionally its linked files.
    """
    ensure_dirs()
    meta, _body = read_note(note_id)
    if not meta:
        return f"Muistiinpanoa ei l\u00f6ydy id: {note_id}"

    if remove_files and meta.linked_files:
        for lf in list(meta.linked_files):
            delete_attachment(lf)

    note_path = _note_path(note_id)
    if note_path.exists():
        try:
            note_path.unlink()
        except Exception:
            return f"Muistiinpanon poisto ep\u00e4onnistui: {note_path}"

    return f"Poistettu muistiinpano: {note_id}"

def export_index_jsonl(filepath: str = "data/index.jsonl", limit: int = 100000) -> str:
    """
    Makes a simple JSONL index for future AI/RAG:
    Each line: {id, title, system, device, tags, created_at, updated_at, linked_files, body}
    """
    ensure_dirs()
    out_path = Path(filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for p in files:
            meta, body = read_note(p.stem)
            if not meta:
                continue
            rec = {
                "id": meta.id,
                "title": meta.title,
                "system": meta.system,
                "device": meta.device,
                "tags": meta.tags,
                "created_at": meta.created_at,
                "updated_at": meta.updated_at,
                "linked_files": meta.linked_files,
                "body": body or "",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n >= limit:
                break

    return str(out_path)
