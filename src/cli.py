from src.kb import (
    _normalize_tags,
    attach_file_to_note,
    create_note,
    export_index_jsonl,
    list_notes,
    read_note,
)

from src.ai import rebuild_index, answer_with_gpt


def _print_note_line(m):
    tags = ", ".join(m.tags) if m.tags else "-"
    files = len(m.linked_files) if m.linked_files else 0
    print(f"- {m.id} | {m.title} | system={m.system} | tags={tags} | files={files}")


def run_cli():
    chat_history = []  # list of (question, answer)

    while True:
        print("\nTietopankki")
        print("1) Lisää muistiinpano")
        print("2) Listaa muistiinpanot")
        print("3) Näytä muistiinpano")
        print("4) Liitä tiedosto muistiinpanoon")
        print("5) Vie index.jsonl (AI/RAG)")
        print("6) Rakenna AI-indeksi (embeddings + liitteet)")
        print("7) Kysy AI:lta (chat, jatkokysymykset)")
        print("8) Tyhjennä chat-historia")
        print("9) Poistu")

        choice = input("Valinta: ").strip()

        if choice == "1":
            title = input("Otsikko: ").strip()
            system = input("Järjestelmä (esim. sap / zebra / jira): ").strip()
            device = input("Laite (valinnainen): ").strip()
            tags_in = input("Tagit (pilkulla eroteltu, valinnainen): ").strip()
            tags = _normalize_tags(tags_in)
            print("Kirjoita muistiinpano (lopeta tyhjällä rivillä):")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            body = "\n".join(lines)

            meta = create_note(title=title, system=system, device=device, tags=tags, body=body)
            print("\n✅ Muistiinpano luotu:")
            _print_note_line(meta)

        elif choice == "2":
            notes = list_notes(limit=200)
            if not notes:
                print("\nEi muistiinpanoja.")
            else:
                print("\nMuistiinpanot:")
                for m in notes:
                    _print_note_line(m)

        elif choice == "3":
            note_id = input("Anna muistiinpanon id: ").strip()
            meta, body = read_note(note_id)
            if not meta:
                print("\nMuistiinpanoa ei löydy.")
            else:
                print("\n" + "=" * 70)
                print(f"{meta.title} ({meta.id})")
                print("=" * 70)
                print(f"system: {meta.system}")
                print(f"device: {meta.device}")
                print(f"tags: {', '.join(meta.tags) if meta.tags else '-'}")
                print(f"created_at: {meta.created_at}")
                print(f"updated_at: {meta.updated_at}")
                if meta.linked_files:
                    print("linked_files:")
                    for lf in meta.linked_files:
                        print(f"  - {lf}")
                else:
                    print("linked_files: -")
                print("\n---\n")
                print(body or "")
                print("\n" + "=" * 70)

        elif choice == "4":
            note_id = input("Muistiinpanon id: ").strip()
            path = input(r"Tiedoston polku (esim. C:\temp\ohje.pdf): ").strip()
            meta, msg = attach_file_to_note(note_id, path)
            print("\n" + msg)
            if meta:
                _print_note_line(meta)
                print("Huom: aja kohta 6 uudelleen, jotta liite tulee mukaan AI-hakuun.")

        elif choice == "5":
            out = export_index_jsonl()
            print(f"\n✅ Luotu: {out}")

        elif choice == "6":
            print("\nRakennetaan AI-indeksi (muistiinpanot + tuetut liitteet: PDF/DOCX/TXT/MD/CSV/PNG/JPG/WEBP)...")
            rebuild_index(include_attachments=True, verbose=True)

        elif choice == "7":
            print("\nAI-chat (tyhjä kysymys = takaisin valikkoon)")
            sysf = input("Rajaa järjestelmään (tyhjä = ei): ").strip()
            while True:
                q = input("\nKysymys: ").strip()
                if not q:
                    break
                try:
                    answer, used = answer_with_gpt(q, system_filter=sysf, history=chat_history)
                    print("\n" + answer)

                    # pidä historia
                    chat_history.append((q, answer))

                except Exception as e:
                    print("\n❌ AI-kysely epäonnistui:")
                    print(str(e))
                    print("Vinkki: varmista OPENAI_API_KEY ja että indeksi on rakennettu (kohta 6).")
                    break

        elif choice == "8":
            chat_history = []
            print("\n✅ Chat-historia tyhjennetty.")

        elif choice == "9":
            print("Näkemiin!")
            break

        else:
            print("Virheellinen valinta.")
