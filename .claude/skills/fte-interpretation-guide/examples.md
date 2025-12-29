# FTE Interpretation Guide - Príklady

## Príklad 1: Čo znamená produktivita

**Používateľ:** "Moja lekáreň má produktivitu 115. Čo to znamená?"

**Odpoveď:**
Produktivita 115 znamená, že vaša lekáreň je **o 15% efektívnejšia** ako priemer vášho segmentu.

**Čo to prakticky znamená:**
- Váš tím obslúži viac zákazníkov na jedného zamestnanca
- Pracujete efektívnejšie ako podobné lekárne
- Môže to signalizovať vysoký výkon, ALE aj preťaženie

**Kontextová škála:**
```
80  ────────── 100 ────────── 115 ────────── 130
Podpriemer    Priemer       Vy            Extrém
```

**Čo s tým robiť:**
- Ak máte zároveň pozitívny FTE gap → Tím je preťažený, zvážte rozšírenie
- Ak máte negatívny gap → Skvelé, máte efektívny tím s dostatočnou kapacitou

---

## Príklad 2: Zmätok so znamienkom gapu

**Používateľ:** "Prečo je môj gap +0.7? Znamená to že mám o 0.7 viac ako treba?"

**Odpoveď:**
Nie, je to naopak. **Plus znamená že potrebujete viac**.

**Logika:**
```
Gap = Odporúčané - Aktuálne
```

Ak máte:
- Aktuálne: 3.5 FTE
- Odporúčané: 4.2 FTE
- Gap: 4.2 - 3.5 = **+0.7**

**Interpretácia:**
- **+0.7** = Potrebujete 0.7 FTE navyše = Poddimenzovaní
- **-0.7** = Máte 0.7 FTE navyše = Predimenzovaní

**Pamätátko:**
| Znamienko | Význam | Akcia |
|-----------|--------|-------|
| **+** (plus) | Potrebujete viac | Prijímanie |
| **-** (mínus) | Máte navyše | Realokácia |

---

## Príklad 3: NET vs GROSS FTE

**Používateľ:** "Aký je rozdiel medzi NET a GROSS FTE?"

**Odpoveď:**
Predstavte si to ako **teoretická** vs **praktická** kapacita.

**NET FTE (fte):**
- Koľko ľudí reálne pracuje každý deň
- Nezahŕňa absencie (dovolenka, PN)

**GROSS FTE (actual_fte_gross):**
- NET + pokrytie absencií (fte_n)
- Celková zmluvná kapacita

**Príklad:**
```
Zmluvne máte 5 ľudí = GROSS 5.0
Jeden je vždy na dovolenke = NET 4.0
Ale máte zástup = fte_n 1.0

GROSS = NET + fte_n = 4.0 + 1.0 = 5.0
```

**Prečo je to dôležité:**
Model počíta s GROSS, lebo musíte plánovať aj pokrytie absencií. Keď model hovorí "potrebujete 4.5 FTE", myslí GROSS - teda vrátane zástupcov.

---

## Príklad 4: Prečo nemám revenue at risk

**Používateľ:** "Som poddimenzovaný ale nemám žiadne ohrozené tržby. Prečo?"

**Odpoveď:**
Revenue at risk sa počíta len pre lekárne, ktoré spĺňajú **OBE podmienky**:

1. ✅ Poddimenzované (gap > 0)
2. ✅ Nadpriemerne produktívne (produktivita > priemer segmentu)

**Vaša situácia pravdepodobne:**
Gap > 0, ALE produktivita < priemer segmentu

**Čo to znamená:**
Model hovorí: "Máte málo ľudí, ALE váš tím nepracuje efektívne. Pridanie ďalších ľudí by len zvýšilo náklady bez zvýšenia výkonu."

**Akcia:**
1. Najprv zistite prečo je produktivita nízka
2. Optimalizujte procesy
3. Až potom uvažujte o rozšírení

**Typické príčiny nízkej produktivity:**
- Nevhodná organizácia práce
- Príliš veľa administratívy
- Nízka návštevnosť (lokácia, konkurencia)
- Neefektívne zmeny

---

## Príklad 5: Čo je segment

**Používateľ:** "Čo znamená že som v segmente D?"

**Odpoveď:**
Segmenty kategorizujú lekárne podľa ich typu a lokácie:

| Segment | Názov | Charakteristika |
|---------|-------|-----------------|
| A | Shopping Premium | Veľké nákupné centrá, vysoký traffic |
| B | Shopping | Stredné nákupné centrá |
| C | Street + | Ulica s vysokou návštevnosťou |
| D | Street | Bežná uličná lekáreň |
| E | Poliklinika | V zdravotníckych zariadeniach |

**Prečo je to dôležité:**
- Každý segment má iné priemerné hodnoty
- Porovnávate sa s lekárňami vo vašom segmente
- Produktivita 100 v segmente A ≠ produktivita 100 v segmente E

**Segment D - Street:**
- Typická uličná lekáreň
- Stredný traffic zákazníkov
- Priemerná produktivita segmentu: 5.55
- Porovnávate sa s ~60 podobnými lekárňami

---

## Príklad 6: Priority klasifikácia

**Používateľ:** "Prečo som v kategórii OPTIMIZE a nie URGENT?"

**Odpoveď:**
Klasifikácia závisí od **kombinácie** FTE gapu a produktivity:

**URGENT = Gap ≥ 0.05 + Vysoká produktivita**
- "Máte málo ľudí A pracujete efektívne"
- → Okamžite pridať personál

**OPTIMIZE = Gap ≥ 0.05 + Nízka produktivita**
- "Máte málo ľudí ALE nepracujete efektívne"
- → Najprv zlepšiť efektívnosť

**Vaša situácia (OPTIMIZE):**
- Máte pozitívny gap (potrebujete viac ľudí)
- Ale produktivita je pod priemerom segmentu
- → Pridanie ľudí by len zvýšilo náklady

**Ako sa dostať do URGENT (ak chcete podporu pre hiring):**
1. Zlepšite produktivitu (znížte administratívu, optimalizujte procesy)
2. Keď prekročíte priemer segmentu, automaticky sa preradíte

---

## Príklad 7: Interpretácia konkrétnych čísel

**Používateľ:** "Môžeš mi vysvetliť tieto čísla pre moju lekáreň?"

**Predpokladané dáta:**
```
ID: 185
Aktuálne FTE: 3.5
Odporúčané FTE: 4.2
FTE Gap: +0.7
Produktivita: 118
Revenue at Risk: 125,000 EUR
Segment: D
```

**Odpoveď:**
Tu je kompletná interpretácia:

**1. FTE Gap: +0.7**
- Potrebujete 0.7 FTE navyše (približne 28 hodín týždenne)
- To je významný deficit

**2. Produktivita: 118**
- O 18% efektívnejší ako priemer segmentu D
- Váš tím pracuje nadštandardne
- → Preto máte high priority

**3. Revenue at Risk: 125,000 EUR**
- Potenciálna ročná strata z preťaženia
- Výpočet: (4.2/3.5 - 1) × 0.5 × tržby

**4. Segment D: Street**
- Typická uličná lekáreň
- Porovnávate sa s podobnými

**Záver:**
Vaša lekáreň je **URGENT** - vysoká produktivita s nedostatkom personálu. Každý mesiac bez akcie potenciálne strácate ~10,000 EUR.

**Odporúčanie:**
Pridať 0.7-1.0 FTE čo najskôr. ROI: náklad ~21K EUR/rok, chránené tržby ~125K EUR = **návratnosť 6x**.
