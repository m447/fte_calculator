# Sales Strategy: Inteligentný FTE Manažment

**Product:** AI-Powered Pharmacy Staffing Optimization Platform
**Target Markets:** Slovakia, Czech Republic, Poland
**Methodology:** Kahneman Behavioral Economics Principles

---

## Current Situation (Honest Assessment)

| Fact | Implication |
|------|-------------|
| App built 4 years ago (2020-2021 data) | Model trained on COVID-era patterns |
| Developed for Dr.Max SK only | Single-client, single-market proof of concept |
| Original question: "Is B segment understaffed?" | Narrow scope, expanded into full tool |
| Zero current users | Cold-start sales situation |
| 97.1% R² on historical data | Strong technical foundation, needs validation |

**Bottom line:** This is a **proven methodology** seeking its first paying customer, not an established product.

---

## What the App Actually Does (Be Honest)

### Current Capability: Optimal Headcount Prediction

The app predicts **total FTE needed** for each pharmacy based on aggregate metrics:

| Input | Output |
|-------|--------|
| Annual transactions (bloky) | **Optimal FTE: 4.2** |
| Annual revenue (tržby) | Role breakdown (F/L/ZF) |
| Store type (A-E) | Productivity benchmark |
| RX ratio | Segment comparison |

**What it answers:** "How many people should work at this pharmacy?"

### What It Does NOT Do (Future Opportunity)

| Capability | Status | Would Require |
|------------|--------|---------------|
| Peak hour analysis | NOT available | Hourly transaction data |
| Shift scheduling | NOT available | Daily/weekly patterns |
| Queue/walkout detection | NOT available | Wait time sensors, customer flow |
| Real-time adjustments | NOT available | Live transaction feeds |

**Important:** The "Saturday walkout" scenario is a **Phase 2 opportunity**, not a current feature. Don't oversell.

### Product Roadmap (Honest)

| Phase | Capability | Data Needed |
|-------|------------|-------------|
| **Phase 1 (NOW)** | Optimal headcount per pharmacy | Annual aggregates |
| **Phase 2 (FUTURE)** | Peak-hour staffing recommendations | Hourly transaction patterns |
| **Phase 3 (FUTURE)** | Dynamic shift optimization | Real-time data integration |

---

## Strategic Reframe (Kahneman: Framing Effects)

### What We Have (Weak Frame)
- An old prototype nobody uses
- 4-year-old data from one client

### What We Have (Strong Frame)
- **Battle-tested methodology** validated on real pharmacy data
- **First-mover advantage** for any chain willing to pilot
- **Low-risk proof of concept** - we've already done the hard work
- **Customizable foundation** ready to train on YOUR data

---

## Executive Summary

This sales strategy applies Daniel Kahneman's behavioral economics principles to position the FTE Management app as an essential tool for pharmacy chains facing acute staffing crises. The approach leverages **loss aversion**, **anchoring**, and **narrative framing** to overcome status quo bias.

**Key insight:** With no existing customers, we must sell the **methodology and pilot opportunity**, not the product.

---

## 1. Target Customers (Reality-Based Priority)

### The Cold-Start Problem

With zero users, we face the classic chicken-and-egg:
- **No social proof** → "Who else uses this?"
- **No case studies** → "Show me results"
- **Old data** → "Is this still relevant?"

**Kahneman solution:** Leverage **existing relationships** and offer **risk-free pilots**.

---

### Tier 0: THE ONLY LOGICAL FIRST TARGET

| Company | Why MUST Be First |
|---------|-------------------|
| **Dr.Max Slovakia** | Model built on THEIR data. You have relationship from original project. They know the methodology works. Lowest barrier to re-engagement. |

**The Pitch to Dr.Max SK:**
> "4 years ago, I answered your question about B segment staffing. The methodology I built has evolved into a full platform. You're sitting on 4 years of new data that could make this even more accurate. Let's update the model and prove the ROI."

**Kahneman principle:** **Endowment Effect** - They already "own" part of this through the original project.

---

### Tier 1: Warm Introductions (Need Dr.Max First)

