# Productivity Metrics Explained

## The Current Metric: bloky/hod

Most pharmacy managers use **bloky/hod** (transactions per hour) as their main performance metric:

```
bloky/hod = annual_transactions / operating_hours
          = bloky / 3000
```

This tells you: **How busy is the pharmacy?**

---

## The Problem: No Normalization

Comparing bloky/hod across pharmacies is like comparing:

> "Factory A produces 1000 widgets/day"
> "Factory B produces 500 widgets/day"
> Conclusion: Factory A is better?

But what if:
- Factory A has 100 workers → 10 widgets/worker/day
- Factory B has 25 workers → 20 widgets/worker/day

**Factory B is actually 2x more efficient!**

### Real Example from the Network

| Pharmacy | bloky/hod | FTE | produktivita |
|----------|-----------|-----|--------------|
| ID 29 (Nitra, Kaufland) | 57 | 10.8 | 7.6 |
| ID 552 | 18 | 1.5 | 12.0 |

- Pharmacy 29: "Best" by bloky/hod (57 txns/hour)
- Pharmacy 552: "Worst" by bloky/hod (18 txns/hour)

**Reality**: Pharmacy 552 is 58% MORE PRODUCTIVE per person!

---

## The Normalized Metric: produktivita

```
produktivita = bloky/hod ÷ staff_on_duty
             = bloky / (FTE × 2080)
```

Where:
- `bloky` = annual transactions
- `FTE` = full-time equivalent staff (pharmacists + non-pharmacists)
- `2080` = annual working hours per FTE (40 hrs × 52 weeks)

This tells you: **How busy is each person?**

### Interpretation

| produktivita | Meaning |
|--------------|---------|
| ~6-7 | Comfortable workload |
| ~8-9 | Normal workload |
| ~10-11 | Above average (efficient or stretched) |
| >11 | **Likely understaffed** |

---

## What is Normalization?

**Normalization = adjusting for size differences to enable fair comparison**

| Raw Metric | Normalized Metric |
|------------|-------------------|
| Revenue | Revenue per employee |
| GDP | GDP per capita |
| Goals scored | Goals per game |
| **bloky/hod** | **bloky/hod per FTE (produktivita)** |

### Without Normalization: Misleading Conclusions

```
bloky/hod ranking:
  #1  Pharmacy 29:  57 txns/hour  ← "Best performer!"
  ...
  #286 Pharmacy 552: 18 txns/hour ← "Worst performer!"
```

### With Normalization: True Picture

```
produktivita ranking:
  Pharmacy 29:  57 ÷ 10.8 FTE = 7.6 txns/person/hour (comfortable)
  Pharmacy 552: 18 ÷ 1.5 FTE  = 12.0 txns/person/hour (stretched!)
```

---

## Two Pharmacies, Same Traffic, Different Story

| Metric | Pharmacy 196 | Pharmacy 298 |
|--------|--------------|--------------|
| bloky/hod | 34 | 36 |
| FTE | 7.3 | 4.3 |
| produktivita | 6.7 | 11.9 |

Same traffic (~35 txns/hour), but:
- **Pharmacy 196**: 7.3 staff → 6.7 txns/person/hour (comfortable)
- **Pharmacy 298**: 4.3 staff → 11.9 txns/person/hour (stretched!)

**Which pharmacy needs help? Pharmacy 298.**

bloky/hod alone cannot identify this.

---

## The Key Insight

| Metric | What it Measures | Limitation |
|--------|------------------|------------|
| **bloky/hod** | Pharmacy traffic (demand) | Big pharmacies always "win" |
| **produktivita** | Workload per person (efficiency) | Fair comparison across all sizes |

### One-Liner

> **"bloky/hod tells you the pharmacy is busy.**
> **bloky/hod per FTE tells you if the PEOPLE are busy."**

---

## What the App Adds Beyond produktivita

Even with produktivita, you still cannot answer:

| Question | produktivita | App |
|----------|--------------|-----|
| Is this pharmacy busy? | ✓ | ✓ |
| Is staff stretched? | ✓ | ✓ |
| How many FTE should it have? | ✗ | ✓ **7.7 FTE** |
| How many FTE to add? | ✗ | ✓ **+0.7 FTE** |
| Which role to add? | ✗ | ✓ **+0.5L, +0.2F** |
| What's the ROI? | ✗ | ✓ **€52k/year** |
| Which pharmacy to prioritize? | ✗ | ✓ **#3 of 94** |

### Why Not Just "If produktivita > 9, Add Staff"?

Simple thresholds don't work because:

1. **Segment matters**:
   - A-shopping premium avg: 6.4
   - B-shopping avg: 8.4
   - D-street avg: 5.8
   - produktivita=7 is HIGH for A-premium, LOW for B-shopping

2. **Rx ratio matters**:
   - High Rx pharmacy needs more time per transaction
   - Same bloky/hod requires more staff

3. **No specific action**:
   - How much FTE to add?
   - Which role (F, L, ZF)?

---

## The ML Model's Job

The model takes multiple inputs:
- bloky (transaction volume)
- podiel_rx (Rx ratio - affects time per transaction)
- typ (segment - different workload patterns)
- zastup (substitution rate)
- bloky_trend (growth trend)

And outputs:
- **Exact FTE needed**: 7.7
- **By role**: 2.5F + 3.0L + 1.0ZF
- **Gap**: +0.7 FTE
- **Revenue at risk**: €52k

---

## Summary for Stakeholders

| Level | Metric | Insight |
|-------|--------|---------|
| Current | bloky/hod | "This pharmacy is busy" |
| Better | produktivita (bloky/hod ÷ FTE) | "The staff is stretched" |
| **App** | ML prediction + RAR | "Add +0.7 FTE (+0.5L, +0.2F) to recover €52k/year. Priority: #3 of 94." |

### The App's Value Proposition

> **"bloky/hod tells you a pharmacy is busy.**
> **The app tells you WHAT TO DO about it."**

---

## Segment Averages (Reference)

| Segment | Avg bloky/hod | Avg produktivita |
|---------|---------------|------------------|
| A - shopping premium | 30 | 6.4 |
| B - shopping | 33 | 8.4 |
| C - street + | 13 | 6.0 |
| D - street | 11 | 5.8 |
| E - poliklinika | 15 | 5.3 |

Note: B-shopping has both high traffic AND high productivity because these pharmacies typically run leaner operations.
