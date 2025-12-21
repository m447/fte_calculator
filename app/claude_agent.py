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
from dataclasses import dataclass

# Check if SDK is available
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed. Agent features disabled.")

from .data_sanitizer import (
    generate_sanitized_data,
    get_understaffed_pharmacies,
    compare_to_peers
)


@dataclass
class AgentConfig:
    """Configuration for the hybrid agent architecture."""
    architect_model: str = "claude-opus-4-5"    # Planning & synthesis (Opus 4.5)
    worker_model: str = "claude-haiku-4-5"      # Tool execution (Haiku 4.5)
    architect_max_tokens: int = 4096
    worker_max_tokens: int = 2048
    temperature: float = 0


# System prompt for the agent - emphasizes using indexed values
AGENT_SYSTEM_PROMPT = """Si expertný FTE analytik pre sieť lekární Dr.Max na Slovensku.

TVOJA ÚLOHA:
Analyzuješ personálne obsadenie lekární a generuješ odporúčania na základe dát.

DOSTUPNÉ NÁSTROJE:
1. search_pharmacies - Vyhľadaj lekárne podľa kritérií
2. get_pharmacy_details - Získaj detaily konkrétnej lekárne
3. compare_to_peers - Porovnaj lekáreň s podobnými prevádzkami
4. get_understaffed - Zoznam poddimenzovaných lekární
5. get_regional_summary - Súhrn za región
6. generate_report - Vytvor report vo formáte Markdown

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

PRÍKLAD VÝSTUPU:
"Lekáreň ID 33 (Levice) má nadpriemernú produktivitu (index 115, 28. z 93 v segmente B).
Napriek tomu je poddimenzovaná o 1.2 FTE. Ohrozené tržby: €232K ročne."

PRÍKLAD ODMIETNUTIA:
Otázka: "Ako sa počíta produktivita?"
Odpoveď: "Produktivita je vyjadrená relatívnym indexom, kde 100 = priemer segmentu.
Konkrétna metodológia je interná."
"""

# Architect prompt - for planning and synthesis (Opus 4.5)
ARCHITECT_PLAN_PROMPT = """Si expertný analytik pre sieť lekární Dr.Max.

TVOJA ÚLOHA: Analyzuj požiadavku používateľa a vytvor PLÁN krokov.

DOSTUPNÉ NÁSTROJE:
1. search_pharmacies - Vyhľadaj lekárne (typ, región, bloky)
2. get_pharmacy_details - Detaily lekárne podľa ID
3. compare_to_peers - Porovnaj s podobnými lekárňami
4. get_understaffed - Zoznam poddimenzovaných lekární
5. get_regional_summary - Súhrn za región
6. generate_report - Vytvor Markdown report

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
- Pri porovnaniach použi compare_to_peers alebo search_pharmacies
- Pri regionálnej analýze použi get_regional_summary + get_understaffed
"""

ARCHITECT_SYNTHESIZE_PROMPT = """Si expertný analytik pre sieť lekární Dr.Max.

TVOJA ÚLOHA: Syntetizuj výsledky z nástrojov do prehľadnej odpovede.

CHRÁNENÉ INFORMÁCIE - NIKDY NEZVEREJŇUJ:
- Presné hodnoty produktivity (použi len indexy, napr. "index 115")
- Vzorce výpočtu produktivity alebo ohrozených tržieb
- Koeficienty modelu

PRAVIDLÁ FORMÁTOVANIA:
- ID lekární: "ID 33"
- Bloky: "131k blokov"
- Tržby: "2.5M €"
- FTE: "6.5 FTE"
- Ohrozené tržby: "€232K ročne"
- Produktivita: "nadpriemerná (index 115)" alebo "podpriemerná (index 85)"

Pri tabuľkách použi ASCII formát:
Lekáreň                 Bloky    FTE    Rozdiel
ID 33  Levice           131k     6.5    +1.2
ID 74  Martin           126k     6.9    +0.4

Ukonči stručným odporúčaním.
"""

WORKER_PROMPT = """Vykonaj nástroj a vráť výsledok. Neinterpretuj, len vráť dáta."""


