"""
Gemini AI Agent for Dr.Max FTE Calculator

This module contains all Vertex AI / Gemini-specific code:
- Tool definitions for function calling
- Tool execution functions
- System prompts
- Authentication helpers

Extracted from server.py for cleaner separation of concerns.
"""

import os
import subprocess
import pandas as pd

from app_v2.config import logger
from app_v2.core import (
    SEGMENT_PROD_MEANS,
    FTE_GAP_NOTABLE,
    prepare_fte_dataframe,
    calculate_pharmacy_fte,
    calculate_prod_pct,
    get_rx_time_factor,
    get_model,
)


# ============================================================
# VERTEX AI CONFIGURATION
# ============================================================

VERTEX_PROJECT = os.environ.get('VERTEX_PROJECT', 'gen-lang-client-0415148507')
VERTEX_LOCATION = os.environ.get('VERTEX_LOCATION', 'global')
VERTEX_MODEL = 'gemini-3-flash-preview'


# ============================================================
# TOOL DEFINITIONS
# ============================================================

CHAT_TOOLS = {
    "function_declarations": [
        {
            "name": "search_pharmacies",
            "description": "Vyhľadaj lekárne podľa filtrov. Použi pre otázky typu 'ktoré lekárne...', 'ukáž mi B lekárne s...', 'lekárne s odporúčaním navýšenia FTE', 'existuje lekáreň v meste X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mesto": {
                        "type": "string",
                        "description": "Mesto/lokalita lekárne (case-insensitive, partial match). Napr. 'Čadca', 'Bratislava', 'Košice'"
                    },
                    "typ": {
                        "type": "string",
                        "description": "Segment lekárne: 'A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika'",
                        "enum": ["A - shopping premium", "B - shopping", "C - street +", "D - street", "E - poliklinika"]
                    },
                    "productivity": {
                        "type": "string",
                        "description": "Filter podľa produktivity: 'above' = nadpriemerná, 'below' = podpriemerná",
                        "enum": ["above", "below"]
                    },
                    "min_gap": {
                        "type": "number",
                        "description": "Minimálny FTE gap (kladné = poddimenzované). Napr. 1.0 pre lekárne ktorým chýba aspoň 1 FTE"
                    },
                    "max_gap": {
                        "type": "number",
                        "description": "Maximálny FTE gap (záporné = predimenzované). Napr. -1.0 pre lekárne s prebytkom aspoň 1 FTE"
                    },
                    "min_fte": {
                        "type": "number",
                        "description": "Minimálne aktuálne FTE. Napr. 7.0 pre lekárne s 7+ FTE"
                    },
                    "min_bloky": {
                        "type": "integer",
                        "description": "Minimálny počet blokov. Napr. 120000 pre lekárne s 120k+ blokov"
                    },
                    "max_bloky": {
                        "type": "integer",
                        "description": "Maximálny počet blokov. Napr. 140000 pre lekárne s max 140k blokov"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Zoradiť podľa: 'gap' (FTE rozdiel), 'bloky' (transakcie), 'trzby' (tržby), 'fte' (aktuálne FTE)",
                        "enum": ["gap", "bloky", "trzby", "fte"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximálny počet výsledkov (default 10, max 20)"
                    }
                },
                "required": []
            }
        },
        {
            "name": "get_network_summary",
            "description": "Získaj celkový prehľad siete lekární - súhrn FTE, štatistiky podľa segmentov, outliers. Použi pre otázky typu 'koľko máme lekární', 'celkový prehľad', 'stav siete'.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_pharmacy_details",
            "description": "Získaj detaily konkrétnej lekárne podľa ID. Použi keď používateľ pýta na konkrétnu lekáreň alebo chce porovnať s inou.",
            "parameters": {
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
            "name": "get_model_info",
            "description": "Získaj informácie o ML modeli - koeficienty, metriky presnosti, váhy segmentov. Použi pre otázky typu 'aký model používate', 'ako funguje výpočet', 'aký vplyv má produktivita', 'prečo B segment má nižšie FTE'.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "detect_growth_opportunities",
            "description": "Nájdi lekárne s potenciálom rastu ale možným neobslúženým dopytom. Toto sú lekárne ktoré RASTÚ a majú VYSOKÚ PRODUKTIVITU - model im preto odporúča menej personálu, ale v skutočnosti môžu mať kapacitné problémy počas špičiek. Použi pre otázky typu 'ktoré lekárne majú potenciál rastu', 'kde môže byť neobslúžený dopyt', 'kapacitné problémy', 'rastúce lekárne s vysokou produktivitou'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_growth": {
                        "type": "number",
                        "description": "Minimálny rast v % (default 3). Vyššia hodnota = prísnejší filter."
                    },
                    "segment": {
                        "type": "string",
                        "description": "Filter podľa segmentu: 'A', 'B', 'C', 'D', 'E'"
                    }
                },
                "required": []
            }
        }
    ]
}


