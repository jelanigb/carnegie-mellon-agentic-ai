# Demo Deals

**What this document is:** a plain-language guide to the eight synthetic listings the demo
runs on, and *why each one exists* — what it is built to show a reader, and what in the
system's output actually demonstrates it. Written so a reader doesn't have to reverse
that purpose out of `src/demo_deals.py` or `src/eval/cases.py` themselves.

**Scope.** This covers the eight `main.py --deal` listings plus the one ablation
run (`--no-retrieval`) that rides along with them. It does not walk through the 21
engineered fixtures in `src/eval/cases.py` (`la-ordinary-duplex`, `chicago-five-bedroom`,
and so on) — those exist to trip one specific flag apiece for the U8 evaluation harness,
are already documented case-by-case in that file's docstrings, and are a separate kind of
evidence from the demo (see "How the demo deals relate to the eval harness" below).
Started Aug 29, 2026, alongside U8.

**Brought back into line with the build on Sept 1, 2026 (U9.6), and the drift is worth
naming rather than quietly fixing.** Between U9.3 and U9.5 this document went four units
stale while continuing to read as current: it described `overpriced` as a Los Feliz
listing in Los Angeles (U9.4 re-sited it to Uptown, Chicago), reported `chicago` as
reporting normally (it escalates), and gave confidence scores and disclosure counts for
five of the six deals that no run produces. **None of that was visible from this file** —
every figure in it was true when written. Every number below is now transcribed from
`src/eval/results/results.md`, the committed table the harness regenerates, so the two
cannot drift apart silently again.

---

## Overview

The system evaluates small multi-family (2–4 unit) residential listings as investment
candidates. The demo deals (`src/demo_deals.py`) are eight synthetic listings, each run
independently with `.venv/bin/python main.py --deal <key>` from `src/`. They are not
random examples — each one is built to land on a different point of the system's
operating range, from "everything works cleanly" to "the system can't do part of its job
and says so."

That range exists on purpose. The project's central design principle is **Transparent
Degradation**: when an agent has to proceed on incomplete or relaxed information, it
raises a named flag rather than silently absorbing the gap, and those flags propagate
downstream to the final report. A demo that only ever showed the clean path would prove
the pipeline runs; it would not prove degradation is disclosed rather than hidden. The
deals together are what makes that second claim demonstrable.

