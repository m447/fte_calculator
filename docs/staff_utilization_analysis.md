# Staff Utilization Analysis

Automated analysis of pharmacy staff utilization to identify lost revenue due to understaffing and generate optimization recommendations.

## Overview

The system analyzes transaction data to:
1. Identify periods when staff is overloaded (customers leave without purchase)
2. Calculate estimated lost revenue per hour/day
3. Propose schedule optimizations (hour-neutral and with extra hours)
4. Calculate ROI for each optimization option

## Data Requirements

### Input: Transaction Data (CSV)

| Column | Type | Description |
|--------|------|-------------|
| datum | datetime/float | Transaction timestamp (Excel serial or ISO format) |
| meno | string | Staff member name who processed transaction |
| hodnota | float | Transaction value in EUR |

Optional columns: `pokladna`, `doklad`, `hotovost`, `karta`, `zisk`

### Minimum data period
- Recommended: 4-6 weeks
- Minimum: 2 weeks (for weekly pattern detection)

## Methodology

### 1. Staff Detection
```
Staff per hour = count(unique meno per hour)
```
Derived from transaction data - if an employee processed a transaction in that hour, they were working.

### 2. Load Calculation
```
Load = Transactions per hour / Staff on duty
```
Expressed as transactions per staff member per hour (txn/staff/h).

### 3. Baseline Load Detection
```
Baseline = average load during adequately staffed periods
```
Heuristic: Use morning hours (8-10) or lowest 25th percentile of load values.

Typical baseline: 10-12 txn/staff/h

### 4. Lost Revenue Estimation

When load exceeds baseline by >15%, conversion drops:

```
If load_ratio > 1.15:
    conversion_drop = (load_ratio - 1) × 0.5
    lost_revenue = revenue × conversion_drop
Else:
    lost_revenue = 0
```

The 0.5 coefficient is based on empirical analysis showing ~50% of excess customers leave when overloaded.

### 5. Optimization Calculation

**Hour-neutral optimization:**
- Identify overstaffed periods (load < baseline × 0.85)
- Identify understaffed periods (load > baseline × 1.15)
- Redistribute hours from overstaffed → understaffed
- Calculate recovered revenue

**Full optimization (with extra hours):**
- Calculate hours needed to bring all periods to baseline
- Extra cost = additional hours × hourly wage
- ROI = recovered revenue / extra cost

## Output Schema

### Pharmacy Summary
```json
{
  "pharmacy_id": "string",
  "pharmacy_name": "string",
  "period": {"start": "date", "end": "date"},
  "monthly_revenue": 151600,
  "monthly_lost_revenue": 7972,
  "lost_percentage": 5.3,
  "critical_hours": 29,
  "baseline_load": 11.7,
  "total_weekly_hours": 257
}
```

### Hourly Metrics
```json
{
  "day": "Po",
  "hour": 16,
  "avg_staff": 3.1,
  "avg_transactions": 47,
  "avg_revenue": 580,
  "load": 15.3,
  "monthly_lost_revenue": 364
}
```

### Current Schedule
```json
{
  "day": "Po-Pi",
  "blocks": {
    "8-11": {"staff": 4, "status": "ok"},
    "11-16": {"staff": 4, "status": "ok"},
    "16-19": {"staff": 3, "status": "understaffed"}
  },
  "daily_hours": 41
}
```

### Optimization Options
```json
{
  "option_a": {
    "name": "Hour-neutral",
    "weekly_hours": 257,
    "extra_hours": 0,
    "extra_cost": 0,
    "recovered_revenue": 3000,
    "net_benefit": 3000,
    "changes": [
      {"day": "Po-Pi", "block": "8-11", "from": 4, "to": 3},
      {"day": "Po-Pi", "block": "16-19", "from": 3, "to": 4}
    ]
  },
  "option_b": {
    "name": "Full solution",
    "weekly_hours": 270,
    "extra_hours": 13,
    "extra_cost": 675,
    "recovered_revenue": 4800,
    "net_benefit": 4125,
    "roi_multiplier": 7.1,
    "changes": [...]
  }
}
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DATA SOURCES                         │
│  CSV exports / Central DB / POS API                     │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│               ANALYSIS SCRIPT (Python)                  │
│  - Load transaction data                                │
│  - Calculate staff per hour                             │
│  - Calculate load, baseline, lost revenue               │
│  - Generate optimization recommendations                │
│  - Output standardized JSON                             │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│                   RESULTS DATABASE                      │
│  Tables:                                                │
│  - pharmacies (id, name, location)                      │
│  - analysis_runs (id, pharmacy_id, run_date)            │
│  - hourly_metrics (run_id, day, hour, staff, load...)   │
│  - optimization_options (run_id, option, cost, benefit) │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│                      API LAYER                          │
│  GET /api/pharmacies                                    │
│  GET /api/pharmacy/{id}/utilization                     │
│  GET /api/pharmacy/{id}/optimization                    │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│                     DASHBOARD                           │
│  - Pharmacy selector dropdown                           │
│  - Summary stats                                        │
│  - Lost revenue heatmap                                 │
│  - Schedule comparison (current vs optimized)           │
│  - ROI calculator                                       │
└─────────────────────────────────────────────────────────┘
```

