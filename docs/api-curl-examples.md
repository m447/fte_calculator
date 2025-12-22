  | Endpoint               | Method | Auth            | Description                     |
  |------------------------|--------|-----------------|---------------------------------|
  | /                      | GET    | Basic           | Main web UI (index-v2.html)     |
  | /v1                    | GET    | Basic           | Legacy web UI (index.html)      |
  | /utilization           | GET    | Basic           | Utilization page                |
  | /api/predict           | POST   | Basic + API Key | Calculate recommended FTE       |
  | /api/network           | GET    | Basic + API Key | Network summary with priorities |
  | /api/pharmacies        | GET    | Basic + API Key | List all pharmacies             |
  | /api/pharmacies/search | GET    | Basic + API Key | Search pharmacies by name       |
  | /api/model/info        | GET    | Basic + API Key | ML model information            |
  | /api/pharmacy/<id>     | GET    | Basic + API Key | Get specific pharmacy details   |
  | /api/benchmarks        | GET    | Basic + API Key | Segment benchmarks              |
  | /api/chat              | POST   | Basic + API Key | AI assistant (simple)           |
  | /api/agent/analyze     | POST   | Basic + API Key | AI agent (multi-step analysis)  |
  | /api/agent/status      | GET    | Basic           | Check agent availability        |


# FTE Calculator API - Curl Examples

Base URL: `https://fte-calculator-638044991573.europe-west1.run.app`

## Authentication

All API endpoints require **two** authentication methods:

### 1. Basic Auth (required)
```bash
-u 'drmax:FteCalc2024!Rx#Secure'
```

### 2. API Key (required for direct API access)
```bash
-H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y'
```

**Note:** The web UI uses Basic Auth only (API key is not required when accessing through the browser).

---

## Endpoints

### 1. Get Pharmacy Details
Get details for a specific pharmacy by ID.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/pharmacy/71'
```

**Response:** Pharmacy data including predicted FTE, actual FTE, gap, revenue at risk.

---

### 2. Predict FTE
Calculate recommended FTE for given parameters.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{
    "typ": "B - shopping",
    "bloky": 158000,
    "trzby": 2600000,
    "podiel_rx": 0.56,
    "productivity_z": 0,
    "pharmacy_id": 71
  }' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/predict'
```

**Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| typ | string | Segment: "A - shopping premium", "B - shopping", "C - street +", "D - street", "E - poliklinika" |
| bloky | int | Annual transactions |
| trzby | int | Annual revenue in EUR |
| podiel_rx | float | Rx ratio (0-1) |
| productivity_z | float | Productivity: -1 (below), 0 (average), 1 (above) |
| pharmacy_id | int | Optional: pharmacy ID for actual FTE comparison |

---

### 3. Get Network Summary
Get overview of entire pharmacy network with priorities.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/network'
```

**Response:** Summary stats, segment breakdown, urgent/optimize/monitor pharmacy lists.

---

### 4. List All Pharmacies
Get list of all pharmacies with optional filters.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/pharmacies'
```

With filters:
```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/pharmacies?typ=B%20-%20shopping&region=RR1'
```

---

### 5. Search Pharmacies
Search pharmacies by city name.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/pharmacies/search?q=Kosice'
```

---

### 6. Get Model Info
Get information about the ML model.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/model/info'
```

---

### 7. Get Benchmarks
Get segment benchmarks and statistics.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/benchmarks'
```

---

### 8. AI Chat
Ask questions to the AI assistant.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Ktore lekarne su poddimenzovane?",
    "context": {}
  }' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/chat'
```

With pharmacy context:
```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Preco ma tato lekaren vysoke ohrozene trzby?",
    "context": {
      "pharmacy_id": 33,
      "pharmacy_name": "Levice",
      "typ": "B - shopping",
      "bloky": 120000,
      "trzby": 2000000,
      "fte_total": 7.7,
      "fte_actual": 6.5,
      "fte_diff": 1.2,
      "revenue_at_risk": 232436
    }
  }' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/chat'
```

---

## Quick Test

Test connectivity (will fail without API key):
```bash
curl -I --user 'drmax:FteCalc2024!Rx#Secure' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/pharmacy/1'
```
Expected: `HTTP/2 403` (API key required)

