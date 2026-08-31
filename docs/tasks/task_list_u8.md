# U8 — Evaluation harness — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#19) refer to
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

## Status at a glance

**Audited Aug 30, 2026 against the code rather than against this file's prose**, at the
architect's request. Each ✅ below was verified by checking the thing it claims exists —
case counts and tiers out of `eval/cases.py`, flag members out of `state.py`, functions out
of the agents. One subsection did not survive that check and is marked 🟨 with the specific
bullets that never landed (U8.6c).

| | Subsection | Status |
| --- | --- | --- |
| ✅ | **U8.0** ZORI measurement | Built; its conclusion superseded by U11.3, which acted on it |
| ✅ | **U8.1** harness, runner, census | Built |
| ✅ | **U8.1b** two census defects | Built |
| ✅ | **U8.2** engineered cases | 15 golden cases + 3 declared faults |
| ✅ | **U8.2b** New York anchor label | Built |
| ✅ | **U8.3** recorded extractions | 6 replay-tier cases |
| ✅ | **U8.4** New York rent error | Built |
| ✅ | **U8.4b** rent-drift correction | Built, then **retired structurally** at U11.3 — the anchor divides the drift out where it arises |
| ✅ | **U8.4c** New York price series | Built |
| ✅ | **U8.5** pass-scoped flags | Built (`critic._kinds`) |
| ✅ | **U8.6** decision #6's numbers | **Closed** — held on measurement, stable region published |
| ✅ | **U8.6b** straddle pairs | 6 fixtures, 3 clean pairs, 1 documented negative result |
| ✅ | **U8.6c** near-tie split + evaluator scores | **Completed Aug 30, 2026** — the two audited gaps built; the cut-boundary measurement found the tie-break deciding the reported scenario set |
| ✅ | **U8.6d** confidence decomposition | Built, plus the stale Critic stub-node claim it surfaced |
| ✅ | **U8.6e** the objection gate *(unplanned)* | Repairs built; **one open decision for the architect** |
| 🟨 | **U8.7** checks A and B | Re-measured; **the veto's premise expired, so the decision is open** |
| 🟨 | **U8.8** sub-metro price benchmark | Spike done for 2 of 3 metros; **ingest unbuilt**; drop-dead Sept 1 |
| ✂️ | **U8.9** live runs, traces, diagram | Dropped Aug 30, 2026 by the architect |
| ⬜ | **U8.10** close-out | Not started |
| 🟨 | **U8.M** maintenance | TODO inventory reconciled; remainder open |

**Two decisions are waiting on the architect**, both written up in full where they arose:
the divergence gate in front of the Critic's objections (U8.6e) and what to do with the
stated-rent comparison now that its veto no longer holds (U8.7).

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
`RENT_ANCHOR_UNAVAILABLE`, which reads as *HUD publishes no schedule for this county*
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

### U8.2 ✅ — The engineered cases (golden fixtures, plus one declared fault)

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

### U8.2b ✅ — The FMR anchor was labelled ZIP-resolution in every New York county

**Taken Aug 28, 2026 by the architect, as its own commit.** Found by U8.2's case work, and
a production defect rather than an eval artifact.

`tools/hud_fmr`'s `used_msa_fallback` answers two different questions depending on which
response shape HUD returned. For a county *with* Small Area FMRs it means "a ZIP was asked
for and none matched". For a county with **no** ZIP-level schedule at all HUD returns a
single flat record, there is no fallback to record, and the field is `False`.
`agents/valuation_rent.py` read it alone, so the second case was recorded as *ZIP
resolution*.

**Measured: all five New York counties** — New York, Kings, Queens, Bronx, Richmond —
return the flat shape. Every New York subject therefore recorded `anchor_tier = "zip"`
against a county-wide figure with no ZIP to name, `agents/summarizer.py:489` printed a bare
"(ZIP)" beside the anchor, and `RENT_ANCHOR_COUNTY_LEVEL` was **suppressed** — a
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

### U8.3 ✅ — Recorded extractions (tier 2)

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
two warns (`unresolved_field` plus `rent_anchor_county_level`, this ZIP's Small Area
schedule not matching). Worth stating plainly: **any replay-tier case with a real, valid
address inherits a live Census call**, and that call's outcome is part of the case's
result whether or not geography is the target. Two case notes originally guessed Los
Angeles County's Small Area coverage would keep `rent_anchor_county_level` off these rows
entirely; both were wrong (a ZIP-match miss reaches the same flag through the fallback
U8.2b's fix already distinguishes) and are corrected in `eval/cases.py` to state what was
actually measured rather than what seemed likely.

### U8.4 ✅ — New York rent error: the disclosure and the case (OQ-3)

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

---

**Built Aug 29, 2026.** All four pieces landed; measured against real HUD/Census calls and
the real comp index throughout, not mocked.

**Measure.** `tools/model/rent_model.py`'s `train()` already computed the holdout residuals
this needed — the change was carrying `df.index` through the existing `train_test_split`
call so the test rows could be traced back to `state`/`cityname` afterward. Grouped by
`config.INDEXED_MARKETS`, whose own docstring already named it "the inference trio plus New
York" — exactly the four markets OQ-3 asks about, with no new config needed for the
grouping itself. Matched the way `scripts/metro_shortlist_ablation.py`'s module docstring
already documented as correct, rather than repeating the `ignore_index` bug it exists to
avoid. Measured on today's retrain: overall $524.03; **Chicago $492.14, Los Angeles
$530.46, Cleveland $452.49 — all within 1.1x of the overall figure — against New York's
$1,048.38, at 2.00x.** Consistent with the $518/$1,065 figures OQ-3 and U8's planning
carried forward from `scripts/metro_shortlist_ablation.py`'s original measurement.

**Flag.** `FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED`, WARN severity. The threshold is a
*ratio* to the model's own overall holdout MAE rather than a fixed dollar figure —
`config.RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD = 1.5` — so a retrain does not silently
invalidate it. Set on the one measurement above, with wide margin on both sides (trio tops
out at 1.1x; New York sits at 2.00x), and marked `PROVISIONAL` for U8.6 alongside
`RENT_COMP_DIVERGENCE_THRESHOLD_PCT` and `COMP_MAX_OUTSIDE_MATCH_SHARE` — this repository
already has a place for a threshold set on one clean measurement and revisited once the
batch exists to tune against, and this joins it rather than inventing a second category.
`agents/valuation_rent.py`'s `_attach_metro_error` resolves the subject's market the same
way `_attach_benchmark` already resolves a Redfin metro (`kaggle_data.city_matches` against
the same `INDEXED_MARKETS` grouping the measurement used, so the two cannot drift apart),
and runs immediately after `_attach_model_provenance` — independent of whether the county,
the FMR lookup, or the estimate itself later fails, mirroring `_attach_benchmark`'s own
independence and satisfying Q2(a)'s "render always" on its own by construction.

**Render.** Both the "Estimated rent" table cell and the "How the rent figure was reached"
narrative in `agents/summarizer.py` print the subject's market figure whenever it resolves,
flagged or not — confirmed on live runs of all three inference-trio demos plus
`staten-island`: Los Angeles and Chicago each read "in line with the figure above," New
York reads "materially worse … see the disclosure below."

**Case.** The `staten-island` demo needed no new work — it already carries real coordinates
in a real New York county and picked up the new flag automatically once the model was
retrained (disclosures 8 → 9, confidence unchanged at 0.00 on zero comps, verdict
unchanged). But that is the disclosure firing by the same accident OQ-3 named — zero comps,
not a market property — so a second case was added to show it firing where the accident
does not apply: **`ny-bedstuy-triplex`**, a fixture at a real, Census-geocoded
Bedford-Stuyvesant address (40.672786, -73.950302) chosen specifically because it returns a
real comp set (8 comps) rather than reproducing Staten Island's zero. Declared `reports` per
the mechanical rule — both its targets (`RENT_ESTIMATE_MARKET_ERROR_ELEVATED` and the
incidental `COMPS_SPATIALLY_CONCENTRATED`, a genuine property of this corpus location, not
engineered) are warn-severity — and measured `escalates` once New York's standing
county-anchor warn stacks with the other two. A second tuning signal alongside
`chicago-five-bedroom`, by the same triage rule: the target fired as designed, so this is
evidence for U8.6, not a broken case. Recorded once with `--record`, reproduces identically
under replay.

**Batch re-run after the retrain: coverage 27 → 28 of 29 kinds** (only `rework_limit_reached`
remains, unchanged from U8.3); **7/7 published baselines still match**; **12/14 predicted
verdicts agree**, the two disagreements being the tuning signals above.

### U8.4b ✅ — The rent-drift correction (U8.0's consequence) — **built, then superseded at U11.3**

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

---

**Landed late — built Aug 29, 2026, after U8.5, and the miss is recorded rather than
renumbered.** U8.5 landed while this subsection sat unbuilt, which inverted the sequencing
argument above; caught during U8.6's evidence review (the model code had no correction in
it), flagged to the architect, and built immediately on his direction. The label stays
U8.4b so the plan's own sequencing argument remains legible against what actually happened.

**One design refinement over the plan above, found by reading the cross-check before
building (and it prevents a defect):** `rent_model.anchor_comp_rents` expresses every
comp-implied rent the same way the estimate is expressed — a vintage ratio times the
subject's *today* FMR — so the comp side carries **exactly the same drift** as the model
side. Correcting only the estimate would have injected a systematic ~−12% gap into
`RENT_DIVERGES_FROM_COMPS` that is neither the model's error nor the comps'. The factor
therefore applies to **both sides symmetrically** (estimate and comp-implied p25 / median /
p75); it cancels out of `divergence_pct`, so the cross-check keeps measuring structure
against structure while every reported today-dollar figure gets the level correction.