## Database Schema

```sql
CREATE TABLE pharmacies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    location VARCHAR(255),
    type VARCHAR(50)  -- A/B/C/D/E segment
);

CREATE TABLE analysis_runs (
    id SERIAL PRIMARY KEY,
    pharmacy_id INTEGER REFERENCES pharmacies(id),
    run_date DATE,
    period_start DATE,
    period_end DATE,
    monthly_revenue DECIMAL(12,2),
    monthly_lost_revenue DECIMAL(12,2),
    baseline_load DECIMAL(5,2),
    total_weekly_hours INTEGER
);

CREATE TABLE hourly_metrics (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES analysis_runs(id),
    day_of_week SMALLINT,  -- 0=Po, 6=Ne
    hour SMALLINT,         -- 8-19
    avg_staff DECIMAL(4,2),
    avg_transactions DECIMAL(6,2),
    avg_revenue DECIMAL(10,2),
    load DECIMAL(5,2),
    monthly_lost_revenue DECIMAL(10,2)
);

CREATE TABLE schedule_blocks (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES analysis_runs(id),
    day_group VARCHAR(10),  -- 'Po-Pi', 'So', 'Ne'
    time_block VARCHAR(10), -- '8-11', '11-16', '16-19'
    current_staff DECIMAL(4,2),
    status VARCHAR(20)      -- 'ok', 'understaffed', 'overstaffed'
);

CREATE TABLE optimization_options (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES analysis_runs(id),
    option_code CHAR(1),    -- 'A' or 'B'
    option_name VARCHAR(100),
    weekly_hours INTEGER,
    extra_hours INTEGER,
    extra_cost_monthly DECIMAL(10,2),
    recovered_revenue_monthly DECIMAL(10,2),
    net_benefit_monthly DECIMAL(10,2),
    changes JSONB
);
```

## Run Frequency

| Scenario | Frequency |
|----------|-----------|
| Initial analysis | Once per pharmacy |
| Regular update | Weekly or monthly |
| After schedule change | Ad-hoc |

## Implementation Steps

1. **Create analysis script** (`analyze_pharmacy.py`)
   - Input: pharmacy CSV or DB query
   - Output: JSON matching schema above

2. **Set up database**
   - Create tables
   - Initial pharmacy list

3. **Build API**
   - Flask/FastAPI endpoints
   - Query pre-calculated results

4. **Update dashboard**
   - Add pharmacy selector
   - Fetch data from API
   - Render dynamically

5. **Automate**
   - Cron job for regular analysis
   - Alert if lost revenue increases

## Files

| File | Description |
|------|-------------|
| `/app/static/utilization.html` | Dashboard prototype (single pharmacy) |
| `/app/server.py` | Flask server with `/utilization` route |
| `/docs/staff_utilization_analysis.md` | This documentation |

## Assumptions & Limitations

1. **Staff detection accuracy**: Assumes staff who processed transactions were on duty. Does not capture staff on break or doing non-transaction work.

2. **Conversion drop model**: The 50% coefficient is an estimate. Real conversion drop varies by pharmacy type, location, and customer demographics.

3. **Opening hours**: Detected from transaction data. May not reflect official hours if pharmacy is slow at open/close.

4. **Baseline selection**: Morning hours (8-10) assumed adequate. May need adjustment for pharmacies with morning rush.

5. **Hourly wage**: ROI calculations assume 12 EUR/hour. Should be parameterized per pharmacy/region.

## Potential Enhancements

### Time Navigation

Current dashboard shows aggregated weekly average. Future versions could include:

**Week/Month Selector**
```
[◀] Week 37 (Sep 6-12) [▶]    or    [September ▼]
```
- Navigate through individual weeks
- Compare different periods
- Identify seasonal patterns

**Calendar Heatmap View**
```
         Po  Ut  St  Št  Pi  So  Ne
Week 36  🟢  🟢  🟢  🟡  🟡  🔴  🔴
Week 37  🟢  🟢  🟡  🟡  🔴  🔴  🔴
Week 38  🟢  🟢  🟢  🟢  🟡  🔴  🔴
Week 39  🟢  🟡  🟡  🟡  🔴  🔴  🔴
```
- Bird's eye view of all weeks
- Click week to see hourly detail
- Quickly spot problem weeks