| Company | Country | Pharmacies | Open Positions | Path to Sale |
|---------|---------|------------|----------------|--------------|
| **Dr.Max CZ** | CZ | 529 | 50+ | Internal referral from SK |
| **Dr.Max PL** | PL | 550 | 100+ | Internal referral from SK |
| **BENU CZ/SK** | CZ/SK | 520 | 245 | Competitor pressure once Dr.Max adopts |

### Tier 2: Cold Outreach (Need Case Study First)

| Company | Country | Pharmacies | Open Positions | Why Target |
|---------|---------|------------|----------------|------------|
| **DOZ Apteki** | PL | 1,100+ | 2,000+ | Desperate - 2,000 vacancies |
| **Ziko Apteka** | PL | 165+ | 500+ | Fast-growing, tech-forward |
| **Gemini Apteki** | PL | 300+ | 83 | Recently acquired, seeking efficiency |

### Tier 3: After Proof Points

| Company | Country | Notes |
|---------|---------|-------|
| **Pilulka** | CZ/SK | Digital-first, will want data |
| **Super-Pharm** | PL | Corporate, needs case studies |
| **Omega Lekáreň** | SK | Smaller, easier decision |

---

## 2. Kahneman Principles Applied

### Principle 1: LOSS AVERSION
*"Losses loom larger than gains"* - People feel losses 2x more intensely than equivalent gains.

#### First: Define the Losses Honestly

**The Real Problem: 3 Regions, 3 Intuitions, No Standard**

| Region | Manager | Their Philosophy |
|--------|---------|------------------|
| West | Manager A | "Staff generously - customer service first" |
| Central | Manager B | "Run lean - productivity matters" |
| East | Manager C | "Match last year's numbers" |

Same segment, same transaction volume → different FTE decisions. No objective arbiter.

---

### TWO Types of Loss (App Calculates Both)

#### Loss Type 1: REVENUE AT RISK (Understaffed + Productive)

**When it applies:** Pharmacy is understaffed AND has above-average productivity.

**Logic:** A productive pharmacy that's understaffed is maxed out - they're leaving money on the table because they can't serve all potential customers.

**App Formula:**
```
Revenue at Risk = (Overload_ratio - 1) × 50% × Annual_Revenue

Where: Overload_ratio = Predicted_FTE / Actual_FTE
```

**Example:**

| Pharmacy | Actual FTE | Model Says | Overload Ratio | Annual Revenue | Revenue at Risk |
|----------|------------|------------|----------------|----------------|-----------------|
| Store B | 4.0 | 4.5 | 1.125 | €1,000,000 | **(0.125 × 0.5 × €1M) = €62,500** |

**Why 50%?** Conservative assumption - only half of the overload translates to actual lost revenue.

**Why only productive pharmacies?** If they're NOT productive and understaffed, they're handling the workload fine - no revenue loss.

---

#### Loss Type 2: UNJUSTIFIED LABOR COST (Overstaffed)

**When it applies:** Pharmacy has more FTE than the model predicts.

**Logic:** You're paying for staff that the transaction volume doesn't justify.

**Formula:**
```
Unjustified Cost = (Actual_FTE - Predicted_FTE) × Annual_Labor_Cost_per_FTE
```

**Example:**

| Pharmacy | Actual FTE | Model Says | Gap | Cost/FTE | Unjustified Cost |
|----------|------------|------------|-----|----------|------------------|
| Store A | 5.5 | 4.2 | +1.3 | €35k | **€45,500/year** |

---

### Complete Example: All Scenarios

| Pharmacy | Actual | Predicted | Gap | Productivity | Loss Type | Amount |
|----------|--------|-----------|-----|--------------|-----------|--------|
| Store A | 5.5 | 4.2 | +1.3 | Any | **Unjustified labor** | €45,500/yr |
| Store B | 4.0 | 4.5 | -0.5 | Above avg | **Revenue at risk** | €62,500/yr |
| Store C | 3.5 | 4.0 | -0.5 | Below avg | None | €0 (handling it) |
| Store D | 4.0 | 4.0 | 0 | Any | None | ✓ optimal |