class DrMaxAgent:
    """
    Autonomous agent for pharmacy staffing analysis.

    Uses custom tools with sanitized data to protect proprietary formulas.
    """

    def __init__(self, data_path: Path, predictions_cache: dict = None):
        """
        Initialize the agent.

        Args:
            data_path: Path to data directory
            predictions_cache: Optional dict of pharmacy predictions
                               {id: {'predicted_fte': X, 'diff': Y, 'revenue_at_risk': Z}}
        """
        self.data_path = data_path
        self.predictions_cache = predictions_cache or {}
        self.config = AgentConfig()

        if ANTHROPIC_AVAILABLE:
            self.client = Anthropic()
        else:
            self.client = None

        # Pre-generate sanitized data
        self._sanitized_df = None

    @property
    def sanitized_data(self):
        """Lazy-load sanitized data."""
        if self._sanitized_df is None:
            self._sanitized_df = generate_sanitized_data(self.data_path)
        return self._sanitized_df

    def _get_predictions_df(self):
        """Convert predictions cache to DataFrame."""
        import pandas as pd

        if not self.predictions_cache:
            # If no cache, return empty predictions
            return pd.DataFrame(columns=['id', 'predicted_fte', 'diff', 'revenue_at_risk'])

        records = [
            {
                'id': int(k),
                'predicted_fte': v.get('predicted_fte', 0),
                'diff': v.get('diff', 0),
                'revenue_at_risk': v.get('revenue_at_risk', 0)
            }
            for k, v in self.predictions_cache.items()
        ]
        return pd.DataFrame(records)

    # === TOOL IMPLEMENTATIONS ===

    def tool_search_pharmacies(
        self,
        typ: str = None,
        region: str = None,
        min_bloky: int = None,
        max_bloky: int = None,
        understaffed_only: bool = False,
        limit: int = 10
    ) -> dict:
        """Search pharmacies with filters."""
        df = self.sanitized_data.copy()

        if typ:
            df = df[df['typ'].str.contains(typ, case=False)]
        if region:
            df = df[df['region_code'] == region]
        if min_bloky:
            df = df[df['bloky'] >= min_bloky]
        if max_bloky:
            df = df[df['bloky'] <= max_bloky]

        # Merge with predictions
        pred_df = self._get_predictions_df()
        if not pred_df.empty:
            df = df.merge(pred_df, on='id', how='left')

            if understaffed_only:
                df = df[df['diff'] < -0.5]

        df = df.head(limit)

        return {
            'count': len(df),
            'pharmacies': df.to_dict('records')
        }

    def tool_get_pharmacy_details(self, pharmacy_id: int) -> dict:
        """Get details for a specific pharmacy."""
        df = self.sanitized_data
        pharmacy = df[df['id'] == pharmacy_id]

        if pharmacy.empty:
            return {'error': f'Pharmacy {pharmacy_id} not found'}

        result = pharmacy.iloc[0].to_dict()

        # Add predictions if available
        if pharmacy_id in self.predictions_cache:
            pred = self.predictions_cache[pharmacy_id]
            result['predicted_fte'] = round(pred.get('predicted_fte', 0), 1)
            result['fte_diff'] = round(pred.get('diff', 0), 1)
            result['revenue_at_risk'] = round(pred.get('revenue_at_risk', 0))
            result['staffing_status'] = (
                'poddimenzovaná' if result['fte_diff'] < -0.5
                else 'naddimenzovaná' if result['fte_diff'] > 0.5
                else 'optimálna'
            )

        return result

    def tool_compare_to_peers(
        self,
        pharmacy_id: int,
        n_peers: int = 5,
        higher_fte_only: bool = False
    ) -> dict:
        """Compare pharmacy to similar peers."""
        pred_df = self._get_predictions_df()
        result = compare_to_peers(pharmacy_id, self.data_path, pred_df, n_peers)

        if result is None:
            return {'error': f'Pharmacy {pharmacy_id} not found'}

        if higher_fte_only:
            target_fte = result['target'].get('fte_actual', 0)
            result['peers'] = [
                p for p in result['peers']
                if p.get('fte_actual', 0) > target_fte
            ]

        return result

    def tool_get_understaffed(
        self,
        region: str = None,
        min_gap: float = -0.5,
        limit: int = 20
    ) -> dict:
        """Get list of understaffed pharmacies."""
        pred_df = self._get_predictions_df()
        understaffed = get_understaffed_pharmacies(
            self.data_path, pred_df, region, min_gap
        )

        return {
            'count': len(understaffed),
            'total_revenue_at_risk': sum(p.get('revenue_at_risk', 0) for p in understaffed),
            'pharmacies': understaffed[:limit]
        }

    def tool_get_regional_summary(self, region: str) -> dict:
        """Get summary statistics for a region."""
        df = self.sanitized_data
        region_df = df[df['region_code'] == region]

        if region_df.empty:
            return {'error': f'Region {region} not found'}

        pred_df = self._get_predictions_df()
        if not pred_df.empty:
            region_df = region_df.merge(pred_df, on='id', how='left')
            understaffed = region_df[region_df['diff'] < -0.5]
            overstaffed = region_df[region_df['diff'] > 0.5]
        else:
            understaffed = region_df.head(0)
            overstaffed = region_df.head(0)

        return {
            'region': region,
            'pharmacy_count': len(region_df),
            'total_fte': round(region_df['fte_actual'].sum(), 1),
            'total_bloky': int(region_df['bloky'].sum()),
            'understaffed_count': len(understaffed),
            'overstaffed_count': len(overstaffed),
            'total_revenue_at_risk': round(understaffed['revenue_at_risk'].sum()) if not understaffed.empty else 0,
            'avg_productivity_index': int(region_df['productivity_index'].mean()),
            'types': region_df['typ'].value_counts().to_dict()
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
                f"- Ohrozené tržby: €{summary['total_revenue_at_risk']:,}",
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
                        f"{p.get('fte_diff', 0):+.1f} | "
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

    # === TOOL DEFINITIONS FOR CLAUDE ===

    def get_tools(self) -> list:
        """Return tool definitions for Claude API."""
        return [
            {
                "name": "search_pharmacies",
                "description": "Vyhľadaj lekárne podľa kritérií (typ, región, bloky). Vráti zoznam s indexovanou produktivitou.",
                "input_schema": {
                    "type": "object",
                    "properties": {
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
                            "description": "Len poddimenzované lekárne"
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
                "name": "compare_to_peers",
                "description": "Porovnaj lekáreň s podobnými prevádzkami v segmente (podobný objem blokov).",
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
                            "description": "Len lekárne s vyšším FTE"
                        }
                    },
                    "required": ["pharmacy_id"]
                }
            },
            {
                "name": "get_understaffed",
                "description": "Získaj zoznam poddimenzovaných lekární s ohrozenými tržbami.",
                "input_schema": {
                    "type": "object",
                    "properties": {
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
                        }
                    }
                }
            },
            {
                "name": "get_regional_summary",
                "description": "Získaj súhrnné štatistiky za región.",
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
            }
        ]

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return result as string."""
        tool_map = {
            'search_pharmacies': self.tool_search_pharmacies,
            'get_pharmacy_details': self.tool_get_pharmacy_details,
            'compare_to_peers': self.tool_compare_to_peers,
            'get_understaffed': self.tool_get_understaffed,
            'get_regional_summary': self.tool_get_regional_summary,
            'generate_report': self.tool_generate_report
        }

        if tool_name not in tool_map:
            return json.dumps({'error': f'Unknown tool: {tool_name}'})

        try:
            result = tool_map[tool_name](**tool_input)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({'error': str(e)})

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
            # Call Claude
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
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

    def analyze_sync(self, prompt: str) -> dict:
        """
        Hybrid Opus + Haiku architecture for Flask.

        1. Opus 4.5 (Architect) - Plans the approach
        2. Haiku (Worker) - Executes tools
        3. Opus 4.5 (Synthesizer) - Creates final response

        Returns final response and metadata.
        """
        if not ANTHROPIC_AVAILABLE or not self.client:
            return {
                "error": "Anthropic SDK not available",
                "response": None
            }

        tools_used = []
        tool_results = []

        # === STEP 1: OPUS PLANS ===
        print("[HYBRID] Step 1: Opus planning...")
        plan_response = self.client.messages.create(
            model=self.config.architect_model,
            max_tokens=self.config.architect_max_tokens,
            system=ARCHITECT_PLAN_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        plan_text = ""
        for block in plan_response.content:
            if block.type == "text":
                plan_text = block.text
                break

        # Parse plan (extract steps)
        import re
        steps = []
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', plan_text)
            if json_match:
                plan_json = json.loads(json_match.group())
                steps = plan_json.get('steps', [])
                print(f"[HYBRID] Plan: {plan_json.get('analysis', 'No analysis')}")
                print(f"[HYBRID] Steps: {len(steps)}")
        except json.JSONDecodeError:
            print(f"[HYBRID] Could not parse plan, using fallback")
            # Fallback: try to identify tool mentions
            pass

        # === STEP 2: HAIKU EXECUTES TOOLS ===
        print("[HYBRID] Step 2: Haiku executing tools...")

        if steps:
            # Execute planned steps
            for i, step in enumerate(steps[:5]):  # Max 5 steps
                tool_name = step.get('tool', '')
                tool_params = step.get('params', {})

                if tool_name in ['search_pharmacies', 'get_pharmacy_details',
                                  'compare_to_peers', 'get_understaffed',
                                  'get_regional_summary', 'generate_report']:
                    print(f"[HYBRID]   Step {i+1}: {tool_name}")
                    result = self.execute_tool(tool_name, tool_params)
                    tools_used.append(tool_name)
                    tool_results.append({
                        'tool': tool_name,
                        'purpose': step.get('purpose', ''),
                        'result': result
                    })
        else:
            # Fallback: Let Haiku decide which tools to use
            haiku_messages = [{"role": "user", "content": f"Analyze: {prompt}"}]

            for round_num in range(3):
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
                        has_tool_use = True
                        print(f"[HYBRID]   Haiku tool: {block.name}")
                        result = self.execute_tool(block.name, block.input)
                        tools_used.append(block.name)
                        tool_results.append({
                            'tool': block.name,
                            'purpose': '',
                            'result': result
                        })

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
        print("[HYBRID] Step 3: Opus synthesizing...")

        # Build synthesis prompt with all results
        synthesis_input = f"""PÔVODNÁ OTÁZKA:
{prompt}

VÝSLEDKY Z NÁSTROJOV:
"""
        for tr in tool_results:
            synthesis_input += f"\n--- {tr['tool']} ---\n"
            if tr['purpose']:
                synthesis_input += f"Účel: {tr['purpose']}\n"
            # Truncate very long results
            result_str = tr['result']
            if len(result_str) > 2000:
                result_str = result_str[:2000] + "... (skrátené)"
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

        print(f"[HYBRID] Complete. Tools used: {tools_used}")

        return {
            "response": final_response,
            "tools_used": tools_used,
            "rounds": len(tool_results),
            "architecture": "opus-haiku-opus"
        }
