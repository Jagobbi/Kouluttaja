from src.notes import add_note

def run_cli():
    print("\nTietopankki")
    print("1) Lisää muistiinpano")
    print("2) Poistu")

    choice = input("Valinta: ").strip()

    if choice == "1":
        add_note()
    else:
        print("Näkemiin!")