"""
Claude Agent SDK Integration for Dr.Max FTE Calculator

This module provides an autonomous agent that can analyze pharmacy staffing
using sanitized data (indexed productivity values, no raw formulas exposed).

The agent uses custom tools that access pre-sanitized data rather than
raw files, protecting proprietary productivity calculations.
"""

import json
import os
from pathlib import Path
from typing import AsyncIterator, Optional
from dataclasses import dataclass, field

from app_v2.data_sanitizer import generate_sanitized_data
from app_v2.core import calculate_fte_from_inputs
from app_v2.config import (
    AGENT_ARCHITECT_MODEL,
    AGENT_WORKER_MODEL,
    AGENT_ARCHITECT_MAX_TOKENS,
    AGENT_WORKER_MAX_TOKENS,
    AGENT_MAX_TOOL_CALLS,
    AGENT_MAX_PLAN_STEPS,
    REVENUE_MONTHLY_PATH,
    REVENUE_ANNUAL_PATH,
    logger,
)

# Check if SDK is available
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Agent features disabled.")


@dataclass
class AgentConfig:
    """Configuration for the hybrid agent architecture.

    Values are loaded from config.py (which reads from environment variables).
    This allows model upgrades without code changes.
    """
    architect_model: str = field(default_factory=lambda: AGENT_ARCHITECT_MODEL)
    worker_model: str = field(default_factory=lambda: AGENT_WORKER_MODEL)
    architect_max_tokens: int = field(default_factory=lambda: AGENT_ARCHITECT_MAX_TOKENS)
    worker_max_tokens: int = field(default_factory=lambda: AGENT_WORKER_MAX_TOKENS)
    temperature: float = 0
    # P2: Safety limits
    max_tool_calls: int = field(default_factory=lambda: AGENT_MAX_TOOL_CALLS)
    max_plan_steps: int = field(default_factory=lambda: AGENT_MAX_PLAN_STEPS)


# P3: Output Schema Validation
PHARMACY_REQUIRED_FIELDS = ['id', 'mesto', 'fte_actual', 'fte_recommended', 'fte_gap']
PHARMACY_LIST_REQUIRED_FIELDS = ['count', 'pharmacies']


def validate_pharmacy_output(result: dict) -> dict:
    """Ensure pharmacy data has required fields."""
    if 'error' in result:
        return result

    missing = [f for f in PHARMACY_REQUIRED_FIELDS if f not in result]
    if missing:
        return {'error': f'Missing fields: {missing}', 'partial_data': result}

    return result


def validate_pharmacy_list_output(result: dict) -> dict:
    """Ensure pharmacy list has required structure."""
    if 'error' in result:
        return result

    missing = [f for f in PHARMACY_LIST_REQUIRED_FIELDS if f not in result]
    if missing:
        return {'error': f'Missing list fields: {missing}', 'partial_data': result}

    return result


# System prompt for the agent - emphasizes using indexed values
AGENT_SYSTEM_PROMPT = """Si expertný FTE analytik pre sieť lekární Dr.Max na Slovensku.

TVOJA ÚLOHA:
Analyzuješ personálne obsadenie lekární a generuješ odporúčania na základe dát.

DOSTUPNÉ NÁSTROJE:
1. search_pharmacies - Vyhľadaj lekárne podľa kritérií
2. get_pharmacy_details - Získaj detaily konkrétnej lekárne
3. get_pharmacy_revenue_trend - Historický vývoj tržieb (2019-2021), YoY rast
4. get_segment_position - Pozícia lekárne v segmente (min/max/avg pre každý KPI)
5. simulate_fte - Simulácia "čo ak?" (zmena blokov/tržieb → nové FTE)
6. compare_to_peers - Porovnaj lekáreň s podobnými prevádzkami
7. get_understaffed - Zoznam poddimenzovaných lekární
8. get_regional_summary - Súhrn za región
9. get_all_regions_summary - Porovnaj všetky regióny
10. generate_report - Vytvor report vo formáte Markdown
11. get_segment_comparison - Porovnaj segmenty (A-E)
12. get_city_summary - Súhrn za mesto s viacerými lekárňami
13. get_network_overview - Rýchly prehľad celej siete
14. get_trend_analysis - Rastúce/klesajúce lekárne
15. get_priority_actions - Prioritizovaný zoznam akcií

═══════════════════════════════════════════════════════════════
CHRÁNENÉ INFORMÁCIE - NIKDY NEZVEREJŇUJ:
═══════════════════════════════════════════════════════════════

1. PRODUKTIVITA:
   - NIKDY neuvádzaj presné hodnoty produktivity (napr. 7.53, 9.14)
   - Používaj LEN indexy (100 = priemer) a percentily
   - NIKDY nevysvetľuj vzorec výpočtu produktivity
   - Ak sa pýtajú na vzorec: "Produktivita je vyjadrená relatívnym indexom"

2. OHROZENÉ TRŽBY (Revenue at Risk):
   - Môžeš uviesť HODNOTU v eurách (napr. €232K)
   - NIKDY nevysvetľuj ako sa počítajú
   - Ak sa pýtajú na výpočet: "Hodnota vychádza z internej metodológie"

3. MODEL A KOEFICIENTY:
   - NIKDY neuvádzaj koeficienty modelu
   - NIKDY nevysvetľuj ako model funguje interne
   - Ak sa pýtajú: "Model využíva machine learning na základe historických dát"

4. SEGMENTOVÉ PRIEMERY:
   - NIKDY neuvádzaj presné segmentové priemery produktivity
   - Používaj LEN relatívne porovnania ("nadpriemerná", "podpriemerná")

═══════════════════════════════════════════════════════════════

PRAVIDLÁ PRE PRODUKTIVITU:
- Produktivita je vyjadrená ako INDEX (100 = priemer segmentu)
- Index 115 = 15% nad priemerom segmentu
- Index 85 = 15% pod priemerom segmentu

FORMÁT ODPOVEDÍ:
- Používaj čísla ID lekární (napr. "ID 33")
- Uvádzaj bloky v tisícoch (napr. "131k blokov")
- Tržby v miliónoch (napr. "2.5M €")
- FTE s jedným desatinným miestom (napr. "6.5 FTE")
- Ohrozené tržby v tisícoch alebo miliónoch (napr. "€232K")

FORMÁT TABULIEK (POVINNÉ):
Pre tabuľky používaj HTML formát, NIE markdown:
<table>
<tr><th>ID</th><th>Mesto</th><th>FTE</th><th>Prod</th><th>Risk€</th><th>Gap</th></tr>
<tr><td>42</td><td>Bratislava</td><td>7.3</td><td>↑</td><td>130K</td><td>+0.8</td></tr>
</table>

⚠️ KRITICKÉ: V KAŽDEJ tabuľke MUSÍ byť stĺpec "ID" na prvom mieste!
Bez ID nie je možné identifikovať konkrétnu lekáreň (môže byť viac v jednom meste).
Formát: "ID" alebo "ID Lekárne" - VŽDY číselné ID z dát.

NIKDY nepoužívaj markdown tabuľky s | znakmi!

PRÍKLAD VÝSTUPU:
"Lekáreň ID 33 (Levice) má nadpriemernú produktivitu (index 115, 28. z 93 v segmente B).
Napriek tomu je poddimenzovaná o 1.2 FTE. Ohrozené tržby: €232K ročne."

PRÍKLAD ODMIETNUTIA:
Otázka: "Ako sa počíta produktivita?"
Odpoveď: "Produktivita je vyjadrená relatívnym indexom, kde 100 = priemer segmentu.
Konkrétna metodológia je interná."

═══════════════════════════════════════════════════════════════
DÁTOVÁ SCHÉMA - VÝZNAM POLÍ:
═══════════════════════════════════════════════════════════════

IDENTIFIKÁTORY:
- id: Unikátny identifikátor lekárne (číslo)
- mesto: Názov mesta/lokality
- region_code: Kód regiónu (napr. RR15)
- typ: Typ lekárne (A-E)

FTE (PERSONÁLNE OBSADENIE) - TOTO SÚ POZÍCIE, NIE PRODUKTIVITA:
- fte_actual: Aktuálny počet FTE (súčasný stav)
- fte_F: FTE farmaceutov
- fte_L: FTE laborantov
- fte_ZF: FTE zástupcov
- fte_recommended: Odporúčaný počet FTE (výstup modelu)
- fte_gap: Rozdiel (fte_actual - fte_recommended)
  → ZÁPORNÉ = poddimenzovaná (napr. -2.0 = chýbajú 2 FTE)
  → KLADNÉ = naddimenzovaná

OBJEM A TRŽBY:
- bloky: Ročný počet transakcií
- trzby: Ročné tržby v EUR
- podiel_rx: Podiel receptových transakcií (0-1)
- bloky_trend: Medziročná zmena transakcií (%)

PRODUKTIVITA (NIE JE TO ISTÉ AKO FTE!):
- productivity_index: Index produktivity (100 = priemer segmentu)
  → 115 = o 15% produktívnejšia než priemer
  → 85 = o 15% menej produktívna
- productivity_percentile: Percentil v rámci segmentu
- productivity_vs_segment: Text ("nadpriemerná"/"podpriemerná"/"priemerná")

FINANČNÉ RIZIKO:
- revenue_at_risk_eur: Ohrozené tržby v EUR (len pre poddimenzované + produktívne)

DÔLEŽITÉ UPOZORNENIE:
⚠️ NIKDY NEZAMIEŇAJ productivity_index s FTE!
   - productivity_index je EFEKTIVITA (hodnota okolo 100)
   - fte_actual/fte_recommended sú POČTY ZAMESTNANCOV (hodnoty 2-12)

═══════════════════════════════════════════════════════════════
AKO VYSVETLIŤ ML MODEL A VÝHODY APLIKÁCIE:
═══════════════════════════════════════════════════════════════

Keď sa používateľ pýta "ako to funguje", "prečo AI", "čo je ML model", "aké sú výhody":

KONTEXT DR.MAX:
- 3 regióny, 200+ lekární na Slovensku
- ŽIADNA jednotná metodológia personálneho obsadenia
- Rozhodnutia doteraz na základe intuície
- Špecializovaný personál (farmaceuti) = limitujúci faktor rastu
- Bez metodológie nie je možné efektívne škálovať sieť

1. PROBLÉM PRED APLIKÁCIOU:
   - Každý región si riadil personál po svojom
   - Manažéri trávili dni zberom dát z rôznych systémov
   - Rozhodnutia na základe pocitu, nie dát
   - Žiadny jednotný pohľad na celú sieť
   - Nedalo sa identifikovať, kde presne chýba personál

2. ČO PRINÁŠA ML MODEL:
   - PRVÁ JEDNOTNÁ METODOLÓGIA pre celú sieť Dr.Max
   - Analyzuje historické dáta všetkých lekární
   - Zohľadňuje: tržby, bloky, typ lekárne, sezónnosť, trendy
   - Predpovedá optimálne personálne obsadenie (FTE)
   - Identifikuje ohrozené tržby pri poddimenzovaní
   - Objektívne kritériá namiesto intuície

3. ČO ROBÍ AI ASISTENT (ty):
   - Sprístupňuje ML model v reálnom čase
   - Prirodzená komunikácia v slovenčine
   - Bez čakania na IT, bez ticketov
   - Drill-down: sieť → segmenty → regióny → lekárne
   - Export do PDF pre manažment

4. KONKRÉTNE PRÍNOSY:
   - Čas: dni práce → sekundy
   - Jednotná metodológia naprieč 3 regiónmi
   - Identifikované ohrozené tržby (použi get_network_overview pre aktuálne číslo)
   - Dátami podložené rozhodnutia o alokácii vzácneho personálu
   - Podklad pre strategické plánovanie rastu

Pri vysvetľovaní VŽDY uveď konkrétne čísla zo siete (použi get_network_overview).
"""