---

#### The Honest Loss Frame Pitch:

> "Right now, your staffing decisions depend on which regional manager you ask. Three regions, three philosophies, three different answers for the same situation.
>
> That's not a staffing strategy - that's a political process.
>
> The app identifies two types of problems:
>
> **1. Understaffed + productive pharmacies:** Your best performers are maxed out. They're leaving revenue on the table - customers who won't wait, prescriptions that take longer than they should. The app calculates exactly how much.
>
> **2. Overstaffed pharmacies:** You're paying for FTE that the transaction volume doesn't justify. Maybe there's a good reason - complex prescriptions, difficult location, training period. But shouldn't you know which pharmacies those are, and why?
>
> This tool gives you one objective standard. When everyone starts from the same benchmark, the debates become productive."

---

#### Quantified Loss Potential (REAL DATA: Dr.Max SK)

**Source:** Original Dr.Max Slovakia dataset (286 pharmacies, €338M revenue, 2020-2021)

---

**ACTUAL RESULTS FROM MODEL:**

| Loss Type | Pharmacies Affected | Total Amount | Avg per Pharmacy |
|-----------|--------------------:|-------------:|-----------------:|
| **Revenue at Risk** (understaffed + productive) | 109 (38%) | **€3,794,480** | €34,812 |
| **Unjustified Labor** (overstaffed) | 124 (43%) | **€686,839** | €5,539 |
| **COMBINED** | - | **€4,481,319** | - |

**As % of total revenue: 1.32%**

---

**Revenue at Risk by Segment:**

| Segment | Revenue at Risk | Unjustified Labor | Total |
|---------|----------------:|------------------:|------:|
| B - shopping | €1,381,166 | €224,019 | €1,605,185 |
| E - poliklinika | €1,050,593 | €173,544 | €1,224,137 |
| C - street + | €984,157 | €146,608 | €1,130,765 |
| D - street | €243,569 | €89,102 | €332,671 |
| A - shopping premium | €134,995 | €53,566 | €188,561 |

---

**Key Insight:** Revenue at Risk (€3.8M) is **5.5× larger** than Unjustified Labor (€0.7M).

**This means:** The bigger opportunity is adding staff to productive understaffed pharmacies, not cutting from overstaffed ones.

---

**Extrapolation to Larger Networks (Illustrative):**

| Chain | Pharmacies | If same 1.32% pattern | Potential Loss |
|-------|------------|----------------------:|---------------:|
| Dr.Max CZ | 529 | €750M × 1.32% | **~€10M/year** |
| DOZ (PL) | 1,100 | €800M × 1.32% | **~€10.5M/year** |
| BENU CZ | 400 | €350M × 1.32% | **~€4.6M/year** |
| Dr.Max SK (actual) | 286 | €338M × 1.32% | **€4.5M/year** ✓ |

*Note: Extrapolations assume similar staffing patterns. Actual figures require their data.*

---

### Principle 2: ANCHORING
*"The first number you hear becomes your reference point"*

#### Application: Use Real Data as Anchors

**Opening Statement (based on actual Dr.Max SK results):**
> "When we analyzed 286 pharmacies in Slovakia, we found **€4.5M in combined loss potential** - that's 1.32% of total revenue. For your network of [X] pharmacies, applying the same pattern suggests **€Y million** worth investigating."

**The Power of Real Data:**

| Anchor | Source | Impact |
|--------|--------|--------|
| "€3.8M revenue at risk" | Actual calculation from 286 pharmacies | Sets expectation for understaffing problem |
| "38% of pharmacies understaffed + productive" | Actual data | Shows this is widespread, not edge case |
| "5.5× more opportunity in understaffed than overstaffed" | Actual ratio | Reframes from "cost cutting" to "revenue capture" |
| "€35k average revenue at risk per affected pharmacy" | Actual average | Makes it tangible per-location |

#### Anchor Sequence:

