# Action Planning Guide - Príklady

## Príklad 1: Čo robiť s dátami

**Používateľ:** "Mám zoznam 10 poddimenzovaných lekární. Čo s tým mám robiť?"

**Odpoveď:**
Poďme to rozdeliť na konkrétne kroky:

**Krok 1: Roztriedenie (5 minút)**

Rozdeľte 10 lekární do kategórií:

| Kategória | Kritérium | Akcia |
|-----------|-----------|-------|
| URGENT | Produktivita > 100 + Gap > 0 | Okamžite riešiť |
| OPTIMIZE | Produktivita < 100 + Gap > 0 | Najprv zefektívniť |

**Krok 2: Zoradenie URGENT podľa ROI (5 minút)**

```
ROI = Revenue at Risk / Náklady na FTE

Príklad:
Lekáreň A: Risk 150K, potreba 0.8 FTE → ROI = 150K / 24K = 6.25x
Lekáreň B: Risk 80K, potreba 1.2 FTE → ROI = 80K / 36K = 2.2x

→ Začnite lekárňou A
```

**Krok 3: Akčný plán (10 minút)**

Pre top 3 URGENT lekárne:
1. Overiť s regionálnym manažérom
2. Skontrolovať možnosti realokácie v regióne
3. Ak nie, vypísať pozíciu

**Výstup:**
Pripravený report s odporúčaním pre každú lekáreň.

---

## Príklad 2: Prioritizácia

**Používateľ:** "Ako mám prioritizovať? Mám 94 urgentných lekární."

**Odpoveď:**
94 lekární nie je možné riešiť naraz. Tu je prioritizačný framework:

**Tier 1: Top 10 (Okamžite)**

Kritériá:
- Revenue at Risk > 100,000 EUR
- FTE Gap > 0.5
- Produktivita > 115

→ Očakávaný počet: 8-12 lekární
→ Čas: 0-30 dní

**Tier 2: Ďalších 20 (Kvartál)**

Kritériá:
- Revenue at Risk 50,000-100,000 EUR
- FTE Gap 0.3-0.5
- Produktivita 105-115

→ Očakávaný počet: 15-25 lekární
→ Čas: 30-90 dní

**Tier 3: Zvyšok (Polrok)**

Kritériá:
- Revenue at Risk < 50,000 EUR
- FTE Gap < 0.3

→ Očakávaný počet: 50-60 lekární
→ Čas: 90-180 dní

**Praktický tip:**
Začnite s Tier 1 a sledujte výsledky. Ak sa osvedčí, rozšírte na Tier 2.

---

## Príklad 3: Nákladová kalkulácia

**Používateľ:** "Koľko to bude stáť riešenie 10 najurgentnejších lekární?"

**Odpoveď:**
Poďme to vypočítať:

**Predpoklady:**
- Priemerné náklady na 1 FTE: 30,000 EUR/rok
- Priemerný FTE gap: 0.6 na lekáreň
- 10 lekární × 0.6 = 6 FTE celkovo

**Náklady:**
| Položka | Kalkulácia | Suma |
|---------|------------|------|
| Personálne náklady | 6 FTE × 30,000 | 180,000 EUR/rok |
| Recruiting náklady | 6 × 2,000 | 12,000 EUR (jednorazovo) |
| Školenie | 6 × 1,000 | 6,000 EUR (jednorazovo) |
| **Prvý rok** | | **198,000 EUR** |
| **Ďalšie roky** | | **180,000 EUR/rok** |

**ROI:**
| Položka | Suma |
|---------|------|
| Chránené tržby (10 lekární) | ~600,000 EUR |
| Ročné náklady | 180,000 EUR |
| **Čistý prínos** | **420,000 EUR** |
| **ROI** | **2.3x** |

**Záver:**
Investícia 198K EUR prvý rok prinesie ~600K EUR v chránených tržbách = návratnosť 2-3 roky.

---

## Príklad 4: Akčný plán pre región

**Používateľ:** "Vytvor akčný plán pre región RR11"

**Odpoveď:**
Tu je kompletný akčný plán:

---

## AKČNÝ PLÁN - REGIÓN RR11

**Dátum:** [Aktuálny dátum]
**Manažér:** [Meno]

### SÚHRN

| Metrika | Hodnota |
|---------|---------|
| Lekární v regióne | 18 |
| Urgentných | 7 |
| Na optimalizáciu | 4 |
| Predimenzovaných | 2 |
| Celkový FTE gap | +4.2 |
| Revenue at Risk | 485,000 EUR |

### FÁZA 1: IHNEĎ (0-30 dní)

**Cieľ:** Riešiť top 3 urgentné

| ID | Mesto | Gap | Risk | Akcia |
|----|-------|-----|------|-------|
| 185 | Trebišov | +0.8 | 125K | Nová pozícia |
| 203 | Košice | +0.6 | 98K | Realokácia z ID 217 |
| 156 | Prešov | +0.5 | 72K | Rozšírenie úväzku |

**Náklady Fázy 1:** ~24,000 EUR
**Chránené tržby:** 295,000 EUR

