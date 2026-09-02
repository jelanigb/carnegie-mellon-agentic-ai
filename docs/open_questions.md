# Open Questions

**Everything unresolved, and nothing else.** Closed decisions are in
[`implementation_plan.md`](implementation_plan.md) §7 (the register) and
[`history/decision_log.md`](history/decision_log.md) (the reasoning). This file is loaded
at the start of every session, so it is kept short on purpose — an entry that closes gets
**deleted** from here and its verdict written into the §7 register, not struck through.

**Grouped by the part of the system it affects.** Each entry names the unit that must
close it and what closing it looks like. `OQ-n` numbers are stable handles for
conversation; they are not decision numbers.

Last reviewed: Aug 30, 2026 — at U8's close-out
([`tasks/task_list_u8.md`](tasks/task_list_u8.md) §U8.10).

**Six entries closed there and two areas emptied.** *Orchestration & control flow* and
*Data & sources* now carry nothing open: OQ-1 closed as #6, OQ-15 and OQ-16 as U8.5's build,
OQ-7 as #11 and U8.8's benchmark, OQ-3 as U8.4's per-metro disclosure, and OQ-6 as #20 plus
U11.3's anchor. OQ-12 was folded into OQ-4 so the transfer question has one owner. Two
entries were **retargeted rather than closed** — OQ-5 to U9, OQ-18 to no unit — and each
says why at the entry. Two are new, both opened by U8 and both live decisions rather than
deferred work.

**Documentation audit, Aug 31, 2026 — no entries closed, one gap surfaced.** A prose
cross-check of `task_list_u7.md`, `task_list_u8.md`, `task_list_u11.md`,
`maintenance.md` and `changelog.md` against the code found no discrepancy in anything
already ✅ or already tracked here — this project's own audits (U8.6c, U8.6b, U11.5) had
already caught what there was to catch. One thing wasn't previously written down: OQ-20's
tier-flag argument (below) has an expiry condition with no independent trigger, now noted
at the entry. Two `maintenance.md` items (M1, M2) were reconfirmed still open and two more
(M4, M5) were added there — the §6 unit table omits U8.9's drop and carries no row for U11
at all, despite U11 being closed.

---

## Rent & valuation

### OQ-19 · U11.3 — is the rent-to-market-index ratio stable over seven years?
**Raised Aug 30, 2026, when the anchor moved.** The model learns how a unit's rent
compares to its ZIP's typical rent from 2018-19 listings, then applies that ratio to
today's index. U8.0 measured the *old* anchor's assumption and found it false (FMR drifted
18 points from the market); the new one has a much stronger prior — numerator and
denominator are both market rents for the same ZIP — but **it has not been measured over
the interval that matters, and cannot be**: that needs current-vintage rents for
individual units, which this project does not have.

**Bounded rather than open.** `scripts/anchor_stability.py` falsifies it cheaply over the
corpus's own 13-month window and it survives: **+3.6%** cost to extrapolating in time
(within-metro, so geography is held constant), and a **6.3%** peak-to-trough spread in the
monthly ratio across the four months carrying 97% of the rows. Cleveland is the weakest at
+15.9% and also the thinnest in month coverage. **That is a floor the assumption clears,
not a demonstration that it holds for seven years**, and the report should say so in those
terms. **Closes when** a current-vintage rent sample exists to test it directly — no such
source is in scope before the freeze.

**One property of the training data surfaced by this and worth carrying:** the corpus is
not a uniform time series. 3,825 of 5,701 rows share a single listing month, and the metro
mix shifts 51 percentage points between the window's halves — so any future temporal
analysis of it must hold geography constant or it will measure the scrape's schedule
instead. `config.py`, `tools/model/rent_model.py`.

### OQ-20 · no unit — check B was never separately decided, and the benchmark's tier flag waits on it
**Two questions, in order, because the first gates the second.** Raised Aug 30–31, 2026 at
U8.8 and U8.10.