# Architect prompt - for planning and synthesis (Opus 4.5)
ARCHITECT_PLAN_PROMPT = """Si expertný analytik pre sieť lekární Dr.Max.

TVOJA ÚLOHA: Analyzuj požiadavku používateľa a vytvor PLÁN krokov.

DOSTUPNÉ NÁSTROJE A PARAMETRE:
1. search_pharmacies
   - mesto: Mesto/lokalita (partial match) ⚠️ PRE OTÁZKY O KONKRÉTNOM MESTE (Košice, Bratislava...)
   - typ: Typ lekárne (A/B/C/D/E)
   - region: Kód regiónu (RR11, RR15...)
   - min_bloky, max_bloky: Rozsah blokov
   - understaffed_only: Len poddimenzované (bool)
   - overstaffed_only: Len naddimenzované (bool) ⚠️ PRE PRESUN PERSONÁLU - lekárne s prebytkom FTE
   - limit: Max počet výsledkov

2. get_pharmacy_details
   - pharmacy_id: ID lekárne (required)

3. get_pharmacy_revenue_trend ⚠️ PRE HISTORICKÝ VÝVOJ TRŽIEB
   - pharmacy_id: ID lekárne (required)
   - Vráti mesačné tržby za roky 2019, 2020, 2021
   - YoY medziročný rast (2020 vs 2019, 2021 vs 2020)
   - Použiť pri otázkach o vývoji tržieb, trende, raste lekárne

4. compare_to_peers ⚠️ PRE POROVNANIE S PODOBNÝMI LEKÁRŇAMI
   - pharmacy_id: ID lekárne (required)
   - n_peers: Počet podobných lekární (default 5)
   - higher_fte_only: Len lekárne s VYŠŠÍM FTE (bool) ⚠️ POUŽIŤ pre hľadanie zdrojov na presun
   - Nájde lekárne s podobnými bloky A tržbami (±20%) v rovnakom segmente
   - Vráti štatistiky peers (avg FTE, produktivita) a porovnanie s cieľovou lekárňou

5. get_understaffed
   - mesto: Mesto/lokalita (partial match) ⚠️ PRE OTÁZKY O KONKRÉTNOM MESTE
   - region: Filter podľa regiónu
   - min_gap: Minimálny FTE deficit
   - limit: Max výsledkov
   - high_risk_only: Len s ohrozenými tržbami > 0 (bool) ⚠️ PRE OTÁZKY O OHROZENÝCH TRŽBÁCH
   - high_productivity_only: Len nadpriemerná produktivita (bool) ⚠️ PRE "VYSOKÁ PRODUKTIVITA"
   - sort_by: "fte_gap" | "revenue_at_risk" | "productivity" ⚠️ PRE TOP RIZIKO použi "revenue_at_risk"

6. get_regional_summary
   - region: Kód regiónu (required)

7. get_all_regions_summary ⚠️ POVINNÉ PRE POROVNANIE REGIÓNOV
   - sort_by: "revenue_at_risk" | "productivity" | "understaffed"
   - Vráti VŠETKY regióny naraz - použiť pri "porovnaj regióny", "všetky regióny"

8. generate_report
   - title: Názov reportu
   - pharmacy_ids: Zoznam ID
   - region: Región

9. get_segment_comparison ⚠️ PRE POROVNANIE SEGMENTOV (A-E)
   - Bez parametrov - vráti všetky segmenty s ohrozenými tržbami a produktivitou
   - Použiť pri "ktorý segment", "porovnaj segmenty"

10. get_city_summary ⚠️ PRE MESTÁ S VIACERÝMI LEKÁRŇAMI
    - mesto: Názov mesta (required)
    - Vráti aj info o možnosti presunu personálu v rámci mesta

11. get_network_overview ⚠️ PRE CELKOVÝ PREHĽAD SIETE
    - Bez parametrov - rýchly health check celej siete
    - Použiť pri "ako je na tom sieť", "celkový prehľad", "koľko lekární"

12. get_trend_analysis ⚠️ PRE RASTÚCE/KLESAJÚCE LEKÁRNE
    - trend_threshold: Prah v % (default 10)
    - limit: Max počet (default 20)
    - Použiť pri "rastúce lekárne", "klesajúce", "trendy"

13. get_priority_actions ⚠️ PRE "ČO RIEŠIŤ NAJSKÔR"
    - limit: Max počet akcií (default 10)
    - Kombinuje riziko, produktivitu a FTE gap do prioritizovaného zoznamu

VÝSTUP: Vytvor JSON plán s krokmi:
{
  "analysis": "Stručná analýza požiadavky",
  "steps": [
    {"tool": "názov_nástroja", "params": {...}, "purpose": "účel kroku"},
    ...
  ],
  "synthesis_focus": "Na čo sa zamerať pri syntéze výsledkov"
}

PRAVIDLÁ:
- Max 5 krokov
- Vyber len potrebné nástroje
- Pri otázkach o MESTE (Košice, Bratislava...) použi get_city_summary ALEBO parameter "mesto"
- Pri porovnaniach použi compare_to_peers alebo search_pharmacies
- Pri POROVNANÍ REGIÓNOV použi get_all_regions_summary (nie get_regional_summary viackrát!)
- Pri POROVNANÍ SEGMENTOV použi get_segment_comparison
- Pri analýze JEDNÉHO regiónu použi get_regional_summary + get_understaffed
- Pri "celkový prehľad" alebo "ako je na tom sieť" použi get_network_overview
- Pri "čo riešiť najskôr" alebo "priority" použi get_priority_actions
- Pri "rastúce/klesajúce lekárne" alebo "trendy" pouzi get_trend_analysis
- Ak user chce "lekárne s vyšším FTE" alebo "presun personálu", použi overstaffed_only: true
- Ak user chce "lekárne s vyšším FTE" na porovnanie, použi higher_fte_only: true
"""

ARCHITECT_SYNTHESIZE_PROMPT = """Si expertný analytik pre sieť lekární Dr.Max.

TVOJA ÚLOHA: Syntetizuj výsledky z nástrojov do STRUČNEJ odpovede.

═══════════════════════════════════════════════════════════════
DÔLEŽITÉ - STRUČNOSŤ
═══════════════════════════════════════════════════════════════
- Max 3 vety pre jednu lekáreň
- Pri viacerých lekárňach použi tabuľku
- Žiadne zbytočné úvody ani záverečné frázy

═══════════════════════════════════════════════════════════════
DÁTOVÁ SCHÉMA
═══════════════════════════════════════════════════════════════
- fte_actual: Aktuálne FTE
- fte_recommended: Odporúčané FTE
- fte_gap: Rozdiel (ZÁPORNÉ = poddimenzovaná)
- productivity_index: Index (100 = priemer) - TOTO NIE JE FTE!
- revenue_at_risk_eur: Ohrozené tržby v EUR

═══════════════════════════════════════════════════════════════
KEDY ODPORÚČAŤ PRIDANIE FTE
═══════════════════════════════════════════════════════════════
Odporúčaj pridanie FTE IBA ak SÚ SPLNENÉ OBE podmienky:
1. revenue_at_risk_eur > 0
2. productivity_index > 100 (nadpriemerná)

Ak productivity_index < 100 → "Produktivita podpriemerná - najprv optimalizovať."

═══════════════════════════════════════════════════════════════
TABUĽKA PRE VIACERO LEKÁRNÍ (ID JE POVINNÉ!)
═══════════════════════════════════════════════════════════════
<table>
<tr><th>ID</th><th>Mesto</th><th>FTE</th><th>Prod</th><th>Risk€</th><th>Gap</th></tr>
<tr><td>33</td><td>Levice</td><td>6.5</td><td>↑</td><td>232K</td><td>+1.2</td></tr>
<tr><td>74</td><td>Martin</td><td>6.9</td><td>↓</td><td>0</td><td>+0.4</td></tr>
</table>

⚠️ Stĺpec ID je POVINNÝ - bez neho nie je jasné, ktorú lekáreň používateľ má otvoriť!
Legenda: Prod ↑=nadpriem. ↓=podpriem. | Risk€=ohrozené | Gap=chýba FTE
Na konci: "⚠ Celkovo ohrozené: €XXK" (ak súčet > 0)

═══════════════════════════════════════════════════════════════
CHRÁNENÉ INFORMÁCIE
═══════════════════════════════════════════════════════════════
NESMIEŠ: vzorce, koeficienty, segmentové priemery, presné hodnoty produktivity
"""

WORKER_PROMPT = """Vykonaj nástroj a vráť výsledok. Neinterpretuj, len vráť dáta."""


