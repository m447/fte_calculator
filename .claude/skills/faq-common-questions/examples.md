# FAQ - Príklady Odpovedí

## Príklad 1: Nesúlad s realitou

**Používateľ:** "Model hovorí že potrebujem viac ľudí, ale my stíhame všetko. Prečo?"

**Odpoveď:**
Rozumiem, toto je častá otázka. Poďme sa pozrieť prečo to tak môže byť:

**Možné vysvetlenia:**

1. **Váš tím je výnimočný**
   - Produktivita nad 100 znamená že pracujete efektívnejšie ako priemer
   - To je pozitívne, ALE môže maskovať preťaženie

2. **"Stíhame" vs. "Fungujeme optimálne"**
   - Stíhate základné úlohy
   - Ale možno: kratšie konzultácie, menej upsellingu, dlhšie čakanie zákazníkov

3. **Krátkodobé vs. dlhodobé**
   - Teraz stíhate
   - Ale čo pri PN? Dovolenke? Decembri?

**Čo odporúčam:**
- Sledujte čakacie doby zákazníkov
- Opýtajte sa tímu či sa cítia preťažení
- Porovnajte sa s podobnými lekárňami (mám nástroj na to)

Model nehovorí že nefungujete. Hovorí že podobné lekárne majú viac kapacity.

---

## Príklad 2: Veľká vs. malá lekáreň

**Používateľ:** "Prečo má menšia lekáreň rovnaké odporúčanie FTE ako moja väčšia?"

**Odpoveď:**
Výborná otázka! Veľkosť lekárne (m²) nie je hlavný faktor. Rozhoduje **objem práce**.

**Čo model pozerá:**
| Faktor | Váš vplyv |
|--------|-----------|
| Transakcie (bloky) | Vysoký |
| Tržby | Stredný |
| Podiel Rx | Stredný |
| Plocha | Žiadny |

**Prečo menšia môže potrebovať rovnako:**
- Viac zákazníkov (lepšia lokácia)
- Vyšší podiel Rx (časovo náročnejšie)
- Menej self-service (viac obsluhy)

**Praktický príklad:**
```
Lekáreň A: 150 m², 500 blokov/deň = potrebuje 4.5 FTE
Lekáreň B: 80 m², 500 blokov/deň = potrebuje 4.5 FTE

Rovnaký objem práce = rovnaká potreba personálu
```

Plocha ovplyvňuje náklady na nájom, nie na personál.

---

## Príklad 3: Sezónne výkyvy

**Používateľ:** "Teraz je december a sme v chaose. Model to nevidí?"

**Odpoveď:**
Model pracuje s priemernými hodnotami, nie s aktuálnym mesiacom.

**Prečo:**
- Sezónnosť je predvídateľná (december je vždy špička)
- Rozhodnutia o personáli sú dlhodobé (nie pre 1 mesiac)
- Prijatý zamestnanec zostáva aj po decembri

**Čo s decembrom:**
1. **Krátkodobé riešenia:**
   - Brigádnici / dohody
   - Predĺžené zmeny (overtime)
   - Výpomoc z iných lekární (zastup)

2. **Dlhodobé riešenia:**
   - Ak je december každý rok chaos → celoročne poddimenzovaní
   - Zvážte trvalé rozšírenie

**Tip:**
Pozrite sa na trend za celý rok. Ak ste "len v decembri" v probléme, sezónne riešenie stačí. Ak je problém aj v iných mesiacoch, potrebujete trvalé rozšírenie.

---

## Príklad 4: Nový zamestnanec nepomáha

**Používateľ:** "Prijali sme človeka pred mesiacom a stále sme preťažení. Prečo?"

**Odpoveď:**
Mesiac je krátka doba. Tu je typický priebeh:

**Týždeň 1-4: Zaškoľovanie**
- Nový zamestnanec potrebuje 50% času skúseného
- Efektívne máte menej kapacity, nie viac
- Produktivita dočasne klesá

**Týždeň 5-8: Adaptácia**
- Začína pracovať samostatne
- Stále pomalší ako skúsení
- Chyby vyžadujú korekcie

**Týždeň 9-12: Stabilizácia**
- Pracuje na 70-80% efektivity
- Prestáva vyťažovať ostatných
- Prvé prínosy viditeľné

**Mesiac 4+: Plná kapacita**
- Pracuje ako ostatní
- Odľahčenie tímu reálne

**Čo robiť:**
- Buďte trpezliví (3 mesiace minimum)
- Sledujte progres nie absolútne čísla
- Ak po 3 mesiacoch stále problémy → konzultujte HR

---

## Príklad 5: Zákazníci bez čakania

**Používateľ:** "Nemáme fronty, tak prečo by sme mali byť poddimenzovaní?"