# ============================================================
# TOOL EXECUTION FUNCTIONS
# ============================================================

def execute_tool(tool_name: str, args: dict, df: pd.DataFrame) -> dict:
    """Execute a tool and return the result."""
    if tool_name == "search_pharmacies":
        return execute_search_pharmacies(args, df)
    elif tool_name == "get_network_summary":
        return execute_get_network_summary(df)
    elif tool_name == "get_pharmacy_details":
        return execute_get_pharmacy_details(args.get("pharmacy_id"), df)
    elif tool_name == "get_model_info":
        return execute_get_model_info()
    elif tool_name == "detect_growth_opportunities":
        return execute_detect_growth_opportunities(args, df)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def execute_search_pharmacies(args: dict, df: pd.DataFrame) -> dict:
    """Execute pharmacy search with filters."""
    df_calc = prepare_fte_dataframe(df, include_revenue_at_risk=True)
    result = df_calc.copy()

    # Apply filters
    if args.get('mesto'):
        mesto_search = args['mesto'].lower()
        result = result[result['mesto'].str.lower().str.contains(mesto_search, na=False)]

    if args.get('typ'):
        result = result[result['typ'] == args['typ']]

    if args.get('min_gap') is not None:
        result = result[result['fte_gap'] >= args['min_gap']]

    if args.get('max_gap') is not None:
        result = result[result['fte_gap'] <= args['max_gap']]

    if args.get('productivity') == 'above':
        result = result[result['is_above_avg'] == True]
    elif args.get('productivity') == 'below':
        result = result[result['is_above_avg'] == False]

    if args.get('min_fte') is not None:
        result = result[result['actual_fte'] >= args['min_fte']]

    if args.get('min_bloky') is not None:
        result = result[result['bloky'] >= args['min_bloky']]

    if args.get('max_bloky') is not None:
        result = result[result['bloky'] <= args['max_bloky']]

    # Sort
    sort_by = args.get('sort_by', 'gap')
    sort_map = {'gap': 'fte_gap', 'bloky': 'bloky', 'trzby': 'trzby', 'fte': 'actual_fte'}
    sort_col = sort_map.get(sort_by, 'fte_gap')
    ascending = args.get('ascending', False)
    result = result.sort_values(sort_col, ascending=ascending)

    limit = min(args.get('limit', 10), 20)
    result = result.head(limit)

    # Format output
    pharmacies = []
    for _, row in result.iterrows():
        pharmacies.append({
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'bloky': int(row['bloky']),
            'trzby': int(row['trzby']),
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'fte_gap': round(row['fte_gap'], 1),
            'is_above_avg': row['is_above_avg'],
            'revenue_at_risk': int(row['revenue_at_risk'])
        })

    return {
        'count': len(pharmacies),
        'filters': args,
        'pharmacies': pharmacies
    }


