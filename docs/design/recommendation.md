# The recommendation — what the system is willing to say about a deal

**Written Sept 1, 2026, at U9.4.** Section numbers (§1–§9) and decision numbers (#1–#21)
refer to [`../implementation_plan.md`](../implementation_plan.md).

**Until U9.4 this system never said whether a property was worth buying.** It said whether
it could stand behind its own numbers — `reports` or `escalates` — and readers took that
for the other question. On `staten-island` the two answers are opposites: the deal
escalates because no comparables were found, while asking **17% below its ZIP median**. A
banner reading *"🚩 Escalated to human review"* on a deal priced below its market is the
report telling a reader the reverse of what the evidence says.

So the report now carries **two axes, rendered as two lines that never merge**:

| | Question | Field | What it is a statement about |
| --- | --- | --- | --- |
| **1** | Can the system stand behind its own numbers? | `needs_human_review` | the **software** |
| **2** | Is this a good deal? | `recommendation` | the **property** |

This document is the evidence and the design behind axis 2.

---

## 1. The measurement, because the threshold had nothing under it

The rule reads the asking price against `ValuationDetail.benchmark_median_sale_price` and
has to decide where *"priced materially above comparable sales"* begins. Nothing in this
repository said what a premium was worth. The committed table
(`tools/data/zip_sale_benchmarks.json`) holds **one median per ZIP and no dispersion at
all**, so a threshold read off it would have been read off nothing — the same defect #21
was adopted to fix on the rent side, where a correlation was asserted once and never
re-measured.

`scripts/sale_premium_distribution.py` re-pulls the individual sales behind those medians
— NYC `w2pb-icbu` and Cook `wvhk-k5uv` joined to `nj4t-kc8j`, over
`config.SALE_BENCHMARK_WINDOW_START` and through the publishers' own arm's-length screens.
The filters are **imported from `scripts/build_sale_benchmarks.py` rather than restated**,
so "a qualifying sale" has one definition; that import is why the two fetchers now return
per-sale prices and `main()` reduces them.

It asks the only question that can place a threshold on evidence: **among sales that
actually happened, what share cleared their own benchmark by X%?**

### ZIP tier — 44,358 sales across 222 ZIPs

| premium | +15% | +20% | +30% | +40% | +50% | +55% | +75% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| percentile of actual sales at or below | 68% | 72% | **80%** | 85% | **89%** | 91% | 95% |

Read the other way — the column a threshold is set from:

| percentile | p75 | p80 | p85 | p90 | p95 |
| --- | --- | --- | --- | --- | --- |
| **pooled** | +23% | **+30%** | +39% | **+52%** | +76% |
| New York | +20% | +26% | +34% | +44% | +64% |
| Chicago | +29% | +38% | +49% | +66% | +95% |

**The dispersion is wide but not so wide that nothing can be said**, which was the outcome
this measurement was run to rule out. A 15% premium is the 68th percentile of real
transactions — an ordinary sale, and calling it material would be false. A 50% premium is
the 89th. That is a claim the data supports.

Two markets, measured separately, agree closely, and **weighting every ZIP equally instead
of pooling moves nothing below +30%** (pooled 79.8% against 82.6% per-ZIP at +30%) — so
the pooled figure is describing a market rather than a few dense ZIPs. Above +40% the
pooled number runs lower than the per-ZIP median, meaning dense ZIPs carry slightly fatter
right tails; it does not move where the thresholds land.

### Metro tier — roughly twice as wide, and the two markets disagree

| percentile | p75 | p80 | p85 | p90 | p95 |
| --- | --- | --- | --- | --- | --- |
| New York | +39% | +52% | +68% | +97% | +168% |
| Chicago | +52% | +67% | +88% | +117% | +183% |

A metro median describes properties an hour apart with one number, so the spread around it
is mostly geography. **Los Angeles is absent from this measurement entirely** — California
publishes assessed value under Proposition 13, not transaction price, which is why it has
no local tier in the first place — so every metro-tier figure this project uses is
extrapolated from two other cities.

### What the measurement does *not* say

The spread is driven mostly by **what was sold**, not by what anyone overpaid: the
benchmark carries no adjustment for square footage, unit count, condition or block, which
is the caveat `agents/summarizer._benchmark_section` prints in bold under every figure. A
premium's percentile answers *"how rare is a price this far above the local median"* and
never *"how far above fair value is this property"*. **That is the weaker of the two claims
and it is the only one the recommendation makes.**

---

## 2. What the measurement changed

**The worked example U9.4 was planned around was wrong on both halves.** The plan read:
*"asking price 55% above the ZIP benchmark → exceeds threshold."* The `overpriced` demo
deal is `1801 N Vermont Ave, Los Angeles` and **90027 has no ZIP benchmark** — LA reads the
metro tier — so its `price_premium_to_basis = 0.55` is 55% above a *metro* median, which
this measurement places at roughly the **78th percentile of actual sales**. An ordinary
transaction. A rule honest to the evidence returns *Proceed* on the deal named
`overpriced`.

**Resolved by re-siting the deal, not by bending the threshold** (architect, Sept 1, 2026).
`overpriced` moves to a market with a local tier, where +55% is genuinely around the 90th
percentile and the threshold it trips was measured in that market rather than extrapolated
into it. It is now **4700 N Racine Ave, Chicago 60640** — Uptown, asking $1,345,000 against
that ZIP's $867,500 median over 148 recorded sales.

**Uptown rather than Logan Square, and the choice was made by running both.** Both have a
local tier and Logan Square's is deeper (709 sales). But Logan Square's comp set relaxes
the size band, which raises a critical objection and escalates the deal — so the report
showed a cautionary recommendation beside an escalation, and a reader could not tell which
of the two the asking price had caused. Uptown returns eight matching comps and reports at
confidence **1.00**, exactly as the `chicago-uptown-duplex` control does on the same
property profile. **The asking price is then the only thing that fires anywhere in the
report**, which is what this fixture exists to demonstrate.

The alternatives were considered and declined:

- **Abstain on price wherever only a metro benchmark exists.** The most literal reading of
  the measurement, and closest to #15 and #20. Declined because it silences the price axis
  on both Los Angeles demo deals, including the clean flagship one.
- **Keep the fixture and accept *Proceed* on `overpriced`.** Correct on the evidence and
  free. Declined because a deal documented as *"deliberately mispriced"* reporting *Proceed*
  reads as a defect to anyone watching the recording, whatever the report says beneath it.
- **Raise the LA premium to ~+120%** to clear the extrapolated metro p90. Declined: a 2-unit
  listing asking 120% over its metro median is a less believable synthetic listing, and the
  threshold it trips is still extrapolated.

---

## 3. The rule

**Deterministic, and the reason is measured rather than stylistic.** OQ-17 found this
model scoring an identical prompt 0.05 on one call and 0.95 on the next, same deployment,
`temperature=0`. A recommendation behind that would make the same deal *proceed* on Tuesday
and *do not proceed* on Wednesday with nothing able to explain why, and it would create a
second axis the eval harness cannot score. **"Agentic" is not "stochastic"** — the Critic's
escalate decision is already a pure function, and it is what makes this system autonomous
rather than advisory.

It lives in `agents/critic.py` because that agent already aggregates flags into confidence
and decides routing; a recommendation is the same kind of judgment over the same state, and
putting it there keeps the Summarizer's rule that it **reports rather than computes**.

### Four verdicts, and every one of them is reachable

| Verdict | When |
| --- | --- |
| **No recommendation** | no asking price, or no sale benchmark of any tier |
| **Do not proceed** | premium ≥ the reject threshold **and** the rent claim is uncorroborated |
| **Proceed with caution** | premium ≥ the caution threshold |
| **Proceed** | neither |

**Reject needs two independent things to be true, and that is the design rather than
caution about the vocabulary.** A premium on its own is a fact about price; a premium the
income does not support is a fact about the deal. The benchmark is explicitly not a
valuation — the report says so in bold — so resting an outright rejection on that single
figure would contradict the caveat printed beside it. Requiring the rent side to fail too
means the verdict rests on two instruments that fail independently.

**The price finding is the only thing that can start a verdict; the rent side only ever
modifies one.** This was drafted the other way — uncorroborated rent reaching caution on
its own — and `staten-island` showed why that is wrong. Whether the comp cross-check could
run is largely a fact about *data coverage in this market*, which is why `state.scope_of`
classifies the sparse-comp disclosure as market-scoped. Letting it reach a verdict alone
puts an axis-1 observation on the axis-2 line. Staten Island has zero comparables and asks
**17% below its ZIP median**; under the first draft the report said *proceed with caution*
about a deal whose only measured fact is that it is cheap — which is the misreading the
escalation banner already produced, reintroduced one line lower. It now reports **Proceed**
on axis 2 and **escalated** on axis 1, and the distance between those two lines is the
point.

*"The rent claim is uncorroborated"* means the comp cross-check could not confirm it —
either it never ran (fewer than `config.RENT_COMP_CROSSCHECK_MIN_COMPS` surviving comps) or
it ran and diverged. **Those are deliberately one outcome here** though they are two
elsewhere: the rule asks whether independent local evidence supports the rent, and "no
evidence" and "evidence that disagrees" are both *not support*. The report distinguishes
them in the disclosures, where the difference is actionable. The rule reads neither the
confidence score nor the escalation decision, for the reason above.

### The thresholds, and which tier they apply to

Set at stated percentiles of the distribution in §1 rather than at round numbers, so the
report can say what a threshold *means* rather than only what it is:

| | ZIP tier | metro tier |
| --- | --- | --- |
| **caution** | p80 → **+30%** | p80 → **+67%** |
| **reject** | p90 → **+52%** | p90 → **+117%** |

**The metro-tier pair is the more conservative of the two measured markets, and it is
extrapolated.** Chicago's metro dispersion is wider than New York's at every percentile, so
its numbers are the ones taken: a threshold set from the narrower market would call
ordinary Chicago sales unusual. Los Angeles is not in the measurement at all, so its
figures rest on the assumption that LA's metro dispersion resembles Chicago's — **an
assumption, labelled as one**, and the reason the report names which tier it read.

---

## 4. The cross-check: the model proposes, the rule decides

**Adopted Aug 31, 2026 after establishing that this system has only one reasoning locus**
(OQ-22): the forecast's search is the only place a model exercises judgment, since #12's
Critic half was retired on evidence at U7.7. This is the cheapest place to add a second,
and it lands where the reader is actually looking.

The model produces **its own independent verdict from the same state**, used only as a
cross-check:

- **The report shows the rule's verdict, always.**
- On disagreement it adds a line saying an independent review of the same evidence reached
  a different conclusion, that the verdict follows the system's stated rule, and that the
  disagreement is **disclosed rather than resolved**.

**The disagreement is the product.** A deal where both agree is more trustworthy than one
where they split, and the reader learns which they are holding. **Reproducibility is
untouched** — the rule always decides, so the model can never move a verdict, only annotate
it. That is what makes this safe against OQ-17 where a model-decides design would not be.

---

## 5. Open

- **The metro-tier thresholds are extrapolated**, and Los Angeles — the market they are
  most often applied to — is the one market that cannot be measured from assessor data.
  Closing it needs a transaction-price source for California.
- **The premium's percentile is not a valuation.** Closing the gap between *"rare"* and
  *"overpriced"* needs size, unit count and condition on the comparable sales, which no
  source in this project carries. §7's public-records item is where that would land.
- **Gross rent multiplier (U9.8)** is the one investor-facing ratio this project's data can
  support without new sources, and it is the non-circular one: the demo deals' prices are
  calibrated to Redfin medians and their rents to the rent anchor **independently**, so
  their ratio is not calibrated by construction the way each side separately is.
