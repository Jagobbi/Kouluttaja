---
id: "20260115_145913_ids-stream-dp-leica-gs20-ja-leica-captiv"
title: "IDS Stream dp, Leica GS20 ja Leica captivaten valmistelu maastossa"
system: "ids"
device: "IDS Stream dp, Umap_logger, Leica captivate"
tags: [georadar, leica-gs20, leica-captivate, umis, rtk, gps]
created_at: "2026-01-15T14:59:13"
updated_at: "2026-01-15T14:59:15"
linked_files: [docs/20260115_145913_uMap-Logger 1_8 Users Manual.pdf, docs/20260115_145914_StreamDP Users Manual.pdf, docs/20260115_145915_991611_IDS_Georadar_Stream_DP_QG_V.1-0-0_en.pdf, docs/20260115_145915_R8_User+Manual_20240412_EN.pdf]
---
Tämä ohje koskee käyttämämme maatutkan (IDS georadar stream dp) käyttöä työmaalla. Varmista että sinulla on kaikki tarvittava laitteisto mukana: 
- IDS Stream Dp tutka ja sen työntökärry + 2 isompaa akkua
- leican antennikeppi (hiilikuitukeppi jossa korkeussäätö)
- Maatutkan ohjaukseen ja Umapsin käyttöön tarkoitettu tabletti (panasonic)
- Leica GS20 gps antenni + akku
- GPS:n hallintaan käytetty tabletti (leica captivate ohjelmisto)
- Virtapankki, jolla voi tarvittaessa ladata tabletteja (ei pakollinen, mutta vaikeissa olosuhteissa tablettien akku kuluu nopeasti)

Valmistelut:
Asenna suurempi panasonic tabletti tutkan karryyn sille kuuluvalle paikalle ja käynnistä tabletti. Liitä tutkasta tuleva kaapeli tabletin ethernet porttiin. Käynnistä tutka virtanapista, syttyy siniseksi kun käynnistyy. Kierrä GS20 antenni antennitikun päähän. Aseta akku antenniin ja käynnistä painamalla virtanäppäintä. Aseta antenni ja antennin keppi tutkan kärriin sille kuuluvalle paikalle. Asenna toinen pienempi tabletti antennikepin tablettitelineeseen ja käynnistä tabletti. Tutkan panasonic tabletilla avaa umap-logger sovellus etusivulta. Umap ohjelmassa varmista että antennikorkeus täsmää, tarkista että radar system ja gps välilehdellä kaikki on kunnossa (kun rtk korjattu gps signaali tulee oikein, signaali on 5Hz), Jos radar system välilehti herjaa  muuta PPS enabled --> disabled. 

Leica Captivate:
Antennin tabletissa captivate sovellus aukeaa automaattisesti käynnistyksen yhteydessä. Yhdistä antenni tablettiin joko bluetoothin tai tabletin oman internet hotspotin kautta. Usein yhdistys tapahtuu automaattisesti ja voit tarkistaa tämän antennin valoista (wifi symboli palaa vihreällä tai sinisellä jos yhteydessä). Usein tässä ongelmia johon löytyy useita mahdollisia ratkaisuja. Valitse captivaten oikeasta yläreunasta sihdin symboli ja paina aloita RTK virta. Antenni ja captivate tabeltti on oikein yhteydessä kun oikeassa yläkulmassa näkyvä tarkkuus tippuu alle 0.1 m. Antenni ja Umap (panasonic tutkan tabletti) tabletti on yhteydessä bluetoothin välityksellä ja ne voit yhdistää tämän tabletin asetusten kautta. Voit testata että kaikki toimii luomalla uuden projektin umap-loggerissa ja painamalla play nappia. Jos tutka alkaa kerätä dataa, kaikki pitäisi olla kunnossa. Nyt voit aloittaa tutkaamisen, tarkaile umapsiss että sijainti pysyy hyvälä eikä se heittele minne sattuu tutkauksen aikana.