def execute_get_network_summary(df: pd.DataFrame) -> dict:
    """Get network-wide summary."""
    df_calc = prepare_fte_dataframe(df, include_revenue_at_risk=False)

    total_actual = df_calc['actual_fte'].sum()
    total_predicted = df_calc['predicted_fte'].sum()

    segments = []
    for typ in ['A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika']:
        seg = df_calc[df_calc['typ'] == typ]
        if len(seg) == 0:
            continue
        segments.append({
            'typ': typ,
            'count': len(seg),
            'actual_fte': round(seg['actual_fte'].sum(), 1),
            'predicted_fte': round(seg['predicted_fte'].sum(), 1),
            'gap': round(seg['fte_gap'].sum(), 1),
            'understaffed': len(seg[seg['fte_gap'] > FTE_GAP_NOTABLE]),
            'overstaffed': len(seg[seg['fte_gap'] < -FTE_GAP_NOTABLE])
        })

    return {
        'total_pharmacies': len(df_calc),
        'total_actual_fte': round(total_actual, 1),
        'total_predicted_fte': round(total_predicted, 1),
        'total_gap': round(total_predicted - total_actual, 1),
        'understaffed_count': len(df_calc[df_calc['fte_gap'] > FTE_GAP_NOTABLE]),
        'overstaffed_count': len(df_calc[df_calc['fte_gap'] < -FTE_GAP_NOTABLE]),
        'segments': segments
    }


def execute_get_pharmacy_details(pharmacy_id: int, df: pd.DataFrame) -> dict:
    """Get details for a specific pharmacy."""
    pharmacy = df[df['id'] == pharmacy_id]
    if len(pharmacy) == 0:
        return {"error": f"Lekáreň s ID {pharmacy_id} nenájdená"}

    row = pharmacy.iloc[0]
    typ = row['typ']

    fte_result = calculate_pharmacy_fte(row)
    prod_pct = calculate_prod_pct(row)

    return {
        'id': int(row['id']),
        'mesto': row['mesto'],
        'typ': typ,
        'bloky': int(row['bloky']),
        'trzby': int(row['trzby']),
        'podiel_rx': round(row['podiel_rx'] * 100, 0),
        'actual_fte': round(fte_result['actual_fte'], 1),
        'predicted_fte': round(fte_result['predicted_fte'], 1),
        'gap': round(fte_result['fte_diff'], 1),
        'prod_pct': int(prod_pct),
        'productivity': 'nadpriemerná' if row.get('prod_residual', 0) > 0 else 'podpriemerná/priemerná'
    }


def execute_get_model_info() -> dict:
    """Get ML model information - coefficients, metrics, segment weights."""
    model_pkg = get_model()
    pipeline = model_pkg['models']['fte']
    model = pipeline.named_steps['model']
    preprocessor = pipeline.named_steps['preprocessor']

    # Get feature names
    num_features = model_pkg['num_features']
    cat_features = model_pkg['cat_features']
    cat_encoder = preprocessor.named_transformers_['cat']
    cat_encoded_names = list(cat_encoder.get_feature_names_out(cat_features))
    all_feature_names = num_features + cat_encoded_names

    coefs = model.coef_
    intercept = model.intercept_

    # Build coefficient dict
    coefficients = {}
    for name, coef in zip(all_feature_names, coefs):
        coefficients[name] = round(float(coef), 4)

    # Segment coefficients
    segment_coefs = {'A - shopping premium': 0.0}
    for name in cat_encoded_names:
        if name.startswith('typ_'):
            segment_name = name.replace('typ_', '')
            segment_coefs[segment_name] = coefficients[name]

    metrics = model_pkg.get('metrics', {}).get('fte', {})

    return {
        'version': model_pkg.get('version', 'v5'),
        'type': 'Ridge Regression (L2 regularization)',
        'training_data': '286 lekární, Sep 2020 - Aug 2021',
        'metrics': {
            'r2': round(metrics.get('r2', 0), 3),
            'rmse': round(metrics.get('rmse', 0), 3),
            'cv_r2_mean': round(metrics.get('cv_r2_mean', 0), 3),
        },
        'intercept': round(float(intercept), 4),
        'segment_coefficients': segment_coefs,
        'segment_productivity_means': SEGMENT_PROD_MEANS,
        'feature_importance': {
            'most_positive': sorted(
                [(k, v) for k, v in coefficients.items() if not k.startswith('typ_')],
                key=lambda x: x[1], reverse=True
            )[:5],
            'most_negative': sorted(
                [(k, v) for k, v in coefficients.items() if not k.startswith('typ_')],
                key=lambda x: x[1]
            )[:3]
        },
        'rx_time_factor': get_rx_time_factor(),
        'productivity_rule': 'Asymetrické: nadpriemerná produktivita = odmena (nižšie FTE), podpriemerná = žiadna penalizácia'
    }