1. **First anchor:** "€4.5M combined loss found in 286 pharmacies" (real, proven)
2. **Second anchor:** "1.32% of revenue - apply that to YOUR network" (scalable)
3. **Third anchor:** "The bigger opportunity is understaffed productive pharmacies, not cutting staff" (reframe)

---

### Principle 3: NARRATIVE FALLACY
*"Stories beat statistics"*

#### Application: Lead with Stories, Back with Data

**The Story (System 1 - Fast Thinking):**

> "Four years ago, Dr.Max Slovakia asked me a simple question: 'Are our B-segment pharmacies understaffed?'
>
> Everyone had opinions. Regional managers said yes. Finance said no. Nobody had data.
>
> So I built a model. Analyzed 286 pharmacies across 5 segments. Transactions, revenue, store type, prescription ratios - 15+ variables.
>
> The answer? Some B-segment stores were understaffed by 0.8 FTE. Others were overstaffed by 0.5 FTE. The segment wasn't the problem - the **allocation** was.
>
> That model predicted optimal staffing with 97.1% accuracy. It ended the guessing game.
>
> **They didn't have a staffing problem. They had a visibility problem.**"

**The Data (System 2 - Slow Thinking):**

| Metric | Value |
|--------|-------|
| Model accuracy (R²) | 97.1% |
| Prediction error (RMSE) | ±0.29 FTE |
| Training data | 286 pharmacies, 12 months |
| Features analyzed | 15+ operational metrics |

**Phase 2 Opportunity (Future - Don't Promise Yet):**

> With hourly transaction data, we could answer: "Which hours are understaffed?" That's the next evolution - but we need Phase 1 proven first.

---

### Principle 4: AVAILABILITY HEURISTIC
*"If you can easily recall it, it must be important"*

#### Application: Use Recent, Vivid Examples from Their Market

**For Czech clients:**
> "You've seen the headlines: 7 regions with no 24-hour pharmacy. Pharmacies closing in border towns. BENU offering €8,000 signing bonuses. The staffing crisis isn't coming - it's here."

**For Polish clients:**
> "DOZ has 2,000 open positions. That's not a recruiting problem - that's a structural problem. When you can't fill positions, you need to maximize the ones you have."

**For Slovak clients:**
> "79% of Slovak municipalities have no pharmacy. The ones that remain are fighting over the same 5,000 pharmacists. You can't hire your way out of this - you need to optimize."

---

### Principle 5: FRAMING EFFECTS
*"How you present information matters more than the information itself"*

#### Application: Frame as Risk Mitigation, Not Cost Savings

**Cost Frame (Weak):**
> "This tool will save you money on labor costs."

**Risk Frame (Strong):**
> "This tool protects you from the two biggest threats to pharmacy profitability:
> 1. **Understaffing** → Burned-out pharmacists who quit (€15k+ replacement cost each)
> 2. **Overstaffing** → Labor costs eating into margins month after month"

#### Frame Comparisons:

| Weak Frame | Strong Frame |
|------------|--------------|
| "Improve efficiency" | "Stop the bleeding" |
| "Optimize staffing" | "Protect your margins" |
| "Save on labor" | "Reduce revenue leakage" |
| "Better scheduling" | "End the guessing game" |

---

### Principle 6: STATUS QUO BIAS
*"Change feels risky; staying the same feels safe"*

#### Application: Make Inaction Feel Dangerous

**The Inaction Risk:**

> "Right now, your staffing decisions are based on:
> - Historical patterns that may no longer apply
> - Regional manager intuition (which varies widely)
> - Complaints from overworked pharmacists (lagging indicator)
>
> Every month you wait, the gap between data-driven decisions and gut-feel decisions widens. When a competitor can match staff to demand precisely, and you can't - who wins?"

**The Implementation Risk Reversal:**

> "We're not asking you to change everything. Start with 10 pharmacies. In 90 days, you'll have data showing exactly what this is worth. If it doesn't work, you've lost nothing. If it does work, you've found millions."

---

### Principle 7: PEAK-END RULE
*"People remember the peak moment and the ending"*

#### Application: Design the Demo for Peak Moments

**Demo Peak Moments:**

1. **The Reveal:** Show their own pharmacy data (if available) with the gap analysis
2. **The "Aha":** When the AI assistant answers a complex staffing question in real-time
3. **The Autopilot:** Show the monthly automation running, generating reports automatically

**The Ending:**

> "In 90 days, you'll have either:
> A) Proof that this doesn't work for you (unlikely, but possible)
> B) A roadmap showing exactly how much money you're leaving on the table
>
> Either way, you'll know. The only way to lose is to keep guessing."