Test with API key:
```bash
curl -I --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/pharmacy/1'
```
Expected: `HTTP/2 200`

---

## Response Formats

All endpoints return JSON. Example pharmacy response:
```json
{
  "id": 71,
  "mesto": "Košice, Kaufland Galeria",
  "typ": "B - shopping",
  "actual_fte": 8.0,
  "predicted_fte": 8.3,
  "fte_diff": 0.3,
  "revenue_at_risk": 49954,
  "is_above_avg_productivity": true
}
```

## Error Responses

### Missing Basic Auth (401)
```
Prístup zamietnutý. Zadajte správne prihlasovacie údaje.
```

### Missing API Key (403)
```json
{"error": "API key required. Use X-API-Key header."}
```

---

## AI Agent Endpoint (Claude Opus 4.5)

The agent endpoint uses a hybrid Opus + Haiku architecture for complex multi-step analysis.

### 9. Agent Analyze
Ask complex analytical questions. The agent autonomously plans and executes tool calls.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  -H 'X-API-Key: fte-api-2024-xK9mP2vL8nQ4wR7y' \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Z akého regiónu je ID 33?"}' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/agent/analyze'
```

**Response:**
```json
{
  "response": "Lekáreň ID 33 (Levice, TESCO) patrí do regiónu **RR11**.",
  "tools_used": ["get_pharmacy_details"],
  "tool_call_count": 1,
  "duration_seconds": 6.83,
  "request_id": "30e93356",
  "model": "claude-opus-4-5"
}
```

### Example Prompts

**Get pharmacy details:**
```bash
-d '{"prompt":"Detaily lekárne ID 33"}'
```

**City-based FTE optimization (with staff transfer):**
```bash
-d '{"prompt":"Existuju v meste Kosice lekarne s ohrozenymi trzbami? Ak ano, je mozne optimalizaovat FTE v ramoci Kosic? Ak ano, uved aj lekarne v ktorych je mozne presunut personal. Dakujem"}'
```

**Compare to peers with higher FTE:**
```bash
-d '{"prompt":"Porovnaj ID 33 s podobnými lekárňami (pocet blokov), ktore maju viac FTE"}'
```

**Top understaffed with risk:**
```bash
-d '{"prompt":"Top 10 poddimenzovaných lekární s ohrozenými tržbami"}'
```

**Regional report:**
```bash
-d '{"prompt":"Report za všetky regióny so sumárom ohrozených tržieb, skutočným a optimálnym FTE"}'
```

**Compare to peers:**
```bash
-d '{"prompt":"Porovnaj ID 33 s podobnými lekárňami"}'
```

**Region-specific:**
```bash
-d '{"prompt":"Poddimenzované lekárne v RR15"}'
```

**High productivity + high risk:**
```bash
-d '{"prompt":"Lekárne s nadpriemernou produktivitou a ohrozenými tržbami"}'
```

**Network overview (health check):**
```bash
-d '{"prompt":"Ako je na tom celá sieť lekární?"}'
```

**Segment comparison:**
```bash
-d '{"prompt":"Ktorý segment má najväčšie problémy s ohrozenými tržbami?"}'
```

**Priority actions:**
```bash
-d '{"prompt":"Čo riešiť najskôr? Top 10 priorít."}'
```

**Trend analysis (growing/declining):**
```bash
-d '{"prompt":"Ktoré lekárne rastú a ktoré klesajú?"}'
```

**City summary:**
```bash
-d '{"prompt":"Ako je na tom Košice celkovo?"}'
```

### 10. Agent Status
Check if the agent is available.

```bash
curl --user 'drmax:FteCalc2024!Rx#Secure' \
  'https://fte-calculator-638044991573.europe-west1.run.app/api/agent/status'
```

**Response:**
```json
{
  "available": true,
  "model": "claude-opus-4-5",
  "features": [
    "search_pharmacies",
    "compare_to_peers",
    "get_understaffed",
    "get_regional_summary",
    "get_all_regions_summary",
    "generate_report",
    "get_segment_comparison",
    "get_city_summary",
    "get_network_overview",
    "get_trend_analysis",
    "get_priority_actions"
  ]
}
```
