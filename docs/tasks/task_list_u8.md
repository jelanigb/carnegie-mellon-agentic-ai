# U8 — Evaluation harness — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#17) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

**Feeds Checkpoint 6.1, the final report, and the video.** §6 sizes this unit as *8–10
synthetic listings each engineered to trip a specific flag, plus the New York
sparse-comps case run against real data, plus a batch runner producing a results table* —
and, since Aug 26, **the absorbed U10 scope**: per-metro end-to-end runs, LangSmith
traces, demo screenshots, and the graph diagram generated from the compiled graph.

**This is the unit that cannot be cut** (§6, "Never cut"). Everything else in the
remaining schedule yields to it.

**Nine open questions are labelled U8** — OQ-1, OQ-3, OQ-5, OQ-7, OQ-12 (two halves), OQ-15,
plus four `TODO(U8)` sites in `config.py` and `agents/critic.py`.

**Answered Aug 28, 2026, by the architect: all of them are taken, including both cut-list
items** — OQ-6/ZORI (which had no unit at all) and OQ-7/#11 public-record ground truth
(cut-list position 2). That is a deliberately ambitious unit against a Sept 4 freeze with
U9 unbuilt, and **the schedule risk is real and is stated here rather than discovered on
Sept 3**: U8's core is eight change sets, the two absorbed items add two more, and U9 owes
a Streamlit surface. The plan below manages that risk structurally rather than by
optimism — see *Sequence*.

---

## Sequence, and why

**ZORI runs first (U8.0), not last.** It was the last subsection in this plan's first
draft, on the reasoning that it is optional. That was wrong on dependency: if checks A and
B are promoted to Critic objections they fire on eval cases and change confidence, and
confidence is the thing U8.6 exists to tune. A measurement that can change what the batch
scores has to land before the batch is scored. It is also the cheapest item in the unit —
a flat file and one ratio, no pipeline wiring — and the one whose result most changes other
decisions, which is the profile of work that belongs at the front.

**Measure the coverage gap before designing cases against it.** U8.1 builds the runner and
points it at the deal set that already exists; its first output is a census of which
`FlagKind` members the current demo set actually raises. U8.2's cases are then written
against a measured gap rather than a guessed one. Building the cases first would mean
designing eight fixtures from an assumption about what is already covered — the exact
failure this project's CRISP-DM lesson is about.

**Pass-scoped flags (U8.5) land before the tuning run (U8.6), not after.** The batch will
contain rework laps, and a stale objection printed in a *published results table* is worse
than the same sentence in one demo report — the table is the evaluation evidence. It is
also a precondition for trusting any confidence number measured on a case that reworks.

**Public-record ground truth (U8.8) sits behind the harness core and carries a drop-dead
date, Mon Sept 1.** It is the one item in the unit whose cost is not bounded in advance
(see Q3), and it is attached to the unit that must not slip. Putting it after U8.6 means
the un-cuttable work is already green before the risky work starts; the drop-dead date
means the cut, if taken, is taken with three days in hand rather than on the freeze
morning. **This is what makes "revisit if we run short" a mechanism instead of an
intention.**

**The absorbed-U10 evidence (U8.9) is last but is not a leftover.** It is the part of the
unit that makes live model calls, so it wants a settled system to run against, and
OQ-13's LangSmith traces expire after 14 days on the free tier — so it wants to be near
the write-up rather than early.

## Unit-level open questions

### Q1 — ANSWERED Aug 28, 2026: declared verdicts, written before the first run. Blocks U8.6.

The demo deals were rejected as a tuning instrument on explicit grounds: they were
*calibrated to run clean*, so a threshold fitted to them would be measuring this
repository's own fixtures. **An engineered eval batch is calibrated to fail.** Fitting the
threshold to it is the same error with the sign reversed, and it is less obvious because
the batch is called an evaluation.

There is no held-out population of real listings to tune against and none is reachable in
seven days, so the instrument has to be built rather than found. **Proposal: each case
declares an intended verdict** — `reports` or `escalates` — **in its case definition,
written before the first run**, next to the flag it targets. The threshold and weights are
then scored on agreement with those declarations rather than on the flag counts they
produce, and a disagreement is triaged by a rule fixed in advance:

- the target flag fired as designed and the verdict still disagrees → **a tuning signal**;
- the target flag did not fire → **the case is wrong, not the threshold.**

Writing the verdict before the run is what keeps this from being circular. Reading the
system's output and then recording it as the intended verdict would produce a perfect
score and prove nothing.

**Recommendation: declared verdicts, and be willing to leave `0.60` where it is.** "The
batch agrees with the shipped threshold" is a real result and a publishable one. A number
moved to improve agreement with fixtures the same unit authored is not.

**Alternative if that is judged too strong a claim:** do not tune at all — characterize the
score distribution across the batch, publish what would change at each candidate threshold,
and close #6 as *evidenced and held* rather than *tuned*. This is cheaper and defensible;
it forfeits the ability to say the numbers were chosen against evidence.

**Taken: declared verdicts.** #6 closes as *tuned*, on the condition that the triage rule
above is fixed before the first run rather than after seeing a disagreement — the rule is
what separates tuning from fitting, and a rule written afterwards is not a rule.

### Q2 — ANSWERED Aug 28, 2026: render always + flag when elevated (C), from per-metro holdout residuals (2). Blocks U8.4.

OQ-3 is a disclosure requirement, not a modelling problem: New York predicts at ~$1,065 MAE
against the trio's ~$518, no shortlist fixes it, and `INDEXED_MARKETS` still admits a Staten
Island subject to the rent model. Two sub-decisions:

**(a) What the system does — taken: C, render always *and* flag when elevated.** A new
`FlagKind` raised by the Valuation agent when the subject's market is measurably worse,
*plus* the per-market error rendered on every report so a reader in a good market can see
what good looks like. This is the U7.5 pattern — the Summarizer renders the number
unconditionally, the flag fires only when it crosses the line — and the two halves buy
different things: the disclosure lets a reader compare markets, the flag makes the system's
noticing **assertable** by a test and countable by U8.1's census.

