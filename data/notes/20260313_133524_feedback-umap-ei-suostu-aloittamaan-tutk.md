---
id: "20260313_133524_feedback-umap-ei-suostu-aloittamaan-tutk"
title: "Feedback: umap ei suostu aloittamaan tutkausta kun painan play"
system: "umap"
device: ""
tags: [tutkaus, play, ongelma, feedback]
created_at: "2026-03-13T13:35:24"
updated_at: "2026-03-13T13:35:24"
linked_files: []
---
Kysymys:
umap ei suostu aloittamaan tutkausta kun painan play

AI-vastaus:
1) Yhteenveto  
Umapsissa tutka ei käynnisty "play"-painikkeella, jos yhteys tai järjestelmän asetukset eivät ole täysin kunnossa. On varmistettava, että antenni, tutka ja tabletit ovat käynnistettyinä ja liitettyinä oikein, antennikorkeus on asetettu, GPS-signaali toimii ja radar system -välilehden ilmoitukset ovat kunnossa.

2) Toimintaohjeet (Step-by-step)  
1. Varmista, että IDS Stream DP tutka on käynnistetty virtapainikkeesta (valo muuttuu siniseksi).  
2. Tarkista, että datasignaali kulkee: tutkasta tuleva kaapeli on liitetty oikein tabletin ethernet-porttiin.  
3. Käynnistä Panasonic-tabletti ja avaa uMap-Logger -sovellus.  
4. Tarkista radar system- ja GPS-välilehdillä:  
   - GPS-signaalin laatu: GPS:n tulee antaa korjattu RTK-signaali (esim. 5 Hz päivitys).  
   - Radar system -välilehdellä ei saa olla virheilmoituksia, kuten PPS enabled/disablen häiriöitä.  
5. Varmista antennikorkeus on fyysisesti ja uMap-loggerissa asetettu oikein, koska virheellinen antennikorkeus voi estää tutkan datan keruun.  
6. Leica Captivate -tabletti ja antenni tulee olla yhdistettynä Bluetooth- tai hotspot-yhteydellä ja RTK-virran käynnistettynä Captivaten sihdin symbolista. Oikea yhteys näkyy tarkkuuden tippumisena alle 0.1 metriin.  
7. Luo uMap-Loggerissa uusi projekti ja paina play-painiketta. Jos tutka ei ala kerätä dataa, tee yllä olevat tarkistukset uudelleen tai tutka ja yhteydet voivat olla vialliset.  
8. Jos tilanne ei korjaannu, tarkista antennin ja tutkan fyysinen ja ohjelmallinen liittymä, ja että virtapankit ja akut ovat kunnossa.

3) Vianrajaus / huomioitavaa  
- Jos radar system -välilehti herjaa, esimerkiksi PPS enabled/disbabled, yhteys ei ole kunnossa.  
- GPS-signaalin puute estää tutkan käynnistymisen.  
- Varmista, että Bluetooth-yhteys Leica Captivate -tabletilla toimii ja RTK virta on päällä.  
- Seuraa uMap-loggerista antennin sijaintia, sen pitää pysyä vakaana tutkauksen aikana.  
- Tutka vaatii oikeat fyysiset kytkennät ja laitteiston; puuttuvat tai väärät yhdistykset estävät tutkan käynnistyksen.

4) Lähteet:  
- 20260115_145913_ids-stream-dp-leica-gs20-ja-leica-captiv::note (Lähteet 1, 2, 8)  
- 20260115_145913_uMap-Logger 1_8 Users Manual.pdf (Lähde 9)

5) Luotettavuusarvio:  
- Perustuuko vastaus suoraan lähteisiin: kyllä  
- Puuttuuko oleellista tietoa: ei

Kayttajan palaute / ratkaisu:
-

Tila: Kyllä
