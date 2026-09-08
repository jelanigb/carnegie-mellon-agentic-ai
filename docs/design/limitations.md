# Limitations, disclosures and next steps

**What this document is:** the honest accounting of what this system cannot do, written
for a reader deciding how far to trust its output. It is not exhaustive — it is the set of
gaps large enough that a reader who did not know about them would draw a wrong conclusion.

This is a seven-week capstone build, not a production system. The gaps below are disclosed
deliberately rather than hidden, and most of them are disclosed *by the system itself*, in
the report, on the runs where they apply — that is what the project means by **Transparent
Degradation**. What this document adds is the measurement behind each one and what closing
it would take.

Every figure quoted here re-derives from a script in `src/scripts/`, named at the point it
is used.

---

## 1. The rent model has never seen a market outside its training set, and transfer costs about 13%

Leave-one-metro-out validation (`scripts/lomo_validation.py`) holds each of the nine
training metros out entirely and scores it with a model fit on the other eight:
**$512/mo pooled, against the $452 the cross-validated figure reports.** The model still
beats a predict-the-average baseline in **all nine** held-out markets.

The figure the reports publish is the cross-validated one, and that is the correct figure
for this system — every market it indexes is in the training set. But it says nothing about
a market that is not, and the LOMO number is the upper bound for one. It is an upper bound
rather than an estimate because a fold that removes a large market also trains on far less
data: Los Angeles alone is 42% of the corpus.

**What closing it would take:** listings from the target market in the training corpus.
There is no modelling fix — the gap is coverage.

## 2. New York's elevated error is permanent, not a coverage gap

New York carries the largest per-market error — **$855/mo against ~$452 overall, 1.9×** —
and the report flags it on every New York deal. The natural reading is that more New York
listings would close it. **The same LOMO run shows they would not.**

Removing New York from training entirely moves its error from $855 to **$875 — 2%**. A market
whose error barely notices its own training data being deleted does not have an error that is
*about* training data.

**That 2% is a clean reading, and it is worth saying why**, because the same table's Los
Angeles row is not. Holding out a metro changes two things at once: the model has never seen
that market (the effect being measured) *and* the model trained on fewer rows (an artifact of
how the fold is built). New York is 5% of the corpus, so its fold still trains on **95%** of
the data and the 2% is almost purely transfer cost. Los Angeles is 42% of the corpus, so its
fold trains on **58%**, and its **19%** rise mixes transfer cost with having 2.4× less data to
learn from. **19% is therefore an upper bound on Los Angeles's transfer cost, not an estimate
of it**, and the true New York/Los Angeles contrast is smaller than those two figures suggest.
The New York conclusion does not rest on that contrast — it rests on 2% being small in
absolute terms — but the contrast should not be quoted as though both halves were measured the
same way.

What it is instead is **within-ZIP rent dispersion**: two apartments on the same block in
New York rent for amounts that bedrooms, bathrooms and floor area cannot tell apart, and
those three features are all this model has. So the flag is disclosed as a permanent
property of this feature set rather than as work outstanding.

**What closing it would take:** location-aware features below the ZIP — building age,
walk-up versus elevator, subway distance, sub-neighborhood — none of which are in the
corpus.

## 3. The comp corpus is a single 2017–2019 scrape

Retrieval runs over 3,880 listings across four metros, drawn from one historical scrape
(the UCI *Apartment for Rent Classified* dataset, donated December 2019). **No comparable
in any report is a current listing.** Two consequences:

- **Rent levels are bridged, not observed.** Every rent figure is normalized against a
  market rent index at the listing's own month and re-anchored to the subject's ZIP at
  today's index, so what the model carries forward is *how a property compares to its
  neighbors* rather than what anything cost in 2019. An unanchored dollar figure from this
  corpus never reaches the report — that is an architectural invariant, not a convention.
- **Comp density is fixed at 2019's.** A neighborhood that has been built out since then
  looks as thin as it was, and `staten-island` — six listings in the entire borough — is
  the demo deal that exists to show what that looks like in a report.

**What closing it would take:** a current listings feed. That is a licensing and cost
question rather than an engineering one, which is why it was not attempted inside a $100
budget.

## 4. Los Angeles has no ZIP-level sale benchmark, so its asking-price check is metro-wide

California publishes **assessed value** under Proposition 13 rather than sale price, so no
county-assessor sale medians exist for Los Angeles ZIPs. Chicago and New York deals are
benchmarked against their own ZIP's recorded sales; Los Angeles falls back to the Redfin
metro median, which describes a 2-unit duplex in Echo Park and a 4-unit building forty
miles away with one number.

