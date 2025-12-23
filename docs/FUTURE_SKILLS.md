# Dr.Max FTE Calculator - Future Skills Roadmap

## Overview

This document outlines potential skills to enhance the AI agent capabilities. Skills are organized by priority and purpose.

---

## Priority 1: High Value / Quick Implementation

### 1. Action Plan Generator

**Purpose:** Transform analysis into actionable staffing decisions.

**Why it matters:**
- Management needs decisions, not just data
- Provides clear prioritization (what to fix first)
- Calculates ROI to justify hiring costs
- Creates phased implementation timeline

**Sample interaction:**
```
User: "Vytvor akčný plán pre riešenie poddimenzovaných lekární"
Agent: Returns 3-phase plan with costs, timelines, and ROI
```

**Output format:**
```
AKČNÝ PLÁN PERSONÁLNEHO OBSADENIA - Q1 2025

📊 SÚHRN
├─ Lekární na riešenie: 23
├─ Potrebné FTE: +15.4
├─ Investícia: €462K/rok
├─ Chránené tržby: €3.99M
└─ ROI: 8.6x

🔴 FÁZA 1: IHNEĎ (5 lekární)
   Náklady: €144K | Chráni: €1.4M | ROI: 9.7x

   | # | ID  | Mesto     | Gap  | Náklad | Chráni |
   |---|-----|-----------|------|--------|--------|
   | 1 | 102 | Trebišov  | +1.2 | €36K   | €366K  |
   | 2 | 637 | Lučenec   | +0.9 | €27K   | €238K  |
   ...
```

**Implementation:**
- Add `tool_generate_action_plan()` to `claude_agent.py`
- Parameters: `phases` (1-5), `cost_per_fte` (EUR)
- Uses existing data + ROI calculations

---

### 2. ML Model Explainer

**Purpose:** Help non-technical users understand the AI predictions.

**Why it matters:**
- Dr.Max staff have never used ML models
- Builds trust through transparency
- Explains what the model CAN and CANNOT predict
- Helps interpret confidence levels

**Key topics to cover:**

#### A. What the Model Does
```
"Model analyzuje historické dáta lekární a predpovedá,
koľko personálu (FTE) potrebujete na základe:

📊 VSTUPY:
├─ Tržby a počet blokov
├─ Typ lekárne (Poliklinika, Street+, Mall...)
├─ Lokalita a región
├─ Sezónnosť a trendy
└─ Historická produktivita

🎯 VÝSTUPY:
├─ Odporúčané FTE (optimálny počet)
├─ FTE Gap (rozdiel oproti súčasnosti)
├─ Ohrozené tržby (ak nepridáte personál)
└─ Index produktivity (porovnanie s priemerom)
"
```

#### B. How to Interpret Predictions
```
PRODUKTIVITA (Index)
├─ > 120: Kriticky preťažená - urgentne riešiť
├─ 100-120: Nadpriemerná - sledovať
├─ 80-100: Optimálna - v poriadku
└─ < 80: Podpriemerná - možná neefektívnosť

FTE GAP
├─ +1.0 a viac: Výrazne poddimenzovaná
├─ +0.5 až +1.0: Mierne poddimenzovaná
├─ -0.5 až +0.5: Správne dimenzovaná
└─ -1.0 a menej: Predimenzovaná

OHROZENÉ TRŽBY
= Tržby, ktoré riskujete stratiť ak:
  - Zákazníci odídu kvôli dlhému čakaniu
  - Personál nestíha obslúžiť všetkých
  - Kvalita služieb klesá
```

#### C. Model Limitations
```
⚠️ ČO MODEL NEVIE:
├─ Predpovedať náhle zmeny (nový konkurent, pandémia)
├─ Zohľadniť kvalitu jednotlivých zamestnancov
├─ Vedieť o plánovaných investíciách/rekonštrukciách
└─ Nahradiť lokálnu znalosť manažéra

✅ PRETO VŽDY:
├─ Kombinujte s vlastnou skúsenosťou
├─ Konzultujte s regionálnym manažérom
└─ Sledujte trendy, nie len aktuálny stav
```

**Implementation:**
- Add as Skill (SKILL.md) with comprehensive instructions
- Include visual examples and Slovak explanations
- Add sample Q&A for common questions

---

### 3. App Benefits Explainer (Sales Skill)

**Purpose:** Help explain and "sell" the app to stakeholders.

**Why it matters:**
- New users need to understand value proposition
- Helps justify investment in the tool
- Provides consistent messaging across organization
- Addresses common objections

**Key benefits to communicate:**

#### A. Business Value
```
💰 FINANČNÝ PRÍNOS

Problém BEZ aplikácie:
├─ Rozhodnutia na základe intuície
├─ Poddimenzované lekárne strácajú tržby
├─ Predimenzované lekárne plytvajú nákladmi
└─ Žiadny prehľad o celej sieti

S aplikáciou:
├─ Dátami podložené rozhodnutia
├─ Identifikácia €3.99M ohrozených tržieb
├─ Optimalizácia personálnych nákladov
└─ Jednotný pohľad na 200+ lekární
```

