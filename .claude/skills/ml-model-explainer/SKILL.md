---
name: ml-model-explainer
description: Použite tento skill keď používateľ pýta ako funguje model, prečo odporúča určité FTE, či môže veriť predikciám, alebo chce vysvetlenie výpočtov. Spúšťacie frázy: "Ako funguje model?", "Prečo mi odporúča X FTE?", "Môžem veriť týmto číslam?", "Vysvetli predikciu", "Čo je to ML model?"
---

# ML Model Explainer - Vysvetľovač Modelu

## Inštrukcie

Keď používateľ pýta o fungovaní modelu alebo dôveryhodnosti predikcií, postupuj nasledovne:

1. **Zisti kontext otázky** - Pýta sa všeobecne o modeli, alebo konkrétne o svojej lekárni?
2. **Vysvetli jednoducho** - Používaj biznis jazyk, nie technický žargón
3. **Použi analógie** - Prirovnania k známym konceptom
4. **Buď transparentný** - Priznaj limitácie modelu

## Čo Model Robí

Model analyzuje historické dáta lekární a predpovedá optimálny počet personálu (FTE).

### Vstupy (čo model vidí):
- **Bloky (transakcie)** - Hlavný faktor, počet obsluhovných zákazníkov
- **Tržby** - Celkové príjmy lekárne
- **Podiel Rx** - Percento receptových liekov (časovo náročnejšie)
- **Typ lekárne** - Segment A-E (Mall, Street, Poliklinika...)
- **Historická produktivita** - Ako efektívne lekáreň pracuje

### Výstupy (čo model vracia):
- **Odporúčané FTE** - Optimálny počet pracovníkov
- **FTE Gap** - Rozdiel oproti súčasnosti (+ = potrebujete viac, - = máte prebytok)
- **Ohrozené tržby** - Potenciálna strata z poddimenzovanosti
- **Produktivita** - Index porovnania s priemerom segmentu (100 = priemer)

## Ako Interpretovať Predikcie

### Produktivita (Index)
| Hodnota | Význam | Akcia |
|---------|--------|-------|
| > 120 | Kriticky preťažená | Urgentne riešiť - personál nestíha |
| 100-120 | Nadpriemerná | Sledovať - funguje dobre |
| 80-100 | Priemerná | V poriadku |
| < 80 | Podpriemerná | Optimalizovať pred pridávaním |

### FTE Gap (Rozdiel)
| Hodnota | Význam | Akcia |
|---------|--------|-------|
| +1.0 a viac | Výrazne poddimenzovaná | Urgentné prijímanie |
| +0.5 až +1.0 | Mierne poddimenzovaná | Plánovať rozšírenie |
| -0.5 až +0.5 | Správne dimenzovaná | Bez zásahu |
| -1.0 a menej | Predimenzovaná | Zvážiť realokáciu |

### Ohrozené Tržby
Tržby, ktoré riskujete stratiť ak:
- Zákazníci odídu kvôli dlhému čakaniu
- Personál nestíha obslúžiť všetkých
- Kvalita služieb klesá

**Dôležité:** Ohrozené tržby sa počítajú LEN pre lekárne, ktoré sú:
1. Poddimenzované (gap > 0) A ZÁROVEŇ
2. Nadpriemerne produktívne (produktivita > 100)

Prečo? Lebo len efektívne lekárne majú potenciál zarobiť viac s ďalším personálom.

## Limitácie Modelu

### Čo Model NEVIE:
- Predpovedať náhle zmeny (nový konkurent, pandémia, rekonštrukcia)
- Zohľadniť kvalitu jednotlivých zamestnancov
- Vedieť o plánovaných investíciách či otvoreniach
- Nahradiť lokálnu znalosť manažéra

### Preto VŽDY:
- Kombinujte s vlastnou skúsenosťou
- Konzultujte s regionálnym manažérom
- Sledujte trendy, nie len aktuálny stav
- Overte si dáta pred veľkými rozhodnutiami

## Kedy Veriť Modelu

### Vysoká dôveryhodnosť:
- Stabilné lekárne bez veľkých zmien
- Dlhodobé trendy (nie jednomesačné výkyvy)
- Porovnania medzi podobnými lekárňami

### Nižšia dôveryhodnosť:
- Novootvorené lekárne (< 12 mesiacov)
- Lekárne po rekonštrukcii
- Extrémne hodnoty (veľmi vysoká/nízka produktivita)
- Sezónne špičky (december, prázdniny)

## Kľúčové Body

1. **Model používa VAŠE dáta** - Nevymýšľa čísla, analyzuje reálne transakcie a tržby
2. **100 = priemer segmentu** - Produktivita 115 znamená o 15% lepšia ako priemer
3. **Gap = potreba zmeny** - Kladné číslo = potrebujete viac ľudí
4. **Rozhodnutie je na vás** - Model odporúča, manažér rozhoduje