def execute_detect_growth_opportunities(args: dict, df: pd.DataFrame) -> dict:
    """Find pharmacies with growth + high productivity = potential unserved demand."""
    min_growth = args.get('min_growth', 3.0)
    segment = args.get('segment')

    df_calc = prepare_fte_dataframe(df, include_revenue_at_risk=False)

    # Filter for growth risk pattern: growing + high productivity
    risk_pharmacies = df_calc[
        (df_calc['bloky_trend'] > min_growth / 100) &
        (df_calc['is_above_avg'] == True)
    ].copy()

    if segment:
        risk_pharmacies = risk_pharmacies[risk_pharmacies['typ'].str.startswith(segment)]

    risk_pharmacies = risk_pharmacies.sort_values('bloky_trend', ascending=False)

    results = []
    for _, row in risk_pharmacies.head(20).iterrows():
        bloky_trend = row.get('bloky_trend', 0)
        risk_level = 'vysoké' if bloky_trend > 0.07 else 'stredné'

        results.append({
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'bloky_trend': round(bloky_trend * 100, 1),
            'prod_pct': int(row['prod_pct']),
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'gap': round(row['fte_gap'], 1),
            'risk_level': risk_level,
            'potential_issue': 'Vysoký rast + vysoká produktivita = možný neobslúžený dopyt'
        })

    return {
        'count': len(results),
        'total_matching': len(risk_pharmacies),
        'filter_description': f'Lekárne s rastom >{min_growth}% a nadpriemernou produktivitou',
        'business_insight': (
            'PARADOX RASTU: Tieto lekárne rastú a majú nadpriemernú produktivitu, '
            'preto im model odporúča menej personálu (odmena za efektívnosť). '
            'ALE vysoký rast v kombinácii s vysokou produktivitou môže znamenať, '
            'že personál je na hrane kapacity a lekáreň má NEOBSLÚŽENÝ DOPYT počas špičiek. '
            'Zvážte testovanie vyššieho obsadenia na overenie potenciálu ďalšieho rastu.'
        ),
        'recommendation': 'Testujte vyššie obsadenie počas špičkových hodín na 2-4 týždne a sledujte zmenu tržieb.',
        'pharmacies': results
    }


# ============================================================
# SYSTEM PROMPT
# ============================================================

