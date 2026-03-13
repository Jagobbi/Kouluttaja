---
id: "20260126_120651_iqmapsilla-pirrettyjen-putkien-kohdistam"
title: "Iqmapsilla pirrettyjen putkien kohdistaminen gps:llä mitattujen pisteiden kanssa auto-cadissa"
system: "autocad"
device: ""
tags: [iqmaps, gps, koordinaatit, kohdistaminen, xref, align]
created_at: "2026-01-26T12:06:51"
updated_at: "2026-01-26T12:06:51"
linked_files: []
---
Ongelmana oli, että iq-mapsista tuodun aineiston koordinaatit oli väärät ja halusin kohdistaa ne gps:llä mitattujen kaivojen kansien kanssa oikein. Aluksi varmista että molemmat aineistot (iq-mapsista tuodut putket ja gps:llä mitatut kaivojen kannet) ovat samassa yksikössä (metreissä). Tämä tapahtuu komennolle UNITS. Tämän jälkeen avaa erikseen cadissa putket sisältävä aineisto ja liitä gps:llä mitatut pisteet sisältävä dwg aineisto XREF komennolla. Nyt voit kohdistaa aineiston oikein komennolla ALIGN: valitse ensin aktiiviseksi iqmapsista tuotu putkiaineisto. Sitten valitse yksi piste (kaivon kansi) tästä aineistosta ja vastaava piste xrefillä tuodusta gps mittausaineistosta. Toista tämä toisella pisteellä. Paina enter ja valitse NO kun ohjelma kysyy skaalauksesta. Nyt aineisto pitäisi siirtyä oikeaan paikkaan. HUOM: jos align komentoa käyttäessä pisteiden klikkaamisen sijaan syötät koordinaatit manuaalisesti, muista käyttää "#" ennen koordinaattien syöttöä. Tämä varmistaa että ohjelma lukee syöttämäsi tiedot varmasti koordinaatteina. 

Tämä ohje auttaa vain siirtämään aineistoa x,y tasossa. Z-tasossa tehtävä geoidikorjaus täytyy tehdä erikseen hyödyntäen autocad scriptiä, joihin löytyy ohjeet onedrivestä.