### FÁZA 2: KRÁTKODOBÉ (30-90 dní)

**Cieľ:** Ďalšie 4 urgentné

| ID | Mesto | Gap | Risk | Akcia |
|----|-------|-----|------|-------|
| 178 | Michalovce | +0.4 | 45K | Nová pozícia |
| 192 | Humenné | +0.3 | 38K | Part-time |
| 167 | Snina | +0.4 | 35K | Realokácia |
| 201 | Bardejov | +0.2 | 27K | Optimalizácia |

**Náklady Fázy 2:** ~36,000 EUR
**Chránené tržby:** 145,000 EUR

### REALOKAČNÉ PRÍLEŽITOSTI

| Zdroj | Cieľ | FTE | Poznámka |
|-------|------|-----|----------|
| ID 217 (Košice) | ID 203 (Košice) | 0.5 | Rovnaké mesto |
| ID 189 (Prešov) | ID 167 (Snina) | 0.3 | 40 km vzdialenosť |

### MONITORING

Prehodnotiť za 90 dní:
- [ ] Zmenila sa produktivita?
- [ ] Znížil sa FTE gap?
- [ ] Klesol Revenue at Risk?

---

---

## Príklad 5: Realokácia

**Používateľ:** "Kde môžem presunúť personál namiesto prijímania?"

**Odpoveď:**
Poďme nájsť realokačné príležitosti:

**Zdroje (predimenzované lekárne):**

Hľadám lekárne s:
- FTE gap < -0.3 (prebytok)
- Produktivita < 100 (nie sú preťažené)

**Ciele (poddimenzované lekárne):**

Hľadám lekárne s:
- FTE gap > +0.3 (deficit)
- Produktivita > 100 (efektívne)
- V rovnakom regióne

**Matching kritériá:**
1. Rovnaký región (priorita) alebo susedný
2. Podobný segment (farmaceuti vs. laboranti)
3. Vzdialenosť < 50 km (pre dochádzkový presun)

**Typický výstup:**

| Zdroj | Prebytok | Cieľ | Deficit | Vzdialenosť |
|-------|----------|------|---------|-------------|
| ID 217 Košice | -0.6 | ID 203 Košice | +0.5 | 0 km |
| ID 189 Prešov | -0.4 | ID 156 Prešov | +0.5 | 0 km |

**Výhody realokácie:**
- Žiadne náklady na recruiting
- Okamžitá dostupnosť
- Zamestnanec pozná systémy
- Win-win (odľahčenie aj pomoc)

**Proces:**
1. Konzultácia s oboma manažérmi lekární
2. Rozhovor so zamestnancom
3. Dohoda o podmienkach (trvalý presun vs. výpomoc)
4. Administratívna zmena

---

## Príklad 6: Report pre vedenie

**Používateľ:** "Potrebujem report pre vedenie o personálnej situácii"

**Odpoveď:**
Tu je štruktúra executive reportu:

---

## PERSONÁLNY REPORT - EXECUTIVE SUMMARY

**Obdobie:** [Mesiac/Rok]
**Pripravil:** [Meno]

### KĽÚČOVÉ ČÍSLA

| KPI | Aktuálne | Cieľ | Status |
|-----|----------|------|--------|
| Urgentné lekárne | 94 | < 20 | 🔴 |
| Revenue at Risk | 3.74M EUR | < 1M EUR | 🔴 |
| Priemerný FTE gap | +0.15 | < ±0.1 | 🟡 |
| Lekárne na optimalizáciu | 10 | 0 | 🟡 |

### TOP 5 AKCIÍ

| # | Lekáreň | Akcia | Náklad | Prínos | ROI |
|---|---------|-------|--------|--------|-----|
| 1 | ID 185 Trebišov | +1 FTE | 30K | 125K | 4.2x |
| 2 | ID 637 Lučenec | +0.5 FTE | 15K | 85K | 5.7x |
| 3 | ID 203 Košice | Realokácia | 0 | 98K | ∞ |
| 4 | ID 156 Prešov | +0.5 FTE | 15K | 72K | 4.8x |
| 5 | ID 178 Michalovce | +0.5 FTE | 15K | 45K | 3.0x |

### POŽIADAVKA NA BUDGET

| Položka | Q1 | Q2 | Rok |
|---------|----|----|-----|
| Nové FTE | 75K | 50K | 200K |
| Školenia | 10K | 5K | 20K |
| **Spolu** | **85K** | **55K** | **220K** |

### OČAKÁVANÝ IMPACT

| Scenár | Chránené tržby | Net Benefit |
|--------|----------------|-------------|
| Konzervatívny (50%) | 1.87M | 1.65M |
| Realistický (70%) | 2.62M | 2.40M |
| Optimistický (90%) | 3.37M | 3.15M |

### ĎALŠIE KROKY

1. Schválenie budgetu pre Q1 (85K EUR)
2. Spustenie hiring procesu pre top 5
3. Identifikácia realokačných príležitostí
4. Review za 30 dní

---

Mám ti pomôcť s konkrétnymi číslami pre tvoj región alebo segment?