This is not cosmetic. `scripts/sale_premium_distribution.py` measured what a premium
against a *metro* median is worth across 44,358 real sales: **55% over a metro median is
the 78th percentile — an ordinary transaction.** The same 55% against Uptown's own ZIP
median is around the 90th. A benchmark this coarse cannot call a price unusual, and the
report says which tier it used on every run.

## 5. The forecast's band pairing rests on a relationship weaker than the design assumed

The forecast projects rent growth and price growth as separate series, then pairs a rent
band with a price band. **The step that decides which pairings are plausible has no
directional rule behind it**, and that is a corrected belief rather than an original one.

Reading the sample reports partway through the build surfaced a real defect: the two series
were built by different methods over different windows, which showed up as implausible
pairings. That is fixed — rent growth now comes from the same market index the rent
estimate is anchored to, and both series are banded by one estimator over one span. What
the fix exposed is the deeper problem. Re-measured (`scripts/growth_correlation.py`), the
rent/price correlation **explains under a tenth of the variance in every pass (r² 0.04–0.10)
and changes sign by market** — and measured against market rent rather than the federal
schedule it is *positive*, the opposite sign to the one the original design was reasoned
from.

So the pairing step is disclosed as thin rather than presented as settled reasoning. Full
measurement in [`evaluator.md`](evaluator.md).

**Next step, already designed and deferred rather than open-ended:** re-purpose the search
to ask a question the evidence in the prompt can actually answer — *how far should this
forecast trust the rent estimate it compounds from?* A deal with eight comparables agreeing
within 1% projects from the point estimate; a deal with zero comparables projects from its
error band's edges, or declines the optimistic case. That needs no correlation at all,
which is what makes it survive the measurement above. It was deferred because it is a full
change set — the prompt's question, the candidate payload, the scenario assembly, two state
models and every recording. Written up in
[`forecast_starting_point_spike.md`](forecast_starting_point_spike.md).

## 6. "The same model" on OpenRouter is not one deployment

Live runs are not exactly reproducible, and the reason is routing rather than sampling.
OpenRouter serves a single model id from **multiple backend deployments**, chosen per
request — different hardware, different quantization, different inference stacks — so two
calls with identical text and `temperature=0` can land on different machines and return
different scores. Measured here at roughly **1 in 15–20 live attempts** on the forecast's
scenario-scoring step, which is where it matters most, since a score shift can reorder
which scenario pairings reach the table.

**This is why every published figure replays.** The evaluation harness's `golden` and
`replay` tiers and all three committed sample reports are served from recorded responses
and never call a model, so they are exact regardless. Reaching a live model takes an
explicit flag.

## 7. No cap rate or NOI — a refusal, not an omission

This project has no operating-expense data: no taxes, insurance, vacancy or maintenance. It
therefore does not estimate net operating income and **will not invent one.** What it
computes instead is the asking price against a market benchmark and a **gross rent
multiplier** — the one investor ratio this project's data supports — built on the modelled
rent rather than the listing's claimed rent, so it is available even on a listing that
states none.

The report says what it is refusing and why, rather than approximating a cap rate from
costs it does not have. An investor who needs a return figure needs a different input
dataset, not a different prompt.

## 8. Test coverage is deliberately scoped

Two suites are load-bearing and were never cut: `tests/test_flag_propagation.py` (a flag
raised in the Extractor must survive every downstream node and appear in the report) and
the `eval/` harness (30 cases, 30 of 30 flag kinds raised, verdict agreement 20/23 with
every mismatch triaged). Broad unit coverage was a deliberate cut against a seven-week
window, recorded as such in `implementation_plan.md` §8 — deferred, not dismissed.

---

## Next steps

Ordered by what would change the most about the system's output.

1. **Re-purpose the forecast search to the starting-point question** (§5 above). Designed,
   spiked, and deferred on schedule rather than on doubt — it is the one change that would
   replace a step currently resting on a measured-weak relationship.
2. **Incorporate operating-expense data** so the system can compute a real return metric
   rather than a gross rent multiplier (§7).
3. **Sample the forecast's scenario scoring multiple times and disclose the variance**,
   rather than taking one draw and disclosing that repeat runs vary (§6). This turns a
   known non-determinism into a reported error bar.
4. **Let a Tree-of-Thought choose which retrieval criterion to relax**, rather than the
   fixed ladder the comps agent walks today — which concedes radius, then size, then
   bedrooms, in an order that is the same for every deal regardless of which attribute
   actually matters to that property's rent. Tracked as `TODO(retrieval)` at the site.
5. **Expose the evaluation itself as an MCP capability**, so an external real-estate agent
   or another system could call this pipeline as a tool rather than run it as an app.
6. **Extend the rent model's feature set below the ZIP** (§2), which is the only route to
   New York's disclosed error.