A new kind rather than widening an existing one, because the reader's response differs from
every rent flag that exists. `RENT_ESTIMATE_UNAVAILABLE` means there is no number;
`RENT_DIVERGES_FROM_COMPS` means two of our own inputs disagree. This one means *there is an
estimate, it is the system's ordinary output, and it is twice as wrong here as the figure
quoted in the report's accuracy section.*

**Rejected: D, refusing the estimate in high-error markets.** $1,065 MAE is degraded, not
useless, and refusing destroys information a reader could weigh. §2 designates New York as
the case grounded in real market thinness — it should degrade **visibly, not vanish**.

**(b) Where the number comes from — taken: per-metro breakdown of the existing holdout
residuals. This corrects what this plan first proposed.** The first draft said the number
should come from the leave-one-metro-out run OQ-12 asks for, on the reasoning that it folds
two open items into one measurement. That is tidy and **wrong on substance**: LOMO measures
*transfer to a market the model never saw*, and **New York is in the training set**. A
Staten Island subject is not in the LOMO situation, so a LOMO figure would overstate the
error this flag exists to disclose.

The per-metro holdout breakdown is the number a subject in that market actually faces, it
is nearly free (the fit already exists — this is a groupby over residuals already computed),
and because it comes from the same split as the headline MAE the report can put both in one
sentence honestly: *"±$518 overall, ±$1,065 in New York."* **Report `n` beside each figure**
— per-metro holdout slices may be thin, and a MAE over forty rows should not be presented
like a MAE over five thousand.

**Consequence, stated rather than glossed: U8.4 no longer closes OQ-12's first half.**
`config.py:309`'s leave-one-metro-out request is a *transfer* question and stays open. It is
a real limitation of the reported MAE and is worth having, but it is not this flag's
instrument, and folding it in to close two items at once would have put the wrong number in
a reader-facing disclosure. Reclassified to the U8.9 report artifacts if the schedule holds,
otherwise carried forward.