**Every figure that can be anchored to something real, is.** The street address (and
therefore the geocode, county, and Fair Market Rent that county attracts) is real. Asking
prices are anchored to a recorded-sale benchmark — the subject's own ZIP where
county-assessor records reach it, the Redfin metro median otherwise. Stated rents are
anchored to one of two references, and **which one a listing declares is a statement
about its vintage** (U9.6): the four oldest deals name HUD's Fair Market Rent for the
resolved county, which is what decision #11 calibrated them against; the two newest name
the market rent index at the subject's own ZIP, which is what the system actually prices
against today (#19). The older four were deliberately left on the retired reference — see
`demo_deals.py` for why — and `los-angeles-current` exists to show the same property
under each. What's
invented is that the property is for sale at all, its condition, amenities, and the
specific numbers within a stated tolerance. `src/scripts/verify_demo_calibration.py`
re-derives each figure from live sources and reports drift, so the committed values stay
checkable rather than just asserted. Full reasoning in `demo_deals.py`'s module
docstring.

**Where the demo deals sit in the build.** They were originally U10 (a separate
end-to-end pass), folded into U8's eval harness on Aug 26, 2026 so the demo evidence and
the evaluation evidence come from one code path and can't disagree with each other — see
`eval/cases.py`'s `demo_cases()`. In that harness they're recorded as `BASELINE`
verdicts (a previously *measured* outcome, treated as a regression check) rather than
`PREDICTED` ones (a claim made before the run, which is what the harness's threshold
tuning is actually scored against) — see "How the demo deals relate to the eval harness"
below for why that distinction matters.

---

## How an outcome is decided: confidence and escalation

Every deal ends one of two ways: the Summarizer produces a normal report, or the Critic
routes the deal to `human_review` and pauses there. What decides which is worth knowing
before reading the deals below, because it's the mechanism each one is chosen to
exercise.

The Critic aggregates every flag raised anywhere in the pipeline into a single confidence
score, starting at 1.0 and subtracting a penalty per flag by severity
(`config.FLAG_SEVERITY_PENALTY`, **provisional, tuned in U8**):

| Severity | Penalty |
| --- | --- |
| `info` | 0.0 |
| `warn` | 0.15 |
| `critical` | 0.40 |

If the score falls below `config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD` (**0.60**,
provisional), the deal escalates. **But there are two further, independent grounds** —
a single critical flag escalates on its own however high the score, and a retryable
objection that survives the rework budget does the same. `chicago --no-retrieval` below
is the case that isolates the critical-flag rule from the score-based one; the eval
harness's `chicago-geocoder-outage` row isolates the rework-budget one. Mechanism in
`agents/critic.py`; both constants are marked provisional in `config.py` because U8's
eval batch is what tunes them against real evidence rather than against the demo deals,
which were calibrated to run clean and can't stress-test a threshold themselves.

**One consequence of the arithmetic is worth seeing before reading the deals below.**
Because info-severity disclosures cost nothing and warns cost 0.15, the score is
effectively a count: one warn reports at 0.85, two report at 0.70, and **three warns
escalate at 0.55**. So the practical question the threshold asks is *"have three
independent things gone wrong?"* — and a market that supplies a standing warning to every
listing in it (see New York, below) has spent part of that budget before the property is
examined at all.

**How much room those two numbers have was measured in U8.6 and is published in
`src/eval/results/sensitivity.md`.** The shipped threshold is 0.60 and stays 0.60; the
sweep asks what *would* happen at other values. Holding the warn weight at 0.15, **any**
threshold from 0.30 to 0.70 decides all 21 predicted eval cases identically; holding the
threshold at 0.60, any warn weight from 0.100 to 0.200 does. That is a statement about the *batch's*
resolving power, not a licence — a set of cases that cannot tell two settings apart is
saying it has no evidence either way, which is why the shipped values were held rather
than declared optimal.

---

## Two questions, deliberately kept apart

**Added U9.4, and this document predated it.** Every deal below now produces *two*
verdicts, and the whole point is that they answer different questions and can disagree:

- **Axis 1 — can the system stand behind its own numbers?** `reports` or `escalates to
  human review`. This is a statement about the *software*, and it is what the confidence
  score above decides.
- **Axis 2 — is this property worth buying?** *Proceed*, *Proceed with caution*, *Do not
  proceed*, or *No recommendation*. Computed by the Critic from the asking price against
  its benchmark and whether nearby listings corroborate the rent — and it **never reads
  the confidence score or the escalation decision**, because those are axis 1.

**`staten-island` is why they are separated.** It escalates on zero comparables while
asking 17% below its own neighborhood's median, so a reader who took the escalation
banner as a verdict on the *property* read the evidence exactly backwards. It reports
**Proceed** on axis 2 and **escalates** on axis 1, and the distance between those two
lines is the point.

The axis-2 verdict is **deterministic** — a pure function, so the same deal cannot be
"proceed" on Tuesday and "do not proceed" on Wednesday (OQ-17 measured this model scoring
an identical prompt 0.05 and then 0.95). A model does produce its own independent verdict
from the same evidence, but it can only ever *annotate*: where the two disagree the report
says so and discloses the disagreement rather than resolving it. Rows carrying that
disagreement are marked ⚖ in the results table.

---

## The demo deals

### Los Angeles — the clean baseline, and it only became clean on Aug 30, 2026

`main.py --deal los-angeles` · confidence **1.00** · 4 disclosures (4 info) ·
**reports** · axis 2: **Proceed**

An Echo Park duplex, dense market, full 8-comp set. This is the "everything worked"
case, and it is now literally that: three info-severity disclosures, no warnings, a
perfect score.

**It used to score 0.85, and this document argued that was the correct ceiling.** The
paragraph here read: *"even here, one warn-severity disclosure fires — Los Angeles
County's rent anchor falls back to the county-wide Fair Market Rent … the clean row in
this demo set is 'reports with no critical flag', not 'raises zero flags'. A perfectly
silent run doesn't exist in this system by design."* That was an accurate reading of a
real limitation, and it is worth keeping because **it was reasoning from a constraint
that turned out to be removable.**

HUD publishes no ZIP-level Fair Market Rent for Los Angeles County at the vintage the
model trained on, so every LA estimate was anchored to a figure describing a county that
runs from Malibu to Compton — and the report correctly warned about it on every single
run. U11.3 re-based the anchor on Zillow's ZIP-level market rent index, which *does*
cover 90026. The warning stopped firing because the condition stopped being true, not
because the disclosure was softened.

The four surviving disclosures are mechanism, not weakness, and cost the score nothing:
how the rent figure was anchored (`rent_anchored_to_market_index` — a modelled ratio of
1.06 times this ZIP's own market rent), which series the price appreciation comes from
(`appreciation_source`), which series the *rent* growth comes from
(`rent_growth_source`), and a near-tie between two forecast scenario pairings
(`forecast_branches_near_tied`, info-severity since U8.6c). **The third is new as of
U9.3** and replaced a disclosure this paragraph used to name — "which fiscal years were
screened out of the rent bands" — which retired with the cohort screen when rent growth
was re-sourced from the federal schedule to the market index (#21). A fourth used to sit here — a *drift correction*, scaling this deal's
estimate down by 0.74 because the federal schedule for this ZIP had risen 62% since the
training vintage against 21% for observed market rents. That correction is gone too, and
for the better reason: the anchor now reads a market index at both ends, so the drift
divides out where it arises instead of being subtracted afterwards.

### Chicago — the deal that escalated, stopped, and escalates again

`main.py --deal chicago` · confidence **0.70** · 10 disclosures (6 info, 3 warn, 1
critical) · **escalates to human review** · axis 2: **Proceed**

A Logan Square two-flat with a full 8-comp set. **Through U8.5 this deal escalated at
0.55**, and it was the demo set's one example of "escalates on accumulated warnings
alone, with nothing actually broken" — a deliberately accepted outcome, on the principle
that you don't move a production threshold to make a demo pass.

It reports now, and the reason is a severity change made on evidence rather than a
threshold nudge. One of its three warns was a **near-tie between forecast scenarios**.
U8.6c found that flag was two different disclosures sharing one name: a tie between
*framings* (which years feed every band) discards a whole reading of the data and stays
warn-severity, but a tie between *scenario pairings* — which is what fired here —
changes nothing a reader sees, because both tied pairings appear in the scenario table
anyway and each scenario's label comes from its projected outcome, not its rank. It was
also being measured by a scorer whose repeat runs vary by more than the tie threshold
itself (see OQ-17). Charging 0.15 of confidence for it was pricing the model's own
noise as doubt about the deal, so the pairing variant is now info-severity.

**Worth stating plainly, because it is a real cost:** the demo set no longer has a
"escalates purely on accumulated warns" case. That property is now carried by the eval
harness's engineered fixtures instead.

**It moved again on Aug 30, 2026, to 0.85 on one warn**, for the same reason Los Angeles
went clean: the re-anchored rent model. Chicago is the market the anchor change helped
most on accuracy — its per-metro error fell from $454 to $343, a 24% improvement — and
it is the result that changed the *reasoning* behind the change, because Cook County was
already the one county with ZIP-level Fair Market Rents. Grain cannot explain a 24%
improvement where the grain was already fine. The market index is simply a better
reference series than the administrative schedule.

**And it moved a third time, back to escalating, on Aug 30, 2026 (U8.6e) — recorded here
because the paragraphs above read as a settled story and are not one.** It now runs at
**0.70 with ten disclosures, one of them critical, and routes to human review.** The
score is not what escalates it: 0.70 clears the 0.60 threshold comfortably, and the deal
escalates on the independent critical-flag rule. What changed is that the Critic's first
interaction check was ungated. This Logan Square listing carries
`comps_outside_match_criteria` on an ordinary run — three of eight comparables fall
outside the size band searched — and that now draws a **critical objection**: the comp
set was widened on an attribute the rent model prices on, so the comparable-implied
median describes a different kind of unit than the one being priced, and the rent figure
has no usable independent check on this deal.

**Nothing about that was reverted, and it is the system working.** But it cost the demo
set its middle case — one clean run against five escalations — which is what OQ-21 was
raised to fix and what `chicago-uptown` below now supplies.

### Staten Island / New York — the real-data degradation case

`main.py --deal staten-island` · confidence **0.00** · 12 disclosures (6 info, 5 warn, 1
critical) · **escalates to human review** · axis 2: **Proceed** ⚖

This is the one deal grounded in a real, *measured* market gap rather than a
constructed one, and it's worth walking through why New York needed a case like this at
all.

**New York almost wasn't in the demo at all.** The original metro shortlist hypothesis
was New York/Chicago/Philadelphia, reasoned from housing-stock knowledge (small
multi-family buildings concentrate in older Northeast/Midwest cities). Measured against
the actual rental corpus, New York had only 271 listings across all five boroughs — too
thin by the selection bar — so Chicago/Los Angeles/Cleveland became the inference trio
instead (`design/data_strategy.md` §"Metro Selection").

**But "271 citywide" turned out to be the wrong statistic.** A follow-up measurement
showed those 271 listings aren't spread thin across the metro — they cluster densely in
central Brooklyn (Bedford-Stuyvesant alone returns 38 comps within 3 miles), while
Staten Island holds only 6 listings in the *entire borough*. New York isn't uniformly
sparse; it's a metro where comp density swings enormously by neighborhood, and that's a
genuine property of the data — not something engineered for the demo
(`design/data_strategy.md` §"Sparsity is a property of sub-locations"). Staten Island —
specifically Tottenville, a far corner of the borough — is the sub-location where that
real thinness is worst, so it's the deal that demonstrates it: 4 relaxation iterations
(the retrieval agent keeps widening its search), radius maxed out at 8 miles, still zero
qualifying comps, `sparse_comps` fires at **critical** severity, and the deal escalates.

**A second, independent problem stacks on top of the comps gap:** New York's rent model
also predicts materially worse than the other three markets — **about $855 mean absolute
error against ~$452 overall, 1.9x**, measured per-metro. (It was $1,048 against $524 when
this was written; the anchor change improved both figures without changing the ratio much,
which is the honest summary of what it did.) That's a training and anchoring issue — the
rent-to-market-index ratio New York properties show does not generalize as cleanly from
the national corpus — not a retrieval issue, so it is present *even on New York listings
that do have comps*. On the Staten Island deal itself
this second problem is invisible — the run is already escalating on zero comps, so the
rent-error disclosure never gets a moment to matter on its own. To show it firing
independently, a second fixture (`ny-bedstuy-triplex`, an eval-only case, not a
`--deal` key) was added in `eval/cases.py` at a real, Census-geocoded Bed-Stuy address
that *does* return 8 comps — specifically so the elevated-market-error flag can be
observed on a deal that isn't already escalating for an unrelated reason. It reports at
0.70, paying a spatial-concentration warn on top of New York's standing one because
Brooklyn's corpus listings nearly all share a single placeholder coordinate. (It escalated
at 0.55 until U11.3; see the floor arithmetic below for what moved.)

**A third gap used to be listed here and turned out not to exist — the correction is
kept rather than quietly deleted, because believing it shaped this deal's design.**
Staten Island was described as having no price anchor at all, on the stated grounds that
"Redfin's sale-price extract doesn't cover the New York metro." Checked directly against
the file on Aug 29, 2026, that is false: the extract carries a New York series with 102
fully-populated months at 700–950 multi-family sales each. What excluded it was a filter
in this build's own loader, scoped to three metros before New York was ever a demo case
and never revisited (fixed in U8.4c). The listing's committed $875,000 asking price was
set without a benchmark *because of* that belief; it now measures about 11% below the
metro's multi-family median (~$981K), a plausible Staten Island discount, so the figure
stands as committed and the report benchmarks it like any other deal.

**Updated Aug 30, 2026 (U8.8): the benchmark this deal is read against is now
Tottenville's, not New York's.** County-assessor sale records give ZIP 10307 a median of
**$1,054,490** over 152 recorded sales since 2023, so the committed $875,000 reads **17%
below its own neighborhood** rather than 11% below the metro. The figure still stands as
committed; what changed is that the comparison is now to the borough's south shore rather
than to a median that includes Manhattan.

The distinction matters for the same reason it did when U8.2b fixed the FMR anchor
label: **"the source publishes nothing" and "this system never looked" read identically
in a report and are completely different facts.** What remains genuinely missing here is
the comp set — zero comparables, from a real and measured thinness — which is the gap
this deal exists to show.

**Why this matters for the demo as a whole:** every other case here (and every
engineered case in the U8 eval harness) proves the degradation mechanism fires when a
listing is built to trip it. This is the one that proves it fires when a *real* place is
genuinely under-covered by the data — reality, not the author, supplies the gap. See
`history/decision_log.md` ("why the eval harness is protected from the cut list") for
why this distinction is treated as important enough that U8 is never cut from schedule.

#### What New York costs *every* deal, before its own comps are counted

Measured during U8.6 (Aug 29, 2026). The investigation started from a question worth
repeating — *why should a rent-forecasting system struggle with the largest rental
market in the country?* — and the answer turned out to be partly real and partly this
project's own stale assumption. Both halves are recorded, because the second one was
believed for weeks.

**Two warn-severity disclosures fire for any New York deal**, before a single comp is
retrieved, because each is a property of the market rather than of the listing:

1. **The rent model's error is elevated market-wide.** About $1,048 mean absolute error
   in New York against ~$524 overall — 2.0x, past the 1.5x disclosure threshold. The
   rent-to-anchor structure the model learned from the national corpus generalizes worst
   here. *(Now $855 against $452, 1.9x — see below.)*
2. **The rent anchor is county-wide in all five boroughs.** HUD publishes no ZIP-level
   Fair Market Rent schedule for any New York county (U8.2b), and a county-wide figure
   is at its coarsest exactly here: Kings County prices Williamsburg and
   Brownsville/East New York with one number, and those are not one market.

**The floor is now one warn, not two — measured Aug 30, 2026, and this is the third time
it has moved.** It was three, until U8.4c found that "Redfin doesn't cover New York" was
this build's own filter. It was two, until U11.3 re-anchored the rent model on Zillow's
ZIP-level index, which covers New York's ZIPs — so **item 2 above no longer fires
anywhere in the five boroughs.** Item 1 survives and still should: New York's per-metro
error improved from $981 to **$855** against a **$452** overall figure, which is 1.9x —
lower than the 2.0x quoted above but still comfortably past the 1.5x line. The model got
better at New York and did not stop being worse at New York than everywhere else.

**The pattern across all three moves is the same and is the point of this section:** each
time, the honest response to "New York looks bad" was to check whether the system's stated
reasons were true. Two of the three were artifacts of this build. One was real, and it is
still disclosed.

**A third disclosure used to fire and no longer does, because it was never true.** Every
New York report carried "no price appreciation series" — and this document, and the
report text itself, attributed that to Redfin not covering the metro. Checked directly
on Aug 29, 2026: the extract carries a full New York series, 102 months at 700–950
multi-family sales each. The gap was a filter in this build's own code, scoped to three
metros before New York was ever a demo case and never revisited (U8.4c). It is fixed,
New York deals now get a price forecast and a sale-price benchmark like any other
market, and the standing cost is two warns rather than three.

**So the floor is 0.85, which reports** — it was 0.70 when the anchor warn still fired,
and 0.55 before U8.4c. One market-level warn costs 0.15, leaving a New York deal two
disclosures clear of the threshold before anything about the property is considered.

Comp quality is what usually spends the rest, and it varies enormously sub-metro — a
genuine property of the corpus rather than something engineered. Brooklyn's 89 corpus
listings collapse onto essentially one coordinate (87 of 89 share a single placeholder
point), Staten Island holds 6 listings at 1 coordinate, while Manhattan's 161 spread
across 60 distinct coordinates. **That single fact is now measurable as a pair of eval
fixtures rather than only described:** `ny-bedstuy-triplex` and `ny-manhattan-dispersed`
are the same property specification in the same city, and one pays a spatial-concentration
warn while the other does not. Bed-Stuy reports at 0.70 and Manhattan at 0.85; neither
escalates any more, where Bed-Stuy escalated at 0.55 before the anchor changed. Staten
Island still escalates at 0.00, on no comps at all.

**The thresholds were held rather than tuned (architect's decision, Aug 29, 2026).** The
floor could be lifted by lowering the per-warn penalty or the threshold — both sit
inside ranges the eval batch measurably cannot distinguish from the shipped values — but
each of these disclosures is a serious, independent limitation, and it is their
*combination* that makes a human's look warranted. Production parameters are not moved
to make a demo read better. What did move was a wrong fact about the data. That is the
distinction this whole section is here to show: **the right response to "New York looks
bad" was to check whether the system's reasons were true, not to adjust the bar until
the complaint went away** — and one of the three reasons turned out not to be.

### No Geography — nowhere to anchor to

`main.py --deal no-geography` · confidence **0.00** · 5 disclosures (1 warn, 4
critical) · **escalates to human review** · axis 2: **No recommendation**

A listing at a fictional address (Tallow Bend, WY) that resolves through neither the
Census geocoder nor the corpus's city-centroid fallback. With no coordinates, there's no
county, so no Fair Market Rent, no comps, and no appreciation series — every downstream
number is unavailable rather than approximate. This is the totally-ungrounded case, one
level worse than Staten Island: Staten Island still resolves a *place* and fails to find
comps there; this deal fails to resolve a place at all. The listing's own price figure
is stated as illustrative for exactly this reason — there's no benchmark it could be
checked against.

### Overpriced — exercising the price-benchmark disclosure

`main.py --deal overpriced` · confidence **1.00** · 6 disclosures (6 info) ·
**reports** · axis 2: **Proceed with caution** ⚖

An Uptown two-flat in Chicago, asking **$1,345,000 — 55% above ZIP 60640's median
recorded sale price** of $867,500, on purpose (`price_premium_to_basis=0.55` in
`demo_deals.py`). It exists to solve a specific problem: every *other* demo listing is
calibrated to its own benchmark, so the report's asking-price-versus-benchmark disclosure
reads near 0% on all of them, and a real check had no listing that could exercise it.
This is not a claim that Uptown trades at this price.

**It is the demo set's clearest demonstration that the two axes are independent.** Axis 1
is spotless — 1.00 confidence, eight matching comparables, not a single warning — while
axis 2 says *proceed with caution*. Nothing is wrong with the analysis; something is
wrong with the price, and the report says exactly that rather than blurring the two into
one verdict.

**This deal was in Los Angeles until Sept 1, 2026, and the reason it moved is a
measurement that falsified it.** It was a Los Feliz listing at 55% above the Redfin
*metro* median. Los Angeles has no ZIP-level sale benchmark at all — California publishes
assessed value under Proposition 13 rather than sale price — so the only reference
available there is metro-wide, and `scripts/sale_premium_distribution.py` measured what a
premium against one of those is actually worth across 44,358 real sales: **55% over a
metro median is the 78th percentile. An ordinary transaction.** The deal documented as
deliberately mispriced was, on the evidence, priced unremarkably, and the recommendation
rule returned *Proceed* on it.

Uptown has a local tier built from 148 recorded county-assessor sales, where the same 55%
sits around the **90th percentile** — a premium the data can call unusual. **Uptown
rather than Logan Square, and the reason is what each market does to axis 1:** Logan
Square was tried first, and its comp set relaxes the size band, which raises the critical
objection described above and escalates the deal — so the report would have shown a
cautionary recommendation beside an escalation and a reader could not tell which the
asking price caused. Uptown returns eight matching comps and reports cleanly, so **the
price is the only thing that fires anywhere in the report.**

**A second thing this deal used to demonstrate has moved to `chicago-uptown` below.** The
older text here said the benchmark going ZIP-level (U8.8) made other deals' calibrations
visible — `chicago` reading 31% below Logan Square's median, `staten-island` 17% below
Tottenville's. That is still true and still worth seeing. What it does not do is give the
set a deal whose *clean* recommendation means anything, which is the gap the next deal
fills.

### Coordinate Conflict — supplied coordinates disagree with the address

`main.py --deal coord-conflict` · confidence **0.60** · 6 disclosures (4 info, 1 warn,
1 critical) · **escalates to human review** · axis 2: **Proceed**

The same Echo Park listing as the Los Angeles deal, but with coordinates supplied
directly that actually describe a property in Santa Monica, ~14 miles away. This
exercises one of the Critic's cross-agent consistency checks: it catches the case where
a subject's stated address and its supplied coordinates disagree about where the
property actually is — something neither the Extractor nor the geocoder would notice on
its own, since each only sees one half of the conflict.

### Chicago Uptown — the second clean run, and the first meaningful *Proceed*

`main.py --deal chicago-uptown` · confidence **1.00** · 5 disclosures (5 info) ·
**reports** · axis 2: **Proceed**

**Added Sept 1, 2026 (U9.6) to close OQ-21**, and the purpose was restated once the
premise was measured. OQ-21 was raised when `chicago` began escalating and `los-angeles`
became the only deal reaching 1.00 and reporting clean — a set carried entirely by
degrees of escalation understates a system whose whole argument is that it reports
cleanly when it can. By the time this deal was built, U9.4's re-siting of `overpriced` to
Uptown had already given the set a second clean axis-1 run, so that original wording was
satisfied without it.

**What the set still lacked is a deal whose *Proceed* means something**, and this is the
one thing it supplies. Under decision #11 no demo figure is invented — every asking price
is derived from a published market source — and until now that source was the Redfin
*metro* median. Los Angeles has no ZIP-level tier, so `los-angeles` is compared against
the very figure its price was calibrated from and reads 0% by construction. Its *Proceed*
is circular. This listing is calibrated to **ZIP 60640's own median, built from 148
recorded county-assessor sales** — a benchmark #11 did not supply — so its *Proceed* is
measured against a local figure rather than against itself. The circularity on the other
deals is real, is tracked as OQ-20, and is out of this unit's scope.

**Read it next to `overpriced`.** Same ZIP, same benchmark, same unit mix, both reporting
at 1.00 with nothing but info-severity disclosures — and opposite axis-2 verdicts,
turning on the one input the recommendation rule reads. They are not a true one-variable
control (this deal is 1,100 sq ft against `overpriced`'s 950), and the eval batch's
`chicago-uptown-*` fixtures are where floor area is isolated properly.

It is sited at **5100 N Kenmore Ave**, which is the same address as four golden eval
fixtures, so the demo listing and those fixtures describe one property at several
specifications rather than nearby buildings that resemble each other. 1,100 sq ft is the
specification whose 1,300 sq ft sibling escalates — so the deal inherits a documented
statement of how narrow the clean margin is without having to make it itself.

### Los Angeles (current anchor) — the same property, re-based

`main.py --deal los-angeles-current` · confidence **1.00** · 4 disclosures (4 info) ·
**reports** · axis 2: **Proceed**

**A shadow of `los-angeles`, added Sept 1, 2026 (U9.6).** Byte-identical to it — same
address, same description, same asking price — except that its two stated rents are
declared against the market rent index the system actually prices with (#19) instead of
HUD's Fair Market Rent schedule that decision #11 calibrated the original against. The
original is deliberately left untouched, so the pair *shows* what the anchor change means
for a listing's own figures rather than asserting it.

**The entire visible difference is one line, and that is the design.** Both reports
estimate the same **$2,861/mo** — the model never sees a stated rent, so its output
cannot move. What moves is the comparison beneath it:

| | stated rents | vs. the estimate |
| --- | --- | --- |
| `los-angeles` (HUD schedule, #11) | $2,850 / $2,950 | **1% above** |
| `los-angeles-current` (market index, #19) | $2,650 / $2,730 | **6% below** |

**The direction is the finding.** HUD's schedule is a 40th-percentile rent and is usually
described — including elsewhere in this project — as running *under* the market. In ZIP
90026 it runs **7.3% over**, because HUD publishes no Small Area figure for Los Angeles
County and the lookup falls back to a county-wide number covering Malibu to Compton. The
staleness is real in every market; its *direction* is not uniform, and this repository's
own docstring had generalized Chicago's direction to the whole set until this deal was
measured.

**Why Los Angeles rather than a market where the gap is larger.** Re-basing moves Echo
Park's rents −7.2%, against +14% in Uptown and +34% in Logan Square. The size of the
number is not the point: on `los-angeles` the report is clean, so the re-basing is the
*only* difference between two otherwise identical reports. A Logan Square shadow would
move three times as far and land it inside a report that escalates carrying ten
disclosures, where a reader could attribute it to nothing in particular.

### The ablation: isolating the critical-flag escalation rule

`main.py --deal chicago --no-retrieval` · confidence **0.60** (exactly) · 6 disclosures
(4 info, 1 warn, 1 critical) · **escalates to human review** · axis 2: **Proceed** ⚖

Not a seventh listing — the Chicago deal run with retrieval switched off, which is the
U4 ablation demonstrating what the system does without its comps step at all. It's
included here because it's the one live run that isolates the *critical-flag* escalation
rule from the *score* rule described above: `retrieval_disabled` costs 0.40, landing the
score at exactly 0.60 — not below the 0.60 threshold, so the score alone would **not**
escalate this deal. It escalates anyway, because `retrieval_disabled` is critical
severity and that rule fires independent of the score.

**This paragraph used to end by claiming no other deal lands on that boundary, and that
is no longer true — corrected Sept 1, 2026 (U9.6).** `coord-conflict` also scores exactly
**0.60** and also escalates on the critical rule rather than on the score, and `chicago`
escalates at **0.70**, well clear of the threshold. Three of the nine live runs now
separate the two escalation grounds where this one used to be alone, and the eval batch
adds five more (the rows marked † in `eval/results/results.md`). The sensitivity sweep
makes the same point from the other side: the critical weight is behaviorally **inert
across its entire range, including zero**, because every deal carrying a critical
escalates on the independent rule whatever the weight says.

So this run no longer earns its place by being the only case at the boundary. It earns it
by being the only one where the critical is `retrieval_disabled` — the whole comps step
switched off, which no listing can produce and which is what makes it the U4 ablation
rather than a seventh property.

---

## How the demo deals relate to the eval harness

The demo deals answer "does the system behave sensibly on a handful of representative,
real-world-anchored cases." The U8 eval harness (`src/eval/cases.py`,
`src/eval/README.md`) answers a different question — "does every specific degradation
path in the system actually fire, on a listing built to trip exactly that path and
nothing else" — with 21 engineered fixtures, each targeting one named flag.

The two are kept structurally separate inside the harness by a case's **verdict
source**, not by its tier. `BASELINE` means a previously measured and published outcome,
which makes re-running the case a regression check — did the number move. `PREDICTED`
means a claim made about the case before it was ever run, and it is the only kind U8.6's
confidence-threshold tuning is allowed to score against, because agreeing with an answer
transcribed from the answer key proves nothing.

**The six original demo deals are `BASELINE`** — their outcomes were published in the
U7.8 table before the harness existed. **The two added at U9.6 are `PREDICTED`**, and the
distinction is about provenance rather than about how confidently the outcome could be
guessed: a deal that has never been run has no published outcome to transcribe, so its
verdict is a claim, derived from the disclosures the design expects and the shipped
escalation rule and from nothing else. Both claims held on the first recorded run.

**The sensitivity sweep still excludes all eight**, and that is deliberate rather than an
oversight: demo deals are calibrated to run clean, and a threshold swept over deals that
were never near it measures nothing. So `results.md` reports agreement over 23 predicted
cases while `sensitivity.md` sweeps 21. Full reasoning in `eval/cases.py`'s module
docstring and at the filter in `scripts/confidence_sensitivity.py`.

---

## The rest of the demo surface

**Updated Sept 1, 2026 (U9.6).** Most of what this section listed as unbuilt has landed;
what remains is named honestly rather than left as an aspiration.

**Built since this section was written:**

- **The report itself was reworked** (U9.4) — the two axes above, a recommendation and
  its independent cross-check, a short model-written summary above the report, and
  progressive detail so the headline figures come before the boilerplate disclosures.
- **Every deal replays from committed recordings** (U9.5). All 30 rows in the eval batch,
  the demo deals included, are reproducible from a fresh clone with no model calls and no
  quota. Before that the demo rows fell through to a developer's working cache, so the
  figures the write-up quoted could not be re-derived by anyone else.
- **Two deals added** (U9.6), documented above.

**Still to build:**

- **Streamlit app.** The intended interactive demo surface — a listing goes in, the report
  with every disclosure comes out. Decision #3 in the plan's register, and §6's cut-list
  item 4. It is kept in scope deliberately *because* a fallback exists if the schedule
  forces it: a terminal recording plus LangSmith traces of the same deals, which the
  harness already produces as a byproduct. **Its risk went down at U9.5**, not up — its
  stated default of replaying the demo deals instantly and deterministically is now true
  rather than planned.
- **Final report and video.** Due Sept 7, 2026, after the Sept 4 code freeze. Expected to
  draw its evidence largely from the harness output — the demo deals' reports, the eval
  batch's results table, and the graph diagram generated from the compiled graph — rather
  than being written separately from scratch.
- **LangSmith traces.** Each demo deal run with tracing enabled (`LANGSMITH_TRACING=true`)
  produces a trace of the full seven-agent pipeline, showing the actual agent-to-agent
  flow rather than only its final output. Free-tier traces expire after 14 days, so they
  are captured close to the write-up rather than long before (OQ-13).

**One limitation worth stating here rather than only in the report.** The short written
summary at the top of each report is model-generated. The figures it quotes are computed
and checked; **its prose is not verified**, and it needed two prompt passes plus a
structural change before it stopped mischaracterizing evidence. The recording pass freezes
one draw per deal, so what ships is a fixed artifact that can be read once and checked —
which is the strongest mitigation available inside the freeze, not a guarantee.