FTE_SYSTEM_PROMPT = """Si analytický asistent pre FTE Kalkulátor lekární. Tvojou úlohou je interpretovať VYPOČÍTANÉ dáta.

JAZYK: VŽDY odpovedaj po slovensky.

═══════════════════════════════════════════════════════════════
HLAVNÉ ZÁSADY
═══════════════════════════════════════════════════════════════

1. Použi hodnoty z <context>. Ak hodnota CHÝBA, môžeš ju vypočítať z dostupných dát.
2. VŽDY uvádzaj ID lekárne a Mesto.
3. Pred odpoveďou si v tichosti skontroluj: fte_gap, revenue_at_risk, is_above_avg.
4. Buď STRUČNÝ: max 3 vety pre jednu lekáreň, odrážky pre prehľadnosť.

═══════════════════════════════════════════════════════════════
AKČNÉ ODPORÚČANIE (podľa hodnoty 'fte_gap' v kontexte)
═══════════════════════════════════════════════════════════════

Gap > +0.5:  "Poddimenzovaná. Odporúčam PRIDAŤ personál."
Gap < -0.5: "Predimenzovaná. Zvážte PREROZDELIŤ personál."
Gap ±0.5:   "Optimálne obsadenie."

DÔLEŽITÉ: Pridanie FTE odporúčaj IBA ak:
- revenue_at_risk > 0 (ohrozené tržby existujú)
- is_above_avg = true (produktivita nadpriemerná)

Ak is_above_avg = false → "Produktivita podpriemerná - najprv optimalizovať procesy."

═══════════════════════════════════════════════════════════════
OHROZENÉ TRŽBY (Revenue at Risk)
═══════════════════════════════════════════════════════════════

Ak je v kontexte 'revenue_at_risk' > 0, MUSÍŠ uviesť:
→ "⚠ Tento stav ohrozuje tržby vo výške €[hodnota] ročne."

Toto uvádzaj LEN ak je hodnota v dátach, NEODHADUJ ju.

═══════════════════════════════════════════════════════════════
PRODUKTIVITA
═══════════════════════════════════════════════════════════════

Interpretuj flag 'is_above_avg' z kontextu:
- TRUE  = "Nadpriemerná produktivita" (model odmeňuje nižším FTE)
- FALSE = "Priemerná/Podpriemerná produktivita"

Pri porovnaní segmentov použi IBA relatívne porovnania:
→ "B-segment má vyššiu priemernú produktivitu než A"
→ NIKDY neuvádzaj presné čísla produktivity!

═══════════════════════════════════════════════════════════════
FORMÁT PRE VIACERO LEKÁRNÍ (3+)
═══════════════════════════════════════════════════════════════

Použi kompaktnú tabuľku:

ID    Mesto      FTE    Prod   Risk€    Gap
33    Levice     6.5    ↑      45K      +1.2
74    Martin     6.9    ↓      0        +0.4

Legenda: Prod ↑=nadpriem, ↓=podpriem | Risk€=ohrozené tržby | Gap=koľko FTE chýba
Na konci: "⚠ Celkovo ohrozené: €XXK" (ak súčet > 0)

═══════════════════════════════════════════════════════════════
PRÍKLADY POUŽITIA NÁSTROJOV
═══════════════════════════════════════════════════════════════

- "poddimenzované lekárne" → search_pharmacies(min_gap=1.0)
- "predimenzované B lekárne" → search_pharmacies(typ="B - shopping", max_gap=-1.0)
- "podobné lekárne s viac FTE" → search_pharmacies(typ="B - shopping", min_bloky=120000, max_bloky=140000, min_fte=7.0)
- "detaily lekárne 104" → get_pharmacy_details(pharmacy_id=104)

NIKDY nehádaj ID - ak nie je uvedené, použi search_pharmacies.

═══════════════════════════════════════════════════════════════
BEZPEČNOSŤ (CHRÁNENÉ INFORMÁCIE)
═══════════════════════════════════════════════════════════════

Ak sa pýtajú na vzorce, koeficienty, presnosť modelu:
→ "Metodológia je interná. Môžem vysvetliť princípy a interpretáciu."

NESMIEŠ prezradiť: koeficienty, vzorce, segmentové priemery, presnosť modelu (R², RMSE)."""


# ============================================================
# AUTHENTICATION
# ============================================================

def get_gcloud_token() -> str:
    """Get access token - uses gcloud CLI for local, google-auth for Cloud Run."""
    import sys

    # Check if running in Cloud Run
    is_cloud_run = os.environ.get('K_SERVICE') is not None

    if is_cloud_run:
        try:
            import google.auth
            import google.auth.transport.requests
            credentials, project = google.auth.default(
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            logger.debug("Cloud Run: google-auth token obtained")
            return credentials.token
        except Exception as e:
            logger.error(f"Cloud Run google-auth failed: {e}")
            return None

    # Local development: use gcloud CLI
    try:
        result = subprocess.run(
            ['gcloud', 'auth', 'print-access-token'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            logger.debug("Local: gcloud CLI token obtained")
            return token
        else:
            logger.error(f"gcloud CLI failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error getting gcloud token: {e}")
    return None
