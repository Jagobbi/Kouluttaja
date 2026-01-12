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
    while True:
        print("\nTietopankki")
        print("1) Lisää muistiinpano")
        print("2) Listaa muistiinpanot")
        print("3) Näytä muistiinpano")
        print("4) Liitä tiedosto muistiinpanoon")
        print("5) Vie index.jsonl (AI/RAG)")
        print("6) Rakenna AI-indeksi (embeddings)")
        print("7) Kysy AI:lta (GPT)")
        print("8) Poistu")

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

        elif choice == "5":
            out = export_index_jsonl()
            print(f"\n✅ Luotu: {out}")

        elif choice == "6":
            print("\nRakennetaan AI-indeksi (tämä käyttää OpenAI Embeddings APIa)...")
            rebuild_index(verbose=True)

        elif choice == "7":
            q = input("\nKysymys: ").strip()
            sysf = input("Rajaa järjestelmään (tyhjä = ei): ").strip()
            try:
                answer, used = answer_with_gpt(q, system_filter=sysf)
                print("\n" + answer)
                # tulosta myös top chunkit debugina
                if used:
                    uniq = []
                    for ch in used:
                        if ch.note_id not in uniq:
                            uniq.append(ch.note_id)
                    print("\n(Lähteet / note_id): " + ", ".join(uniq))
            except Exception as e:
                print("\n❌ AI-kysely epäonnistui.")
                print(str(e))
                print("Varmista että OPENAI_API_KEY on asetettu ja että olet ajanut ensin kohdan 6 (AI-indeksi).")

        elif choice == "8":
            print("Näkemiin!")
            break

        else:
            print("Virheellinen valinta.")