**Odpoveď:**
Absencia frontov ≠ optimálny stav. Tu je prečo:

**Čo model meria:**
- Objem práce (transakcie)
- Nie dĺžku frontov

**Prečo nemáte fronty ale ste poddimenzovaní:**

1. **Skrátené služby**
   - Menej času na konzultácie
   - Menej upsellingu
   - "Ďalší prosím" namiesto poradenstva

2. **Stratení zákazníci**
   - Tí čo nečakajú odišli
   - Nevidíte ich, len stratu tržieb

3. **Kompenzácia tímu**
   - Kratšie prestávky
   - Rýchlejšie tempo
   - Dlhodobo neudržateľné

**Test:**
Sledujte 1 týždeň:
- Priemerný čas na zákazníka
- Počet zákazníkov čo odišli
- Spokojnosť tímu (1-10)

Ak čas < 3 min, odchody > 5/deň, spokojnosť < 6 → poddimenzovaní aj bez frontov.

---

## Príklad 6: Dva segmenty v meste

**Používateľ:** "Mám dve lekárne v jednom meste ale rôzne odporúčania. Prečo?"

**Odpoveď:**
Rôzne lekárne = rôzne charakteristiky, aj keď sú v jednom meste.

**Faktory ktoré sa líšia:**

| Faktor | Lekáreň A | Lekáreň B |
|--------|-----------|-----------|
| Segment | B (Mall) | D (Ulica) |
| Transakcie | 600/deň | 350/deň |
| Podiel Rx | 40% | 70% |
| Tržby | 150K/mes | 90K/mes |

**Prečo rôzne odporúčania:**
- Mall má viac transakcií ale rýchlejších
- Ulica má menej ale náročnejších (Rx)
- Segment B má iný priemer ako D

**Logika:**
Model neporovnáva lekárne medzi sebou. Porovnáva každú s jej segmentom.

**Prakticky:**
- Lekáreň A sa porovnáva s inými mall lekárňami
- Lekáreň B sa porovnáva s inými uličnými

Obe môžu byť "v poriadku" alebo "problémové" voči svojmu segmentu, nezávisle od seba.

---

## Príklad 7: Rozpor s regionálnym manažérom

**Používateľ:** "Môj regionálny manažér hovorí niečo iné ako model. Komu veriť?"

**Odpoveď:**
Obom, pretože vidia rôzne veci.

**Čo vidí model:**
- Objektívne čísla (transakcie, tržby)
- Porovnanie so sieťou
- Historické trendy
- Kvantifikované riziko

**Čo vidí manažér:**
- Kvalitu jednotlivcov
- Plánované zmeny
- Lokálny kontext
- Tímovú dynamiku

**Ideálny postup:**

1. **Zdieľajte dáta**
   - Ukážte manažérovi čo hovorí model
   - Spýtajte sa na jeho pohľad

2. **Identifikujte rozpor**
   - Kde presne sa líšia?
   - Je to v číslach alebo interpretácii?

3. **Hľadajte pravdu**
   - Ak manažér má informáciu ktorú model nemá → upravte očakávania
   - Ak model vidí niečo čo manažér prehliadol → zvážte

4. **Dokumentujte rozhodnutie**
   - Kto rozhodol a prečo
   - Podklad pre budúce vyhodnotenie

**Pamätajte:**
Ani model ani manažér nie sú neomylní. Najlepšie rozhodnutia vznikajú kombináciou oboch pohľadov.

---

## Príklad 8: Prečo práve 0.05 FTE threshold

**Používateľ:** "Prečo je hranica pre urgentné 0.05 FTE? To je len 2 hodiny týždenne."

**Odpoveď:**
Dobrá otázka. Prah 0.05 FTE je zámerný kompromis:

**Matematika:**
- 0.05 FTE = 2 hodiny týždenne = 8 hodín mesačne
- Za rok: 96 hodín = takmer 2.5 týždňa práce

**Prečo tak nízko:**
1. **Agresívna identifikácia** - Zachytiť všetky problémy
2. **Revenue at Risk** - Aj malý gap pri vysokej produktivite = veľká strata
3. **Kumulatívny efekt** - 0.05 × 94 lekární = významný celkový gap

**Porovnanie prahov:**

| Prah | Urgentných | Revenue at Risk |
|------|------------|-----------------|
| 0.5 FTE | 8 | 961K EUR |
| 0.25 FTE | 42 | 2.78M EUR |
| 0.05 FTE | 94 | 3.74M EUR |

**Prakticky:**
- Vysoký prah (0.5) = menej lekární, väčšie problémy
- Nízky prah (0.05) = viac lekární, aj menšie problémy

Aktuálne nastavenie maximalizuje demonštráciu hodnoty aplikácie. Pre operatívne rozhodnutia môžete filtrovať na vyšší gap.