**What "check B" is.** One of the six cross-agent pairs enumerated in
[`tasks/task_list_u7.md`](tasks/task_list_u7.md) Q1: **the listing's asking price
(`deal_terms.price`, Extractor) against the market benchmark
(`ValuationDetail.benchmark_median_sale_price`, Valuation).** Its sibling, **check A**, is
the listing's *stated rents* against the modelled rent. U7 Q4 shipped both as **Summarizer
disclosures rather than Critic objections** — rendered as prose, raising no flag and moving
no verdict — and scheduled promoting them to U8.

**Check A closed on measurement as #20. Check B closed only by inheritance, and that is the
gap.** U8.7 measured *A* (`scripts/stated_rent_gap.py`, 13 fixtures) and held it as a
disclosure on a specific finding: every fixture a 20–35% threshold would fire on already
carried a flag naming a more specific cause. The phrase "checks A and B" then carried B
along with it — the code at `valuation_rent._attach_benchmark` now says "check B was not
promoted at U8.7" — but **no measurement of B was taken and no decision about B was
recorded.** #20's register row is about the stated-rent comparison alone.

**What closing check B would take, in order:**

1. **The measurement that does not exist** — the B analogue of `scripts/stated_rent_gap.py`:
   each fixture's asking price against its own ZIP benchmark, printed beside the flags the
   report already raises and beside the fixture's declared price basis. Every input is
   committed (`tools/data/zip_sale_benchmarks.json`), no model calls, so it costs roughly
   what A's script cost.
2. **A confound worse than A's, which that measurement has to survive.** #11 set the demo
   and eval asking prices *from the Redfin metro median*, and U8.8 replaced the comparison
   basis with the **ZIP** median. So the measured gap is now mostly *(metro median − ZIP
   median)* for that ZIP, plus whatever the deal itself carries — and the first term
   dominates: ZIP 60640 runs **77% above** the Chicago metro, which is why
   `chicago-uptown-duplex` reads 39% cheap while nothing about the property is unusual.
   A threshold fitted to that would bury #11's calibration inside a production constant,
   which is the class of error U7 Q4 refused for A. The one fixture carrying a
   deal-specific signal is `overpriced`, whose `price_premium_to_basis` is a **declared**
   +55%.
3. **The likely outcome, stated in advance so the measurement can falsify it** rather than
   confirm it: B closes as a disclosure like A did, but for a *different* reason — A's
   threshold would have restated an existing flag, B's would restate #11's calibration.
4. **What would change the answer:** asking prices set independently of the benchmark —
   either fixtures declaring an offset from their **ZIP** figure (the `overpriced` pattern,
   repointed), or real listings, which §8 excludes. The first is cheap and is the only route
   inside the freeze.

**The dependent half — should the benchmark's *tier* raise a flag?** The rent anchor
discloses its own grain: `rent_anchor_county_level` fires at warn when it resolves coarser
than ZIP. The **sale-price benchmark** — `ValuationDetail.benchmark_median_sale_price`, the
figure U8.8 made ZIP-level for New York and Chicago and left metro-level for Los Angeles and
Cleveland — has the same two tiers and discloses which it used **in prose, without a flag**.

**Why not, as argued at `valuation_rent._attach_benchmark`:** a coarse rent anchor
*propagates* — into the estimate, the forecast, and the comp cross-check — while **nothing
computes from the sale-price benchmark.** It is printed beside the asking price and read by
a human. Charging confidence for the width of a figure that enters no calculation would tell
the reader this deal's numbers are shakier when none of them moved.

**That argument expires the moment check B is promoted**, because the benchmark then becomes
an input to a check and its grain starts deciding an outcome. And promotion would need a
rule *first*, not after: Los Angeles and Cleveland have **no ZIP tier at all**, so B would
compare an asking price against a metro-wide median in half the inference set. **Closes
when** check B is decided — as a disclosure with its own measured reason, or as an objection
with the tier rule that promotion requires. Recorded here rather than left in a docstring
because an argument with an expiry condition is one nobody re-reads on the day it expires.
`agents/valuation_rent._attach_benchmark`, `agents/critic._consistency_objections`,
[`tasks/task_list_u8.md`](tasks/task_list_u8.md) §U8.7–U8.8.

