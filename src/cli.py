from src.notes import add_note, list_notes, search_notes

def run_cli():
    while True:
        print("\nTietopankki")
        print("1) Lisää muistiinpano")
        print("2) Listaa muistiinpanot")
        print("3) Hae muistiinpanoja")
        print("4) Poistu")

        choice = input("Valinta: ").strip()

        if choice == "1":
            add_note()
        elif choice == "2":
            list_notes()
        elif choice == "3":
            system = input("Hae järjestelmällä (tyhjä = ei suodatusta): ").strip()
            tag = input("Hae tagilla (tyhjä = ei suodatusta): ").strip()
            text_q = input("Hae tekstillä (tyhjä = ei suodatusta): ").strip()
            search_notes(system=system, tag=tag, text_query=text_q)
        elif choice == "4":
            print("Näkemiin!")
            break
        else:
            print("Virheellinen valinta.")
