from datetime import datetime
from pathlib import Path

NOTES_DIR = Path("data/notes")

def add_note():
    print("\nUusi muistiinpano")

    system = input("Järjestelmä: ").strip()
    device = input("Laite (valinnainen): ").strip()
    tags = input("Tagit (pilkulla eroteltu): ").strip()
    content = input("Kirjoita muistiinpano:\n")

    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"note_{timestamp}.md"
    filepath = NOTES_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"system: {system}\n")
        f.write(f"device: {device}\n")
        f.write(f"tags: [{tags}]\n")
        f.write(f"date: {datetime.now().isoformat()}\n")
        f.write("---\n\n")
        f.write(content)

    print(f"\n✅ Muistiinpano tallennettu: {filepath}")

from pathlib import Path
import re

NOTES_DIR = Path("data/notes")

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _parse_meta(text: str) -> dict:
    """
    Erittäin kevyt metaparseri:
    - Etsii '---' ... '---' välistä rivit muotoa key: value
    - Tagit voidaan olla muodossa: tags: [a, b] TAI tags: a, b
    """
    meta = {}
    parts = text.split("---")
    if len(parts) >= 3:
        header = parts[1]
        for line in header.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()

    # normalisoi tags -> list
    tags_raw = meta.get("tags", "")
    tags_raw = tags_raw.strip()
    if tags_raw.startswith("[") and tags_raw.endswith("]"):
        tags_raw = tags_raw[1:-1]
    tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    meta["tags_list"] = tags

    meta["system"] = (meta.get("system", "")).strip().strip('"').strip("'").lower()
    meta["device"] = (meta.get("device", "")).strip().strip('"').strip("'")
    return meta

def list_notes(limit: int = 30):
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)  # uusimmat ensin
    if not files:
        print("\nEi muistiinpanoja vielä.")
        return

    print(f"\nMuistiinpanot (näytetään max {limit}):")
    for p in files[:limit]:
        text = _read_text(p)
        meta = _parse_meta(text)
        system = meta.get("system", "")
        tags = ", ".join(meta.get("tags_list", []))
        print(f"- {p.name} | system: {system} | tags: {tags}")

def search_notes(system: str = "", tag: str = "", text_query: str = ""):
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    system = (system or "").strip().lower()
    tag = (tag or "").strip().lower()
    text_query = (text_query or "").strip().lower()

    results = []
    for p in files:
        content = _read_text(p)
        meta = _parse_meta(content)

        if system and meta.get("system", "") != system:
            continue
        if tag and tag not in meta.get("tags_list", []):
            continue
        if text_query and text_query not in content.lower():
            continue

        results.append((p, meta))

    if not results:
        print("\nEi osumia hakuehdoilla.")
        return

    print(f"\nOsumat ({len(results)}):")
    for p, meta in results:
        system_out = meta.get("system", "")
        tags_out = ", ".join(meta.get("tags_list", []))
        print(f"- {p.name} | system: {system_out} | tags: {tags_out}")
