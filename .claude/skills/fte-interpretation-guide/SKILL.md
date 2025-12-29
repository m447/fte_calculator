---
name: fte-interpretation-guide
description: Použite tento skill keď používateľ pýta na význam FTE metrík, nerozumie produktivite, zmätený znamienkom gapu, alebo nechápe rozdiel NET vs GROSS. Spúšťacie frázy: "Čo znamená produktivita 115?", "Prečo je gap kladný?", "Aký je rozdiel medzi NET a GROSS?", "Prečo nemám revenue at risk?", "Čo je FTE gap?"
---

# FTE Interpretation Guide - Sprievodca Metrikami

## Inštrukcie

Keď používateľ nechápe metriky alebo ich interpretáciu:

1. **Identifikuj konkrétny zmätok** - Ktorá metrika je nejasná?
2. **Vysvetli jednoducho** - Použi príklady z reálneho sveta
3. **Daj kontext** - Čo je dobré/zlé číslo
4. **Prepoj s akciou** - Čo to znamená pre rozhodnutie

## Základná Terminológia

### FTE (Full-Time Equivalent)

**Definícia:** Počet pracovníkov prepočítaný na plný úväzok.

| Príklad | FTE |
|---------|-----|
| 1 zamestnanec na plný úväzok | 1.0 FTE |
| 2 zamestnanci na polovičný úväzok | 1.0 FTE |
| 3 zamestnanci: 1 plný + 2×50% | 2.0 FTE |

### NET vs GROSS FTE

**NET FTE (`fte`):**
- Pracovníci skutočne pracujúci (bez absencií)
- Čo máte "k dispozícii" každý deň

**GROSS FTE (`actual_fte_gross`):**
- NET + fte_n (zástupy za absencie)
- Celková zmluvná kapacita vrátane pokrytia

**Vzorec:**
```
GROSS = NET + fte_n
```

**Príklad:**
- NET FTE: 4.0 (reálne pracujúci)
- fte_n: 0.5 (pokrytie absencií)
- GROSS FTE: 4.5 (celková kapacita)

**Prečo je to dôležité:**
Model predikuje GROSS FTE, pretože potrebujete plánovať aj s absenciami.

## FTE Gap (Rozdiel)

### Definícia

```
FTE Gap = Odporúčané FTE - Aktuálne FTE
```

### Interpretácia znamienka

| Gap | Význam | Akcia |
|-----|--------|-------|
| **+0.5** | Potrebujete 0.5 FTE viac | Poddimenzovaní - zvážte prijatie |
| **0** | Správne dimenzovaní | Bez zásahu |
| **-0.5** | Máte 0.5 FTE navyše | Predimenzovaní - zvážte realokáciu |

### Prahy pre akciu

| Gap | Kategória | Priorita |
|-----|-----------|----------|
| ≥ +0.5 | Výrazne poddimenzovaní | Vysoká |
| +0.05 až +0.5 | Mierne poddimenzovaní | Stredná |
| -0.05 až +0.05 | Optimálni | Žiadna |
| -0.5 až -0.05 | Mierne predimenzovaní | Nízka |
| ≤ -0.5 | Výrazne predimenzovaní | Stredná |

**Poznámka:** Aktuálny prah pre "urgentné" je 0.05 FTE (~1.5 hodiny týždenne).

## Produktivita (Index)

### Definícia

Produktivita je **relatívny ukazovateľ** porovnávajúci lekáreň s priemerom jej segmentu.

```
Produktivita 100 = priemer segmentu
Produktivita 115 = o 15% lepšia ako priemer
Produktivita 85 = o 15% horšia ako priemer
```

### Segmentové priemery

Každý segment má iný priemer produktivity:

| Segment | Popis | Referenčný priemer |
|---------|-------|-------------------|
| A | Shopping Premium | 6.27 |
| B | Shopping | 7.96 |
| C | Street + | 5.68 |
| D | Street | 5.55 |
| E | Poliklinika | 5.23 |

### Interpretácia

| Produktivita | Stav | Čo to znamená |
|--------------|------|---------------|
| > 120 | Kriticky vysoká | Preťaženie, risk vyhorenia |
| 110-120 | Nadpriemerná | Efektívny tím, sledovať |
| 90-110 | Priemerná | Štandard, v poriadku |
| 80-90 | Podpriemerná | Priestor na zlepšenie |
| < 80 | Nízka | Nutná optimalizácia |

### Dôležité upozornenie

Produktivita NIE JE percento využitia času. Je to **index porovnania**.
- Produktivita 100 NEznamená 100% využitie
- Produktivita 115 NEznamená 115% kapacity

## Revenue at Risk (Ohrozené Tržby)

### Definícia

Potenciálne stratené tržby kvôli poddimenzovaniu u vysokovýkonných lekární.

### Vzorec

```
Revenue at Risk = (Preťaženie - 1) × 0.5 × Ročné tržby
```

Kde:
- Preťaženie = Odporúčané FTE / Aktuálne FTE
- 0.5 = konzervatívny faktor (50% preťaženia = strata)

### Podmienky pre výpočet

Revenue at Risk sa počíta LEN ak:
1. ✅ Lekáreň je poddimenzovaná (gap > 0)
2. ✅ Produktivita je nadpriemerná (> 100)
3. ✅ Tržby > 0
4. ✅ Aktuálne FTE > 0

### Prečo len pre vysokú produktivitu?

Logika je jednoduchá:
- **Vysoká produktivita + poddimenzovanosť** = Tím pracuje na maximum, nemôže viac → strácame zákazníkov
- **Nízka produktivita + poddimenzovanosť** = Tím nie je efektívny → najprv optimalizovať

### Príklad

| Lekáreň | Aktuálne FTE | Odporúčané FTE | Produktivita | Tržby | Revenue at Risk |
|---------|--------------|----------------|--------------|-------|-----------------|
| A | 4.0 | 4.5 | 115 | 2M | 125,000 EUR |
| B | 4.0 | 4.5 | 85 | 2M | 0 EUR |

Lekáreň A dostane revenue at risk, lebo je efektívna.
Lekáreň B nedostane, lebo najprv musí zlepšiť efektívnosť.

## Priority Klasifikácia

### URGENT (Urgentné)
- Gap ≥ 0.05 FTE
- Produktivita > priemer segmentu
- → **Okamžite riešiť** - vysoký výkon, chýba kapacita

### OPTIMIZE (Optimalizovať)
- Gap ≥ 0.05 FTE
- Produktivita ≤ priemer segmentu
- → **Najprv zefektívniť** - nepridávať personál kým nezlepšíte produktivitu

### MONITOR (Sledovať)
- Gap < -0.05 FTE (prebytok)
- → **Možnosť realokácie** - zvážiť presun personálu

### OPTIMAL (Optimálne)
- Gap medzi -0.05 a +0.05
- → **Bez zásahu** - správne dimenzované

## Kľúčové Body

1. **Gap má znamienko** - Plus = potrebujete viac, mínus = máte navyše
2. **100 = priemer** - Produktivita je relatívna, nie absolútna
3. **NET ≠ GROSS** - GROSS zahŕňa pokrytie absencií
4. **Revenue at Risk ≠ automatická strata** - Je to potenciál, nie istota
5. **Priorita závisí od kombinácie** - Gap + produktivita = akcia