**(c) Where the number is stored.** `mae_dollars_by_metro` on `TrainingReport`, which
**already travels with the model artifact** (`tools/model/rent_model.py:443` — *"The report
travels with the model on purpose"*). No new machinery, and it cannot drift from the model
it describes, which a hand-copied `config.py` table silently can. The **threshold** for
raising the flag stays in `config.py`, where tunables live. That split respects §8's
"config is the only home for tunable parameters" without putting a *measured* model property
there.

### Q3 — ANSWERED Aug 28, 2026: taken, at U8.8, behind a drop-dead date. Reframed on what it can actually deliver.

Cut-list position 2, and **its stated cost is out of date.** The cut list says cutting it
"costs a validated value estimate, not a working one" — but #15 made `value_estimate`
permanently `None` in U6. There is no value estimate to validate. What county-assessor data
would actually score is the **asking-price-versus-benchmark disclosure** (#15's labelled
metro median) — a narrower prize than the cut list prices it at, and one the rent model's
held-out corpus slice already has an equivalent of on the rent side.

**And it cannot score the demo deals' asking prices either.** Those listings are synthetic:
the property is not for sale, and #11 set the asking price *from* the Redfin metro median.
There is no real asking price and no real sale to score it against. So what parcel data
delivers here is not a scored estimate at all — it is a **sub-metro sale-price benchmark**
replacing the metro median in `ValuationDetail.benchmark_median_sale_price`, which
addresses §2's "location-blind below the county" limitation on the *price* side, the way
ZIP-resolution anchoring already did on the rent side. Real value; different value from the
one the cut list names. **U8.8 is specified as that, not as scoring.**

**Its cost is shaped differently from every other item in this unit.** ZORI is a flat file
with a bounded cost. Parcel data is an **address-matching problem** — joining a listing's
street address to an assessor record is the same class of work that produced U3's
geocoding tier fallbacks, and it is bounded only if the join works first try.

**Taken, with the risk managed structurally:** scheduled at U8.8, *behind* the harness
core rather than ahead of U8.2, with a **drop-dead of Mon Sept 1**. If the parcel join is
not working by then, the cut is taken and the gap written up in U8.10, with three days
still in hand. Sequencing it ahead of the harness would have inverted the risk ordering —
putting unbounded work in front of the work that cannot be cut.

### Q4 — ANSWERED Aug 28, 2026: taken, at U8.5, before the tuning run. Cheaper than the cut list priced it.

The cut list describes stamping flags with `planner_invocations` as "a §5 change touching
every agent that raises a flag", which reads as expensive. **Measured today:** 37 `flag()`
call sites across five agents, every one of them inside a node function that already holds
`state`, plus six helper functions that would take a pass index as an argument
(`valuation_rent._cross_check`, `scenario_forecast._disclosure_flags`,
`_distinctness_flags`, `expand`, `extractor._resolve_geography`, `_extraction_failed`).
`state.flag()` is a single central constructor. That is **one mechanical commit plus the
Critic filter**, not a redesign.

The wrinkle the cut list names is real and stays: **an agent skipped on a rework raises
nothing, so absence must not read as *cleared* when it means *not re-examined***.
`state.plan` records which agents ran, so the Critic's per-pass read has to distinguish
"this pass looked and found nothing" from "this pass did not look". That is the substance
of U8.5 and where review attention belongs.

**Taken, at U8.5, before the tuning run.**

### Q5 — ANSWERED Aug 28, 2026: ZORI is absorbed, and moves to the *front* of the unit as U8.0.

Three separate items are all gated on the same missing measurement — whether the market's
rent/FMR ratio is ~1.40 (the corpus) or ~1.00 (FMR itself):

| Item | Site | What ZORI would settle |
| --- | --- | --- |
| Promote checks A and B to Critic objections | `agents/critic.py:187` | Whether the ~-29% stated-vs-modelled gap is a deal signal or a percentile artifact |
| Set or delete the stated-rent emphasis threshold | `config.py:413` | The same number, from the other side |
| Confirm `RENT_COMP_DIVERGENCE_THRESHOLD_PCT` still fires | `config.py:386` | Independent — see below |

**The measurement can veto the promotion, not only unlock it, and that is the reason to
run it.** The two readings lead to opposite actions:

- **Market rent ≈ 1.0× FMR** → the rent model over-predicts by ~40%, and A's −29% reading
  is *the model's error, not the deal's*. A must **not** be promoted; the finding redirects
  at the rent model and becomes a limitation the report states precisely instead of
  vaguely.
- **Market rent ≈ 1.4× FMR** → the model is right, #11's listings are calibrated to the
  affordable end by construction, and A's threshold can be set above that known offset. A
  and B promote to Critic objections with a defensible number.

Either outcome is publishable, and the current state — three items deferred on a question
nobody has measured — is the only one that is not.

**So U8.0 measures and reports the ratio; the promotion decision is made on the number.**
Structuring it that way keeps the fallback intact: if the measurement is late or
inconclusive, `config.py:413` is deleted and `critic.py:187` becomes a stated limitation,
exactly as the deletion path would have done.

**The third row is not gated on ZORI and is genuinely U8 work regardless.** `config.py:386`
moved from firing on 2 of 5 subjects to 0 of 5 in a single change, and a flag nothing can
raise would corrupt U8.2's coverage assertion. It needs a case built to sit on the far side
of the line — **U8.2**.

### Q6 — not blocking, recorded as decided. Two run modes in one table.

`eval/README.md` already commits to this and it is restated here so it is not rediscovered:
tiers 1 and 2 make **no model calls**, which is what makes the batch quota-independent and
reproducible — and is also a limitation the results table must **state rather than imply
away**. The absorbed-U10 rows (U8.9) are live end-to-end runs. **One table, with a
provenance column** naming each row as `golden` / `replay` / `live`, so a reader can see
which rows exercised a model and which replayed one.

---

## Subsections

### U8.0 ✅ — ZORI: measure the rent/FMR ratio, then decide (OQ-6, #16)

**First, because its result changes what U8.6 is tuning** (Q5). A script —
`scripts/zori_evidence.py` — pulling Zillow's ZORI series for the ZIPs the three inference
metros' demo subjects resolve to, and reporting the observed market-rent-to-FMR ratio
against the corpus's ~1.40 at both ends of the ~7-year vintage gap #16 adopted it to test.
No pipeline wiring, no agent touched.

**Source verified Aug 28, 2026, before planning the rest of the subsection** — the premise
this whole branch rests on is that an independent series is actually obtainable, and that
had never been checked:

| | |
| --- | --- |
| File | `Zip_zori_uc_sfrcondomfr_sm_month.csv`, Zillow public research CSVs |
| Reachable | HTTP 200, 9.9 MB, last modified Aug 16, 2026 |
| Grain | one row per ZIP, monthly columns from **2015-01** to present |
| Join keys present | `RegionName` (ZIP), **`CountyName`**, `Metro`, `State` |

Two consequences. The series **spans both ends of the ~7-year vintage gap** — the corpus's
2018-19 and today — so the stability question #16 posed can be asked at both ends rather
than inferred from one. And `CountyName` means it joins to HUD FMR at the county level
directly, not only through the ZCTA crosswalk, so the ratio can be measured at the same
grain the anchor uses. **Confirm the attribution/license terms before committing any
derived file.**

**It states what it could have returned before it runs**, per §8: ~1.0 means the rent model
over-predicts and check A must not be promoted; ~1.4 means the model is right and A gets a
threshold above #11's known calibration offset; anything else means the assumption is
unstable across the gap and the report says so. **All three are results.**

The promotion of checks A and B, and the disposition of `config.py:413`, follow from the
number rather than preceding it. If this lands inconclusive, the fallback stands unchanged:
`config.py:413` is deleted, `critic.py:187` becomes a stated limitation, and both are
recorded in U8.10 as closed on evidence rather than deferred again.

---

**Built Aug 28, 2026. The assumption does not hold, and the reason is not the one either
branch anticipated.** Measured over 64 ZCTAs and 912 ZIP-anchored corpus rows:

| | |
| --- | --- |
| ZORI / FMR at 2019-06 | **1.186** |
| ZORI / FMR today | **1.046** |
| Drift over the gap | **−11.8%** |
| Corpus rent / FMR (same date) | 1.341 — the corpus sits ~13% above its own market |

**The decomposition is the finding, and it was not in the plan.** A ratio can fall two
ways, and the two call for opposite responses, so the script splits it rather than
asserting it: **market rent rose +33.5% while the FMR schedule rose +51.9%.** The ratio
fell because **the denominator outran the market by 18.5 points** — not because rents
stalled. This was added after a first run reported only the drift, which would have been
read as "rents fell relative to FMR" and is close to the opposite of what happened.

**It corroborates something the system already measured from the other side.**
`config.py`'s cohort-shift screen found FY2023 (+5.10pp) and FY2024 (+7.48pp) moving
every area in the FMR panel together, and could not attribute it — *"whether HUD changed
its methodology or the 2021-22 market surge reached an administrative series two years
late is not determinable from FMR alone."* An independent market series now says FMR rose
half again as fast as the market it prices. That is the attribution the screen deferred.

**Consequence for the rent model, which is the point of having measured it.** The model
learned rent ≈ 1.34× FMR from 2018-19 and multiplies it by *today's* FMR, but today's
market rents at ≈1.05× FMR. **The shipped model therefore over-predicts rent by roughly a
third** — and §2's "a ratio ages more slowly than a dollar level" holds only while the
reference series tracks the market.

**Q5's veto branch is the one that fired: checks A and B must NOT be promoted (U8.7).** The
~−29% stated-vs-modelled gap on the demo listings is substantially the *model's* error, not
the deal's, so an objection raised from it would blame the listing for the model's drift.

**Bounds on the claim, stated rather than buried:** ZIP-anchored rows only (1,105 of 5,686
the model trains on, since a county-anchored ratio has a different denominator); 188 rows
excluded because their ZORI series begins more than 12 months after the vintage month; and
ZORI's unit mix is not the corpus's, which is why the *level* comparison is labelled
indicative while the *stability* one is not — the same construction at both ends cancels a
constant mix bias out of the difference, but not out of the level.

### U8.1 ✅ — The harness: case schema, batch runner, results table, coverage census

`eval/cases.py` (the case type and the case set) and `eval/runner.py` (batch execution and
tabulation). The runner invokes the **real compiled graph** per case, exactly as
`scripts/confidence_evidence.py:_run_deal` does, with an in-memory checkpointer so no state
persists between cases.

A case carries: key, either raw listing text or a complete `DealTerms` fixture, the
`FlagKind` it is engineered to trip, **its intended verdict (Q1)**, its tier
(`golden`/`replay`/`live`), and a note stating what the case is for.

Two outputs to `eval/results/`: the row-per-case table (comps, confidence, disclosures by
severity, outcome, target flag fired y/n, verdict agreement) and the **coverage census** —
`set(FlagKind)` minus the union of every case's `flag_kinds()`, which is the comparison
`state.FlagKind`'s docstring was written to make possible.

**The six demo deals plus the `--no-retrieval` ablation enter the batch as cases in this
subsection**, which is where the U10 absorption actually happens: the demo evidence becomes
a row set in the evaluation rather than a separate pass.

**Ships incomplete on purpose.** The census will report a large uncovered set until U8.2
fills it; that is the measurement U8.2 is designed against.

---

**Built Aug 28, 2026.** `eval/cases.py`, `eval/runner.py`, output at
`eval/results/results.md`. Three notes.

**All seven live rows reproduce the U7.8 table exactly** — comps, confidence, severity
counts and outcome. That is a regression pass on a published table *and* the evidence that
the runner exercises the same code path `main.py` does rather than a rearrangement of it.

**The verdict instrument is split in two, which was not in the plan.** Q1's design has each
case declare `reports` or `escalates` before the run, and the threshold scored on agreement.
But the demo deals' outcomes are already measured and published, so declaring them as
"intended" would hand U8.6 seven agreements transcribed from the answer key. `EvalCase`
therefore carries `verdict_source`: `PREDICTED` verdicts are claims made in advance and are
the only ones `scoring_cases()` returns for U8.6; `BASELINE` verdicts are prior
measurements, making those rows regression checks. The batch currently reports **0 scoring
cases and 7 baselines**, and says so rather than reporting 7/7 as if it meant something.

**The census found a different gap than this plan guessed, which is the payoff for ordering
it first.** 17 of 29 kinds covered, 11 uncovered, 1 unreachable. The U8.2 table below was
written from assumption and was wrong in both directions — `anomalous_period_included` is
already covered, and six kinds it never named are not. Corrected below from the measurement.

One trap caught while building, worth review attention: a golden fixture that satisfies
`REQUIRED_DEAL_FIELDS` but omits coordinates skips the Extractor *and* therefore the
geocoder, so it degrades on geography rather than on its target — and still produces a
plausible-looking row. `EvalCase.__post_init__` rejects it at import.

### U8.1b ✅ — Two defects the census surfaced *(taken Aug 28, 2026 by the architect)*

Both were found by building U8.1 rather than by reading code, and neither is an eval-only
problem.

**1. `FlagKind.LLM_RENT_FALLBACK_USED` deleted.** The census reported it as the one kind no
case can raise: §6's cut list item 3 was taken and the fallback estimator was never built.
Removed on the rule `state.FlagKind` already wrote down when it retired
`COUNTY_FROM_PRINCIPAL_COUNTY` — *"a kind nothing can ever raise would corrupt that
comparison"* — so the member violated a standard this repository had already set for
itself. `RentEstimateSource.LLM_FALLBACK` stays: it is a different enum, read for
provenance rather than compared against a coverage claim, and `valuation_rent.py` keeps
that seam typed-and-unused on purpose. `UNREACHABLE_BY_ANY_CASE` is now empty, and the
mechanism stays for the next such member. **FlagKind: 29 → 28.**

**2. Complete terms with no coordinates skipped the geocoder — a production defect, not an
eval artifact.** `REQUIRED_DEAL_FIELDS` does not include coordinates, reasonably, since a
listing reaching the Extractor has them derived from its address (#10). But a caller
supplying complete structured terms skipped the Extractor node entirely, so **nothing ever
derived them**, and the deal arrived at comp retrieval with nowhere to search — degrading on
*geography* while looking like an ordinary result. Latent until now only because `main.py`
always supplies raw text.

Fixed on both sides, and without spending a model call: the Planner gains a third reason to
route through the Extractor (terms complete, geography incomplete), and `extractor_agent`
takes a **geography-only path** that skips `_extract_terms`. Verified: a fixture with parsed
address components geocodes to a parcel with **zero flags and no model call**.

**The defect had a second half, found while starting U8.2.** `county_fips` is derived only
inside `_resolve_geography`, so a caller supplying *coordinates* and complete terms still
reached the Valuation agent with no FMR anchor — and the report then said
`FMR_UNAVAILABLE_FOR_COUNTY`, which reads as *HUD publishes no schedule for this county*
when the truth was *nobody looked one up*. Those are different facts and a reader cannot
tell them apart.

So the geography path branches: no coordinates → geocode (which also resolves the county);
coordinates but no county → **resolve the county alone**, via the local point-in-polygon
join, with no geocode. Geocoding there would re-derive a point the caller already gave and
risk raising a coordinate conflict against coordinates nobody disputed. The county join is
network-free, so the golden tier keeps the property `eval/README.md` defines it by, and
fixtures do not have to hand-carry FIPS codes.

**One regression caught by the existing suite, and it was the right test to fail.**
Expressing the Planner's condition as "geography is incomplete" made it true *forever* for
an address that was tried and could not be resolved, so every rework lap re-planned
extraction for a geocode that had already failed on its merits — exactly the distinction
U7.1b drew between a retryable service outage and an unresolvable address. Restricted to
the first pass; later laps stay `_geocode_is_worth_retrying`'s business.
`test_an_unresolvable_address_does_not_re_plan_extraction` exists for this mistake and
caught it.

Two predicates moved onto `state.DealTerms` as part of this — `is_complete()` and
`geography_is_incomplete()` — because two agents now ask each, and leaving either in an
agent would have made the other import an agent, inverting the dependency the graph's
topology sets up. The Planner reaching into the Extractor for a predicate was written and
reverted during this change set; recorded because the pull toward it is structural, not a
slip. `config` is imported inside
the method rather than at `state.py`'s module scope, so the schema module every other
module depends on still loads without reaching back into configuration.

**The harness guard stays as well, and is not made redundant by the fix.** Geocoding is a
Census API call, so a fixture relying on runtime geocoding would put a network dependency
in the golden tier that `eval/README.md` defines as fast and reproducible. Fixtures supply
coordinates; the production path resolves them. Different jobs.

All 60 tests pass.

### U8.2 — The engineered cases (golden fixtures, plus one declared fault)

8–10 cases, each targeting one kind the census reports uncovered, supplied as complete
`DealTerms` so the pre-flight Planner (#9) routes past extraction — no new mechanism
needed, per `eval/README.md`.

**The eleven uncovered kinds, measured by U8.1 rather than assumed.** The list this
section first carried was written from assumption and got it wrong in both directions: it
named `ANOMALOUS_PERIOD_INCLUDED`, which the demo set already covers, and missed six kinds
entirely. Replaced with the census output:

| Uncovered kind | Route to a case | Tier |
| --- | --- | --- |
| `unresolved_field` | A listing that omits a required field | replay (U8.3) |
| `assumed_field_value` | A listing the Extractor must infer from | replay (U8.3) |
| `extraction_retry_exhausted` | Recorded responses that never validate | replay (U8.3) |
| `extraction_unavailable` | No model reached at all | replay (U8.3) |
| `geocoder_service_unavailable` | Census call fails — distinct from an unresolvable address | replay (U8.3) |
| `coordinates_from_city_centroid` | An address that resolves to nothing but whose city does | replay (U8.3) |
| `fmr_bedroom_cap_exceeded` | Bedroom count above HUD's published schedule | golden |
| `rent_estimate_unavailable` | A predicted ratio outside the plausible band | golden |
| `rent_diverges_from_comps` | **Closes OQ-12's second half** — `config.py:386` went from firing on 2 of 5 subjects to 0 of 5 and needs a case on the far side of the line | golden |
| `critic_inconsistency` | An I1/I2/I3 interaction combination (U7.2) | golden |
| `rework_limit_reached` | A retryable objection that survives `MAX_REWORKS` laps | golden |

Plus one target that is not a flag kind: **the critical-flag escalation boundary reached
through a property of a listing.** U7.8 found it reached live only by the `--no-retrieval`
switch, which is not a deal.

**Six of the eleven are extraction- or geography-originated, so they are U8.3's tier-2
cases rather than golden fixtures** — which also means U8.3 is larger relative to U8.2 than
this plan assumed when it called tier 2 "the handful of flags".

**Per §8, the coverage census must state what it could have returned.** Some kinds are
unraisable by construction and the census has to say which and why, rather than reporting
them as gaps. `RETRIEVAL_DISABLED` is reachable only through the ablation flag rather than
through any listing, and is covered by the ablation case. **The one genuinely unraisable
kind was deleted rather than excused — see U8.1b** — so the exclusion table is empty and the
census is exact. A census that silently counts an unbuildable kind
as an uncovered gap is the same overstatement in the other direction.

---

**Built Aug 28, 2026. Eight cases, five of the eleven kinds closed, and two harness
properties that were asserted rather than enforced.**

**Two mechanism gaps were found before the first case was written, and both were taken by
the architect rather than worked around.**

*One — the golden tier was making live model calls, roughly four per case.*
`eval/README.md` claimed tier 1 and 2 make "no model calls at all", which was true of the
Extractor and false of the run: `agents/scenario_forecast` builds an `LlmClient` and calls
it twice per Tree-of-Thought level whatever tier the case is, so a golden fixture skips the
parse and not the pipeline. Every golden row was therefore live, quota-dependent, ~30
seconds, and unreproducible from a fresh clone — and `config.EVAL_RECORDINGS_DIR` had been
defined since U3 with **nothing in the repository reading it**. `runner._case_environment`
now points the cache at the committed store and replays for both offline tiers, with
`--record` to re-record deliberately. The property is enforced rather than asserted.

*Two — `REWORK_LIMIT_REACHED` is not reachable by any fixture or any recording.* A rework
needs an objection the Critic marks retryable; exactly one is, and it is gated on
`GEOCODER_SERVICE_UNAVAILABLE`, which is raised only when the Census *request itself*
fails. A golden fixture carries coordinates and never calls the geocoder; a replay case
calls it and it succeeds, because replay covers model calls and not HTTP generally. So
`EvalCase.injects` declares a simulated fault, entering at the same seam a real outage
does — the request raises and the pipeline's own branch decides outage-versus-unresolvable
— and the injection prints in the results table's tier column so a reader can tell a
simulated failure from a real one.

**The cases.** Eight, across all three inference metros rather than one, because
`critic.confidence_from_flags`'s `TODO(U8)` notes that three of six demo deals share one
county's FMR-anchor warn and asks the batch to show whether that skew is an artifact.
Fixtures in `eval/data/golden_fixtures.py`, each naming what is engineered and what is
real; cases in `eval/cases.py`.

**Verdicts are derived from the target flag's severity and the shipped escalation rule,
from nothing else** — a CRITICAL target escalates, a lone WARN reports, an INFO costs
nothing. That derivation is mechanical and checkable against `config.FLAG_SEVERITY_PENALTY`,
and it does not consult what the case did when it ran. It has to be stated that way because
the fixtures *were* run during design — confirming a case trips its target at all requires
it — so "written before the run" needed a sharper meaning than a promise.

**Two cases predict `reports`, deliberately.** A batch of nothing but escalating cases is
scored 100% by a threshold of 1.0, so the agreement figure would measure nothing.

**Measured on the full batch (`eval/results/results.md`): coverage 17 → 22 of 28 kinds,
verdict agreement 7 of 8, and all 7 published baselines still reproduce the U7.8 table**
after both the harness changes and U8.2b's flag fix — which is the regression evidence those
rows exist for. Five kinds closed: the FMR bedroom cap, the refused rent estimate, the
rent-comp divergence (**closing OQ-12's second half**), the Critic's interaction objection
by two different routes, and the geocoder outage. Six remain: five extraction-originated,
which are U8.3's, and `REWORK_LIMIT_REACHED`, below.

**The above-threshold marker earns its place immediately, and negatively.** It flags
exactly one row — `chicago--no-retrieval`, the ablation — so the published table now shows
what U7.8 could only state: the critical-flag escalation rule is still reached only by a
switch, never by a property of a listing. `chicago-uptown-oversized` was built to change
that and does not.

**Result: 6 of 7 golden verdicts agree, and the disagreement is the instrument working.**
`chicago-five-bedroom` targets an info-severity disclosure, so the derivation says
*reports*; it escalates at 0.10, because a five-bedroom subject also empties the comp set.
The target fired, so the triage rule fixed in advance classes it as a **tuning signal**
rather than a broken case. Transcribing the observed outcome as the intention would have
produced 7/7 and hidden the only finding the batch has so far produced.

**`REWORK_LIMIT_REACHED` is still uncovered, and that is a measured result rather than a
failure to search.** `planner.route_after_critic` checks escalation *before* rework, so the
retry path is reachable only through a narrow window — exactly two warn-severity
disclosures, no critical, on every lap. Two live attempts and a grid search over 9 indexed
markets × 16 configurations found no listing in it:

- **Cleveland** diverged as needed but its comps collapse onto one coordinate, which is a
  *critical* objection; it escalated at lap 0 and never reworked.
- **Chicago** avoided the critical, but drawing comps from the city centroid removed the
  divergence, so nothing objected at all. The grid confirms this is structural rather than
  bad luck: divergence and comp dispersion trade off directly, because both are driven by
  how thin the matching supply is. Every Chicago configuration that diverges past the
  threshold also concentrates past it.
- **Los Angeles and Cleveland** are excluded arithmetically before any fixture is written —
  both pay the county-anchoring warn, making three warns and escalating on score alone.
- **The only six hits were in New York, and U8.2b closes them.** Every one is in a county
  that gains the county-anchoring warn once the FMR-resolution defect below is fixed —
  three warns, window shut.

So the honest resolution is not a cleverer fixture. **It is a question: should a critical
objection preempt a retry that might have cleared it?** Today it does, unconditionally.
Raised against U8.5, which already reworks how the Critic reads flags per pass.

**One more input for U8.6, noted while it is fresh.** `chicago-uptown-oversized` was built
to isolate the critical-flag escalation rule from the score and measured 0.70 during design;
it pinned at **0.55** once recorded, because a forecast near-tie disclosure appeared. Same
root cause as the rework difficulty — a warn-severity flag whose firing is decided by the
branch scorer rather than by the deal. Whatever U8.6 concludes about `MAX_REWORKS`, that
flag's contribution to confidence is worth pricing separately. **The escalation boundary is
therefore not isolated by any case**, and U7.8's request for one is carried forward rather
than met.

### U8.2b — The FMR anchor was labelled ZIP-resolution in every New York county

**Taken Aug 28, 2026 by the architect, as its own commit.** Found by U8.2's case work, and
a production defect rather than an eval artifact.

`tools/hud_fmr`'s `used_msa_fallback` answers two different questions depending on which
response shape HUD returned. For a county *with* Small Area FMRs it means "a ZIP was asked
for and none matched". For a county with **no** ZIP-level schedule at all HUD returns a
single flat record, there is no fallback to record, and the field is `False`.
`agents/valuation_rent.py` read it alone, so the second case was recorded as *ZIP
resolution*.

**Measured: all five New York counties** — New York, Kings, Queens, Bronx, Richmond —
return the flat shape. Every New York subject therefore recorded `fmr_resolution = "zip"`
against a county-wide figure with no ZIP to name, `agents/summarizer.py:489` printed a bare
"(ZIP)" beside the anchor, and `FMR_ANCHOR_COUNTY_LEVEL` was **suppressed** — a
warn-severity disclosure missing from every New York report, worth 0.15 of confidence
wherever the score is not already floored. The `staten-island` demo is not the case that
shows it: that deal sits at 0.00 on zero comps, so it absorbs the difference and its
verdict is unchanged. What the demo shows is the *disclosure* half — the report gained the
sentence it should always have carried. §2 designates New York as the market grounded in
real thinness, and this made it the one market that did not say so. It also sits directly underneath U8.4, which exists to disclose New York's rent
error and would have been built on a report that already misstated the anchor.

Fixed by requiring both halves: an anchor is ZIP-resolution only where HUD published a
schedule (`is_safmr`) *and* a ZIP matched.

**The flag's own message was wrong in the other direction, and is fixed with it.** It
asserted that HUD publishes no ZIP-level schedule — true for New York, false for Los
Angeles, which has 474 ZIP schedules for FY2026 and is county-anchored for an unrelated
reason: the model's training rows there were county-anchored, and mixing the two would
multiply a county-relative ratio by a ZIP-level figure. One flag kind still, on this file's
own rule that the reader's response decides — it is the same response either way — but the
sentence naming the cause now branches, because a fixed sentence was false of half the
deals that saw it.

### U8.3 — Recorded extractions (tier 2)

The handful of kinds that genuinely originate in the Extractor need it to run. Record with
`LLM_CACHE_MODE=read_write`, commit the recordings to `eval/data/llm_recordings/`, and run
the batch under `replay` so a miss is a hard error rather than a live call.

---

**Built Aug 29, 2026.** Five cases in `eval/cases.py`, closing the five kinds U8.2's
census attributed here (the sixth, `geocoder_service_unavailable`, had already closed in
U8.2 via `Fault.GEOCODER_OUTAGE`). **Coverage: 22 → 27 of 28 kinds. `rework_limit_reached`
is the one kind left, and U8.2 already found why** — the retry window needs exactly two
warn-severity disclosures and no critical on every lap, and every indexed market either
escalates first (a critical present) or never diverges enough to draw the retryable
objection at all. Left to U8.5, which is where the question it raises (*should a critical
objection preempt a retry that might have cleared it?*) belongs. All 7 published baselines
still reproduce the U7.8 table exactly, and 12 of 13 predicted verdicts agree — the one
mismatch is U8.2's `chicago-five-bedroom`, untouched by this subsection.

**Two of the five needed a new mechanism; the other three were ordinary `--record` runs**
against a listing built to trip one kind cleanly (a stated-not-inferred unit count with no
price; a bare "duplex" with no numeral; a real city, corpus-covered, with a street Census
cannot match).

**`extraction_unavailable` has no response to record, so `Fault` gained a second member.**
`Fault.LLM_UNAVAILABLE` patches `tools.llm_client.LlmClient.complete` at the class — the
same one-layer-above-transport seam `GEOCODER_OUTAGE` patches `geocode_census` at, chosen
for the same reason: `_extract_terms` builds a fresh `LlmClient()` per call, so there is no
instance to patch ahead of time, and patching here leaves the Extractor's own `except
LlmError` branch doing the deciding rather than a directly-forced flag. **Left unrestricted
for the rest of the case deliberately**, not scoped to the one call: `scenario_forecast`
builds its own `LlmClient` later in the same run and hits the same patch, which is the
honest behaviour of a model that is actually down — it already catches `LlmError` and
raises its own critical `forecast_unavailable`, so the row shows a real multi-flag
cascade (measured: 1 warn, 4 critical) rather than a run that dies partway through.

**`extraction_retry_exhausted` needed responses that are guaranteed to fail validation,
and no live model can be asked for that on demand.** `ListingExtraction` has no required
fields — every one is `Optional` — so an ordinary or even a fairly odd model response
*validates*. `scripts/record_retry_exhausted_fixture.py` hand-authors the three recordings
instead: it reproduces `call_with_schema`'s exact prompt and retry-prompt construction
using the real `_EXTRACTION_PROMPT`, `_EXTRACTION_SYSTEM` and schema, chooses three
responses that fail for three different reasons (outright refusal, then two JSON objects
with type-coercion failures), and verifies each against the real schema before writing it
— so a response that would have accidentally validated fails the script rather than
committing silently. No live call happens; determinism comes from Pydantic validation
being the same function on every run, not from a model's mood. Reproduced clean across
three replay runs.

**`coordinates_from_city_centroid` is the harness's first case with a real, standing
network dependency.** The path it targets fires only when the Census geocoder *runs and
cleanly finds no match* — a naturally-reachable path, unlike an outage, so `Fault` (built
for paths nothing else can reach) does not apply and should not. Verified live before the
case was written: `geocode_census('99999 Nonexistent Fantasy Ln', 'Chicago', 'IL', None)`
returns `None`, and Chicago's corpus coverage resolves the centroid fallback. `eval/
README.md`'s "no model calls" claim for tiers 1–2 is unaffected — it was always scoped to
the LLM, and every replay case with a real address already calls the live geocoder; this
is simply the first case whose target *depends* on that call's outcome rather than
incidentally making it.

**One case was re-sited mid-build, and the reason is worth keeping.** The `unresolved_field`
case first ran in Cleveland and escalated at 0.40 with a critical `critic_inconsistency` —
reproduced identically across three re-runs, so structural rather than a network flake.
Cleveland's comps collapsing onto one coordinate is exactly what `cleveland-triplex`
(U8.2) already evidences; sited there, this case would have measured that confound
instead of the flag it targets. Moved to Los Angeles, where it lands cleanly at 0.70 on
two warns (`unresolved_field` plus `fmr_anchor_county_level`, this ZIP's Small Area
schedule not matching). Worth stating plainly: **any replay-tier case with a real, valid
address inherits a live Census call**, and that call's outcome is part of the case's
result whether or not geography is the target. Two case notes originally guessed Los
Angeles County's Small Area coverage would keep `fmr_anchor_county_level` off these rows
entirely; both were wrong (a ZIP-match miss reaches the same flag through the fallback
U8.2b's fix already distinguishes) and are corrected in `eval/cases.py` to state what was
actually measured rather than what seemed likely.

### U8.4 — New York rent error: the disclosure and the case (OQ-3)

Per Q2 (C + 2). Four pieces, in order:

1. **Measure.** Per-metro breakdown of the existing holdout residuals, with `n` per metro,
   onto `TrainingReport.mae_dollars_by_metro` so it travels with the artifact.
2. **Flag.** A new `FlagKind` raised by the Valuation agent when the subject's market
   exceeds `config`'s threshold — the tunable half, in config; the measured half, in the
   artifact.
3. **Render.** The Summarizer prints the market's error on every report, not only a flagged
   one, so a reader can see what good looks like.
4. **Case.** An eval case that trips the flag, plus the Staten Island case run against real
   data as §6 specifies.

**Closes OQ-3. Does *not* close OQ-12's first half** — see Q2(b); LOMO answers a transfer
question this flag does not ask.

Today the Staten Island error is disclosed by accident — that deal escalates for having
zero comps — and an accident is not a check.

### U8.4b — The rent-drift correction (U8.0's consequence)

**Taken Aug 28, 2026 by the architect, on U8.0's finding.** The model learned rent ≈ 1.3–1.7×
FMR from a 2018-19 corpus and multiplies it by today's FMR, but the FMR schedule has risen
+51.9% against market rent's +33.5% since then. **The shipped rent estimate reads high**, in
a range measured at roughly 15–35% depending on subset and on whether the corpus's premium
over the whole-market index persists.

**The correction is applied per-ZCTA at prediction time, not by retraining.** Retraining
changes nothing — the corpus is still 2018-19 and a refit reproduces the same ratio. The
model's predicted ratio is multiplied by the subject ZCTA's own measured
`(ZORI/FMR today) ÷ (ZORI/FMR at the corpus vintage)`.

**Per-ZCTA rather than one global scalar, because the drift is not uniform:** U8.0 measured
it ranging from **+3.6% to −20%** across ZCTAs. A single factor would be right on average
and wrong nearly everywhere. Worth stating plainly, because it explains why this is not the
cheap option it looks like: **a per-ZCTA correction factor is re-anchoring on ZORI, just
expressed at prediction time instead of at training time.** The structural version is
§6 cut-list item 6.

Ships with a flag disclosing that the correction was applied and by how much — a corrected
estimate that does not say it was corrected is less inspectable than an uncorrected one.
Falls back to the uncorrected estimate, flagged, where the subject's ZCTA has no ZORI
coverage at both ends.

**Sequenced here, before U8.5 and U8.6, and that is not cosmetic.** The correction changes
every rent estimate, which moves `RENT_DIVERGES_FROM_COMPS`, which changes the flag sets the
eval batch produces, which is what U8.6 tunes confidence against. Tuning first would tune
against numbers this subsection then invalidates.

**New runtime dependency, stated because it is a real architectural cost:** every rent
estimate now depends on a ZORI-derived table. It is a committed lookup rather than a live
fetch, and it needs a refresh path and a staleness disclosure of its own.

### U8.5 — Pass-scoped flags (OQ-15, cut-list 2a)

Per Q4. Stamp each `Flag` with the `planner_invocations` that raised it; the Critic's
interaction checks read only the current pass; `state.plan` distinguishes *examined and
clear* from *not re-examined*. Clears the `TODO(U8)` at `critic.py:252` and
`planner.py:90`.

Review attention belongs on the skipped-agent case, not on the stamping.

### U8.6 — Decision #6's numbers against the batch (OQ-1)

Per Q1, in whichever form Q1 settles. Covers `HUMAN_REVIEW_CONFIDENCE_THRESHOLD`,
`FLAG_SEVERITY_PENALTY`, `MAX_REWORKS`, and confirmation of the critical-flag rule at
`critic.py:393` — which U7 left open specifically for this run. Also re-prices, or
explicitly holds, `COMP_MAX_OUTSIDE_MATCH_SHARE` (`config.py:97`), whose `PROVISIONAL`
note names the same batch.

**The demo table must be re-derived after any number moves.**
`scripts/confidence_evidence.py` already does this in one command; a moved weight with a
stale table would republish the exact staleness U7.8 fixed.

### U8.7 — Checks A and B, and `config.py:413` — **the veto branch fired**

**Settled by U8.0's measurement: A and B are NOT promoted.** Q5 framed this as a branch and
the branch resolved against promotion. The ~−29% stated-versus-modelled gap on the demo
listings is substantially *the model's own drift*, not a property of any deal, so an
objection raised from it would blame the listing for the anchor's error. `critic.py:187`
closes as a stated limitation naming the measurement, and `config.py:413` is deleted along
with the emphasis it gates — the stated-rent disclosure stays unconditional.

**Note what U8.4b does to this gap, and re-measure rather than assume.** Correcting the
estimate downward moves the stated-versus-modelled comparison toward zero on every demo
deal. The number in `config.py:413`'s comment (~−29% on all three) will not survive
U8.4b, so this subsection deletes a constant whose justifying measurement has itself
changed — which is a reason to re-run the comparison here, not a reason to skip it.

Kept separate from U8.0 deliberately: measuring and acting on a measurement are different
change sets, and folding them would make it impossible to review the number independently
of the conclusion drawn from it. Safe after U8.6, because nothing here moves confidence.

### U8.8 — Public-record sub-metro price benchmark (OQ-7, #11) — drop-dead Mon Sept 1

Per Q3, and specified as what it can deliver rather than as what the cut list promised:
county-assessor open data (Cook, LA County, NYC) joined to the subject's parcel, producing
a **sub-metro sale-price benchmark** to replace the Redfin metro median in
`ValuationDetail.benchmark_median_sale_price`. This is the price-side counterpart to the
ZIP-resolution rent anchoring that already landed, and it makes #15's labelled benchmark —
and therefore check B — mean something local.

**Review attention goes on the address-to-parcel join**, which is the unbounded part and
the reason this sits behind the harness core. §8's "public" definition admits these
datasets; confirm the license on each of the three before ingesting.

**Drop-dead Mon Sept 1.** If the join is not working by then, take the cut, write the gap
up in U8.10, and keep the metro median. Three days remain at that point, which is the
whole reason the date is set in advance rather than judged on the day.

### U8.9 — Absorbed U10: live runs, traces, diagram, screenshots

Per-metro live end-to-end runs across all three metros as `live` rows in the same table
(Q6); LangSmith traces captured — note OQ-13's 14-day free-tier expiry, so this runs
*close to* the write-up, not early; graph diagram regenerated from the compiled graph via
`scripts/export_graph_diagram.py`; demo screenshots.

**Depends on U9 for the screenshots if the Streamlit surface is what gets captured.** If
U8.9 lands before U9, the screenshots are terminal captures and the Streamlit ones are
added at U9 — flagged here so the dependency is not discovered at capture time. Note the
`TODO(security)` at `tools/diagnostics.py:36` — the full error text deliberately includes
the account identifier, and Week 7's deliverable is a terminal capture. **Redact before
recording.**

### U8.10 — Close-out

Review the changelog rows this unit's commits already wrote; move #6 and #11 to their
settled state in §7's register with reasoning in
[`history/decision_log.md`](../history/decision_log.md); delete the closed entries from
[`open_questions.md`](../open_questions.md) — and, where a question is *retargeted* rather
than closed, say so with its reason, per U7.8's precedent.

**Five open questions can close here** — OQ-1 (#6 tuned), OQ-3, OQ-6, OQ-15, and OQ-7
either as built or as a written gap. **OQ-12's first half does not close** (Q2(b)): its
leave-one-metro-out run is a transfer question that U8.4's flag does not ask. Its second
half — confirming something still trips the rent-comp divergence flag — closes at U8.2. That would be the largest single
close in the project, which is also the reason to review each one against what actually
shipped rather than against this plan.

### U8.M — Maintenance *(separate commit, per §8)*

Clear the `TODO(U8)` markers this unit resolves, and the ones Q5 closes by deletion rather
than by measurement. Update the `TODO` inventory table in
[`design/engineering_standards.md`](../design/engineering_standards.md).