class DrMaxAgent:
    """
    Autonomous agent for pharmacy staffing analysis.

    Uses custom tools with sanitized data to protect proprietary formulas.
    """

    def __init__(self, data_path: Path):
        """
        Initialize the agent.

        Args:
            data_path: Path to data directory (predictions are in CSV)
        """
        self.data_path = data_path
        self.config = AgentConfig()

        if ANTHROPIC_AVAILABLE:
            import httpx
            # Configure longer timeouts for Cloud Run
            self.client = Anthropic(
                timeout=httpx.Timeout(120.0, connect=30.0),
                max_retries=2
            )
        else:
            self.client = None

        # Lazy-load sanitized data (includes predictions from CSV)
        self._sanitized_df = None

    @property
    def sanitized_data(self):
        """Lazy-load sanitized data (includes predictions from CSV)."""
        if self._sanitized_df is None:
            self._sanitized_df = generate_sanitized_data(self.data_path)
        return self._sanitized_df

    # === TOOL IMPLEMENTATIONS ===

    def tool_search_pharmacies(
        self,
        mesto: str = None,
        typ: str = None,
        region: str = None,
        min_bloky: int = None,
        max_bloky: int = None,
        understaffed_only: bool = False,
        overstaffed_only: bool = False,
        sort_by: str = None,
        sort_desc: bool = True,
        limit: int = 10
    ) -> dict:
        """Search pharmacies with filters."""
        # Ensure types (AI might pass strings)
        if min_bloky is not None:
            min_bloky = int(min_bloky)
        if max_bloky is not None:
            max_bloky = int(max_bloky)
        limit = int(limit) if limit is not None else 10

        df = self.sanitized_data.copy()

        if mesto:
            df = df[df['mesto'].str.contains(mesto, case=False, na=False)]
        if typ:
            df = df[df['typ'].str.contains(typ, case=False)]
        if region:
            df = df[df['region_code'] == region]
        if min_bloky:
            df = df[df['bloky'] >= min_bloky]
        if max_bloky:
            df = df[df['bloky'] <= max_bloky]
        if understaffed_only:
            df = df[df['fte_gap'] > 0.5]  # Positive gap = understaffed (need more FTE)
        if overstaffed_only:
            df = df[df['fte_gap'] < -0.5]  # Negative gap = overstaffed (excess FTE)

        # Sort by specified column (default: bloky descending for "top/najväčšie" queries)
        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=not sort_desc)
        else:
            # Default sort by bloky descending (largest first)
            df = df.sort_values(by='bloky', ascending=False)

        df = df.head(limit)

        # P3: Validate output schema
        return validate_pharmacy_list_output({
            'count': len(df),
            'pharmacies': df.to_dict('records')
        })

    def tool_get_pharmacy_details(self, pharmacy_id: int) -> dict:
        """Get details for a specific pharmacy."""
        # Ensure pharmacy_id is int (AI might pass string)
        pharmacy_id = int(pharmacy_id)
        df = self.sanitized_data
        pharmacy = df[df['id'] == pharmacy_id]

        if pharmacy.empty:
            return {'error': f'Pharmacy {pharmacy_id} not found'}

        result = pharmacy.iloc[0].to_dict()

        # Round FTE values for clarity (avoid AI confusion from long decimals)
        result['fte_actual'] = round(result.get('fte_actual', 0), 1)
        result['fte_F'] = round(result.get('fte_F', 0), 1)
        result['fte_L'] = round(result.get('fte_L', 0), 1)
        result['fte_ZF'] = round(result.get('fte_ZF', 0), 1)
        result['trzby'] = int(result.get('trzby', 0))
        result['bloky'] = int(result.get('bloky', 0))
        result['podiel_rx'] = round(result.get('podiel_rx', 0), 2)
        result['bloky_trend'] = round(result.get('bloky_trend', 0) * 100, 0)  # Convert to %

        # Add staffing status based on fte_gap (positive = understaffed)
        fte_gap = result.get('fte_gap', 0)
        result['staffing_status'] = (
            'poddimenzovaná' if fte_gap > 0.5  # Positive gap = understaffed
            else 'naddimenzovaná' if fte_gap < -0.5  # Negative gap = overstaffed
            else 'optimálna'
        )

        # Add explicit summary to prevent AI confusion
        result['_summary'] = (
            f"ID {pharmacy_id}: má {result['fte_actual']} FTE, "
            f"potrebuje {result['fte_recommended']} FTE, "
            f"gap {result['fte_gap']:+.1f}, "
            f"ohrozené €{result['revenue_at_risk_eur']:,}"
        )

        # P3: Validate output schema
        return validate_pharmacy_output(result)

    def tool_get_pharmacy_revenue_trend(self, pharmacy_id: int) -> dict:
        """Get historical revenue trend data for a pharmacy (2019-2021)."""
        import pandas as pd

        pharmacy_id = int(pharmacy_id)

        # Check if revenue data files exist
        if not REVENUE_MONTHLY_PATH.exists() or not REVENUE_ANNUAL_PATH.exists():
            return {'error': 'Historické dáta o tržbách nie sú k dispozícii'}

        # Load revenue data
        df_monthly = pd.read_csv(REVENUE_MONTHLY_PATH)
        df_annual = pd.read_csv(REVENUE_ANNUAL_PATH)

        # Get monthly data for this pharmacy
        pharm_monthly = df_monthly[df_monthly['id'] == pharmacy_id]
        if len(pharm_monthly) == 0:
            return {'error': f'Žiadne dáta o tržbách pre lekáreň {pharmacy_id}'}

        # Organize by year
        monthly = {}
        yearly_totals = {}
        for year in [2019, 2020, 2021]:
            year_data = pharm_monthly[pharm_monthly['year'] == year].sort_values('month')
            if len(year_data) > 0:
                monthly[str(year)] = [
                    {'month': int(row['month']), 'revenue': round(float(row['revenue']), 0)}
                    for _, row in year_data.iterrows()
                ]
                yearly_totals[str(year)] = round(year_data['revenue'].sum(), 0)

        # Get YoY growth data
        pharm_annual = df_annual[df_annual['id'] == pharmacy_id]
        yoy_2020 = None
        yoy_2021 = None
        if len(pharm_annual) > 0:
            annual_row = pharm_annual.iloc[0]
            yoy_2020 = round(annual_row['yoy_growth_2020'], 1) if pd.notna(annual_row['yoy_growth_2020']) else None
            yoy_2021 = round(annual_row['yoy_growth_2021'], 1) if pd.notna(annual_row['yoy_growth_2021']) else None

        # Get pharmacy name from sanitized data
        pharmacy = self.sanitized_data[self.sanitized_data['id'] == pharmacy_id]
        mesto = pharmacy.iloc[0]['mesto'] if not pharmacy.empty else 'Neznáme'

        return {
            'pharmacy_id': pharmacy_id,
            'mesto': mesto,
            'yearly_totals': yearly_totals,
            'yoy_growth': {
                '2020_vs_2019': f"{yoy_2020:+.1f}%" if yoy_2020 else None,
                '2021_vs_2020': f"{yoy_2021:+.1f}%" if yoy_2021 else None
            },
            'monthly_data': monthly,
            '_summary': (
                f"Lekáreň {pharmacy_id} ({mesto}): "
                f"Tržby 2019: €{yearly_totals.get('2019', 0):,.0f}, "
                f"2020: €{yearly_totals.get('2020', 0):,.0f} ({yoy_2020:+.1f}% YoY), " if yoy_2020 else ""
                f"2021: €{yearly_totals.get('2021', 0):,.0f} ({yoy_2021:+.1f}% YoY)" if yoy_2021 else ""
            )
        }

    def tool_get_segment_position(self, pharmacy_id: int) -> dict:
        """Get pharmacy's position within its segment for all KPIs."""
        pharmacy_id = int(pharmacy_id)
        df = self.sanitized_data
        pharmacy = df[df['id'] == pharmacy_id]

        if pharmacy.empty:
            return {'error': f'Lekáreň {pharmacy_id} nenájdená'}

        p = pharmacy.iloc[0]
        typ = p['typ']
        segment_data = df[df['typ'] == typ].copy()

        # Constants for hourly calculations
        HOURS_PER_FTE_YEAR = 2112  # 176 hours/month * 12

        # Calculate hourly metrics for segment
        segment_data['hours'] = segment_data['fte_actual'] * 1.21 * HOURS_PER_FTE_YEAR
        segment_data['bloky_per_hour'] = segment_data['bloky'] / segment_data['hours']
        segment_data['trzby_per_hour'] = segment_data['trzby'] / segment_data['hours']
        segment_data['basket'] = segment_data['trzby'] / segment_data['bloky']

        # Calculate for this pharmacy
        p_hours = p['fte_actual'] * 1.21 * HOURS_PER_FTE_YEAR
        p_bloky_hour = p['bloky'] / p_hours if p_hours > 0 else 0
        p_trzby_hour = p['trzby'] / p_hours if p_hours > 0 else 0
        p_basket = p['trzby'] / p['bloky'] if p['bloky'] > 0 else 0

        def get_position(value, series):
            """Calculate percentile and position description."""
            pct = (series < value).mean() * 100
            avg = series.mean()
            if value > avg * 1.1:
                pos = 'nad priemerom'
            elif value < avg * 0.9:
                pos = 'pod priemerom'
            else:
                pos = 'okolo priemeru'
            return round(pct, 0), pos

        # Build KPI positions
        kpis = {}

        # Bloky (in thousands)
        bloky_pct, bloky_pos = get_position(p['bloky'], segment_data['bloky'])
        kpis['bloky'] = {
            'value': f"{int(p['bloky']/1000)}k",
            'segment_min': f"{int(segment_data['bloky'].min()/1000)}k",
            'segment_max': f"{int(segment_data['bloky'].max()/1000)}k",
            'segment_avg': f"{int(segment_data['bloky'].mean()/1000)}k",
            'percentile': bloky_pct,
            'position': bloky_pos
        }

        # Tržby (in millions)
        trzby_pct, trzby_pos = get_position(p['trzby'], segment_data['trzby'])
        kpis['trzby'] = {
            'value': f"{round(p['trzby']/1000000, 1)}M€",
            'segment_min': f"{round(segment_data['trzby'].min()/1000000, 1)}M€",
            'segment_max': f"{round(segment_data['trzby'].max()/1000000, 1)}M€",
            'segment_avg': f"{round(segment_data['trzby'].mean()/1000000, 1)}M€",
            'percentile': trzby_pct,
            'position': trzby_pos
        }

        # Rx %
        rx_pct, rx_pos = get_position(p['podiel_rx'], segment_data['podiel_rx'])
        kpis['rx_podiel'] = {
            'value': f"{int(p['podiel_rx']*100)}%",
            'segment_min': f"{int(segment_data['podiel_rx'].min()*100)}%",
            'segment_max': f"{int(segment_data['podiel_rx'].max()*100)}%",
            'segment_avg': f"{int(segment_data['podiel_rx'].mean()*100)}%",
            'percentile': rx_pct,
            'position': rx_pos
        }

        # FTE
        fte_pct, fte_pos = get_position(p['fte_actual'], segment_data['fte_actual'])
        kpis['fte'] = {
            'value': round(p['fte_actual'], 1),
            'segment_min': round(segment_data['fte_actual'].min(), 1),
            'segment_max': round(segment_data['fte_actual'].max(), 1),
            'segment_avg': round(segment_data['fte_actual'].mean(), 1),
            'percentile': fte_pct,
            'position': fte_pos
        }

        # Bloky/h
        blokyhod_pct, blokyhod_pos = get_position(p_bloky_hour, segment_data['bloky_per_hour'])
        kpis['bloky_za_hodinu'] = {
            'value': round(p_bloky_hour, 1),
            'segment_min': round(segment_data['bloky_per_hour'].min(), 1),
            'segment_max': round(segment_data['bloky_per_hour'].max(), 1),
            'segment_avg': round(segment_data['bloky_per_hour'].mean(), 1),
            'percentile': blokyhod_pct,
            'position': blokyhod_pos
        }

        # Tržby/h
        trzbyhod_pct, trzbyhod_pos = get_position(p_trzby_hour, segment_data['trzby_per_hour'])
        kpis['trzby_za_hodinu'] = {
            'value': f"{int(p_trzby_hour)}€",
            'segment_min': f"{int(segment_data['trzby_per_hour'].min())}€",
            'segment_max': f"{int(segment_data['trzby_per_hour'].max())}€",
            'segment_avg': f"{int(segment_data['trzby_per_hour'].mean())}€",
            'percentile': trzbyhod_pct,
            'position': trzbyhod_pos
        }

        # Košík
        basket_pct, basket_pos = get_position(p_basket, segment_data['basket'])
        kpis['kosik'] = {
            'value': f"{round(p_basket, 1)}€",
            'segment_min': f"{round(segment_data['basket'].min(), 1)}€",
            'segment_max': f"{round(segment_data['basket'].max(), 1)}€",
            'segment_avg': f"{round(segment_data['basket'].mean(), 1)}€",
            'percentile': basket_pct,
            'position': basket_pos
        }

        # Productivity (index only, not raw value)
        prod_pct, prod_pos = get_position(p['productivity_index'], segment_data['productivity_index'])
        kpis['produktivita'] = {
            'value': int(p['productivity_index']),
            'segment_avg': 100,  # By definition, 100 = segment average
            'percentile': prod_pct,
            'position': prod_pos
        }

        return {
            'pharmacy_id': pharmacy_id,
            'mesto': p['mesto'],
            'segment': typ,
            'segment_count': len(segment_data),
            'kpis': kpis,
            '_summary': f"Lekáreň {pharmacy_id} ({p['mesto']}) v segmente {typ} ({len(segment_data)} lekární)"
        }

    def tool_simulate_fte(
        self,
        pharmacy_id: int = None,
        bloky: float = None,
        trzby: float = None,
        bloky_change_pct: float = None,
        trzby_change_pct: float = None,
        typ: str = None
    ) -> dict:
        """
        Simulate FTE requirements with changed inputs (what-if analysis).

        Can be used in two ways:
        1. With pharmacy_id: Use pharmacy's current values as base, apply % changes
        2. Without pharmacy_id: Use absolute values for bloky/trzby
        """
        # If pharmacy_id provided, get current values as base
        if pharmacy_id is not None:
            pharmacy_id = int(pharmacy_id)
            df = self.sanitized_data
            pharmacy = df[df['id'] == pharmacy_id]

            if pharmacy.empty:
                return {'error': f'Lekáreň {pharmacy_id} nenájdená'}

            p = pharmacy.iloc[0]
            base_bloky = p['bloky']
            base_trzby = p['trzby']
            base_typ = p['typ']
            base_rx = p['podiel_rx']
            current_fte = p['fte_actual']
            current_recommended = p['fte_recommended']

            # Apply percentage changes if provided
            if bloky_change_pct is not None:
                sim_bloky = base_bloky * (1 + bloky_change_pct / 100)
            elif bloky is not None:
                sim_bloky = float(bloky)
            else:
                sim_bloky = base_bloky

            if trzby_change_pct is not None:
                sim_trzby = base_trzby * (1 + trzby_change_pct / 100)
            elif trzby is not None:
                sim_trzby = float(trzby)
            else:
                sim_trzby = base_trzby

            sim_typ = typ if typ else base_typ
            sim_rx = base_rx

        else:
            # Manual simulation without pharmacy context
            if bloky is None or trzby is None:
                return {'error': 'Bez pharmacy_id musíš zadať bloky aj trzby'}

            sim_bloky = float(bloky)
            sim_trzby = float(trzby)
            sim_typ = typ if typ else 'B - shopping'
            sim_rx = 0.5
            base_bloky = None
            base_trzby = None
            current_fte = None
            current_recommended = None

        # Calculate new FTE using core function
        try:
            result = calculate_fte_from_inputs(
                bloky=sim_bloky,
                trzby=sim_trzby,
                typ=sim_typ,
                podiel_rx=sim_rx,
                productivity_z=0,  # Average productivity
                variability_z=0,
                pharmacy_id=pharmacy_id
            )

            new_fte = round(result['fte_total'], 1)
            new_fte_F = round(result['fte_F'], 1)
            new_fte_L = round(result['fte_L'], 1)
            new_fte_ZF = round(result['fte_ZF'], 1)

        except Exception as e:
            return {'error': f'Chyba pri výpočte: {str(e)}'}

        # Build response
        response = {
            'simulation_inputs': {
                'bloky': int(sim_bloky),
                'trzby': int(sim_trzby),
                'typ': sim_typ
            },
            'simulated_fte': {
                'total': new_fte,
                'breakdown': {
                    'F': new_fte_F,
                    'L': new_fte_L,
                    'ZF': new_fte_ZF
                }
            }
        }

        # Add comparison if pharmacy context available
        if pharmacy_id is not None:
            bloky_diff = sim_bloky - base_bloky
            trzby_diff = sim_trzby - base_trzby
            fte_diff = new_fte - current_recommended

            response['pharmacy_id'] = pharmacy_id
            response['current_values'] = {
                'bloky': int(base_bloky),
                'trzby': int(base_trzby),
                'fte_actual': current_fte,
                'fte_recommended': current_recommended
            }
            response['changes'] = {
                'bloky_diff': int(bloky_diff),
                'bloky_diff_pct': round(bloky_diff / base_bloky * 100, 1) if base_bloky > 0 else 0,
                'trzby_diff': int(trzby_diff),
                'trzby_diff_pct': round(trzby_diff / base_trzby * 100, 1) if base_trzby > 0 else 0,
                'fte_diff': round(fte_diff, 1)
            }
            response['_summary'] = (
                f"Simulácia pre lekáreň {pharmacy_id}: "
                f"Pri {int(sim_bloky/1000)}k blokoch a {round(sim_trzby/1000000, 1)}M€ tržbách "
                f"by potrebovala {new_fte} FTE "
                f"({'+'if fte_diff >= 0 else ''}{round(fte_diff, 1)} oproti súčasnému odporúčaniu)"
            )
        else:
            response['_summary'] = (
                f"Simulácia: Pri {int(sim_bloky/1000)}k blokoch a {round(sim_trzby/1000000, 1)}M€ tržbách "
                f"v segmente {sim_typ} je potrebných {new_fte} FTE"
            )

        return response

    def tool_compare_to_peers(
        self,
        pharmacy_id: int,
        n_peers: int = 5,
        higher_fte_only: bool = False
    ) -> dict:
        """Compare pharmacy to similar peers in the same segment."""
        # Ensure types (AI might pass strings)
        pharmacy_id = int(pharmacy_id)
        n_peers = int(n_peers)
        df = self.sanitized_data

        # Get target pharmacy
        target = df[df['id'] == pharmacy_id]
        if target.empty:
            return {'error': f'Pharmacy {pharmacy_id} not found'}

        target = target.iloc[0]
        target_bloky = target['bloky']
        target_trzby = target['trzby']

        # Find peers in same segment with similar bloky AND trzby (±20%)
        same_segment = df[df['typ'] == target['typ']]
        bloky_range = target_bloky * 0.2
        trzby_range = target_trzby * 0.2

        peers = same_segment[
            (same_segment['bloky'] >= target_bloky - bloky_range) &
            (same_segment['bloky'] <= target_bloky + bloky_range) &
            (same_segment['trzby'] >= target_trzby - trzby_range) &
            (same_segment['trzby'] <= target_trzby + trzby_range) &
            (same_segment['id'] != pharmacy_id)
        ].copy()

        if higher_fte_only:
            peers = peers[peers['fte_actual'] > target['fte_actual']]

        # Sort by combined similarity (bloky + trzby difference)
        peers['bloky_diff'] = abs(peers['bloky'] - target_bloky) / target_bloky
        peers['trzby_diff'] = abs(peers['trzby'] - target_trzby) / target_trzby
        peers['similarity_score'] = peers['bloky_diff'] + peers['trzby_diff']
        peers = peers.sort_values('similarity_score').head(n_peers)

        # Calculate peer statistics
        peer_count = len(peers)
        if peer_count > 0:
            avg_fte = round(peers['fte_actual'].mean(), 1)
            avg_fte_recommended = round(peers['fte_recommended'].mean(), 1)
            avg_productivity = int(peers['productivity_index'].mean())
            avg_gap = round(peers['fte_gap'].mean(), 1)

            # Comparison with target
            fte_vs_peers = round(target['fte_actual'] - avg_fte, 1)
            productivity_vs_peers = int(target['productivity_index'] - avg_productivity)
            gap_vs_peers = round(target['fte_gap'] - avg_gap, 1)
        else:
            avg_fte = avg_fte_recommended = avg_productivity = avg_gap = 0
            fte_vs_peers = productivity_vs_peers = gap_vs_peers = 0

        # Format peers for output (remove temp columns)
        peers_output = peers.drop(columns=['bloky_diff', 'trzby_diff', 'similarity_score']).to_dict('records')

        # Format each peer with key metrics
        formatted_peers = []
        for p in peers_output:
            formatted_peers.append({
                'id': int(p['id']),
                'mesto': p['mesto'],
                'bloky': int(p['bloky']),
                'trzby': int(p['trzby']),
                'fte_actual': round(p['fte_actual'], 1),
                'fte_recommended': round(p['fte_recommended'], 1),
                'fte_gap': round(p['fte_gap'], 1),
                'productivity_index': int(p['productivity_index']),
                'revenue_at_risk_eur': int(p['revenue_at_risk_eur'])
            })

        return {
            'target': {
                'id': int(target['id']),
                'mesto': target['mesto'],
                'bloky': int(target_bloky),
                'trzby': int(target_trzby),
                'fte_actual': round(target['fte_actual'], 1),
                'fte_recommended': round(target['fte_recommended'], 1),
                'fte_gap': round(target['fte_gap'], 1),
                'productivity_index': int(target['productivity_index']),
                'revenue_at_risk_eur': int(target['revenue_at_risk_eur'])
            },
            'segment': target['typ'],
            'peer_count': peer_count,
            'peers': formatted_peers,
            'peer_statistics': {
                'avg_fte': avg_fte,
                'avg_fte_recommended': avg_fte_recommended,
                'avg_productivity_index': avg_productivity,
                'avg_fte_gap': avg_gap
            },
            'comparison': {
                'fte_vs_peers': fte_vs_peers,
                'productivity_vs_peers': productivity_vs_peers,
                'gap_vs_peers': gap_vs_peers,
                'fte_assessment': 'vyššie' if fte_vs_peers > 0.5 else ('nižšie' if fte_vs_peers < -0.5 else 'porovnateľné'),
                'productivity_assessment': 'vyššia' if productivity_vs_peers > 5 else ('nižšia' if productivity_vs_peers < -5 else 'porovnateľná')
            },
            'comparison_note': f"Porovnanie s {peer_count} lekárňami segmentu {target['typ']} s podobným objemom ({int(target_bloky/1000)}k blokov, {int(target_trzby/1000000)}M€ tržieb ± 20%)"
        }

    def tool_get_understaffed(
        self,
        mesto: str = None,
        region: str = None,
        min_gap: float = -0.5,
        limit: int = 20,
        high_risk_only: bool = False,
        high_productivity_only: bool = False,
        sort_by: str = 'fte_gap'
    ) -> dict:
        """Get list of understaffed pharmacies with optional filters."""
        # Ensure types (AI might pass strings)
        min_gap = float(min_gap) if min_gap is not None else -0.5
        limit = int(limit) if limit is not None else 20
        df = self.sanitized_data.copy()

        # Filter understaffed (positive gap = understaffed)
        # Note: min_gap parameter is now interpreted as minimum positive gap
        df = df[df['fte_gap'] > abs(min_gap)]

        # Filter by mesto (city) if specified
        if mesto:
            df = df[df['mesto'].str.contains(mesto, case=False, na=False)]

        # Filter by region if specified
        if region:
            df = df[df['region_code'] == region]

        # Filter high risk only (revenue_at_risk > 0)
        if high_risk_only:
            df = df[df['revenue_at_risk_eur'] > 0]

        # Filter high productivity only (index > 100)
        if high_productivity_only:
            df = df[df['productivity_index'] > 100]

        # Sort by specified field
        if sort_by == 'revenue_at_risk':
            df = df.sort_values('revenue_at_risk_eur', ascending=False)
        elif sort_by == 'productivity':
            df = df.sort_values('productivity_index', ascending=False)
        else:
            df = df.sort_values('fte_gap', ascending=False)  # Most understaffed (highest gap) first

        # P3: Validate output schema
        return validate_pharmacy_list_output({
            'count': len(df),
            'total_revenue_at_risk_eur': int(df['revenue_at_risk_eur'].sum()),
            'pharmacies': df.head(limit).to_dict('records')
        })

    def tool_get_regional_summary(self, region: str) -> dict:
        """Get summary statistics for a region."""
        df = self.sanitized_data
        region_df = df[df['region_code'] == region]

        if region_df.empty:
            return {'error': f'Region {region} not found'}

        understaffed = region_df[region_df['fte_gap'] > 0.5]  # Positive gap = understaffed
        overstaffed = region_df[region_df['fte_gap'] < -0.5]  # Negative gap = overstaffed
        # Urgent: understaffed + revenue at risk (same criteria as app)
        urgent = region_df[(region_df['fte_gap'] > 0.5) & (region_df['revenue_at_risk_eur'] > 0)]

        # FTE-weighted productivity
        total_fte = region_df['fte_actual'].sum()
        weighted_prod = (region_df['productivity_index'] * region_df['fte_actual']).sum() / total_fte if total_fte > 0 else 100

        return {
            'region': region,
            'pharmacy_count': len(region_df),
            'total_fte': round(region_df['fte_actual'].sum(), 1),
            'total_bloky': int(region_df['bloky'].sum()),
            'understaffed_count': len(understaffed),
            'overstaffed_count': len(overstaffed),
            'urgent_count': len(urgent),  # Matches app's urgent criteria
            'total_revenue_at_risk_eur': int(urgent['revenue_at_risk_eur'].sum()),
            'avg_productivity_index': int(weighted_prod),  # FTE-weighted
            'types': region_df['typ'].value_counts().to_dict()
        }

    def tool_get_all_regions_summary(self, sort_by: str = 'revenue_at_risk') -> dict:
        """Get summary statistics for ALL regions at once."""
        df = self.sanitized_data
        regions = df['region_code'].unique()

        summaries = []
        for region in sorted(regions):
            region_df = df[df['region_code'] == region]
            understaffed = region_df[region_df['fte_gap'] > 0.5]  # Positive gap = understaffed
            overstaffed = region_df[region_df['fte_gap'] < -0.5]  # Negative gap = overstaffed
            # Urgent: understaffed + revenue at risk (same criteria as app)
            urgent = region_df[(region_df['fte_gap'] > 0.5) & (region_df['revenue_at_risk_eur'] > 0)]

            # FTE-weighted productivity
            total_fte = region_df['fte_actual'].sum()
            weighted_prod = (region_df['productivity_index'] * region_df['fte_actual']).sum() / total_fte if total_fte > 0 else 100

            summaries.append({
                'region': region,
                'pharmacy_count': len(region_df),
                'total_fte_actual': round(region_df['fte_actual'].sum(), 1),
                'total_fte_recommended': round(region_df['fte_recommended'].sum(), 1),
                'understaffed_count': len(understaffed),
                'overstaffed_count': len(overstaffed),
                'urgent_count': len(urgent),  # Matches app's urgent criteria
                'revenue_at_risk_eur': int(urgent['revenue_at_risk_eur'].sum()),
                'avg_productivity_index': int(weighted_prod)  # FTE-weighted
            })

        # Sort by specified field
        if sort_by == 'revenue_at_risk':
            summaries.sort(key=lambda x: x['revenue_at_risk_eur'], reverse=True)
        elif sort_by == 'productivity':
            summaries.sort(key=lambda x: x['avg_productivity_index'], reverse=True)
        elif sort_by == 'understaffed':
            summaries.sort(key=lambda x: x['understaffed_count'], reverse=True)

        total_risk = sum(s['revenue_at_risk_eur'] for s in summaries)

        return {
            'region_count': len(summaries),
            'total_revenue_at_risk_eur': total_risk,
            'regions': summaries
        }

    def tool_generate_report(
        self,
        title: str,
        pharmacy_ids: list = None,
        region: str = None,
        include_recommendations: bool = True
    ) -> dict:
        """Generate a Markdown report."""
        lines = [f"# {title}", ""]

        if region:
            summary = self.tool_get_regional_summary(region)
            lines.extend([
                f"## Región: {region}",
                f"- Počet lekární: {summary['pharmacy_count']}",
                f"- Celkové FTE: {summary['total_fte']}",
                f"- Poddimenzované: {summary['understaffed_count']}",
                f"- Ohrozené tržby: €{summary['total_revenue_at_risk_eur']:,}",
                ""
            ])

        if pharmacy_ids:
            lines.append("## Analyzované lekárne")
            lines.append("")
            lines.append("| ID | Mesto | Typ | FTE | Rozdiel | Produktivita |")
            lines.append("|---|---|---|---|---|---|")

            for pid in pharmacy_ids:
                p = self.tool_get_pharmacy_details(pid)
                if 'error' not in p:
                    lines.append(
                        f"| {p['id']} | {p['mesto']} | {p['typ']} | "
                        f"{p.get('fte_actual', 0):.1f} | "
                        f"{p.get('fte_gap', 0):+.1f} | "
                        f"index {p['productivity_index']} |"
                    )
            lines.append("")

        if include_recommendations:
            lines.extend([
                "## Odporúčania",
                "",
                "1. Prioritizovať lekárne s najvyššími ohrozenými tržbami",
                "2. Zvážiť prerozdelenie z naddimenzovaných prevádzok",
                "3. Pri vysokom raste (+15%) proaktívne navýšiť personál",
                ""
            ])

        report_content = "\n".join(lines)

        return {
            'format': 'markdown',
            'content': report_content,
            'word_count': len(report_content.split())
        }

    def tool_get_segment_comparison(self) -> dict:
        """Compare performance across all segments (A-E)."""
        df = self.sanitized_data
        segments = df['typ'].unique()

        summaries = []
        for segment in sorted(segments):
            seg_df = df[df['typ'] == segment]
            understaffed = seg_df[seg_df['fte_gap'] > 0.5]  # Positive gap = understaffed
            overstaffed = seg_df[seg_df['fte_gap'] < -0.5]  # Negative gap = overstaffed
            # Urgent: understaffed + revenue at risk (same criteria as app)
            urgent = seg_df[(seg_df['fte_gap'] > 0.5) & (seg_df['revenue_at_risk_eur'] > 0)]

            # FTE-weighted productivity (more accurate than simple average)
            total_fte = seg_df['fte_actual'].sum()
            weighted_prod = (seg_df['productivity_index'] * seg_df['fte_actual']).sum() / total_fte if total_fte > 0 else 100

            # Average growth (bloky_trend) - FTE-weighted
            weighted_trend = (seg_df['bloky_trend'] * seg_df['fte_actual']).sum() / total_fte if total_fte > 0 else 0

            summaries.append({
                'segment': segment,
                'pharmacy_count': len(seg_df),
                'total_trzby': int(seg_df['trzby'].sum()),
                'total_fte_actual': round(seg_df['fte_actual'].sum(), 1),
                'total_fte_recommended': round(seg_df['fte_recommended'].sum(), 1),
                'understaffed_count': len(understaffed),
                'overstaffed_count': len(overstaffed),
                'urgent_count': len(urgent),  # Matches app's urgent criteria
                'revenue_at_risk_eur': int(urgent['revenue_at_risk_eur'].sum()),
                'avg_productivity_index': int(weighted_prod),  # FTE-weighted average
                'avg_bloky_trend_pct': round(weighted_trend * 100, 1),  # FTE-weighted, as %
                'avg_bloky': int(seg_df['bloky'].mean()),
                'avg_trzby': int(seg_df['trzby'].mean())
            })

        # Sort by revenue at risk (highest first)
        summaries.sort(key=lambda x: x['revenue_at_risk_eur'], reverse=True)
        total_risk = sum(s['revenue_at_risk_eur'] for s in summaries)

        return {
            'segment_count': len(summaries),
            'total_revenue_at_risk_eur': total_risk,
            'segments': summaries
        }

    def tool_get_city_summary(self, mesto: str) -> dict:
        """Get aggregate statistics for a city with multiple pharmacies."""
        df = self.sanitized_data
        city_df = df[df['mesto'].str.contains(mesto, case=False, na=False)]

        if city_df.empty:
            return {'error': f'No pharmacies found in city: {mesto}'}

        understaffed = city_df[city_df['fte_gap'] > 0.5]  # Positive gap = understaffed
        overstaffed = city_df[city_df['fte_gap'] < -0.5]  # Negative gap = overstaffed
        # Urgent: understaffed + revenue at risk (same criteria as app)
        urgent = city_df[(city_df['fte_gap'] > 0.5) & (city_df['revenue_at_risk_eur'] > 0)]

        # Get list of pharmacies in the city
        pharmacies = []
        for _, row in city_df.iterrows():
            pharmacies.append({
                'id': int(row['id']),
                'mesto': row['mesto'],
                'typ': row['typ'],
                'fte_actual': round(row['fte_actual'], 1),
                'fte_recommended': round(row['fte_recommended'], 1),
                'fte_gap': round(row['fte_gap'], 1),
                'revenue_at_risk_eur': int(row['revenue_at_risk_eur']),
                'productivity_index': int(row['productivity_index'])
            })

        # FTE-weighted productivity
        total_fte = city_df['fte_actual'].sum()
        weighted_prod = (city_df['productivity_index'] * city_df['fte_actual']).sum() / total_fte if total_fte > 0 else 100

        return {
            'city': mesto,
            'pharmacy_count': len(city_df),
            'total_fte_actual': round(city_df['fte_actual'].sum(), 1),
            'total_fte_recommended': round(city_df['fte_recommended'].sum(), 1),
            'total_fte_gap': round(city_df['fte_gap'].sum(), 1),
            'understaffed_count': len(understaffed),
            'overstaffed_count': len(overstaffed),
            'urgent_count': len(urgent),  # Matches app's urgent criteria
            'total_revenue_at_risk_eur': int(urgent['revenue_at_risk_eur'].sum()),
            'avg_productivity_index': int(weighted_prod),  # FTE-weighted
            'pharmacies': pharmacies,
            'transfer_possible': len(understaffed) > 0 and len(overstaffed) > 0
        }

    def tool_get_network_overview(self) -> dict:
        """Get quick health snapshot of the entire pharmacy network."""
        df = self.sanitized_data

        understaffed = df[df['fte_gap'] > 0.5]  # Positive gap = understaffed
        overstaffed = df[df['fte_gap'] < -0.5]  # Negative gap = overstaffed
        optimal = df[(df['fte_gap'] >= -0.5) & (df['fte_gap'] <= 0.5)]

        # Urgent: understaffed > 0.5 FTE + revenue at risk (same criteria as app)
        # This matches server.py lines 745-754
        urgent = df[(df['fte_gap'] > 0.5) & (df['revenue_at_risk_eur'] > 0)]

        # FTE-weighted productivity
        total_fte = df['fte_actual'].sum()
        weighted_prod = (df['productivity_index'] * df['fte_actual']).sum() / total_fte if total_fte > 0 else 100

        return {
            'total_pharmacies': len(df),
            'total_fte_actual': round(df['fte_actual'].sum(), 1),
            'total_fte_recommended': round(df['fte_recommended'].sum(), 1),
            'total_fte_gap': round(df['fte_gap'].sum(), 1),
            'understaffed_count': len(understaffed),
            'overstaffed_count': len(overstaffed),
            'optimal_count': len(optimal),
            'understaffed_pct': round(len(understaffed) / len(df) * 100, 1),
            'overstaffed_pct': round(len(overstaffed) / len(df) * 100, 1),
            'optimal_pct': round(len(optimal) / len(df) * 100, 1),
            'total_revenue_at_risk_eur': int(urgent['revenue_at_risk_eur'].sum()),
            'urgent_count': len(urgent),
            'avg_productivity_index': int(weighted_prod),  # FTE-weighted
            'total_bloky': int(df['bloky'].sum()),
            'total_trzby': int(df['trzby'].sum()),
            'region_count': df['region_code'].nunique(),
            'segment_breakdown': df['typ'].value_counts().to_dict()
        }

    def tool_get_trend_analysis(self, trend_threshold: float = 10.0, limit: int = 20) -> dict:
        """Identify pharmacies with significant transaction trends (growing/declining)."""
        # Ensure types
        trend_threshold = float(trend_threshold) if trend_threshold else 10.0
        limit = int(limit) if limit else 20

        df = self.sanitized_data.copy()

        # Convert bloky_trend to percentage if needed (stored as decimal)
        df['trend_pct'] = df['bloky_trend'] * 100

        # Growing pharmacies (positive trend above threshold)
        growing = df[df['trend_pct'] >= trend_threshold].copy()
        growing = growing.sort_values('trend_pct', ascending=False)

        # Declining pharmacies (negative trend below -threshold)
        declining = df[df['trend_pct'] <= -trend_threshold].copy()
        declining = declining.sort_values('trend_pct')

        def format_pharmacy(row):
            return {
                'id': int(row['id']),
                'mesto': row['mesto'],
                'typ': row['typ'],
                'bloky_trend_pct': round(row['trend_pct'], 1),
                'bloky': int(row['bloky']),
                'fte_actual': round(row['fte_actual'], 1),
                'fte_gap': round(row['fte_gap'], 1),
                'productivity_index': int(row['productivity_index'])
            }

        return {
            'threshold_pct': trend_threshold,
            'growing_count': len(growing),
            'declining_count': len(declining),
            'growing_pharmacies': [format_pharmacy(row) for _, row in growing.head(limit).iterrows()],
            'declining_pharmacies': [format_pharmacy(row) for _, row in declining.head(limit).iterrows()],
            'recommendation': (
                'Rastúce lekárne môžu potrebovať navýšenie FTE. '
                'Klesajúce lekárne zvážiť pre optimalizáciu personálu.'
            )
        }

    def tool_get_priority_actions(self, limit: int = 10) -> dict:
        """Get prioritized action list combining risk, productivity, and FTE gap."""
        limit = int(limit) if limit else 10
        df = self.sanitized_data.copy()

        # Only consider understaffed pharmacies with revenue at risk
        # Positive gap = understaffed (need more FTE)
        candidates = df[(df['fte_gap'] > 0.5) & (df['revenue_at_risk_eur'] > 0)].copy()

        if candidates.empty:
            return {
                'count': 0,
                'actions': [],
                'message': 'Žiadne lekárne s ohrozenými tržbami'
            }

        # Priority score: higher = more urgent
        # Factors: revenue at risk (normalized), productivity (above avg = higher), FTE gap magnitude
        max_risk = candidates['revenue_at_risk_eur'].max()
        candidates['risk_score'] = candidates['revenue_at_risk_eur'] / max_risk * 40  # 0-40 points

        # Productivity bonus: above average gets points
        candidates['prod_score'] = ((candidates['productivity_index'] - 100) / 20).clip(0, 30)  # 0-30 points

        # FTE gap magnitude: bigger gap = more urgent (positive gap = understaffed)
        max_gap = candidates['fte_gap'].max()
        candidates['gap_score'] = (candidates['fte_gap'] / max_gap) * 30 if max_gap > 0 else 0  # 0-30 points

        candidates['priority_score'] = (
            candidates['risk_score'] +
            candidates['prod_score'] +
            candidates['gap_score']
        )

        # Sort by priority score
        candidates = candidates.sort_values('priority_score', ascending=False)

        actions = []
        for _, row in candidates.head(limit).iterrows():
            action_type = 'URGENTNÉ' if row['priority_score'] >= 70 else (
                'VYSOKÁ' if row['priority_score'] >= 50 else 'STREDNÁ'
            )
            actions.append({
                'priority': action_type,
                'priority_score': round(row['priority_score'], 0),
                'id': int(row['id']),
                'mesto': row['mesto'],
                'typ': row['typ'],
                'fte_gap': round(row['fte_gap'], 1),
                'fte_needed': round(abs(row['fte_gap']), 1),
                'revenue_at_risk_eur': int(row['revenue_at_risk_eur']),
                'productivity_index': int(row['productivity_index']),
                'action': f"Pridať {abs(row['fte_gap']):.1f} FTE, ohrozené €{int(row['revenue_at_risk_eur']):,}"
            })

        return {
            'count': len(actions),
            'total_fte_needed': round(sum(a['fte_needed'] for a in actions), 1),
            'total_revenue_at_risk_eur': sum(a['revenue_at_risk_eur'] for a in actions),
            'actions': actions
        }

    # === TOOL DEFINITIONS FOR CLAUDE ===

    def get_tools(self) -> list:
        """Return tool definitions for Claude API."""
        return [
            {
                "name": "search_pharmacies",
                "description": "Vyhľadaj lekárne podľa kritérií (mesto, typ, región, bloky). Výsledky sú zoradené podľa blokov (najväčšie prvé). Pre 'top/najväčšie' lekárne použi sort_by='bloky'.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mesto": {
                            "type": "string",
                            "description": "Mesto/lokalita lekárne (case-insensitive, partial match). Napr. 'Košice', 'Bratislava', 'Levice'"
                        },
                        "typ": {
                            "type": "string",
                            "description": "Typ lekárne (A/B/C/D/E alebo celý názov)"
                        },
                        "region": {
                            "type": "string",
                            "description": "Kód regiónu (napr. RR11, RR15)"
                        },
                        "min_bloky": {
                            "type": "integer",
                            "description": "Minimálny počet blokov"
                        },
                        "max_bloky": {
                            "type": "integer",
                            "description": "Maximálny počet blokov"
                        },
                        "understaffed_only": {
                            "type": "boolean",
                            "description": "Len poddimenzované lekárne (fte_gap > 0.5)"
                        },
                        "overstaffed_only": {
                            "type": "boolean",
                            "description": "Len naddimenzované lekárne (fte_gap < -0.5) - vhodné pre presun personálu"
                        },
                        "sort_by": {
                            "type": "string",
                            "description": "Stĺpec pre zoradenie: 'bloky', 'trzby', 'fte_actual', 'productivity_index', 'revenue_at_risk_eur'. Default: 'bloky'"
                        },
                        "sort_desc": {
                            "type": "boolean",
                            "description": "Zoradiť zostupne (true=najväčšie prvé). Default: true"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max počet výsledkov (default 10)"
                        }
                    }
                }
            },
            {
                "name": "get_pharmacy_details",
                "description": "Získaj detaily konkrétnej lekárne vrátane indexovanej produktivity a odporúčaného FTE.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pharmacy_id": {
                            "type": "integer",
                            "description": "ID lekárne"
                        }
                    },
                    "required": ["pharmacy_id"]
                }
            },
            {
                "name": "get_pharmacy_revenue_trend",
                "description": "Získaj historický vývoj tržieb lekárne (2019-2021) vrátane mesačných dát a medziročného rastu (YoY).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pharmacy_id": {
                            "type": "integer",
                            "description": "ID lekárne"
                        }
                    },
                    "required": ["pharmacy_id"]
                }
            },
            {
                "name": "get_segment_position",
                "description": "Získaj pozíciu lekárne v rámci jej segmentu pre všetky KPI (bloky, tržby, Rx%, FTE, bloky/h, tržby/h, košík, produktivita). Vráti min/max/avg segmentu a percentil lekárne.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pharmacy_id": {
                            "type": "integer",
                            "description": "ID lekárne"
                        }
                    },
                    "required": ["pharmacy_id"]
                }
            },
            {
                "name": "simulate_fte",
                "description": "Simulácia 'čo ak?' - vypočítaj potrebné FTE pri zmene blokov alebo tržieb. Môžeš použiť: 1) s pharmacy_id a percentuálnou zmenou (bloky_change_pct, trzby_change_pct), 2) s pharmacy_id a absolútnymi hodnotami, 3) bez pharmacy_id s absolútnymi hodnotami a typom.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pharmacy_id": {
                            "type": "integer",
                            "description": "ID lekárne (voliteľné - ak nie je zadané, musíš zadať bloky, trzby a typ)"
                        },
                        "bloky": {
                            "type": "number",
                            "description": "Absolútny počet blokov (voliteľné)"
                        },
                        "trzby": {
                            "type": "number",
                            "description": "Absolútne tržby v EUR (voliteľné)"
                        },
                        "bloky_change_pct": {
                            "type": "number",
                            "description": "Percentuálna zmena blokov oproti súčasnosti (napr. 20 pre +20%, -10 pre -10%)"
                        },
                        "trzby_change_pct": {
                            "type": "number",
                            "description": "Percentuálna zmena tržieb oproti súčasnosti (napr. 15 pre +15%)"
                        },
                        "typ": {
                            "type": "string",
                            "description": "Typ lekárne (A-E), povinné ak nie je pharmacy_id"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "compare_to_peers",
                "description": "Porovnaj lekáreň s podobnými prevádzkami v segmente (podobný objem blokov A tržieb ±20%). Vráti štatistiky peers a porovnanie s priemerom.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pharmacy_id": {
                            "type": "integer",
                            "description": "ID lekárne na porovnanie"
                        },
                        "n_peers": {
                            "type": "integer",
                            "description": "Počet podobných lekární (default 5)"
                        },
                        "higher_fte_only": {
                            "type": "boolean",
                            "description": "Len lekárne s vyšším FTE - pre hľadanie zdrojov na presun personálu"
                        }
                    },
                    "required": ["pharmacy_id"]
                }
            },
            {
                "name": "get_understaffed",
                "description": "Získaj zoznam poddimenzovaných lekární s ohrozenými tržbami. Podporuje filtre pre mesto, región, vysoké riziko a produktivitu.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mesto": {
                            "type": "string",
                            "description": "Filter podľa mesta/lokality (case-insensitive, partial match). Napr. 'Košice', 'Bratislava'"
                        },
                        "region": {
                            "type": "string",
                            "description": "Filter podľa regiónu (napr. RR11)"
                        },
                        "min_gap": {
                            "type": "number",
                            "description": "Minimálny FTE deficit (default -0.5)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max počet výsledkov (default 20)"
                        },
                        "high_risk_only": {
                            "type": "boolean",
                            "description": "Len lekárne s ohrozenými tržbami > 0 EUR"
                        },
                        "high_productivity_only": {
                            "type": "boolean",
                            "description": "Len lekárne s nadpriemernou produktivitou (index > 100)"
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["fte_gap", "revenue_at_risk", "productivity"],
                            "description": "Zoradiť podľa: fte_gap (default), revenue_at_risk, productivity"
                        }
                    }
                }
            },
            {
                "name": "get_regional_summary",
                "description": "Získaj súhrnné štatistiky za jeden región.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "description": "Kód regiónu (napr. RR11, RR15)"
                        }
                    },
                    "required": ["region"]
                }
            },
            {
                "name": "get_all_regions_summary",
                "description": "Získaj súhrnné štatistiky za VŠETKY regióny naraz. Použiť pri porovnávaní regiónov.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sort_by": {
                            "type": "string",
                            "enum": ["revenue_at_risk", "productivity", "understaffed"],
                            "description": "Zoradiť podľa: revenue_at_risk (default), productivity, understaffed"
                        }
                    }
                }
            },
            {
                "name": "generate_report",
                "description": "Vygeneruj Markdown report s analýzou a odporúčaniami.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Názov reportu"
                        },
                        "pharmacy_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Zoznam ID lekární na zahrnutie"
                        },
                        "region": {
                            "type": "string",
                            "description": "Región pre súhrnné štatistiky"
                        },
                        "include_recommendations": {
                            "type": "boolean",
                            "description": "Zahrnúť odporúčania (default true)"
                        }
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "get_segment_comparison",
                "description": "Porovnaj výkonnosť všetkých segmentov (A-E). Vráti ohrozené tržby, FTE a produktivitu za segment.",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_city_summary",
                "description": "Získaj súhrnné štatistiky za mesto s viacerými lekárňami. Zobrazí aj možnosť presunu personálu.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mesto": {
                            "type": "string",
                            "description": "Názov mesta (napr. 'Košice', 'Bratislava')"
                        }
                    },
                    "required": ["mesto"]
                }
            },
            {
                "name": "get_network_overview",
                "description": "Rýchly prehľad zdravia celej siete lekární. Celkové FTE, ohrozené tržby, % poddimenzovaných.",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_trend_analysis",
                "description": "Identifikuj lekárne s významným trendom rastu/poklesu transakcií.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "trend_threshold": {
                            "type": "number",
                            "description": "Prahová hodnota trendu v % (default 10)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max počet lekární v každej kategórii (default 20)"
                        }
                    }
                }
            },
            {
                "name": "get_priority_actions",
                "description": "Získaj prioritizovaný zoznam akcií - kombinuje riziko, produktivitu a FTE gap. Odpoveď na 'Čo riešiť najskôr?'",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max počet akcií (default 10)"
                        }
                    }
                }
            }
        ]

    def execute_tool(self, tool_name: str, tool_input: dict, request_id: str = '') -> str:
        """Execute a tool and return result as string."""
        import time
        start_time = time.time()

        tool_map = {
            'search_pharmacies': self.tool_search_pharmacies,
            'get_pharmacy_details': self.tool_get_pharmacy_details,
            'get_pharmacy_revenue_trend': self.tool_get_pharmacy_revenue_trend,
            'get_segment_position': self.tool_get_segment_position,
            'simulate_fte': self.tool_simulate_fte,
            'compare_to_peers': self.tool_compare_to_peers,
            'get_understaffed': self.tool_get_understaffed,
            'get_regional_summary': self.tool_get_regional_summary,
            'get_all_regions_summary': self.tool_get_all_regions_summary,
            'generate_report': self.tool_generate_report,
            'get_segment_comparison': self.tool_get_segment_comparison,
            'get_city_summary': self.tool_get_city_summary,
            'get_network_overview': self.tool_get_network_overview,
            'get_trend_analysis': self.tool_get_trend_analysis,
            'get_priority_actions': self.tool_get_priority_actions
        }

        if tool_name not in tool_map:
            logger.warning(f"Unknown tool: {tool_name}", extra={"request_id": request_id})
            return json.dumps({'error': f'Unknown tool: {tool_name}'})

        try:
            result = tool_map[tool_name](**tool_input)
            duration = time.time() - start_time

            # P2: Audit logging
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            logger.info(f"Tool OK: {tool_name} | {duration:.2f}s | {len(result_str)} chars", extra={"request_id": request_id})

            return result_str

        except TypeError as e:
            # P1: Invalid parameters - don't expose full error
            logger.error(f"Tool error: {tool_name} invalid params: {e}", extra={"request_id": request_id})
            return json.dumps({'error': 'Invalid tool parameters'})

        except KeyError as e:
            # Missing data
            logger.error(f"Tool error: {tool_name} missing key: {e}", extra={"request_id": request_id})
            return json.dumps({'error': 'Required data not found'})

        except Exception as e:
            # P1: Generic error - don't expose internal details
            logger.exception(f"Tool error: {tool_name} {type(e).__name__}: {e}", extra={"request_id": request_id})
            return json.dumps({'error': 'Tool execution failed'})

    async def analyze(
        self,
        prompt: str,
        max_rounds: int = 5
    ) -> AsyncIterator[dict]:
        """
        Run autonomous analysis on the given prompt.

        Yields progress updates:
        - {"type": "thinking", "content": "..."}
        - {"type": "tool_use", "tool": "...", "input": {...}}
        - {"type": "tool_result", "content": "..."}
        - {"type": "response", "content": "..."}
        - {"type": "done", "content": "...", "total_rounds": N}
        """
        if not ANTHROPIC_AVAILABLE or not self.client:
            yield {
                "type": "error",
                "content": "Anthropic SDK not available. Install with: pip install anthropic"
            }
            return

        messages = [{"role": "user", "content": prompt}]

        for round_num in range(max_rounds):
            # Call Claude (using architect model for async flow)
            response = self.client.messages.create(
                model=self.config.architect_model,
                max_tokens=self.config.architect_max_tokens,
                system=AGENT_SYSTEM_PROMPT,
                tools=self.get_tools(),
                messages=messages
            )

            # Process response
            assistant_content = []
            has_tool_use = False

            for block in response.content:
                if block.type == "text":
                    yield {"type": "thinking" if has_tool_use else "response", "content": block.text}
                    assistant_content.append({"type": "text", "text": block.text})

                elif block.type == "tool_use":
                    has_tool_use = True
                    yield {
                        "type": "tool_use",
                        "tool": block.name,
                        "input": block.input
                    }

                    # Execute tool
                    tool_result = self.execute_tool(block.name, block.input)

                    yield {
                        "type": "tool_result",
                        "tool": block.name,
                        "content": tool_result[:500] + "..." if len(tool_result) > 500 else tool_result
                    }

                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })

                    # Add tool result to messages
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result
                        }]
                    })
                    assistant_content = []

            # If no tool use, we're done
            if not has_tool_use:
                yield {
                    "type": "done",
                    "content": "Analysis complete",
                    "total_rounds": round_num + 1
                }
                return

        yield {
            "type": "done",
            "content": f"Reached max rounds ({max_rounds})",
            "total_rounds": max_rounds
        }

    def analyze_sync(self, prompt: str, request_id: str = '') -> dict:
        """
        Hybrid Opus + Haiku architecture for Flask.

        1. Opus 4.5 (Architect) - Plans the approach
        2. Haiku (Worker) - Executes tools
        3. Opus 4.5 (Synthesizer) - Creates final response

        Returns final response and metadata.
        """
        import time
        start_time = time.time()

        if not ANTHROPIC_AVAILABLE or not self.client:
            return {
                "error": "Anthropic SDK not available",
                "response": None
            }

        tools_used = []
        tool_results = []
        tool_call_count = 0

        # === STEP 1: OPUS PLANS ===
        logger.info("STEP 1: Opus planning...", extra={"request_id": request_id})
        try:
            plan_response = self.client.messages.create(
                model=self.config.architect_model,
                max_tokens=self.config.architect_max_tokens,
                system=ARCHITECT_PLAN_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception as api_error:
            error_type = type(api_error).__name__
            error_msg = str(api_error)
            logger.error(f"API error in planning: {error_type}: {error_msg}", extra={"request_id": request_id})
            # Check if API key is set
            import os as agent_os
            api_key = agent_os.environ.get('ANTHROPIC_API_KEY', '')
            logger.debug(f"API key set: {bool(api_key)}, length: {len(api_key)}", extra={"request_id": request_id})
            return {
                "error": f"Anthropic API error: {error_type}",
                "error_detail": error_msg[:200],
                "response": None
            }

        plan_text = ""
        for block in plan_response.content:
            if block.type == "text":
                plan_text = block.text
                break

        # Parse plan (extract steps)
        import re
        steps = []
        plan_analysis = None
        synthesis_focus = None
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', plan_text)
            if json_match:
                plan_json = json.loads(json_match.group())
                steps = plan_json.get('steps', [])
                plan_analysis = plan_json.get('analysis', None)
                synthesis_focus = plan_json.get('synthesis_focus', None)
                logger.info(f'Plan: {plan_analysis[:100] if plan_analysis else "No analysis"}', extra={"request_id": request_id})
                logger.info(f"Steps: {len(steps)}", extra={"request_id": request_id})
        except json.JSONDecodeError:
            logger.warning("Could not parse plan, using fallback", extra={"request_id": request_id})
            pass

        # === STEP 2: HAIKU EXECUTES TOOLS ===
        logger.info("STEP 2: Executing tools...", extra={"request_id": request_id})

        if steps:
            # Execute planned steps (respect config limit)
            max_steps = min(len(steps), self.config.max_plan_steps)
            for i, step in enumerate(steps[:max_steps]):
                # P2: Check tool call limit
                if tool_call_count >= self.config.max_tool_calls:
                    logger.warning(f"LIMIT: Max tool calls ({self.config.max_tool_calls}) reached", extra={"request_id": request_id})
                    break

                tool_name = step.get('tool', '')
                tool_params = step.get('params', {})

                if tool_name in ['search_pharmacies', 'get_pharmacy_details',
                                  'get_pharmacy_revenue_trend', 'get_segment_position',
                                  'simulate_fte', 'compare_to_peers', 'get_understaffed',
                                  'get_regional_summary', 'get_all_regions_summary',
                                  'generate_report', 'get_segment_comparison',
                                  'get_city_summary', 'get_network_overview',
                                  'get_trend_analysis', 'get_priority_actions']:
                    logger.debug(f"Step {i+1}: {tool_name}", extra={"request_id": request_id})
                    result = self.execute_tool(tool_name, tool_params, request_id)
                    tools_used.append(tool_name)
                    tool_results.append({
                        'tool': tool_name,
                        'purpose': step.get('purpose', ''),
                        'result': result
                    })
                    tool_call_count += 1
        else:
            # Fallback: Let Haiku decide which tools to use
            logger.info("Fallback: Haiku autonomous mode", extra={"request_id": request_id})
            haiku_messages = [{"role": "user", "content": f"Analyze: {prompt}"}]

            for round_num in range(3):
                # P2: Check tool call limit before round
                if tool_call_count >= self.config.max_tool_calls:
                    logger.warning(f"LIMIT: Max tool calls ({self.config.max_tool_calls}) reached", extra={"request_id": request_id})
                    break

                haiku_response = self.client.messages.create(
                    model=self.config.worker_model,
                    max_tokens=self.config.worker_max_tokens,
                    system=WORKER_PROMPT,
                    tools=self.get_tools(),
                    messages=haiku_messages
                )

                has_tool_use = False
                haiku_content = []

                for block in haiku_response.content:
                    if block.type == "tool_use":
                        # P2: Check limit per tool call
                        if tool_call_count >= self.config.max_tool_calls:
                            logger.warning(f"LIMIT: Skipping {block.name}, limit reached", extra={"request_id": request_id})
                            break

                        has_tool_use = True
                        logger.debug(f"Haiku tool: {block.name}", extra={"request_id": request_id})
                        result = self.execute_tool(block.name, block.input, request_id)
                        tools_used.append(block.name)
                        tool_results.append({
                            'tool': block.name,
                            'purpose': '',
                            'result': result
                        })
                        tool_call_count += 1

                        haiku_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })

                        haiku_messages.append({"role": "assistant", "content": haiku_content})
                        haiku_messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result
                            }]
                        })
                        haiku_content = []

                if not has_tool_use:
                    break

        # === STEP 3: OPUS SYNTHESIZES ===
        logger.info("STEP 3: Opus synthesizing...", extra={"request_id": request_id})
        logger.info(f"Tool results: {len(tool_results)}, Tool calls: {tool_call_count}", extra={"request_id": request_id})
        for tr in tool_results:
            result_preview = tr['result'][:100] if len(tr['result']) > 100 else tr['result']
            logger.debug(f'{tr["tool"]}: {len(tr["result"])} chars', extra={"request_id": request_id})

        # Build synthesis prompt with all results
        synthesis_input = f"""PÔVODNÁ OTÁZKA:
{prompt}

VÝSLEDKY Z NÁSTROJOV:
"""
        for tr in tool_results:
            synthesis_input += f"\n--- {tr['tool']} ---\n"
            if tr['purpose']:
                synthesis_input += f"Účel: {tr['purpose']}\n"
            # Smart truncation for JSON results
            result_str = tr['result']
            if len(result_str) > 4000:
                # Try to truncate JSON smartly (at array item boundary)
                try:
                    result_json = json.loads(result_str)
                    # Limit arrays to keep size manageable
                    if 'peers' in result_json:
                        result_json['peers'] = result_json['peers'][:3]
                        result_json['_note'] = 'Zobrazené 3 z viacerých peers'
                    if 'pharmacies' in result_json:
                        result_json['pharmacies'] = result_json['pharmacies'][:10]
                        if result_json.get('count', 0) > 10:
                            result_json['_note'] = f"Zobrazených 10 z {result_json.get('count', 'viacerých')}"
                    result_str = json.dumps(result_json, ensure_ascii=False)
                except (json.JSONDecodeError, KeyError):
                    # Fallback: just truncate but ensure valid ending
                    result_str = result_str[:4000] + '... (skrátené)'
            synthesis_input += f"{result_str}\n"

        synthesis_input += "\nVytvor prehľadnú odpoveď pre používateľa."

        synthesis_response = self.client.messages.create(
            model=self.config.architect_model,
            max_tokens=self.config.architect_max_tokens,
            system=ARCHITECT_SYNTHESIZE_PROMPT,
            messages=[{"role": "user", "content": synthesis_input}]
        )

        final_response = ""
        for block in synthesis_response.content:
            if block.type == "text":
                final_response = block.text
                break

        duration = time.time() - start_time
        logger.info(f"COMPLETE: {duration:.2f}s, {tool_call_count} tool calls, tools: {tools_used}", extra={"request_id": request_id})

        return {
            "response": final_response,
            "tools_used": tools_used,
            "tool_call_count": tool_call_count,
            "duration_seconds": round(duration, 2),
            "request_id": request_id,
            "architecture": "opus-haiku-opus",
            # Reasoning data for logging
            "_reasoning": {
                "plan_raw": plan_text,
                "plan_analysis": plan_analysis,
                "synthesis_focus": synthesis_focus,
                "planned_steps": steps,
                "tool_results": tool_results
            }
        }