**Built Aug 29, 2026.** `tools/rent_drift.py` computes the per-subject factor —
`(ZORI today / ZORI vintage) × (FMR vintage / FMR today)`, at the subject's own anchor
grain and bedroom count for both FMR ends, refusing on a grain mismatch between the two
fiscal years rather than mixing baselines. Two new flag kinds:
`RENT_DRIFT_CORRECTION_APPLIED` (INFO, the mechanism plus its arithmetic and a
staleness note past `config.RENT_DRIFT_MAX_ZORI_STALENESS_MONTHS`) and
`RENT_DRIFT_CORRECTION_UNAVAILABLE` (WARN — a measured bias the system could not
remove). `RENT_ANCHORED_TO_MARKET_INDEX`'s closing sentence corrected in both branches: it
claimed the stability assumption was "one nothing in this project verifies", false
since U8.0 measured it.

**Measured factors at landing, live against real HUD and the real ZORI file:**

| Subject ZIP | Factor | Market vs schedule since vintage |
| --- | --- | --- |
| Los Angeles 90026 | **0.744** | +20.5% vs +62.1% |
| Chicago 60647 | **0.799** | +38.5% vs +73.4% |
| Cleveland 44113 | **0.881** | +31.6% vs +49.4% |
| Bedford-Stuyvesant 11216 | **0.934** | +46.5% vs +56.8% |
| Staten Island 10307 | no ZORI coverage → UNAVAILABLE warn | — |

Two findings in that table. **The spread is wider than U8.0's +3.6%..−20% range** —
U8.0 measured ZIP-anchored corpus rows only, which excluded the county-anchored metros,
and the county schedules drifted hardest (recorded at the `RENT_DRIFT_FACTOR_MIN/MAX`
comment). **The `staten-island` demo covers the UNAVAILABLE kind organically** — no
engineered case needed for the census.

**Live Los Angeles run end-to-end:** estimate $4,073 → **$3,031**, factor disclosed in
both flags, confidence 0.70 and verdict unchanged — and the stated-vs-modelled gap
collapsed **−29% → −4%**, confirming U8.7's "re-measure rather than assume" note ahead
of schedule. The Summarizer's stated-rent caveat claimed an independent market series
"is named as future work" — false as of this change set; minimally corrected now, fully
re-measured at U8.7. Tests: `tests/test_rent_drift.py` (factor arithmetic, four refusal
paths, and the symmetry property that keeps the cross-check honest);
`test_flag_propagation.py` gains the unavailable-path WARN reaching the report, and
`offline_valuation` stubs the drift seam so the suite stays hermetic — left unstubbed,
a machine without the ZORI file would flip outcomes in tests that never mention drift.
All 71 pass. **Batch re-derivation deliberately deferred to U8.4c's step 3**, so
recordings are re-cut once for both changes.

### U8.4c ✅ — The New York price-series scoping fix

**Taken Aug 29, 2026 by the architect, on a measurement that overturned a standing
assumption.** Every "Redfin doesn't cover New York" statement in this repository traced
back to `tools/redfin_data.py`'s `TARGET_METROS` — a trio-only mapping written before New
York entered the demo, never revisited. Checked against the raw extract: **"New York, NY
metro area" is present, with 102 fully-populated months at 700–950 multi-family sales per
month.** The absence was this build's filter, not Redfin's coverage — the same defect
shape U8.2b fixed for the FMR anchor.

The change set, per the architect's approval (a–d):

1. **The metro mapping moves to `config.py`** (it is a tunable that predates config and
   never moved, contra §8), keyed to the same market set as `INDEXED_MARKETS` so the
   Redfin reach and the system's market list cannot drift apart again, **with New York
   added**. The load asserts every configured region exists in the extract, so a silent
   absence becomes a loud one.
2. **Reader-facing text stops claiming Redfin coverage facts it never checked** —
   `agents/valuation_rent.py`'s `benchmark_unavailable_reason` says "this build's price
   series doesn't reach {city}", which is the true statement.
3. **One `--record` pass and full batch re-derivation for U8.4b + U8.4c together** —
   both change rent estimates or flag sets, so recordings are re-cut once, not twice.
   `staten-island`'s baseline changes legitimately (it gains an appreciation series and a
   price benchmark); the new baseline is measured and published, not patched.
4. **Docs sweep** — `demo.md`'s pending-decision paragraphs resolve, `data_sources.md`,
   open-questions entries.

**Consequence for the NY floor:** `forecast_unavailable` stops firing for New York, so
the standing-warn floor drops from three warns (0.55, always escalates) to two (0.70) —
a well-sited New York deal can now report **without any tunable moving**, by closing a
real gap rather than lowering the bar. The always-escalate arithmetic in `demo.md`
updates to match.

---

**Built Aug 29, 2026, and it had a second half nobody had looked for.** The trio-only
region filter was only one of the two reasons New York resolved to no benchmark.
`_attach_benchmark` matched the subject's city against the metro **label** alone, with no
state check — so no borough name could ever match "New York", and a Brooklyn subject read
as outside the market even once the region was loaded. Both halves are fixed:
`config.REDFIN_TARGET_METROS` (asserted equal to `INDEXED_MARKETS`' label set, with
`load_redfin` raising on a region absent from the file) and `_resolve_market_label`, now
the single resolver both the benchmark and the per-metro error figure use. **Two
independent bugs producing one symptom is the reason the symptom survived so long** — a
fix to either alone would have looked like it had failed.

`staten-island`'s $875,000 was set without a benchmark *because of* the stale belief; it
now measures ~11% below the metro's multi-family median (~$981K), a plausible borough
discount, so the figure stands as committed rather than being recalibrated to fit.