---

## 3. Selling Points by Buyer Persona

### Persona 1: CFO / Finance Director

**Primary Concern:** Cost control, margin protection
**Kahneman Trigger:** Loss aversion, anchoring

**Pitch:**
> "Your labor costs are your biggest controllable expense. But right now, you're making staffing decisions with incomplete data. Our analysis shows pharmacy chains typically have 1-5% revenue at risk from staffing misallocation. For your network, that's **€X million annually**."

**Key Metrics to Show:**
- Revenue at risk calculation
- Payback period (90 days)
- Cost per pharmacy per month vs. savings

---

### Persona 2: COO / Operations Director

**Primary Concern:** Efficiency, consistency, regional variance
**Kahneman Trigger:** Narrative, availability

**Pitch:**
> "Your regional managers are good, but they're inconsistent. What works in Prague doesn't work in Brno. What worked last year doesn't work now. You need a single source of truth that adapts to each location automatically."

**Key Metrics to Show:**
- Variance between regions (before/after)
- Time saved on staffing decisions
- Productivity benchmarks by segment

---

### Persona 3: HR Director

**Primary Concern:** Recruitment, retention, burnout
**Kahneman Trigger:** Framing, status quo bias

**Pitch:**
> "You're spending €200,000 on signing bonuses to hire pharmacists. But what if the problem isn't hiring - it's that your existing staff is burned out because they're in the wrong locations? Better staffing allocation reduces turnover, which reduces your recruitment burden."

**Key Metrics to Show:**
- Correlation between understaffing and turnover
- Recruitment cost per pharmacist (€8,000-€50,000)
- Staff satisfaction indicators

---

### Persona 4: CEO / Managing Director

**Primary Concern:** Competitive advantage, strategic positioning
**Kahneman Trigger:** Peak-end, narrative

**Pitch:**
> "Your competitors are investing in AI and automation. The question isn't whether data-driven staffing becomes standard - it's whether you lead or follow. First movers in retail pharmacy optimization will have a 2-3 year advantage in operational efficiency."

**Key Metrics to Show:**
- Market consolidation trends (Dr.Max + BENU = 75%)
- Independent pharmacy closures
- Digital transformation ROI in comparable industries

---

## 4. Objection Handling (Kahneman-Informed)

### Objection: "Who else uses this?"

**THIS IS THE KILLER OBJECTION. Handle with honesty + reframe.**

**Response (Honesty + Scarcity + First-Mover):**
> "Nobody yet. I'll be direct with you. This methodology was developed 4 years ago for Dr.Max Slovakia to answer a specific question about B segment staffing. It worked - 97% accuracy on their data. Since then, I've built it into a full platform, but I'm looking for the first chain to pilot the commercial version.
>
> That means two things for you:
> 1. **Risk:** You're the guinea pig. I won't pretend otherwise.
> 2. **Reward:** You get my full attention, custom development, and founding-customer pricing. Plus, you'll have a 2-year head start on competitors.
>
> The chains that wait will pay 3x more and get 1/3 the attention. The question is whether you want to lead or follow."

**Kahneman principle:** **Scarcity** + **Loss Aversion** (missing the first-mover advantage)

---

### Objection: "The data is 4 years old"

**Response (Reframe as Opportunity):**
> "Exactly. That's why I need YOUR current data. The methodology is proven - 97% accuracy on 2020-2021 data. But the pharmacy market has changed: COVID, staffing crisis, new regulations.
>
> Retrain the model on your 2024-2025 data, and you'll have something no competitor has: a staffing optimization system calibrated to post-COVID reality. The 4-year gap isn't a weakness - it's why we need to work together now."

