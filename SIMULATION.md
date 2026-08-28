# Agent Simulation: Loan-Pricing Partner

5 messy phone-scribble deal notes. Each shows agent turns with
real tool results, following the conversation discipline.

---

## Q1: "Duplex in Towson. 700 credit, one flip before. Wants to refi his other property too. What's the play?"

**Turn 1** — Clarify product + priority

```
Tools: get_lender_profile(any), scenario_details("Baltimore")
```

Towson is Baltimore metro. Baltimore scenario triggers:
- 5% LTV/LTC haircut, no appraisal transfers, fee simple required
- Constructive, CV3, Conventus, Gradient handle it

**Synthesize**:

"Towson falls under Baltimore restrictions — expect a 5% LTV haircut and rate adders. Two questions:

1. Is the Towson duplex a buy-and-hold (DSCR) or a flip? You mentioned one prior flip so I'm guessing fix-and-flip.
2. The refi on his other property — is that a separate deal or does he want to do both with one lender?"

---

**Turn 2** — Route the fix-and-flip after user says "flip the duplex, refi the other separately"

```
Tools: find_lenders("700 FICO, 1 prior flip, Towson fix and flip")
```

Learnings:
- Baltimore scenario applies (see above)
- 700 FICO hits most lender minimums
- 1 flip experience is low but some lenders take it

Top suggestions:
1. **Constructive** — 700 FICO meets ≥700, 1+ required, Baltimore OK (with haircut)
2. **CV3** — handles Baltimore, 1 flip borderline
3. **Conventus** — "Not really doing Baltimore right now" per CS sheet

For the refi on the other property, similar lenders can handle both.

**Synthesize**:

"Flip side: Constructive and CV3 both work in Towson. Constructive is your best bet — their fico_min is 700 right on your number, and they accept 1+ flip experience. Expect 5% LTV haircut and extra appraisal restrictions for Baltimore.

For the separate refi on the other property — same lender or different? If different, I can check DSCR lenders separately. Want me to pull Constructive's full pricing?"

---

## Q2: "$2m light rehab in Phoenix. 640 FICO but four long-term rentals. Need 80 cents on the dollar."

**Turn 1** — Disambiguate "80 cents on the dollar" + check $2M capacity

```
Tools: find_lenders("640 FICO, light rehab, fix and flip, Phoenix"),
       get_lender_profile(top_lenders, "fix_and_flip") → check loan_max
```

"80 cents on the dollar" usually means 80% LTV/ARV (not LTC). $2M is large.

Findings:
- 640 FICO hits Groundfloor (640) and Finance of America (620)
- But top-scoring lenders at 640 have loan_max issues:
  - Groundfloor: max ~$1.5M (no explicit loan_max, but product caps)
  - Finance of America: $3M ✓
  - CV3: $5M ✓ but requires 700 FICO
- Four rentals as experience helps but lenders measure experience different ways

**Synthesize**:

"Clarifying: when you say '80 cents on the dollar' — is that 80% of ARV after rehab or 80% of purchase price? Makes a big difference.

For $2M at 640 FICO with experience: **Finance of America** looks like the best fit — they floor at 620 FICO, go to $3M, and take experience into account. Would you like me to pull their full terms and check if they count rental history as deal experience?"

---

## Q3: "Got 11.5% with 2pts, 10.75% with 3pts, and 9.99% with 30% down. Tell me if these are good."

**Turn 1** — Refuse to answer without deal context

```
Tools: none
```

**Synthesize**:

"I can't tell you if those rates are good without the deal details. Rates mean nothing without:
- **Product**: fix-and-flip, DSCR, bridge?
- **FICO**: 680 vs 740 changes pricing by 200+ bps
- **LTV/LTC**: 70% vs 80% changes risk tier
- **Property type**: SFR vs multifamily vs commercial
- **Loan amount**: smaller loans get worse pricing

Can you give me the deal context? Best way: tell me what you're buying, what the borrower looks like, and how much you're borrowing. I'll run the real numbers against 145 lenders."

---

## Q4: "Cleveland triplex. 600 FICO, never done this, $180k. Everyone says no. Anyone?"

**Turn 1** — Check Cleveland restrictions + 600 FICO + 2-4 unit + no experience

```
Tools: find_lenders("600 FICO Cleveland fix and flip"),
       find_lenders("600 FICO, no experience, fix and flip"),
       check_criteria("Hard Money Co", "fix_and_flip", {fico: 600})
```

Learnings:
- Cleveland has no explicit city restrictions scenario (unlike Baltimore)
- **Only 1 lender** takes 600 FICO: Hard Money Co (fico_min=590)
- Hard Money Co: Nationwide except HI/AK/LA, does 2-4 units, no strict experience minimum
- All other lenders minimum is 620+

**Synthesize**:

"Brutal combo. 600 FICO + zero experience is the hardest ask in this market.

The honest answer: **Hard Money Co** is the only lender I can find who'll touch 600 FICO. They do 2-4 units and don't seem to have a strict experience floor. But expect tough terms — high rate, low LTV.

To improve your odds:
1. If you can get the borrower to 620 FICO, your options triple
2. Find someone with any applicable experience (GC license, RE agent, etc.)
3. Lower the ask — at 600/0 experience you're probably at 65-70% LTV, not 80

Want me to pull Hard Money Co's full terms, or explore what changes unlock more lenders?"

---

## Q5: "Best rates investment cash-out refi. Six Texas properties, all 720+ FICO."

**Turn 1** — Confirm product + structure

```
Tools: find_lenders("720 FICO, Texas, cash-out refi"),
       get_fico_ltv_tiers("Conventus", "sfr_dscr"),
       estimate_pricing("Conventus", "sfr_dscr", ltv=75, fico=720)
```

Findings:
- DSCR cash-out is the right product (investment, not owner-occupied)
- Six properties = blanket loan candidate or individual
- 720+ FICO is strong across all lenders
- Texas has no state restrictions in the data

Rate comparison at 720/75% LTV (top contenders):

| Lender | Floor Rate | FICO Tier |
|--------|-----------|-----------|
| Conventus | 5.75% | 680+ |
| Kiavi | 7.35% | 680+ |
| Constructive | 6.125% | 700+ (cash-out) |
| ROC Capital | 7.5% | 740+ |

**Synthesize**:

"Strong deal on paper. At 720+ FICO you're in the top tier at most lenders.

Two questions before I quote:
1. **One blanket loan or six individual?** Blanket narrows options (ROC Capital, Corevest do them). Individual opens up more.
2. **What are the DSCRs?** At investment cash-out, DSCR matters more than FICO. 1.0+ is table stakes, 1.2+ gets best pricing.

Early read: **Conventive** (5.75% floor) and **Constructive** (6.125% floor) lead on rate for individual loans. If blanket, check ROC Capital. Want me to deep-dive one path?"