**Measured after the combined re-record (U8.4b + U8.4c + U8.6c): coverage 31/31 kinds,
baselines 6/7, predicted verdicts 10/14.** The New York floor is now two warns as
predicted — `ny-bedstuy-triplex` escalates at 0.55 on a *third*, deal-specific warn
(Brooklyn's corpus rows sharing one coordinate), not on the market alone. The U8.6b
Manhattan fixture is what would demonstrate a New York deal reporting.

### U8.6c ✅ — Near-tie split *(landed early, with U8.4c)*

> **This block covers the severity split only**, which landed here with U8.4c's
> re-record. The subsection's other two items — rendering `Scenario.evaluator_score` and
> measuring the depth-2 cut boundary — were found unbuilt by the Aug 30 audit and were
> built later the same day; both are written up in the full U8.6c section below.

Built ahead of its place in the sequence because the re-record had to happen once, and
this change moves the same flag sets. Full design in the U8.6 scope revision above.
**Two consequences worth reviewing, both measured rather than anticipated:**

1. **The `chicago` demo re-baselined, 0.55/escalates → 0.70/reports.** Its third warn was
   the pairing near-tie. This is a real loss the plan should not gloss: the demo set no
   longer contains an "escalates on accumulated warnings alone, nothing broken" case, and
   that property now lives only in the engineered fixtures.
2. **`chicago-geocoder-outage` recovered its rework path.** The near-tie had been firing
   as an unrelated third warn and front-loading escalation *before* the rework budget
   could be spent — exactly the failure mode U8.2's case note predicted and picked the
   listing price to dodge empirically. Demoting it fixed the case structurally: 2 reworks,
   0.70, escalating on `budget_exhausted`. That the fix landed on a case built to work
   around the symptom is the strongest evidence the demotion was right.

### U8.5 ✅ — Pass-scoped flags (OQ-15, cut-list 2a)

Per Q4. Stamp each `Flag` with the `planner_invocations` that raised it; the Critic's
interaction checks read only the current pass; `state.plan` distinguishes *examined and
clear* from *not re-examined*. Clears the `TODO(U8)` at `critic.py:252` and
`planner.py:90`.

Review attention belongs on the skipped-agent case, not on the stamping.

---

**Stamping and the Critic filter built Aug 29, 2026, as the two commits OQ-15 itself
estimated.** OQ-16 is answered and now built too — see below, after the two commits.

**Commit 1 — the stamp.** `Flag.planner_invocations`, default 0 as a sentinel no real
pass ever produces (`planner_agent` advances `planner_invocations` to 1 before any other
node can raise anything). `DealState.flag()` bound method stamps `self.planner_invocations`
automatically for the ~40 call sites that already hold `state`; the free `flag()` function
now *requires* `planner_invocations` rather than defaulting it, so a helper that forgets to
thread it fails loudly at the call site instead of silently stamping the sentinel forever.

**Measured against Q4's estimate, and it was off by one function in a way worth
recording.** Of the six helpers Q4 named as needing a threaded parameter, two —
`_cross_check` and `_extraction_failed` — already receive `state` and needed no signature
change at all; `expand` never calls `flag()` and needed nothing either. A fourth helper Q4
could not have named, `valuation_rent._attach_metro_error`, was added by U8.4 *after* Q4 was
written and does need the parameter. Net: three helpers threaded, not six —
`extractor._resolve_geography`, `scenario_forecast._disclosure_flags` (and
`_distinctness_flags`, called from it), and `_attach_metro_error`.

**Commit 2 — the Critic filter.** `agents/critic.py`'s `_kinds` now resolves, per source
agent, the flags "as of its most recent examination": an agent present in `state.plan` this
pass is read from this pass's flags alone — its earlier ones are superseded, whether this
pass repeats or clears them; an agent absent from `state.plan` — skipped, not cleared —
carries forward its flags from the last pass it *did* run. Generalized on `state.plan`
membership rather than hardcoded to the Extractor, even though the Extractor is the only
node `_PIPELINE` ever actually skips today, so the rule does not silently stop applying if a
second step becomes optional later. A state built with no `state.plan` — every case in
`test_critic_interactions.py`, by design, since that file exercises `_interaction_objections`
as a pure function with no pass concept at all — falls back to the pre-U8.5 behavior of
reading every accumulated flag, so those tests needed no rewrite beyond the new required
argument. Clears the `TODO(U8)` at `critic.py:252`.

`agents/planner.py`'s `_geocode_is_worth_retrying` gets the same fix at the other end: it now
filters to `planner_invocations == state.planner_invocations`, i.e. the pass that just
completed, rather than the accumulated history — so a retry that resolves a geocode stops
re-triggering extraction on every later lap. Clears the `TODO(U8)` at `planner.py:90`.

**New tests, since OQ-16 (below) means the eval batch still contains no rework lap to
exercise any of this** — `tests/` is the only place it can be asserted right now, per OQ-15's
own note. `test_critic_interactions.py` gained three: the exact scenario `_kinds`'s old
docstring named (a rework that resolves the geocoder must not keep tripping I3 off the pass
it fixed), the skipped-agent carry-forward, and the supersession case that isolates which
rule is actually firing. `test_flag_propagation.py` gained one, a direct regression test for
`_geocode_is_worth_retrying`'s staleness bug. All read as meaningful against the pre-fix
code — each was checked to fail under the old accumulate-everything behavior before
confirming it passes now, not merely written to pass. All 64 tests pass; the full eval batch
was re-run and reproduces every published row exactly (7/7 baselines, 12/14 verdicts, 28/29
coverage) — expected, since no case in the batch reworks, and the confirmation that this
change is inert on every path the batch already exercises.

---

**Commit 3 — OQ-16, richer fault injection. Built Aug 29, 2026. Coverage: 28 → 29 of 29
kinds — every `FlagKind` this system defines is now raised by some case.** The architect's
answer to OQ-16 was the third option: leave `route_after_critic` unchanged (escalation still
checked before rework, unconditionally) and make the fault injection richer instead of
reordering production routing.

**The mechanism.** `EvalCase.geocoder_fallback_override: Optional[tuple[float, float]]`,
meaningful only alongside `injects=Fault.GEOCODER_OUTAGE`. `runner._case_environment` now
also patches `tools.geocoding.city_centroid` when a case declares it, forcing the outage's
fallback to a chosen point instead of the real corpus-wide `(city, state)` average — the
thing U8.2's 9-markets-x-16-configurations search established never both diverges from the
rent estimate and stays clear of a third warn or a critical, because divergence and comp
dispersion trade off directly on how thin the matching supply is at whatever point a real
centroid lands on.

**Two real defects surfaced building it, both fixed alongside the mechanism, neither
speculative — both found by actually driving a rework through the graph, the first time
anything in this project had.**

1. **`extractor._supplied_coordinates` read a previous pass's centroid fallback as if a
   caller had deliberately supplied it.** On the first rework, that reclassified
   `GEOCODER_SERVICE_UNAVAILABLE` as `GEOCODING_UNAVAILABLE` — a different kind, disclosed
   as "used as given" when the system had derived the coordinates itself — which broke
   `_geocode_is_worth_retrying`'s read of the just-completed pass (stopping a third attempt
   from ever being planned) and added a fresh unique warn to the confidence tally
   (escalating on low confidence one pass early). Fixed by restricting
   `_supplied_coordinates` to the deal's first pass: safe **given this system's one retry
   path today** — a rework only ever happens via I3's `GEOCODER_SERVICE_UNAVAILABLE`
   objection, the only retryable one that exists, and that flag is only ever raised when no
   caller supplied coordinates in the first place, so a second pass can never legitimately
   see caller-supplied coordinates. Re-check if a second retryable objection is ever added.
2. **The results-table footnote was wrong for this row before it existed to be wrong
   about.** `CaseResult.escalated_above_threshold` only ever meant "escalated on the
   critical-flag rule" until this landed — a row escalating on `budget_exhausted` alone
   would have been marked with a footnote naming the wrong reason. `eval/runner.py` gained
   `has_critical`/`budget_exhausted` properties and a second footnote marker (`‡`) so the
   table states which of the (now three) independent escalation grounds actually fired,
   rather than collapsing them under one caption.

**A third finding, not a defect: the live scorer's own non-determinism.** Chosen for the
case's reproducibility, not its substance — `scenario_forecast`'s Tree-of-Thought scorer is
not perfectly deterministic even at `temperature=0.0`, because an earlier call in the chain
(which evidence tools to pull) varies enough between live attempts to change the downstream
scoring prompt's cache key. Roughly 1 in 15-20 live attempts at a given price landed a
mirror-image pairing (rent-up/price-down vs. rent-down/price-up) close enough to tie,
raising `FORECAST_BRANCHES_NEAR_TIED` as an unrelated third warn that front-loaded escalation
before the rework budget was spent. The same non-determinism showed up organically in one
re-run of the `los-angeles` demo deal during this work (a live-tier row, so never cached) —
confirming this is a real, pervasive property of the live model rather than an artifact of
the fault injection, and that a **live**-tier baseline mismatch is not automatically a code
regression. `$640,000` on the `chicago-geocoder-outage` listing is the price that landed
clean across three replay runs; it carries no significance beyond that, and once recorded,
replay is exact regardless — the non-determinism only ever touches a fresh live call.

**The case.** `chicago-geocoder-outage` (already existed, U8.2) updated in place rather than
duplicated: `geocoder_fallback_override` set to the address's own real Census geocode
(verified live, U8.2), so the case isolates the *outage* — only the ability to verify the
address is removed, not the geography a working geocoder would have found anyway. Targets
now `(GEOCODER_SERVICE_UNAVAILABLE, REWORK_LIMIT_REACHED)`, verdict `ESCALATES`. Measured: 2
reworks, confidence 0.70 (clears the threshold — `rework_limit_reached` and
`critic_inconsistency` are both Critic-derived and excluded from the score), escalates on
`budget_exhausted` alone, reproduced identically across three replay runs. Full batch re-run:
**7/7 baselines, 12/14 verdicts, 29/29 coverage — the largest single close in the project**,
and the one U7.8/U8.10 both anticipated without being able to promise.

### U8.6 ✅ — Decision #6's numbers against the batch (OQ-1) — **scope revised Aug 29, 2026**

Per Q1, in whichever form Q1 settles. Covers `HUMAN_REVIEW_CONFIDENCE_THRESHOLD`,
`FLAG_SEVERITY_PENALTY`, `MAX_REWORKS`, and confirmation of the critical-flag rule at
`critic.py:393` — which U7 left open specifically for this run. Also re-prices, or
explicitly holds, `COMP_MAX_OUTSIDE_MATCH_SHARE` (`config.py:97`), whose `PROVISIONAL`
note names the same batch.

**The demo table must be re-derived after any number moves.**
`scripts/confidence_evidence.py` already does this in one command; a moved weight with a
stale table would republish the exact staleness U7.8 fixed.

---

**Scope revision (architect-approved Aug 29, 2026), from the first tuning pass's own
findings.** The pass ran the 14 predicted cases through a threshold/weight sensitivity
sweep instead of scoring bare agreement — the cases were designed knowing the shipped
values, so agreement alone would measure the fixtures. Findings that reshape the close:

