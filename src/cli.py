def run_cli():
    print("Tietopankki käynnissä")
    print("1) Lisää muistiinpano")
    print("2) Listaa muistiinpanot")

    choice = input("Valinta: ")

    if choice == "1":
        print("Muistiinpanon lisäys (tulossa)")
    elif choice == "2":
        print("Listaus (tulossa)")
    else:
        print("Virheellinen valinta")