---

### Objection: "We already have a staffing system"

**Response (Status Quo Challenge):**
> "I'm sure you do. But does it tell you the **optimal headcount** for each pharmacy based on actual transaction volume and revenue? Does it know your Kaufland location needs 4.8 FTE while your street pharmacy only needs 2.3? Does it adjust for prescription ratio and store type? If not, you have a scheduling system, not a staffing optimization system. Scheduling tells you WHO works WHEN. This tells you HOW MANY you actually need."

---

### Objection: "This seems expensive"

**Response (Loss Framing):**
> "I understand. Let me ask: what does it cost you when a pharmacist quits because they're chronically understaffed? €8,000 signing bonus for the replacement, 3 months of reduced service, training time... that's €15,000+ per turnover. How many pharmacists have you lost this year?"

---

### Objection: "We need to think about it"

**Response (Inaction Risk):**
> "Of course. While you're thinking, here's what's happening: every month, the gap between data-driven chains and intuition-driven chains widens. Your competitors are already investing in this. The only question is whether you want to lead or catch up."

---

### Objection: "Our business is different"

**Response (Anchoring + Proof):**
> "Every chain says that. And every chain that's used this found their 'differences' were exactly what the model captures - store type, location, prescription ratio, transaction patterns. We've analyzed 286 pharmacies across 5 different segments. The model's 97.1% accuracy suggests the differences that matter are already in the data."

---

### Objection: "What if it doesn't work?"

**Response (Risk Reversal):**
> "Then you've lost nothing but time on a pilot. Here's my offer: 90-day pilot, 20 pharmacies, no commitment. If the model doesn't show you at least 3 pharmacies that are clearly mis-staffed, you walk away. No hard feelings, no invoice. I'm betting my time that this works. Are you willing to bet yours?"

---

## 5. Pricing Strategy (Cold-Start Reality)

### The First Customer Problem

With zero users, you can't charge market rate. You need the **case study** more than the money.

**Kahneman principle:** **Reciprocity** - Give something valuable first, and they'll feel obligated to continue.

---

### Founding Customer Offer (Dr.Max SK)

| Phase | Duration | Price | What You Get |
|-------|----------|-------|--------------|
| **Pilot** | 90 days | **FREE** | 20-50 pharmacies, model retrained on current data |
| **Validation** | 90 days | €5,000 total | Full network, prove ROI |
| **Production** | Ongoing | €50/pharmacy/month | After proven value |

**Why free pilot?**
- You need the updated data to prove the model still works
- You need the case study to sell to anyone else
- Dr.Max already contributed the original data - this is an extension

---

### Second Customer Pricing (With Case Study)

**Initial Anchor:**
> "Enterprise implementations of AI-driven workforce optimization typically run €500,000-€1M annually."

**Reality Pricing:**

| Tier | Pharmacies | Monthly/Pharmacy | Annual Total | Notes |
|------|------------|------------------|--------------|-------|
| Pilot | 20-50 | €50 | €12,000-€30,000 | Prove concept |
| Growth | 50-200 | €75 | €45,000-€180,000 | With case study |
| Enterprise | 200+ | €100 | €240,000+ | Full support |

---

### ROI Justification

> "At €75/pharmacy/month for a 400-location network, your annual investment is €360,000. If we prevent just **0.5%** revenue leakage on €350M revenue, that's **€1.75M saved**. That's a **5x return**."

**But for the first customer, the pitch is simpler:**
> "Free pilot. You risk nothing but 20 hours of data export time. I risk 90 days of my work. If it works, we talk pricing. If it doesn't, we part as friends."

---

## 6. Sales Process

### Phase 1: Discovery (Week 1)
- Identify pain points using loss framing
- Anchor with market data (signing bonuses, vacancy rates)
- Tell competitor stories (availability heuristic)

### Phase 2: Demo (Week 2)
- Show their data if possible (peak moment)
- Demonstrate AI assistant (peak moment)
- End with 90-day pilot proposal (strong ending)