**Documentation audit, Aug 31, 2026: the coupling has no independent trigger.** Both
halves — check B's own measurement and the tier-flag question — still share no owner and
no unit. The tier-flag argument's stated expiry ("the moment check B is promoted") isn't
wired to anything: a future unit that promotes check B without also re-reading this entry
could leave the expired argument standing uncorrected in `_attach_benchmark`'s docstring.
No code follows from this — it's a reminder that closing check B has to include revisiting
the tier-flag half, not a separate question.

### OQ-22 · U9.3 — the forecast's pairing search rests on a relationship too weak to support it
**Raised Aug 31, 2026 at U9.3, and it is what is *left over* after #21 rather than what #21
fixes.** The Tree-of-Thought's depth-2 level exists to choose which rent band to pair with
which price band, and the evidence it reasons from is the measured rent/price growth
correlation. Re-measured across three passes (`scripts/growth_correlation.py`), **r² never
exceeds 0.10** — 4% to 10% of variance — and the *sign* flips depending on which rent series
is used and which market is examined.

**#21 stops the evaluator being told something false.** It will be told the relationship is
weak, sign-unstable, and not a basis for preferring anti-correlated pairings. **What it does
not answer is whether a pairing search should exist at all** when its governing relationship
is this weak: a level that enumerates nine combinations and keeps three, on a signal that
explains under a tenth of the variance, may be reasoning about noise.

**#21 made this sharper rather than milder, and that is the honest framing.** Before #21 the
level had a clear decision criterion — prefer anti-correlated pairings — which was wrong.
After #21 it has no directional prior at all, and scores nine candidates on flags, band
widths and sample sizes. The false criterion is gone and **nothing replaced it.**

**The closing condition first written here was unreachable** — "a longer panel, or a rent
series matched to multi-family" — neither of which this project will acquire, which made
this an entry that could never close. **Restated and decided Aug 31, 2026 by the architect:
depth 2 ships as-is with #21's corrected instructions, and the re-purposing below is adopted
as the answer, deferred on schedule rather than left open.**

**What ships now.** The nine-way enumeration, beam of 3 with a reserved base/base slot, and
an evaluator told the relationship is weak and supports no directional rule. **This is
knowingly thin** — a level that enumerates nine and keeps three on grounds that explain
under a tenth of the variance — and the final report should describe it that way rather than
as settled reasoning.

**What it becomes.** Stop asking *which pairing is most likely*, which needs a joint
distribution this data cannot supply. Ask instead: **which projections does this deal's
evidence support showing, and how wide should the starting point be?** The bands describe
what the *market* did; the deal's evidence describes how far to trust the *estimate the
projection compounds from*, and depth 2 ignores the second entirely today:

| | `los-angeles` | `staten-island` |
| --- | --- | --- |
| Rent estimate | $2,861 **±$509** | $2,654 **±$855** |
| Comps | 8, all ZIP-anchored | **0** |
| Comp cross-check | implies $2,875 — **1% away** | **not run** |
| Anchor | ZIP 90026 | **county-wide** |

Both get the same three growth bands today, and both are projected five years forward with
equal apparent confidence. Re-purposed: `los-angeles` projects the bands from the point
estimate because eight comparables corroborate it within 1%; `staten-island` projects from
the **edges of its error band**, or declines the optimistic case as unsupported, because
nothing checks it and the anchor is county-wide.

**Deal-specific, grounded in evidence already in the evaluator's prompt, and needing no
correlation at all** — which is exactly what makes it survive #21.

**Why it is deferred rather than built.** The prompt changes from *"score this pairing's
plausibility"* to *"score what this evidence supports showing"*; the candidate payload gains
a starting-point treatment beside `(rent_band, price_band)`, so `_pairings` and the scenario
assembly both change shape; `Scenario`/`ForecastDetail` need a field for it; and everything
re-records. That is a full change set of **new design** inside a five-day window, against a
unit already estimated at seven of twelve landing.

**Closes when** the re-purposing is built, or when a later pass decides the pairing level is
not worth its evidence and deletes it in favour of forecasting the two series independently.

