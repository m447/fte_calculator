# Productivity-Staffing Paradox

## Problem

Some pharmacies appeared both **highly productive** AND **overstaffed**, which seemed contradictory. How can a pharmacy be working at above-average efficiency while simultaneously having too many staff?

## Root Cause

The paradox arose from using different FTE bases for different metrics:

| Metric | FTE Base | Description |
|--------|----------|-------------|
| Productivity | NET FTE | Actual hours worked (excludes absences) |
| Staffing surplus | GROSS FTE | Contracted positions (includes absences) |

**Example - Pharmacy 67 (Stará Ľubovňa, Kaufland, typ B):**

```
produktivita (NET):   bloky / fte_NET / 2088 = 11.36 (above segment avg 9.14)
produktivita (GROSS): bloky / fte_GROSS / 2088 = 9.10 (still above avg)
fte_diff (GROSS):     actual_fte_gross - predicted_fte = +0.6 (overstaffed)
```

The pharmacy appeared paradoxical because:
- High NET productivity = staff work efficiently during actual work hours
- Overstaffed on GROSS = more contracted positions than needed (includes absence buffer)

## Resolution

Added GROSS-based productivity for UI classification to ensure consistency:

1. **`produktivita_gross`** - productivity using GROSS FTE
2. **`is_above_avg_gross`** - classification based on GROSS productivity

See [productivity_metrics.md](productivity_metrics.md) for detailed formulas.

## Impact

| Classification | Paradox Count | Change |
|----------------|---------------|--------|
| NET-based | 13 pharmacies | - |
| GROSS-based | 9 pharmacies | -4 (31% reduction) |

## Current Paradox Pharmacies (GROSS-based)

These pharmacies have above-average GROSS productivity AND are overstaffed (>0.5 FTE surplus):

| ID  | Mesto                      | Typ | Surplus  | Produktivita GROSS |
|-----|----------------------------|-----|----------|-------------------|
| 64  | Piešťany, Kaufland         | B   | +1.0 FTE | 9.06 |
| 127 | Žilina, Národná            | D   | +1.0 FTE | 6.29 |
| 241 | Šaštín-Stráže              | C   | +0.9 FTE | 7.00 |
| 2   | Bratislava, Obchodná       | D   | +0.7 FTE | 5.92 |
| 52  | Sereď, Kaufland            | B   | +0.6 FTE | 9.85 |
| 67  | Stará Ľubovňa, Kaufland    | B   | +0.6 FTE | 9.10 |
| 100 | Sabinov, Nám. Slobody      | D   | +0.6 FTE | 11.33 |
| 267 | Levoča                     | C   | +0.6 FTE | 8.78 |
| 553 | Ban. Štiavnica             | C   | +0.6 FTE | 11.00 |

## Interpretation

These remaining paradox cases may indicate:

1. **Strategic buffer** - Intentional overstaffing for peak periods or expansion
2. **Absence patterns** - Higher-than-average absence rates requiring more contracted positions
3. **Data timing** - Staffing adjusted for anticipated workload changes not yet reflected in transaction data

## Recommendations

1. **Review individually** - Each paradox pharmacy should be examined for context
2. **Monitor trends** - Track if productivity remains high over time
3. **Consider seasonality** - Some locations may need buffer staff for peak seasons