- **The scores are quantized to multiples of the warn weight**, so the whole
  (threshold, warn-weight) space collapses to one question — *how many independent
  warn-level disclosures send a deal to a human* — and the batch measurably cannot
  distinguish any threshold in (0.40, 0.70] or warn weight in [0.125, 0.20] from the
  shipped values. The close is therefore a robustness claim ("held, with the stable
  region measured and published"), not an optimality claim.
- **The critical severity weight is behaviorally inert** — any critical flag escalates
  through the independent rule, so `FLAG_SEVERITY_PENALTY["critical"]` can never change
  a verdict. Documented as a finding; it also *confirms* the critical-flag rule's
  independence, which is what this subsection was asked to check.
- **The verdict mismatches are mostly not threshold evidence, and this plan said
  otherwise for half a day.** The first reading was "target fired, deal escalated anyway
  → tune the threshold." The architect's challenge (below) overturned it: a case sited in
  a given market *inherits that market's standing warns*, and the escalation those
  produce is usually correct on the merits. What is actually wrong is the **predicted-
  verdict derivation**, which predicts from the target flag's severity alone. Fixed here
  rather than in the threshold — see "the derivation gains the market's standing warns"
  below.
- **The New York always-escalate floor** (three standing market-level warns) is held as
  policy by the architect — and one of the three warns traced to the stale Redfin
  assumption U8.4c now fixes, so the floor drops to two warns once U8.4c lands.

**The derivation gains the market's standing warns.** A predicted verdict is still a
claim made before the run, but it is now derived from the target flag's severity **plus
the warns the subject's market raises for every listing in it** — both knowable in
advance, so the prediction stays honest while ceasing to be naive about siting. Cases
whose only "failure" was inheriting their market's floor stop reading as tuning signals
and start reading as what they are: correct escalations of a genuinely shakier estimate.

---

**Closed Aug 30, 2026, against the post-U11.3 batch. The finding is that the batch
produces no evidence the threshold is wrong — which is a real result and a limited one.**

**The batch it closes against.** 28 cases, no errors, **18/21 verdict agreement** on the
predicted set, **7/7** against U7.8's published baselines, and — after U8.6e's two
repairs — **30 of 30 flag kinds raised, none uncovered and none unreachable**. Five rows
carry † (escalated on a critical while the score alone would have reported) and one carries
‡ (escalated on the rework budget), so both independent escalation grounds are demonstrated
by rows rather than asserted.

**Every mismatch triaged, and none of them is threshold evidence.** Three of 21 predicted
cases disagree with their declared verdict. The triage rule fixed in advance says a
mismatch is a tuning signal when the target fired and the case is wrong when it did not;
applied honestly, all three turn out to be a *third* thing the rule did not anticipate —
**a gap in the prediction, not in the parameter.**

| Case | Declared | Observed | What it actually is |
| --- | --- | --- | --- |
| `chicago-five-bedroom` | reports | escalates, 0.25 | The prediction reasoned from the target's info severity. A five-bedroom subject in Logan Square returns **1 comp**, so retrieval alone raises six warns. Escalating an estimate resting on one comparable is correct |
| `cleveland-divergence-over` | reports | escalates †, 0.70 | Predicted from `straddle_probe`, which runs comps and Valuation only. The Critic then raised a critical objection those two agents cannot see. Escalating is correct |
| `la-three-bedroom-comp-drift` | escalates | reports, 0.85 | Left mismatching deliberately — see U8.6e. The divergence gate closed in front of I1, and whether it should sit there is the architect's call |

**So the derivation needs a third input, and this is the same lesson a second time.** The
scope revision above added the market's standing warns after the architect showed that
siting was being ignored. Both of the first two rows are the identical error one level
down: the prediction reasons from what a *flag* implies and ignores what the *deal* makes
inevitable. A five-bedroom subject's comp starvation and a Cleveland subject's Critic
objection are both knowable before the run — from the corpus and from
`_interaction_objections` respectively — so adding them keeps the prediction honest rather
than fitting it. **Not taken here**, because changing the derivation *and* closing against
it in one pass is how a prediction quietly becomes a transcription; it is recorded for
U8.10 to decide on.

**What that leaves for decision #6.** Zero of 21 predicted cases give evidence that 0.60
is the wrong threshold or that 0.15 is the wrong warn weight. The sweep
(`eval/results/sensitivity.md`) measures how much room that leaves: **41 of 80 grid points
decide the batch identically to the shipped configuration**, and through the shipped point
specifically, **any threshold from 0.30 to 0.70** and **any warn weight from 0.100 to
0.200** decides all 21 cases identically. Nothing here changes the shipped values — the
threshold is 0.60 and stays 0.60; the sweep asks what *would* happen elsewhere, so the
answer is how much room the shipped choice has. The dead zone on the threshold is wider
than the first pass estimated — that pass said (0.40, 0.70] on 14 cases.

Those are contiguous runs through the shipped point, not the table's extremes; the corners
do not hold together, and the script reports it that way because the union reads as a
rectangle and is not one. **The grid was extended downward on Aug 30, 2026 after the first
artifact reported its own floor as a finding** — the threshold axis started at 0.30, the
plateau ran to the bottom of it, and "every threshold from 0.30 to 0.70" read as a measured
edge when it was the edge of the search. Re-swept from 0.05: 0.30 *is* the real boundary
(0.25 changes two verdicts), so the number survived, but it had been luck rather than
measurement. `_edge_note` now says so automatically whenever a reported bound lands on the
grid boundary.

**The critical weight is inert across its entire range, including zero.** Charging a
critical disclosure *nothing* changes no verdict on any of the 21 cases, because every deal
carrying one escalates on the independent rule regardless. That is the confirmation
`critic.py`'s escalation rule was explicitly left open for, and it arrives from the
opposite direction to the † rows: those show the rule firing where the score would not,
this shows the score cannot substitute for it even in principle.

**OQ-1's surviving scoring question answered itself.** The causal pair —
`rent_anchor_county_level` as a cause of `rent_estimate_market_error_elevated` — was
supposed to be measured for double-charging. **It co-occurs on 0 of 21 cases.** The hybrid
anchor resolves at ZIP tier in every indexed market, so the county-tier flag has become
rare and the pair has stopped arising. Closed by the anchor change rather than by a
re-pricing; re-open it if county-tier anchoring becomes common again.

Combined, the honest close is:

> **Held, with the stable region measured and published.** Not "optimal" — the batch
> cannot distinguish the shipped values from a wide neighborhood of alternatives, and a
> batch that cannot distinguish two settings is saying it has no evidence either way,
> not that they are equally good.

**One thing this close cannot claim, and says so instead.** The seven demo rows are live
and not reproducible. Across three runs of the same batch this session, `coord-conflict`
escalated on a critical in two and reported without one in the third, and
`staten-island` returned 0 comps twice and 1 comp once. The regression figure against
U7.8's table is therefore noisy at ±1 row, and any future reading of it should be taken as
such rather than as a behavior change. See U8.6e.

### U8.6d ✅ — Confidence decomposition: what the score was made of

**Taken Aug 29–30, 2026 by the architect, and it is a disclosure change rather than a
scoring change — that distinction was itself the decision.** Recorded with the rejected
alternative, because the rejection is the substance.

**The observation that started it.** The confidence score does not distinguish *"this
deal has problems"* from *"our data is thin where this property is."* Four flag kinds are
properties of a **location** and fire identically for every listing there —
`rent_anchor_county_level`, `rent_estimate_market_error_elevated`,
`rent_drift_correction_unavailable`, `comps_spatially_concentrated` — while the rest are
properties of **this listing or this run**. Measured on the batch, the split is stark:
`ny-bedstuy-triplex` scores 0.55 with **every one** of its charged warns market-scoped
and *no* deal-specific reservation at all, while `chicago-five-bedroom` scores 0.25 with
almost all of its deal-scoped. Today those two are one undifferentiated number.

**Proposed and rejected: two scores with independent floors** (`deal_confidence` and
`market_coverage`, escalating on either). It was measured before it was rejected —
`ny-bedstuy-triplex` computes deal 1.00 / market 0.55, `staten-island` deal 0.30 /
market 0.55 — and the arithmetic was seductive: it would have reconciled three of the
four verdict mismatches.

**The architect's objection killed it, and it is the correct objection.** Market coverage
is not a parallel kind of doubt; **it propagates into the deal's own numbers.** Each of
the four does something to *this* estimate: elevated market error doubles its error bar
($1,048 against $524), county-level anchoring means the anchor describes a county whose
ZIP schedules span ~2x, an unavailable drift correction leaves a measured 7–26% upward
bias in place, and spatial concentration weakens the independent check on it. Scoring the
deal side alone would therefore have reported `ny-bedstuy-triplex` at **1.00 confidence
on a rent figure twice as unreliable as the report's own headline accuracy claim** — a
Transparent Degradation regression, and precisely the failure the split was supposed to
prevent. The earlier analogy to the critical-flag rule was wrong: a critical flag is
genuinely independent of the score; coverage is an *input* to it.

**Taken instead: decompose and disclose, don't split and threshold.** One score, market
flags counting exactly as they do today, and three reporting changes:

1. **Show the score's arithmetic.** Not "confidence 0.55" but what the 0.45 deducted was
   made of — e.g. *"0.45 deducted: 0.45 from data coverage in this market, 0.00 from
   this property."* A reader can currently see the flags and the score but cannot see
   the sum that connects them.
2. **Name the dominant ground in the escalation sentence**, so a reviewer knows on sight
   whether there is anything they can act on. A human asked to review "HUD publishes no
   ZIP-level schedule for this county" cannot resolve it; one asked to review "the
   listing never stated a price" can.
3. **Group the report's disclosures** into *about this property* and *about our coverage
   of this market*.

This yields everything the split was for — legibility, an ordered coverage figure,
actionable review — while changing no escalation behavior and suppressing no doubt.
**It is also independent of U11**, since it touches no estimate and no threshold.

---

**Built Aug 30, 2026.** All three changes landed, plus a fourth the work surfaced.

- **`state.FlagScope` / `scope_of()`** carries the classification. Enumerated, not
  derived — nothing about a `FlagKind` predicts this, it is a judgment about each
  disclosure's subject — and **DEAL is the default**, so a kind added later and left
  unclassified reads as something a reviewer might fix rather than something they cannot.
  That is the failure direction that wastes attention instead of hiding a limitation.
- **`ConfidenceBreakdown` and the arithmetic line.** `confidence_from_flags` keeps its
  signature and delegates to `confidence_breakdown`, so routing reads the identical number
  it always did. Measured on the fixture this decision was written about,
  `ny-bedstuy-triplex` now renders *"0.30 deducted from a starting 1.00: 0.00 from this
  property, 0.30 from how much is known about this market."*
- **The escalation sentence names its ground** (`critic._review_guidance`), quoting the
  dominant disclosure's own text — already written for this reader — rather than a flag
  name. No internal vocabulary reaches it (§8).
- **The report's disclosure list is grouped by subject**, property-scoped first, severity
  still ordering within each group and every flag still rendered in full.

**A fourth thing, found by reading a rendered report rather than the code.** The Critic
had returned `stub_nodes: [AGENT]` since U2, when half of it genuinely was a stub. U7
completed it — this module's first line has said "complete as of U7" ever since — and
nobody removed the declaration, so **every report published since U7 opened with a banner
telling its reader the analysis was provisional.** `test_report_discloses_stubbed_agents`
was asserting the defect, and its companion assertion was passing on a string that appears
elsewhere in the report for an unrelated reason. Both rewritten, and a new test checks the
whole `stub_nodes` set rather than one agent by name — which is precisely why the stale
claim survived four units.

**The one surviving scoring question is deferred to the sweep, not answered here.**
Whether de-duplicating the causal pair (`rent_anchor_county_level` is part of *why*
`rent_estimate_market_error_elevated` fires) moves any verdict is a measurement on the
final batch, and it belongs with the sensitivity sweep rather than in a disclosure commit.
OQ-1.

**One narrow scoring question survives, and is measured rather than assumed (see
OQ-1).** `rent_anchor_county_level` is a *cause* of `rent_estimate_market_error_elevated`
— county-level anchoring is part of why New York's holdout error is high — so charging
0.15 for each charges cause and effect separately. The other two are independent axes
(drift is a bias, concentration is about the check rather than the estimate). Whether
de-duplicating that one causal pair moves any verdict is a batch measurement for U8.6,
not a judgment to make in advance.

**Revised sequence for the remainder of the unit** (each line one commit or one
re-derivation; U8.6 does not close until all land, and its numbers are scored against
the *final* batch):

1. ✅ **U8.4b** — drift correction *(landed late, above; retired structurally at U11.3)*
2. ✅ **U8.4c** — NY scoping fix *(above)*
3. ✅ Re-record + batch re-derivation + docs sweep for 1–2 together
4. ✅ **U11 model probe** (see [`task_list_u11.md`](task_list_u11.md)) → architect adopted
   gradient boosting and the hybrid anchor; U11.2 and U11.4's remainder cut to §6
5. ✅ **U8.6c — near-tie split and evaluator-score disclosure** *(below)*
6. ✅ **U8.6d — confidence decomposition** *(below)*; ✅ **U8.6b — straddle pairs**
   *(below)*; ✅ flag renames off FMR (U11.3's leftover, gated the re-record)
7. Re-record + batch re-derivation for 4–6 together, then close: sensitivity sweep
   re-run against the post-change batch, verdicts re-scored, PROVISIONALs resolved,
   #6 register entry, demo table re-derived

**Steps 6 and 7 were batched into one review at the architect's direction (Aug 30, 2026),
against this file's usual one-commit-per-subsection rule.** He was away from the keyboard
and asked for fewer, larger review surfaces rather than the normal cadence. Recorded
because §8's small-commit discipline is a standing rule and this is a deliberate,
time-boxed exception to it, not a drift.

### U8.6e ✅ — What the re-record found: every objection sits behind one flag *(one open decision)*

**Not planned. Found Aug 30, 2026 by re-deriving the batch after U11.3, which is what the
re-derivation is for.** Three cases changed behavior at once and the cause is common to
all of them.

**`critic._interaction_objections` returns early unless `RENT_DIVERGES_FROM_COMPS` is in
the current pass's flag set.** That is deliberate and the reasoning is sound as written —
every interaction check is about *when the comp cross-check's verdict stops being
readable*, and there is no verdict to read when the model and the comps agree. The gate
was invisible while divergence was common. The hybrid anchor made it uncommon, and three
things fell out of the batch together:

| Case | Before | After | Why |
| --- | --- | --- | --- |
| `la-three-bedroom-comp-drift` | 0.55, escalates, critical objection | 0.85, **reports** | 6 of 8 comps still outside the band; divergence gone, so I1 never runs |
| `chicago-geocoder-outage` | 2 reworks, escalates ‡ | 0 reworks, **reports** | I3 is the *only* retryable objection, and it is behind the same gate |
| coverage census | 31 of 31 kinds raised | 28 of 30 | `rework_limit_reached` lost with the rework |

**The second row is the serious one.** §3 requires every cycle to be bounded by an
explicit counter, and `chicago-geocoder-outage` is the only case that exercises that
bound. It did not fail loudly — it returned a clean report and a passing row, and the loss
showed up as one line in the coverage census. **A case can stop testing what it was built
to test while still passing**, which is the argument for the census being a published
artifact rather than an assertion.

**Fixed by re-siting, not by weakening the check.** The case's `geocoder_fallback_override`
was built for exactly this and had drifted to the address's own geocode; it now sits at
41.900000, -87.740000, found by sweeping a 49-point Chicago grid for a fallback that
diverges **and raises nothing else** — 8 comps, 3 locations, ZIP tier, +56.1%, flag set of
exactly one info and one warn. Re-recorded: 2 reworks, escalates ‡, target fires.

**One correctness fix landed with it.** I3's premise had inverted. It argued that a
centroid fallback moves the comp set while leaving the estimate untouched, *because* the
model is location-blind below the county — and told the reader the system "produced the
same estimate it would have for any address in this county." Under the hybrid anchor the
fallback moves the ZIP, hence the anchor, hence the estimate. Both sides of the comparison
now shift. The objection says the narrower true thing instead.

---

## The open decision: should the divergence gate stay in front of I1?

**This is the architect's call and is deliberately not taken. What follows is the full
case on both sides, so the decision can be made from this file without re-deriving it.**

### What the gate is, exactly

`agents/critic._interaction_objections` opens with:

```python
kinds = _kinds(state)
objections: list[Objection] = []

# The comp cross-check is the only independent check on the rent estimate in this
# system, so every interaction below is about when its verdict stops being readable.
if FlagKind.RENT_DIVERGES_FROM_COMPS not in kinds:
    return objections
```

Everything downstream of that line — I1, I2, I3 — is unreachable unless the rent estimate
and the comp median disagree by more than
`config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT` (0.30). Since `_consistency_objections`
delegates entirely to `_interaction_objections`, **that one line gates every objection the
Critic can raise**, which means it also gates `CRITIC_INCONSISTENCY` (the only critical the
Critic produces) and `Objection.retryable` (the only thing that can start a rework).

### The argument for keeping it — which is the argument that built it

The three checks are not about the deal being bad. They are about **the comp cross-check's
verdict being unreadable**, and each one names a specific reason to distrust it:

- **I1** — the comps were widened on an attribute the model prices on, so the median
  describes a different kind of unit.
- **I2** — the comps stand on one coordinate, so the median is a point sample.
- **I3** — the comps were drawn around a fallback location, so they describe somewhere
  else.

Each of those is a reason a *disagreement* should not be read as evidence about the
estimate. If there is no disagreement, there is nothing to reinterpret, and raising a
critical objection would be telling a reader that a check they can see succeeded actually
failed. On that reading the gate is not a filter bolted on top — it is part of what the
objections mean.

### The argument for removing it

**Agreement between two mis-specified quantities is not evidence.** Take
`la-three-bedroom-comp-drift` as it now runs: 6 of 8 comparables fall outside the bedroom
or size band the search started from, the rent model prices on exactly those attributes,
and the two figures come out within 30% of each other. The gate reads that as "no problem
to report." The alternative reading is that a median describing the wrong kind of unit
agreed with an estimate for the right kind by coincidence, and the coincidence is not
reassuring.

I2 has the sharpest version of this. Decision #15 measured a single Chicago coordinate
carrying 150 listings whose rents span $760–$6,995 — a median over that is nearly
uninformative. Whether it happens to land near the model's estimate says almost nothing,
so gating the disclosure on agreement makes the disclosure fire exactly when it is least
needed.

### What changed, and why it only became visible now

Nothing about the gate changed. **The rate at which its condition holds did.** U11.3's
anchor moved `chicago-uptown-duplex` from +46.6% divergence to −6.1% on an unmodified
listing, and the same compression applies across the batch. The gate went from usually-open
to usually-closed, and three things followed:

| Case | Before U11.3 | After | Mechanism |
| --- | --- | --- | --- |
| `la-three-bedroom-comp-drift` | 0.55, escalates on a critical objection | 0.85, **reports** | 6 of 8 comps still out of band; divergence gone, so I1 never runs |
| `chicago-geocoder-outage` | 2 reworks, escalates ‡ | 0 reworks, **reports** | I3 is the only retryable objection, and it is behind the same gate |
| coverage census | 31 of 31 kinds raised | 28 of 30 | `rework_limit_reached` went with the rework |

**The second row is the serious one.** §3 requires every cycle to be bounded by an explicit
counter, and `chicago-geocoder-outage` is the only case in the batch that exercises that
bound. It did not fail loudly — it returned a clean report and a *passing* row, and the
loss surfaced as one line in the coverage census. **A case can stop testing what it was
built to test while still passing**, which is the argument for the census being a
published artifact rather than an assertion buried in a test.

### What was fixed here, and what was deliberately not

**Fixed — the case, not the check.** `geocoder_fallback_override` was built for exactly
this purpose and had drifted to the address's own real geocode. It now sits at
41.900000, -87.740000, found by sweeping a 49-point Chicago grid for a fallback that
diverges **and raises nothing else**: 8 comps, 3 distinct locations, ZIP-tier anchoring,
+56.1% divergence, and a flag set of exactly `rent_anchored_to_market_index` (info) and
`rent_diverges_from_comps` (warn). Re-recorded: 2 reworks, escalates ‡, target fires,
`rework_limit_reached` back in the census. The cost is stated in the case's own note — it
no longer isolates the *outage* from the *displacement*, because the displacement is what
carries the outage into the rework cycle at all.

**Fixed — a correctness defect the same investigation surfaced.** I3's stated premise had
inverted. It argued that a centroid fallback moves the comp set while leaving the estimate
untouched, *because* the model is location-blind below the county — and it told the reader
so, in the objection text: *"the rent model … produced the same estimate it would have for
any address in this county."* Under the hybrid anchor the fallback moves the ZIP, hence the
anchor, hence the estimate. Both sides of the comparison now shift and neither can be held
as the reference. The objection says the narrower true thing instead: both halves describe
a neighborhood the property may not be in.

**Not fixed — `la-three-bedroom-comp-drift`'s declared verdict.** It says `escalates`; it
now reports; the row is a **MISMATCH** in the results table and stays one. Editing a
prediction after seeing the run is precisely what `VerdictSource.PREDICTED` exists to
prevent, and this file would rather carry an honest mismatch than a transcribed agreement.
Its `CRITIC_INCONSISTENCY` target *was* withdrawn — that is a claim about which flags fire,
which the run answers definitively — but the verdict is a claim about what *should* happen,
and that is the open question above.

### If the gate is removed, here is what to expect

- `la-three-bedroom-comp-drift` escalates again on I1 (critical), and its mismatch clears.
- `cleveland-triplex` and `ny-bedstuy-triplex` both carry `comps_spatially_concentrated`,
  so **I2 would fire on them whether or not they diverge** — `ny-bedstuy-triplex` currently
  reports at 0.70 and would begin escalating on a critical.
- Every Cleveland deal, and every Brooklyn deal, inherits a single-coordinate comp set from
  the corpus. Ungating I2 makes a market's data density a critical objection on every
  listing in it, which is a large behavioral change and arguably the wrong instrument —
  `COMPS_SPATIALLY_CONCENTRATED` already discloses it at warn severity.
- A narrower option exists: **ungate I1 and I3, keep the gate on I2.** I1 and I3 are about
  the comp set being *wrong for this subject* (mis-matched attributes, wrong
  neighborhood), which is true independent of whether the numbers agree. I2 is about the
  median being *imprecise*, which is closer to something the existing warn already says.
  This is the option I would take, and it is a recommendation rather than a decision.

**Whichever way it goes, it needs a re-record** — objection text and flag sets both reach
the scoring prompt.

---

### Two reproducibility findings from the same investigation

**The replay tier was not reproducible, and this one was fixed rather than surfaced,
because it was a defect rather than a decision.** One case per batch run
failed with a `CacheMiss`, and **a different case each run**, which is what sent the first
investigation looking for state leakage between cases. Bisecting found a predecessor that
"poisoned" a later case — and then the same pair passed twice out of three, which is what
a flaky test looks like and what a leak does not.

The actual cause: `LLM_CACHE_MODE=replay` covers *model* calls, and the Census Geocoder is
an ordinary HTTP request. When it times out, `geocode()` correctly falls through to the
centroid and raises `GEOCODER_SERVICE_UNAVAILABLE` — which joins the flag set the
forecast's evaluator prompt embeds, changing the prompt, so the recording for it does not
exist. **A live dependency upstream of the recorded call had quietly falsified the
harness's central claim.** `tools/geocoding.py` now caches addresses to disk, committed
beside the recordings for the same reason those are committed; a timeout is never cached,
so a transient outage cannot be frozen into a permanent one. Verified over five
consecutive full replay runs, clean once the cache warms.

**The *live* tier is not reproducible either, and that one is surfaced rather than fixed —
it moved a verdict.** `coord-conflict` reported at 0.70 with no critical in one batch run
and escalated at 0.60 on a critical `supplied_coordinates_conflict` when re-run minutes
later — the Extractor's own model call varies. OQ-17 recorded this as *score* noise; this
is the first time it has been observed changing an **outcome**. It also means the census's
"`supplied_coordinates_conflict` uncovered" line, which appeared in one intermediate run,
was an artifact of a single draw rather than a coverage gap.

Whether the demo deals should be recorded like the other tiers is **the architect's
decision, and it has a real cost on both sides**: they are the live end-to-end evidence,
and recording them removes exactly the property that makes them that. The narrower option
is to keep them live and state the noise band beside the regression figure — across three
full batch runs this session, `coord-conflict` varied by one critical and `staten-island`
returned 0 comps twice and 1 comp once, so "7/7 against U7.8's table" should be read as
±1 row rather than as an exact match.

### U8.6b ✅ — Straddle pairs: measuring brittleness at the per-flag thresholds

**Taken Aug 29, 2026 by the architect, over a schedule-based deferral recommendation —
recorded because the overrule is part of a pattern he has named.** The confidence
threshold's dead zone means verdict-deciding lines live in the *per-flag* thresholds
(they decide whether the third warn fires), so rigidity is measured there: pairs of
near-identical fixtures either side of each line, published as a brittleness section in
the results artifact — how much does a deal have to change to change its verdict.

| Tunable | Straddle pair | Feasible? |
| --- | --- | --- |
| `COMP_MAX_OUTSIDE_MATCH_SHARE` (0.25) | 2-of-8 vs 3-of-8 comps outside the band | Yes — vary subject sqft |
| `COMP_MIN_DISTINCT_LOCATIONS` (3) | NY geography is a natural control: Brooklyn (87 of 89 corpus rows on one coordinate) vs Manhattan (161 rows, 60 coordinates) | Yes — doubles as the NY-floor fixture |
| `RENT_COMP_DIVERGENCE_THRESHOLD_PCT` | `chicago-uptown-duplex` measures 48% (far side); build the near-side sibling | Yes — vary ZIP rent level |
| `MIN_QUALIFYING_COMPS` (8) | A siting returning exactly 7 vs 8 comps | Probably — corpus-determined |
| `RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD` (1.5) | **Not straddleable by any deal** — markets sit at ≤1.1x and 2.0x; a listing cannot move its market's ratio | Documented as such |
| `TOT_TIE_EPSILON` (0.05) | **Not meaningfully straddleable** — the gap is noise-dominated (OQ-17); a recorded straddle measures the recording | Documented as such |

---

**Built Aug 30, 2026.** `scripts/straddle_probe.py` sites the pairs by running the real
comp-retrieval and Valuation agents over a grid — the two agents that produce every
quantity a per-flag threshold is compared against, and the two that make no model call, so
a full sweep is free. Six fixtures added; the table above scored four rows and got three
clean pairs and one instructive failure.

| Tunable | Pair, as built | Measured |
| --- | --- | --- |
| `COMP_MAX_OUTSIDE_MATCH_SHARE` (0.25) | Chicago Uptown, 1,100 vs 1,300 sq ft | 2-of-8 (0.25, clears) vs 3-of-8 (0.38, fires). Exactly one flag differs |
| `RENT_COMP_DIVERGENCE_THRESHOLD_PCT` (0.30) | Cleveland, 1,000 vs 1,050 sq ft | **−30.8% vs −28.9%**. Same coordinate, same eight comps, none out of band — a **5% floor-area change flips the flag**. The tightest pair in the batch |
| `COMP_MIN_DISTINCT_LOCATIONS` (3) | Bed-Stuy vs Hell's Kitchen | 8 comps on **1** coordinate vs 8 on **5**. Needed no engineering at all — the corpus's own distribution supplies both sides |
| `MIN_QUALIFYING_COMPS` (8) | Bed-Stuy vs northern Bronx | 8 vs **7** — and **not a clean pair**, see below |

**Three corrections to the table above, all in the direction of the planned pair being
wrong rather than infeasible.**

1. **`RENT_COMP_DIVERGENCE_THRESHOLD_PCT`'s far side moved out from under it.**
   `chicago-uptown-duplex` measured 48% when this was written and measures **−6.1%** now:
   the hybrid anchor moved it 53 points. The pair was rebuilt in Cleveland, and the
   Chicago case was retargeted as a second control rather than re-engineered — see
   `eval/cases.py` for why re-sizing it would have destroyed the only thing it was worth.
2. **`COMP_MIN_DISTINCT_LOCATIONS` no longer "doubles as the NY-floor fixture."** The
   New York floor was three standing market warns, then two after U8.4c, and is **one**
   now that the county-anchoring warn is gone. The pair still works; the second job it
   was given no longer exists.
3. **`MIN_QUALIFYING_COMPS` is not independently straddleable, and this is a measurement
   rather than a shrug.** A 144-point grid across the four indexed markets returned
   exactly 8 comps at **98** points, 0 at 30, and 7 at **none**; a finer 324-point scan
   found real 7-comp sitings, one of which (1500 E 233rd St, Bronx) is now a fixture. But
   reaching 7 *requires* the retrieval loop to exhaust its radius expansions and its match
   relaxations first, so the case necessarily carries four extra disclosures its partner
   does not. The threshold is the terminal state of a loop whose earlier steps each raise
   their own flag — it cannot be varied alone. Kept as a case, published as a negative
   result.

### U8.6c ✅ — Near-tie split, and the evaluator's scores reach the reader

**Taken Aug 29, 2026 by the architect.** `FORECAST_BRANCHES_NEAR_TIED` turned out to be
two different disclosures sharing one kind, and the reading path shows they deserve
different severities:

- **Pairing near-tie (depth 2) → INFO.** With `TOT_BEAM_WIDTH = 3` over nine pairings,
  both tied candidates survive into the reported scenario set, labels are assigned by
  projected outcome (not score rank), and band provenance comes from the framing every
  pairing shares — so the ordering the tie-break resolves never reaches anything a
  reader sees. It is also measured with an instrument whose single-draw noise (OQ-17:
  0.05→0.95 swings on identical calls) exceeds the 0.05 epsilon by an order of
  magnitude. Message rewritten to stop claiming the ordering matters, and to say the
  gap is one sample's reading.
- **Framing near-tie (depth 1) stays WARN.** `TOT_FRAMING_BEAM_WIDTH = 1` means the
  losing framing — a whole reading of the data — is discarded on a tie-break. The beam
  width itself was revisited at the architect's request and held: the observed defect
  that motivated it (a +19.03%/yr "optimistic" case from an unscreened framing printed
  beneath a basis block claiming screening) and the one-provenance report contract both
  stand. The upgrade is disclosure, not selection: when the tie fires, compute what the
  losing framing's base case would have projected and render the delta — the flag text
  already promises the ledger holds "what it would have implied", and today nothing
  computes the implication.
- **`Scenario.evaluator_score` is rendered.** Populated for every reported scenario
  (`scenario_forecast.py:621`), carried through state, and never rendered — the
  evaluator's credibility judgment across the three scenarios is known and invisible.
  Rendered per scenario with the OQ-17 caveat (a score is one sample of a noisy judge).
  Labels stay outcome-based; reordering by score would break the bracket semantics.
- **The tie measurement gains the depth-2 cut boundary (#3 vs #4)** — the one rank line
  where ordering *is* load-bearing (which pairing makes the scenario set at all), and
  today unmeasured.

---

**Status audited Aug 30, 2026 at the architect's request, and this subsection does not
pass. Two of four items landed; two never did.** Recorded because it was carrying an
implicit ✅ it had not earned — the *first* bullet is the one everything downstream cites,
so the section read as done.

| Item | Status | Evidence |
| --- | --- | --- |
| Pairing near-tie → INFO, framing near-tie stays WARN | ✅ | `scenario_forecast.py` raises `FORECAST_BRANCHES_NEAR_TIED` at `Severity.WARN` for the framing tie and `Severity.INFO` for the two pairing ties. This is what moved the `chicago` demo deal off its 0.55 escalation |
| Both messages rewritten to stop overclaiming | ✅ | The pairing message now says both tied candidates reach the scenario table and no reported figure depends on the ordering |
| **`Scenario.evaluator_score` rendered** | ✅ **built Aug 30, 2026** | Was: populated at `scenario_forecast.py:621`, carried at `state.py:699`, and `grep evaluator_score agents/summarizer.py` returned nothing. Now rendered per scenario in `_scenario_section` |
| **Depth-2 cut boundary (#3 vs #4) measured** | ✅ **built Aug 30, 2026** | `tot.SearchResult.cut_boundary_gap_by_depth`, disclosed at INFO when the cut lands inside `TOT_TIE_EPSILON` |

**Neither gap is a regression — they were never built** — and neither is blocked by
anything. Rendering the score is small: a per-scenario figure in
`summarizer._scenarios_section` with the OQ-17 caveat beside it, labels left outcome-based.
The cut-boundary measurement is a probe rather than a product change.

---

**Both built Aug 30, 2026, and the measurement found something the plan only suspected.**

**1. The scores reach the reader.** `_scenario_section` renders each surviving scenario as
`**Base** *(scored 0.80)* — rationale`, with one paragraph beneath saying what the number
is, that the labels come from projected outcome rather than from it, and that a single
draw of this judge is not a rank (OQ-17). Put with the rationale rather than in the table
because the score is a judgment *about* that rationale, and because the branch ledger
below already renders every discarded hypothesis as `id (score) — summary` — so a survivor
now reads the same way as the branches that lost.

**2. The cut boundary is measured, and it is not the number the plan expected to find.**
`tot.beam_search` now records, per depth, the margin at the line the beam width actually
cut on: last survivor minus best-discarded. That is a different question from
`score_gap_by_depth`, which compares #1 against #2 *among survivors* — the comparison
U8.6c's own demotion argument shows is inert, since both of those reach the report.

**The margin is frequently zero or negative**, which the plan did not anticipate and which
is the finding. Measured across the 15 golden cases, the depth-2 cut margins run
`-0.05, 0.00, 0.05, 0.20, 0.25` and similar. A **negative** margin means the discarded
pairing *outscored* the one that reached the report and lost on `tot._rank`'s conservatism
tie-break. `chicago-uptown-band-under` is the clean illustration, and both halves of it are
now visible in the same report: the ledger shows `f-01-optibase` **scored 0.60, discarded**
while the reported "Pessimistic" scenario **scored 0.55**. Before this change a reader
could see both numbers and had no way to learn why the lower one was kept.

So the disclosure says the specific true thing rather than a generic tie sentence — it
branches on the sign, because "separated by 0.050, inside the 0.05 threshold" would be
self-contradictory *and* weaker than the truth in the case that actually occurs.

**Severity: INFO, and it is a judgment rather than a fact.** The argument for WARN is the
framing tie's: a discarded candidate is a real loss. The argument for INFO, taken here, is
that the discarded pairing is already published in the ledger with its score and its prune
reason — so this names a margin the reader can already see rather than revealing a hidden
one — and that the gap is measured with the instrument whose single-draw noise (OQ-17)
exceeds `TOT_TIE_EPSILON` by an order of magnitude, which is the same argument that
demoted the pairing tie in the first place. **It is a one-word change if the architect
prices it differently**, and the code comment says so at the site.

**Measured consequence on the batch, which is bounded and was checked rather than
assumed.** The new disclosure fires on 6 of 15 golden cases and 3 of 6 replay cases
(`chicago-geocoder-outage` once per pass, as every forecast flag is). INFO costs 0.00
confidence, so **no confidence score, no verdict and no coverage figure moves** — golden
verdict agreement stays 12/15 and replay 6/6, with the same three mismatches. The only
change to the published table is the disclosure count on those rows.
`eval/results/results.md` is **deliberately not republished here**: re-deriving it means
re-running the seven live rows, which U8.6's own close records as non-reproducible at ±1
row, so the table is re-cut once with the next change that needs it rather than spending a
live run on a column of INFO counts. The delta is measured above, so nothing about it is
unknown.

**Replay was verified clean.** A forecast flag's kind reaches the *next* pass's scoring
prompt through `_context_block`'s upstream-flag list, so a new kind on a reworking case
could have invalidated recordings. `forecast_branches_near_tied` was already in that set
for `chicago-geocoder-outage`, so the prompt string is unchanged and all six replay cases
reproduce with no `CacheMiss`. Checked rather than reasoned about.

**Tests:** `tests/test_forecast_tie_disclosures.py` — the cut margin is recorded distinctly
from the top-two gap, a cut taken inside a tie group records a non-positive margin, both
message branches, silence when the cut is decisive, and the two rendering cases (a scored
scenario and one carrying no score). Kept out of `test_flag_propagation.py` on
`test_stated_rent_disclosure.py`'s precedent: nothing here decides anything. 73 tests pass.

**How this went unnoticed is the part worth keeping.** The severity split had visible
downstream consequences — a demo deal's verdict changed, several documents cite it — so the
subsection accumulated references that all pointed at its *first* bullet. Nothing pointed
at the last two, and a section with four bullets and two citations reads as finished. The
checkbox audit that found it was prompted by the architect asking whether U8.2 and U8.3
were really done; those two were, and this one was not.

### U8.7 🟨 — Checks A and B, and `config.py:413` — **the veto fired, then its premise expired**

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

---

**Re-measured Aug 30, 2026 — and the veto's own premise is gone, so the branch is open
again rather than closed.** This subsection was right to insist on re-measuring rather
than assuming, and the instruction paid off in the opposite direction to the one it
expected.

**What the veto rested on.** The gap was **~−29% on all three demo listings** — Los
Angeles −28.8%, Chicago −29.0%, Staten Island −26.8% — a near-constant. A constant is what
a *structural* offset looks like, and the structure was identifiable: the estimate was
`ratio × FMR`, FMR is a 40th-percentile administrative rent, and the corpus the model
learned from rented at ~1.40x it. An objection raised from that would have blamed the
listing for the anchor's percentile.

**What it measures now**, across the 13 eval fixtures carrying independently-set rents:

| | |
| --- | --- |
| mean | **−11.4%** |
| median | **−9.7%** |
| range | **−39.4% to +66.6%** |

**Dispersed, and sign-varying.** That is what a property of the *deal* looks like. The
anchor is a market rent index now, so the percentile mismatch that made this untunable no
longer exists, and the reason U7.5 declined to promote the check has been removed.

**The full measurement**, per fixture, so the distribution can be read rather than
summarized. Every row is a fixture whose stated rents were set independently of the
anchor; `gap = (mean stated rent − modelled rent) ÷ modelled rent`.

| Fixture | Stated | Modelled | Gap |
| --- | --- | --- | --- |
| `la-three-bedroom-comp-drift` | $3,350 | $2,011 | **+66.6%** |
| `la-ordinary-duplex` | $2,250 | $2,046 | +10.0% |
| `cleveland-divergence-over` | $1,125 | $1,206 | −6.7% |
| `cleveland-triplex` | $1,075 | $1,155 | −6.9% |
| `chicago-uptown-band-over` | $2,275 | $2,486 | −8.5% |
| `chicago-uptown-band-under` | $2,075 | $2,293 | −9.5% |
| `cleveland-divergence-under` | $1,175 | $1,301 | −9.7% |
| `chicago-uptown-duplex` | $1,825 | $2,154 | −15.3% |
| `ny-manhattan-dispersed` | $3,500 | $4,828 | −27.5% |
| `ny-bedstuy-triplex` | $2,583 | $3,708 | −30.3% |
| `ny-wakefield-seven-comps` | $2,250 | $3,284 | −31.5% |
| `chicago-five-bedroom` | $3,250 | $5,326 | −39.0% |
| `chicago-uptown-oversized` | $2,500 | $4,128 | −39.4% |

**n = 13 · mean −11.4% · median −9.7% · range −39.4% to +66.6%**

**Read the shape, not just the summary.** Three things in it matter:

- **The sign varies.** Under the old anchor every demo deal was negative and clustered
  within 2.2 points of each other. A quantity that changes sign across fixtures is a
  property of each deal.
- **The tails are explainable, individually.** The +66.6% outlier is the case engineered so
  the comp set drifts onto the wrong unit type. The −39% pair are the two oversized
  subjects, where the model extrapolates past the corpus's ordinary footprint. The New
  York cluster near −30% is the market whose per-metro error is 1.9x the headline. **None
  of those is the anchor, and all of them are things a threshold might legitimately want
  to catch.**
- **The middle is tight.** Seven of thirteen sit between −16% and +10%. A threshold in the
  25–35% region would fire on the tails and stay quiet on the middle, which is the shape
  of a usable disclosure rather than a constant offset.

**Three things follow, and only the first two are mine to land.**

1. **The false claims are corrected wherever they were stated as fact** —
   `config.RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD`'s comment,
   `summarizer._stated_rents_section`'s docstring, and the direction-dependent caveat the
   report prints, which argued from the dead offset in the reader's own text. The caveat
   stays direction-dependent for a narrower and still-true reason: a sitting tenant's rent
   lags the market wherever leases were signed earlier or renewed below it, and an
   above-market claim has no benign default explanation.
2. **The demo deals cannot answer this and that is a finding about them.**
   `DemoDeal.rent_basis` is `hud_fmr:2` — #11 set their stated rents *from* the old
   anchor — so their gap measures the FMR-versus-market spread by construction. **#11's
   calibration is now stale on the rent side as well as the price side**, which was not
   previously on anyone's list. It is why the table above uses the eval fixtures instead:
   their rents were chosen to look plausible for the unit, not derived from the anchor.
3. **The decision is the architect's and is deliberately not taken.** Shipped behavior is
   unchanged either way — the constant stays `None`, the comparison stays a disclosure —
   so nothing is blocked while it waits. What changed is that the *reason* is now honest
   rather than citing a dead offset.

### The open decision: what to do with the stated-rent comparison

**All three options below were closed before Aug 30, 2026 and all three are open now**, so
the choice is genuinely live rather than a formality.

**Option A — set a threshold.** Emphasize the gap in the report when it exceeds some
percentage. The measurement now supports placing one: the middle of the distribution is
tight and the tails are individually explainable. **Cost:** it is a number chosen against
13 fixtures, and §8's three-question check exists to catch exactly that. Mitigated by the
fact that it gates *emphasis*, not a flag or a verdict — the comparison is rendered either
way, so a badly-placed threshold makes a paragraph bolder, not a report wrong.
**Cheapest, and reversible.**

**Option B — delete the constant, keep the disclosure unconditional.** This was U8.7's
original plan, taken when the gap was structural and a threshold would have been
meaningless. **That justification is now gone**, so deleting it would be shedding an option
the evidence just made usable. Recommend against — this is the one option the
re-measurement argues *away* from, which is worth noting because it is what this
subsection previously said it would do.

**Option C — promote the comparison to a Critic objection.** U7.5 declined this only
because the gap was structural, and Q5's veto branch fired on the same reasoning. Both
premises are gone. **Cost:** a new flag kind, a re-record, and a real behavioral change —
an objection escalates. It also needs a decision about severity, and about whether a
*low* stated rent (the common direction, with a benign explanation) should count the same
as a high one, which the report's own caveat says it should not.

**My recommendation, for what it is worth: A, with the threshold placed above the middle
cluster and stated as provisional against 13 fixtures.** It converts a re-measurement into
something a reader sees, costs no re-record, and leaves C available once the demo deals are
re-calibrated off the market index and can contribute independent rows.

**What would make this decidable on better evidence:** re-calibrating `demo_deals.py`'s
`rent_basis` from `hud_fmr:2` to the market-index anchor. That adds six independent
observations and removes the one source in the project whose gap is circular by
construction. It is small work and it is not scheduled anywhere — flagged here rather than
left in conversation.

### U8.8 🟨 — Public-record sub-metro price benchmark (OQ-7, #11) — **spike done, ingest unbuilt** — drop-dead Mon Sept 1

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

---

**Spiked Aug 30, 2026, two days ahead of the drop-dead. Feasible for two metros of three,
and the risk this subsection was scheduled around is not the one that bit.**

**Q3's unbounded cost is not on the critical path, and the reason generalizes.** Q3 priced
this as an address-to-parcel join — "the same class of work that produced U3's geocoding
tier fallbacks, and bounded only if the join works first try." That prices the *original*
specification. The respecified deliverable is a sub-metro **benchmark**, which needs an
aggregate over the subject's ZIP, not a match to the subject's parcel. No fuzzy address
matching is required by any of the three sources. This is the third time in this unit a
cut-list cost has been found to describe work the item no longer contains — §6's own
lesson from item 2a, applied again.

| Metro | Route | Sale price? |
| --- | --- | --- |
| **NYC** | `w2pb-icbu` — `zip_code`, `latitude`, `longitude`, `total_units`, `building_class_category`, `sale_price`, all in one table | ✅ |
| **Cook** | `wvhk-k5uv` (sales) → `nj4t-kc8j` (parcels: `zip_code`, `lat`, `lon`, `class`) on an **exact `pin`** | ✅ |
| **LA County** | Roll data has `Units`, `Bedrooms`, `SQFTmain`, `SitusZIP5`, `CENTER_LAT/LON` — but **no sale price**, only `Roll_LandValue` / `Roll_ImpValue` / `Roll_TotalValue` | ❌ |

**Measured against the real fixture ZIPs:** Bed-Stuy 11216, 402 multi-family sales since
2023, median **$1,750,000**; Tottenville 10307, 152 sales, **$1,054,490**; Logan Square
60647, 6,248 class-211 parcels and 864 sales, **$735,000**; Uptown 60640, 189 sales,
**$850,000**.

**Los Angeles keeps the Redfin metro median, disclosed per-market.** California assessor
rolls publish assessed value, not transaction price. A Prop 13 base-year value approximates
a sale price *at the base year* and is systematically stale for long-held parcels — a
different instrument, and not one to substitute silently. Partial coverage with a stated
reason is the same pattern U8.4b's drift correction already uses.

**One consequence to write up rather than fix: this will make every demo deal look like a
bargain, and that is #11's calibration showing through.** #11 set the demo asking prices
*from the Redfin metro median* — the benchmark being replaced. Against its own ZIP,
`chicago` at $499,000 sits 32% below Logan Square's median and `ny-bedstuy-triplex` at
$1,050,000 sits 40% below Bed-Stuy's. The figures stand as committed and `demo.md` says
why, which is the call U8.4c made when Staten Island's $875,000 was re-benchmarked.

**Recording-safe, verified rather than assumed:** nothing flags on the benchmark value
(checks A and B were not promoted at U8.7) and `scenario_forecast._context_block` does not
carry it, so no prompt changes and no re-record. The ingest itself is not yet built.

### U8.9 ✂️ — Absorbed U10: live runs, traces, diagram, screenshots — **dropped Aug 30, 2026**

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

### U8.10 ⬜ — Close-out

Review the changelog rows this unit's commits already wrote; move #6 and #11 to their
settled state in §7's register with reasoning in
[`history/decision_log.md`](../history/decision_log.md); delete the closed entries from
[`open_questions.md`](../open_questions.md) — and, where a question is *retargeted* rather
than closed, say so with its reason, per U7.8's precedent.

**Carries U11.5 with it**, by the architect's direction (Aug 30, 2026): U11's rename pass
left the rent model's own prose and identifiers on the retired FMR vocabulary, and one
reader-facing string still calls the estimator a linear regression. Documentation and
naming, one artifact-key exception, scoped in full at
[`task_list_u11.md`](task_list_u11.md) §U11.5 — batched here so the two documentation
passes are one review rather than two.

**Five open questions can close here** — OQ-1 (#6 tuned), OQ-3, OQ-6, OQ-15, and OQ-7
either as built or as a written gap. **OQ-12's first half does not close** (Q2(b)): its
leave-one-metro-out run is a transfer question that U8.4's flag does not ask. Its second
half — confirming something still trips the rent-comp divergence flag — closes at U8.2. That would be the largest single
close in the project, which is also the reason to review each one against what actually
shipped rather than against this plan.

### U8.M 🟨 — Maintenance *(separate commit, per §8)*

Clear the `TODO(U8)` markers this unit resolves, and the ones Q5 closes by deletion rather
than by measurement. Update the `TODO` inventory table in
[`design/engineering_standards.md`](../design/engineering_standards.md).
