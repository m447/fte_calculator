# ML Model Explainer - Príklady

## Príklad 1: Všeobecná otázka o modeli

**Používateľ:** "Ako funguje ten váš model?"

**Odpoveď:**
Model funguje podobne ako skúsený manažér, ktorý pozná všetky lekárne v sieti.

Predstavte si, že máte 286 lekární a pre každú viete:
- Koľko zákazníkov denne obslúži (bloky)
- Aké má tržby
- Aký typ lekárne to je (mall, ulica, poliklinika)
- Koľko ľudí tam pracuje

Model sa "naučil" z týchto dát, aký je typický vzťah medzi počtom zákazníkov a potrebným personálom. Keď teraz vidí novú lekáreň, vie povedať: "Pri tomto objeme práce zvyčajne potrebujete X ľudí."

**Dôležité:** Model nehodnotí jednotlivcov - pozerá sa na celkové čísla a porovnáva ich s podobnými lekárňami.

---

## Príklad 2: Prečo konkrétne odporúčanie

**Používateľ:** "Prečo mi model odporúča 4.5 FTE keď mám 3.8?"

**Odpoveď:**
Model vidí, že vaša lekáreň:
- Má vysoký počet transakcií (blokov)
- Dosahuje nadpriemernú produktivitu (nad 100)
- To znamená, že váš tím pracuje efektívne, ale je preťažený

Odporúčanie +0.7 FTE vychádza z porovnania s podobnými lekárňami v sieti. Tie s podobným objemom práce majú v priemere viac personálu.

**Čo to prakticky znamená:**
- 0.7 FTE ≈ cca 28 hodín týždenne
- Mohlo by to byť: 1 zamestnanec na 70% úväzok, alebo rozšírenie zmien

**Prečo je to dôležité:**
Ak máte vysokú produktivitu ALE málo ľudí, riskujete:
- Vyčerpanie tímu
- Dlhšie čakacie doby
- Stratu zákazníkov

---

## Príklad 3: Dôveryhodnosť modelu

**Používateľ:** "Môžem veriť týmto číslam?"

**Odpoveď:**
Áno, s rozumným očakávaním. Tu je čomu môžete veriť a čomu nie:

**Môžete veriť:**
- Relatívnemu porovnaniu (vaša lekáreň vs. podobné)
- Dlhodobým trendom (rast/pokles za 6+ mesiacov)
- Identifikácii extrémov (jasne poddimenzované alebo predimenzované)

**Buďte opatrní pri:**
- Konkrétnych číslach (4.5 FTE je odhad, nie presný výpočet)
- Krátkodobých výkyvoch (jeden zlý mesiac neznamená problém)
- Špeciálnych okolnostiach (rekonštrukcia, nový konkurent)

**Ako to používať:**
Berte to ako "druhý názor" od dát. Ak model hovorí že potrebujete viac ľudí a vy to cítite tiež - pravdepodobne je to pravda. Ak model hovorí niečo čo nedáva zmysel - overte si dáta.

---

## Príklad 4: Prečo nemám ohrozené tržby

**Používateľ:** "Prečo moja lekáreň nemá žiadne ohrozené tržby, keď som poddimenzovaný?"

**Odpoveď:**
Ohrozené tržby sa počítajú len pre lekárne, ktoré spĺňajú OBE podmienky:
1. Sú poddimenzované (gap > 0)
2. Majú nadpriemernú produktivitu (index > 100)

Ak vaša lekáreň má:
- Gap > 0, ale produktivitu < 100: Model hovorí "najprv zefektívnite, potom pridávajte ľudí"
- Produktivitu > 100, ale gap < 0: Nie ste poddimenzovaní

**Logika za tým:**
Ohrozené tržby = potenciál, ktorý nevyužívate. Ak lekáreň pracuje pod priemerom, pridanie ľudí by len zvýšilo náklady bez zvýšenia výkonu.

---

## Príklad 5: Čo je produktivita 115

**Používateľ:** "Čo znamená že mám produktivitu 115?"

**Odpoveď:**
Produktivita 115 znamená, že vaša lekáreň je o **15% efektívnejšia** ako priemer vášho segmentu.

**Ako sa to počíta:**
- 100 = priemer všetkých lekární vo vašom segmente (napr. "D - street")
- 115 = robíte o 15% viac práce na jedného zamestnanca

**Čo to prakticky znamená:**
- Váš tím je výkonný
- Možno ste však na hranici kapacity
- Ak máte zároveň pozitívny FTE gap, môže to signalizovať preťaženie

**Porovnanie:**
| Produktivita | Stav |
|--------------|------|
| 80 | Podpriemerná - rezervy v efektívnosti |
| 100 | Priemerná - štandard |
| 115 | Nadpriemerná - efektívny tím |
| 130+ | Extrémna - pravdepodobne preťaženie |

---

## Príklad 6: Model sa mýli

**Používateľ:** "Model mi odporúča menej ľudí, ale ja viem že ich potrebujem viac. Čo s tým?"

**Odpoveď:**
Model môže mať nepresné dáta alebo nevidí niečo čo vy viete. Tu je čo môže byť príčinou:

**Možné dôvody prečo model "nemá pravdu":**
1. **Sezónnosť** - December má špičku, model pozerá na priemer
2. **Nový personál** - Zaškolenie znižuje produktivitu dočasne
3. **Zmena sortimentu** - Viac služieb = viac práce, ale nie viac transakcií
4. **Kvalita vs. kvantita** - Model meria objem, nie náročnosť

**Čo robiť:**
1. Pozrite sa na trend za 6+ mesiacov, nie len aktuálny stav
2. Porovnajte sa s podobnými lekárňami (nástroj compare_to_peers)
3. Ak máte konkrétny dôvod, zdokumentujte ho pre rozhodnutie

**Pamätajte:** Model je nástroj, nie sudca. Vaša lokálna znalosť má hodnotu.