**Its real subject is broader than the forecast.** Only two agents in this system call a
model, and #12's Critic half was retired on evidence at U7.7, so the forecast's search is
the *only* reasoning locus in the build — one 4→1 selection and one 9→3 selection. Whether
that is enough reasoning for the system's claims is a question the final report has to
answer either way. **Named candidates if a second locus is wanted**, strongest first:
**retrieval relaxation** (today a fixed ladder — size band, then radius, then bedroom count
— where *which criterion to relax for this deal* is a genuine judgment with a measurable
outcome, and U4's ablation harness could score it); and the **recommendation**, where
model-proposes/rule-decides with disagreement disclosed is already designed and deferred at
U9.4. `agents/scenario_forecast.py`, `agents/comps_retrieval.py`,
[`design/evaluator.md`](design/evaluator.md).

### OQ-4 · cut list 1a — rent-model feature engineering, tuning, and transfer
**Retargeted Aug 30, 2026, not closed, and the original wording is kept above the change
so the retarget is visible.** As written it read: *"Measured: ~17% of rent error is
available to model form alone, no new data. Deferred deliberately. **Closes only if**
schedule allows and proper validation replaces the single split"* — citing `config.py:272`
and `agents/valuation_rent.py:78`, both of which have since become unrelated code.

**The model-form half CLOSED Aug 30, 2026 as #18.** Its own condition was met — k-fold CV
replaced the single split — and the 17% survived it (RandomForest 16.5% better than the
shipped linear form). Gradient boosting was adopted rather than the lower-MAE random
forest, on a $18 versus $140 train/holdout gap. **Still open under this item, and narrower
than it was:** hyperparameter tuning under the same CV (the form ships at library
defaults, deliberately) and the **leave-one-metro-out** run — which is the only thing that
can answer the **transfer** question, since every k-fold fold still contains all four
markets. **That question had a second entry (OQ-12) until Aug 30, 2026; it is folded in
here so it has one owner, and its argument comes with it:** LOMO measures transfer to a
market the model has never seen, and every market this system indexes is *in* the training
set — so a LOMO figure would overstate the error a Staten Island subject actually faces,
and must not be substituted for the per-metro breakdown of holdout residuals the report
publishes. The two answer different questions and the earlier entry existed because they
were nearly conflated once.
Feature engineering is the third, and the §2 caution the original deferral raised still
applies to it: location is the dominant driver and this corpus does not carry it at useful
granularity, which may cap the ceiling well below the probe. **Closes when** the schedule
allows all three, or when they are written up as gaps. `config.RENT_MODEL_ESTIMATOR` and
`config.py:479`.

---

## Forecasting & reasoning

### OQ-5 · U9 — the ToT constants are provisional
`TOT_BRANCHING_FACTOR`, `TOT_MAX_DEPTH`, `TOT_BEAM_WIDTH`, `TOT_PRUNE_THRESHOLD` were set
by reading output, not by tuning. **Closes when** synthetic cases supply a known-correct
branch to tune against. Note the framing-level values are already special cases found by
inspection (`TOT_FRAMING_BEAM_WIDTH = 1`, `TOT_FRAMING_PRUNE_THRESHOLD = 0.0`) — treat
those as findings, not defaults. `config.py:663`.

**Retargeted U8 → U9 on Aug 30, 2026, not closed.** U8 planned no subsection for these and
built none, so carrying U8 in the label overstated what was scheduled — the same correction
U8.4 made to OQ-3. It is retargeted to a unit rather than parked with no owner, because the
surface U9 builds is where a reader meets these numbers and the sentence about them should
be written by the unit that shows them.

**Two measurements did land, and they are what is known about any of the four.**
`TOT_TIE_EPSILON` is **not meaningfully straddleable** — the gap it compares is
noise-dominated (OQ-17), so a recorded straddle would measure the recording (U8.6b). And
U8.6c published the depth-2 **cut margin**, the line the beam width actually cuts on:
across the golden batch it is often zero or negative, meaning the discarded pairing
outscored the one reported and lost on `tot._rank`'s conservatism preference. Neither is a
tuning signal; both say what the constants are doing today. **Tuning against the golden
batch was considered and declined** — those fixtures were authored by the unit that would
have tuned against them, which is the error Q1 exists to prevent, applied to a different
tunable.

---

## Geography & anchoring

### OQ-8 · `TODO(geography)` · no unit — New England town-level FMR
HUD prices FMRs by town, not county, in six states, and a county polygon join cannot
produce that entityid. A resolved point in those states returns `None` — declining rather
than guessing. **Cost today:** Boston's 599 rows are excluded from training, and #4's
shortlist is eight metros rather than nine because of it. **Closes when** a Census
county-subdivision layer is built. `tools/county_crosswalk.py:44`, `config.py:189`.

---

## Models & infrastructure

### OQ-9 · decision #8 · U9 — Summarizer model role
Holds the extraction model's value and makes no LLM call yet, so the setting is untested
rather than chosen. **Closes when** the Summarizer first calls a model, U9. **The Critic
half is resolved, not open:** decision #12's Critic ToT half was retired on evidence in
U7.7 — the checks that shipped are pure functions over `state.flags`, so the Critic makes
no LLM call in this design and `config.MODEL_CRITIC` stays untested by construction, not
by omission.

### OQ-10 · `TODO(security)` · no unit — the on-disk token fallback
Keys fall back to plaintext files in a gitignored directory when the env var is unset.
**The question is whether to drop the fallback and require the env var.** Affects
`tools/hud_fmr.py:24`, `tools/llm_client.py:41` and `tools/tracing.py:41` (added Sept 1,
2026 when a LangSmith key first existed — the same trade, taken the same way). Raise
before any public demo.

**The `diagnostics.py` half is closed and was a different question, Sept 2, 2026 at
U9.M.** This entry used to carry it alongside the three fallbacks; it is not the same
trade. The fallbacks ask whether a key may sit on disk in a gitignored directory — a
question with a real answer either way. `diagnostics.py:36` asked whether the account
identifier should be *printed to a terminal that is about to be recorded*, which has no
defensible yes. **Redacted rather than gated behind a quiet-during-recording switch**,
because a switch has to be remembered once, before a capture nobody can edit afterwards,
and on a run where something has already gone wrong. `tests/test_diagnostics_redaction.py`
guards it in both directions — the identifier out, the status and remedy hint in. What
remains under this entry is only the fallback question, and U9.10 closes that.

### OQ-17 · `TODO(reliability)` · no unit — live model calls are not perfectly deterministic, even at temperature 0
Found Aug 29, 2026 while building U8.5's OQ-16 case. `scenario_forecast`'s ToT scorer gave
different depth-2 pairing scores across live re-runs of what looked like an identical
prompt at `temperature=0.0`. Measured empirically: roughly 1 in 15-20 live attempts at a
fixed listing landed a mirror-image pairing (rent-up/price-down vs. rent-down/price-up)
close enough to trip `FORECAST_BRANCHES_NEAR_TIED` as an extra warn that would not
otherwise fire. The same thing showed up unprompted mid-session in the `los-angeles` demo
deal — a `live`-tier eval row — which escalated on one re-run where every run before and
since reports cleanly.

**Diagnosed Aug 29, 2026 with a direct experiment (`agents/scenario_forecast.py`'s design
doc, §3 of `architecture.md` — full detail there). Two independent, confirmed layers, not
one:**

1. **OpenRouter routes "the same model" to different backend deployments per request.**
   8 identical calls to `nvidia/nemotron-3-nano-30b-a3b` at `temperature=0.0` landed on
   four different providers (Novita, Crusoe, Nebius, DeepInfra) running three different
   `vllm` builds. Even a trivial "what is 2+2" prompt came back differently formatted
   depending which one answered.
2. **Even pinned to one fixed deployment (confirmed via OpenRouter's `provider.order`
   parameter — same provider, same `system_fingerprint`, every call), scores still swing
   widely** — one candidate scored 0.05 on one call and 0.95 on the next, same prompt, same
   deployment. `seed` does not help here, and testing confirmed it: at `temperature=0`
   there is no sampling step for a seed to control, so the residual variance has to be
   coming from the forward pass itself — plausibly the well-known GPU floating-point
   reduction-order sensitivity of continuous-batched serving, likely amplified by this
   model's Mixture-of-Experts routing (the `-a3b` in its name), where a near-tied gating
   decision is a hard switch to a different expert rather than a small numerical nudge.
   **This second layer dominates**, and it is not something a client-side parameter fixes.

**Accepted as an inherent property of a stochastic model, not a defect** — the open
question is what it implies about the system's own resilience, not the non-determinism
itself:
- **A committed recording is exact regardless.** Replay reads a frozen response, so this
  only ever touches a fresh live call — `golden`/`replay` eval rows are unaffected; only
  `live` rows (and any future live surface, including a Streamlit demo that calls the
  model live) can drift run to run.
- `FORECAST_BRANCHES_NEAR_TIED`'s disclosure text doesn't currently say the near-tie could
  be a property of *this one sample* rather than a stable fact about the evidence — worth
  checking against §8's Transparent Degradation principle.
- The same variance could in principle tip `HUMAN_REVIEW_CONFIDENCE_THRESHOLD` either way
  on a genuinely borderline live deal — a resilience question separate from, but adjacent
  to, the threshold-tuning question itself (OQ-1/U8.6).
- **Pinning the provider was considered and rejected as a mitigation**, since the
  experiment showed it removes a smaller source of variance than it leaves behind, while
  trading away OpenRouter's automatic failover — a real cost given §3's own history of
  free-tier reliability problems. Not worth the trade for a benefit that does not
  materialize.

**Closes when** a future pass checks whether any of the above needs a system response —
accepted as-is with one disclosure sentence, or addressed structurally (e.g. sampling the
scorer more than once and disclosing disagreement, rather than trusting one draw) if it
turns out to move a real decision. Noted here rather than acted on now, per the
architect's explicit call to document and defer. `agents/scenario_forecast.py`,
`docs/design/architecture.md` §3.

---

## Evaluation & demo

### OQ-18 · no unit — a replay row missed its recordings once, and the cause is not established
**Found Aug 29, 2026 during U8.4c's batch re-derivation.** Three replay-tier cases
(`la-unpriced-triplex`, `la-duplex-near-usc`, `chicago-unmatched-street`) raised
`CacheMiss` in one full-batch run, then passed in every run since — including two later
full batches with identical ordering. **The cause was searched for and not found**, which
is why this is recorded rather than closed: live-tier cases were ruled out by running each
one ahead of the failing case (all passed), golden-tier cases likewise (all passed), the
Census geocoder was ruled out by 20 rapid calls with 0 failures and by 6 repeat calls per
address returning byte-identical coordinates and ZCTAs.

**Why it matters more than a flake.** A `CacheMiss` means a *prompt* changed, and U8.4b
made every rent estimate depend on the subject's ZIP (for the drift factor), while the
scoring prompt embeds the rent estimate. So the replay tier's reproducibility now rides on
ZIP resolution being stable — it was measured stable, but the coupling is new and is the
mechanism by which a silent upstream change becomes a batch-wide replay failure. **Closes
when** either the cause is identified, or the scoring prompt stops embedding a
freshly-computed float (e.g. rounding the rent figure the prompt quotes, which would make
replay robust to sub-dollar drift without changing what the evaluator is told).
`eval/runner.py`, `agents/scenario_forecast._context_block`.

**Retargeted U8 → no unit on Aug 30, 2026, with the mitigation declined for now.** Rounding
the quoted figure is a small change that forces a **full re-record of the replay tier**, and
it would land five days before the freeze against a fault that has not reproduced in three
batches — and could not be shown to have helped, since the batch it would be verified on
already passes. Kept open on OQ-17's precedent rather than closed, because the mechanism is
newer than the fault: every replay prompt now rides on ZIP resolution being stable, and that
coupling arrived with the ZIP-grain anchor. **Re-open with a unit if a second miss occurs** —
two is a pattern and would pay for the re-record.

### OQ-21 · U9 — a sixth demo deal, in Chicago, so the set shows a clean run twice
**Raised Aug 30, 2026 by U8.6e; resolved in approach Aug 31 by the architect.** Ungating the
Critic's first interaction check made `chicago` escalate — it carries
`comps_outside_match_criteria` on an ordinary run, 3 of 8 comparables outside the size band
— so the deal that served as the middle-of-the-road demo now routes to human review, and
`los-angeles` became the only demo deal reaching 1.00 and reporting clean. That escalation is
the system working and nothing about it was reverted.

**Taken: add a sixth deal, also in Chicago. `chicago` is left exactly as it is.** The two
rejected alternatives are recorded because the reason is about what the demo has to show:
*accepting the set as it stands* leaves one clean run against five escalations, and a range
carried entirely by degrees of escalation understates a system whose whole argument is that
it reports cleanly when it can; *re-siting `chicago`* would spend the escalating deal to buy
the clean one, which is a trade, not a gain.

**Why re-siting is not free, in plain terms** — this replaces an earlier note that said only
that `chicago`'s terms are "#11-calibrated". Under decision #11, no demo figure is invented:
each one names the public source it was derived from in `demo_deals.py`, and
`scripts/verify_demo_calibration.py` re-derives every figure from those sources on demand.
The asking price comes from Redfin's median sale price for multi-family in that metro; the
stated rents come from HUD's schedule for **the county the listing's own address geocodes
to**. Move the address and both derivations move with it, the verification script's expected
values change, and — because the address determines the ZIP — the deal stops being the one
U8.8 uses to show a neighborhood median against a metro one.

**Two things the new deal needs, both already known so U9 does not rediscover them:**

- **The siting does not have to be searched for.** U8.6b already found and measured one:
  Chicago Uptown at **1,100 sq ft** returns 8 comparables with 2 outside the size band — the
  share the threshold admits — and raises **no warn-severity disclosure at all**. It runs at
  confidence **1.00** as the eval fixture `chicago-uptown-band-under`. Its 1,300 sq ft
  sibling is the straddle partner that escalates, so the pair also documents how narrow the
  clean margin is.
- **Its rent basis must not be copied from the existing deals.** U8.7 found `DemoDeal.
  rent_basis` is `hud_fmr:2` across the set — #11 set those rents from the anchor #19
  retired — so the existing basis is stale. A new deal should declare its rents against the
  market index the system now uses, or it ships stale on day one.

**Closes when** U9 adds the deal, calibrates it under #11's rules, and re-derives the demo
table. [`tasks/task_list_u8.md`](tasks/task_list_u8.md) §U8.6b, §U8.6e, §U8.7.

### OQ-13 · no unit — LangSmith account
Wiring is done and env-driven; every run prints whether tracing is on, so a silently
uncaptured run is not a failure mode. **Not a build blocker.** It *is* a blocker on
Checkpoint 5.1's trace evidence, and free-tier traces expire after 14 days — so set it up
close to the write-up, not long before.

**A key exists as of Sept 1, 2026**, and `tools/tracing.py` gained the same on-disk
fallback the other two credentials use, so only `LANGSMITH_TRACING=true` has to be typed.
The switch deliberately kept no file fallback: a key on disk says *this machine can
trace*, the variable says *this run should be traced*, and merging them would start
shipping every local run to a hosted service. **Closes when** U9.9 captures traces against
the surface that ships — which is the 14-day clock this entry exists to protect, now
started rather than pending.

### OQ-14 · U9 — checkpoint criteria as build artifacts
Where a checkpoint publishes completion criteria, the unit is specified to *produce* each
one rather than write it up afterward. U4 did this (see the acceptance-criteria table in
[`history/decision_log.md`](history/decision_log.md#retrieval)). **Apply the same treatment
to 5.1** as its criteria are published. **6.1's half is discharged (U7.8):** the unit's
evidence exists as build artifacts rather than as write-up —
`scripts/confidence_evidence.py` for the confidence mechanism and the re-derived demo
table, `tests/test_critic_interactions.py` for the interaction checks, and
`tests/test_flag_propagation.py` for the rework cycle terminating and disclosing that it
did.
