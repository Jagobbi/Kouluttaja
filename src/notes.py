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