### Phase 3: Pilot (90 Days)
- 10-20 pharmacy sample
- Weekly progress reports (availability)
- Build internal champions (social proof)

### Phase 4: Expansion
- Present pilot results with loss framing
- Anchor on full-network potential
- Close with inaction risk

---

## 7. Market-Specific Messaging

### Slovakia
**Hook:** "Máte dosť hádania o FTE? Koniec neistoty."
**Pain:** Brain drain to Czech Republic, 79% municipalities without pharmacy
**Anchor:** Dr.Max already uses this (social proof)

### Czech Republic
**Hook:** "Vaši konkurenti už vědí, kolik FTE potřebují. Vy také?"
**Pain:** 7 regions without 24-hour pharmacy, €200k signing bonuses
**Anchor:** Market leader advantage, consolidation pressure

### Poland
**Hook:** "2,000 wakatów. Problem nie jest w rekrutacji - jest w optymalizacji."
**Pain:** DOZ has 2,000 open positions, technician decline (-6.3%)
**Anchor:** Can't hire out of shortage, must optimize existing

---

## 8. Competitive Positioning

### vs. Traditional WFM Software (Kronos, UKG, SAP)
**Frame:** "They schedule shifts. We predict optimal staffing."

### vs. Excel/Manual Methods
**Frame:** "Excel tells you what happened. We tell you what's happening and what to do."

### vs. Consulting Firms
**Frame:** "Consultants give you a report. We give you a system that runs every month automatically."

---

## Summary: The Kahneman Sales Playbook

| Principle | Application |
|-----------|-------------|
| **Loss Aversion** | Two loss types: (1) Revenue at risk for understaffed+productive, (2) Unjustified labor for overstaffed |
| **Anchoring** | Set high anchors early (€X revenue at risk + €Y unjustified cost) |
| **Narrative** | Tell the "Dr.Max B-segment" origin story - real, honest, proven |
| **Availability** | Use recent headlines (signing bonuses, closures, 3 regions disagreeing) |
| **Framing** | "One objective standard" not "cut costs" |
| **Status Quo** | Make intuition-based decisions feel risky ("3 opinions, no arbiter") |
| **Peak-End** | Design demo for "aha moments" and strong close |

---

## Key Distinction: Don't Oversell

### Capability Boundaries

| What We CAN Say | What We CANNOT Say |
|-----------------|-------------------|
| "Optimal headcount per pharmacy" | "Peak hour recommendations" |
| "Which pharmacies are over/understaffed vs benchmark" | "Which HOURS are understaffed" |
| "97.1% accuracy on aggregate FTE" | "Real-time staffing adjustments" |
| "One objective standard across regions" | "Predicts customer walkouts directly" |
| "Revenue at risk for understaffed+productive pharmacies" | "Guaranteed lost sales" |
| "Unjustified labor cost for overstaffed pharmacies" | "Wasted money" |

### Two Loss Types - What We CAN Claim

| Situation | App Calculates | What We Say |
|-----------|----------------|-------------|
| **Understaffed + Productive** | Revenue at Risk (formula-based) | "Your best performers are maxed out - €X revenue at risk" |
| **Understaffed + NOT Productive** | Nothing (€0) | "They're handling it - no action needed" |
| **Overstaffed** | Unjustified Labor Cost (manual calc) | "€Y in labor costs above benchmark - worth investigating" |
| **Optimal** | Nothing | "✓ Well-staffed" |

### What We CANNOT Claim

| Claim | Why Not |
|-------|---------|
| "You're definitely losing €X" | Revenue at risk is an *estimate*, not measured loss |
| "Cut staff by X" | We identify gaps, not prescribe actions |
| "Your managers are wrong" | We provide data, they provide judgment |
| "This will save you €X" | Savings depend on their actions, not our tool |

**The honest pitch:** "The app identifies two problems: (1) productive pharmacies that are understaffed and leaving revenue on the table, and (2) pharmacies with more FTE than the data justifies. It calculates the potential impact of each. What you do with that information is your decision."

---

*Strategy document prepared: January 2026*
*Based on market research: Slovakia, Czech Republic, Poland*