#### B. Time Savings
```
⏱️ ÚSPORA ČASU

Predtým (manuálne):
├─ Zber dát: 2-3 dni
├─ Analýza v Exceli: 1-2 dni
├─ Tvorba reportov: 1 deň
└─ SPOLU: 4-6 dní

S aplikáciou:
├─ Otázka asistentovi: 10 sekúnd
├─ Odpoveď s analýzou: 5-15 sekúnd
├─ Export do PDF: 1 klik
└─ SPOLU: < 1 minúta
```

#### C. Unique Features
```
🚀 ČO ROBÍ APLIKÁCIU VÝNIMOČNOU

1. AI Asistent rozumie slovenčine
   "Ktoré lekárne potrebujú personál?"

2. Drill-down analýza
   Sieť → Segment → Región → Lekáreň

3. Okamžité odpovede
   Žiadne čakanie na IT, žiadne tickety

4. Vždy aktuálne dáta
   Automatické prepojenie na firemné systémy

5. Export pre manažment
   PDF reporty pripravené na poradu
```

#### D. Addressing Objections
```
❓ ČASTÉ OTÁZKY A ODPOVEDE

"Môžem veriť AI?"
→ AI používa VAŠE dáta, nie vymýšľa čísla.
→ Každá odpoveď ukazuje použité nástroje.
→ Môžete si overiť v zdrojových dátach.

"Je to komplikované?"
→ Stačí písať otázky ako kolegovi.
→ Nie je potrebné poznať Excel vzorce.
→ Žiadne školenie, intuitívne rozhranie.

"Čo ak sa niečo zmení?"
→ Dáta sa aktualizujú automaticky.
→ Model sa učí z nových dát.
→ Administrátor môže upraviť parametre.

"Nahradí to manažérov?"
→ NIE - je to nástroj pre manažérov.
→ Poskytuje dáta, rozhodnutie je na vás.
→ Uvoľní čas na strategické úlohy.
```

**Implementation:**
- Add as Skill (SKILL.md)
- Include demo scenarios and talking points
- Provide ROI calculator examples

---

## Priority 2: Medium Value

### 4. Excel Export

**Purpose:** Export analysis results to Excel for further processing.

**Use cases:**
- Share with colleagues who don't use the app
- Further analysis in Excel/Google Sheets
- Include in presentations
- Archive for compliance

**Implementation:**
- Use `openpyxl` (already in requirements)
- Add `tool_export_to_excel()` function
- Return download link or base64 encoded file

---

### 5. Budget Calculator

**Purpose:** Calculate total hiring costs and budget requirements.

**Features:**
- Input: Number of FTEs, salary assumptions
- Output: Monthly/annual costs, benefits, total investment
- Compare: Current vs. recommended staffing costs

---

### 6. Trend Analysis

**Purpose:** Show historical trends and predict future needs.

**Features:**
- Month-over-month comparison
- Seasonal patterns
- Growth projections
- Early warning indicators

---

## Priority 3: Future Enhancements

### 7. Email Reports
- Scheduled automated reports
- Send to distribution lists
- Customizable frequency

### 8. What-If Simulator
- Model scenarios: "What if we add 5 FTE to Bratislava?"
- Compare outcomes
- Risk assessment

### 9. Competitor Analysis
- Market context
- Benchmark against industry
- Location-based insights

### 10. Employee Scheduling
- Shift optimization
- Peak hour coverage
- Vacation planning

---

## Implementation Notes

### Adding a Tool (Python)

```python
# In claude_agent.py

def tool_new_feature(self, param1: str, param2: int = 10) -> dict:
    """
    Description of what this tool does.

    Args:
        param1: Description
        param2: Description with default

    Returns:
        Structured response
    """
    # Implementation
    return {'result': 'data'}

# Register in __init__:
self.tools.append({
    "name": "new_feature",
    "description": "When to use this tool",
    "input_schema": {...}
})
```

### Adding a Skill (Markdown)

```
.claude/skills/
└── skill-name/
    ├── SKILL.md        # Required: instructions
    └── examples.md     # Optional: examples
```

SKILL.md format:
```markdown
---
name: skill-name
description: When to use this skill
---

# Skill Title

## Instructions
Step-by-step guidance for the AI

## Examples
Sample interactions

## Key Points
Important information to convey
```

---

## Recommended Implementation Order

1. **ML Model Explainer** (Skill) - Builds trust, easy to implement
2. **App Benefits Explainer** (Skill) - Helps adoption
3. **Action Plan Generator** (Tool) - High business value
4. **Excel Export** (Tool) - Practical utility

---

## Questions to Clarify Before Implementation

1. What is the actual cost per FTE? (salary + benefits + overhead)
2. Are there regional salary differences?
3. What hiring timeline is realistic? (30/60/90 days?)
4. Who are the target users for the "sales" skill?
5. What data access do we have for trend analysis?

---

*Document created: December 2024*
*Last updated: December 2024*
