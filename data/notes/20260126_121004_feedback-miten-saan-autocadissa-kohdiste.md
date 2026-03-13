---
id: "20260126_121004_feedback-miten-saan-autocadissa-kohdiste"
title: "Feedback: Miten saan autocadissa kohdistettua aineiston oikeaan koordinaatistoon"
system: "autocad"
device: ""
tags: [autocad, koordinaatisto, gps, kohdistaminen, feedback]
created_at: "2026-01-26T12:10:04"
updated_at: "2026-01-26T12:10:04"
linked_files: []
---
Kysymys:
Miten saan autocadissa kohdistettua aineiston oikeaan koordinaatistoon ja samaan paikkaan mitattujen gps pisteiden kanssa

AI-vastaus:
1) Yhteenveto  
AutoCADissa saat kohdistettua Iqmapsista tuodun aineiston GPS-pisteiden kanssa oikeaan koordinaatistoon käyttämällä UNITS-komentoa, XREF-liitosta ja ALIGN-komentoa. Tämä siirtää aineiston oikeaan paikkaan XY-tasossa, mutta Z-tasossa tehdään korjaukset erillisillä skripteillä.

2) Toimintaohjeet (Step-by-step)  
1. Varmista, että molemmat aineistot (Iqmapsista tuotavat putket ja GPS-mittaukset) ovat samassa yksikössä (metreissä) komennolla UNITS.  
2. Avaa AutoCADissa putket sisältävä aineisto.  
3. Liitä GPS-pisteitä sisältävä DWG-aineisto XREF-komennolla.  
4. Tee kohdistus valitsemalla aktiiviseksi Iqmapsista tuotettu putkiaineisto.  
5. Käynnistä ALIGN-komento.  
6. Valitse ensimmäinen piste (esim. kaivon kansi) Iqmapsin aineistosta.  
7. Valitse vastaava piste XREF:illä tuotusta GPS-aineistosta.  
8. Toista pisteiden valinta vielä toiselle pisteelle.  
9. Paina Enter. Kun ohjelma kysyy skaalauksesta, valitse NO.  
10. Aineisto siirtyy oikeaan paikkaan XY-tasossa.  
11. Jos syötät koordinaatit manuaalisesti ALIGN-komennossa pisteiden klikkaamisen sijaan, käytä "#" merkkiä ennen koordinaatteja varmistaaksesi niiden lukemisen koordinaatteina.  
12. Huomioi, että Z-ten kerroksen eli korkeustason korjaus (geoidikorjaus) tehdään erikseen AutoCAD-skriptillä, jota varten on erilliset ohjeet OneDrivessa.  

3) Vianrajaus / huomioitavaa  
- ALIGN-komento kohdistaa aineiston vain XY-tasossa, ei automaattisesti korkeudessa (Z).  
- Manuaalisten koordinaattien syötössä käytä "#" ennen koordinaattia.  
- Tarkista ennen kohdistusta, että yksiköt ovat samoja.  

4) Lähteet:  
- Iqmapsilla pirrettyjen putkien kohdistaminen gps:llä mitattujen pisteiden kanssa auto-cadissa (doc_id=20260126_120651_iqmapsilla-pirrettyjen-putkien-kohdistam::note)  

5) Luotettavuusarvio:  
- Perustuuko vastaus suoraan lähteisiin: kyllä  
- Puuttuuko oleellista tietoa: ei

Kayttajan palaute / ratkaisu:
-

Tila: Kyllä