**Trend Analysis**
```
Lost Revenue Trend
8000€ ┤    ╭─╮
6000€ ┤ ╭──╯ ╰──╮
4000€ ┤─╯       ╰──
     └─────────────
      W36 W37 W38 W39
```
- Track improvement over time
- Measure impact of schedule changes

### Additional Metrics

| Metric | Description |
|--------|-------------|
| Staff utilization % | Actual vs optimal capacity |
| Peak hour coverage | % of peak hours adequately staffed |
| Schedule adherence | Planned vs actual staffing |
| Customer wait proxy | Based on load/baseline ratio |

### Alerts

- Automatic notification if lost revenue exceeds threshold
- Weekly summary email to pharmacy manager
- Comparison to network average

## Dashboard Review & Improvements

### Overall Assessment

The dashboard effectively bridges the gap between raw operational data (staffing schedules, transaction loads) and business outcomes (lost revenue, ROI). It functions as a **decision-support tool** rather than a raw data dump.

---

### 1. UX & Data Visualization

**Strengths:**
- The "Story" flow is excellent - layout logically leads from problem (Summary Stats & Heatmap) to solution (Optimization & Implementation)
- Heatmap color coding (`loss-0` to `loss-critical`) is intuitive

**Improvements:**

| Issue | Current | Recommendation |
|-------|---------|----------------|
| Cell text size | 0.65rem "3 zam" hard to read | Use dot icons for staff count, or tooltip-only |
| Mobile scrolling | `overflow-x: auto` not obvious | Add shadow fade or "Scroll →" hint |
| Tooltip positioning | May render off-screen on last column | Flip to left when near edge (see code below) |

**Tooltip Fix:**
```javascript
function showTooltip(e) {
  // ... existing content generation code ...

  tooltip.style.display = 'block';

  const rect = cell.getBoundingClientRect();
  const tipRect = tooltip.getBoundingClientRect();
  const margin = 10;

  // Default placement: Right
  let leftPos = rect.right + margin;
  let topPos = rect.top;

  // Check right boundary
  if (leftPos + tipRect.width > window.innerWidth) {
    leftPos = rect.left - tipRect.width - margin;
  }

  // Check bottom boundary
  if (topPos + tipRect.height > window.innerHeight) {
    topPos = window.innerHeight - tipRect.height - margin;
  }

  tooltip.style.left = leftPos + 'px';
  tooltip.style.top = topPos + 'px';
}
```

---

### 2. Business Logic & Content

**ROI Highlighting:**
- Current: "ROI: 7× return" is tucked away at bottom
- Recommendation: Elevate visually - place between header and table in Option B card as key selling point

**Baseline Transparency:**
- Current: Methodology at bottom makes "Kritické hodiny" feel abstract
- Recommendation: Add `(?)` icon next to header stats with tooltip definition (>13.5 txn/staff/hr)

**Missing Context - "Why?":**
- Current: Heatmap shows *where* loss is, not *why* (high traffic vs understaffed)
- Recommendation: Color-code cell border or add indicator when load > critical threshold to distinguish "high traffic day" from "someone called in sick"

---

### 3. Technical Implementation

**Hardcoded Data:**
- Current: `monthlyLoss`, `weeklyLoad`, `weeklyStaff` are hardcoded objects
- Recommendation: Create `renderDashboard(data)` function, fetch JSON from external file/API
- Separates View from Data for multi-store/multi-month use

**Accessibility (A11y):**
- Current: Heatmap cells are `div` with hover listeners, no keyboard access
- Fix: Change to `<button>` elements or add `tabindex="0"` and `aria-label="Monday 8am, Loss 0 Euro, Staff 4"`

**CSS Scalability:**
- Current: `grid-template-columns: 50px repeat(12, 1fr)` is brittle
- Issue: If hours change (e.g., open at 7 AM), CSS breaks
- Fix: Generate `grid-template-columns` dynamically in JS based on data

---

### 4. Refactoring Priorities

| Priority | Task | Effort |
|----------|------|--------|
| High | Separate data from view (JSON) | 2h |
| High | Fix tooltip positioning | 30min |
| Medium | Add accessibility attributes | 1h |
| Medium | Dynamic grid columns | 1h |
| Low | Mobile scroll indicator | 30min |
| Low | ROI visual elevation | 30min |

---

## Example Results

**Kaufland Michalovce (Sep-Oct 2021)**

| Metric | Value |
|--------|-------|
| Monthly revenue | 151,600 EUR |
| Monthly lost revenue | 7,972 EUR (5.3%) |
| Critical hours | 29/84 |
| Baseline load | 11.7 txn/staff/h |
| Current weekly hours | 257h |

| Optimization | Extra Cost | Recovered Revenue | Net Benefit |
|--------------|------------|-------------------|-------------|
| Option A (hour-neutral) | 0 EUR | 3,000 EUR | 3,000 EUR |
| Option B (+13h/week) | 675 EUR | 4,800 EUR | 4,125 EUR |
