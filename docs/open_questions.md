# Open Questions

**Everything unresolved, and nothing else.** Closed decisions are in
[`implementation_plan.md`](implementation_plan.md) §7 (the register) and
[`history/decision_log.md`](history/decision_log.md) (the reasoning). This file is loaded
at the start of every session, so it is kept short on purpose — an entry that closes gets
**deleted** from here and its verdict written into the §7 register, not struck through.

**Grouped by the part of the system it affects.** Each entry names the unit that must
close it and what closing it looks like. `OQ-n` numbers are stable handles for
conversation; they are not decision numbers.

Last reviewed: Sept 2, 2026 — at U9's close-out
([`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.11).

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

**U9's close-out, Sept 2, 2026 — five entries closed, four opened, one retargeted, and one
left open on purpose.**

**Closed:** OQ-9 (the Summarizer's model role — it now makes a real call, and decision #8
records the setting as **inherited** rather than chosen; see the register), OQ-10 (keep the
on-disk credential fallback; the exposure it was really about was an account identifier
printed into a recording, fixed at U9.M), OQ-14 (discharged — Checkpoint 5.1 asked for design
rationale, not build artifacts), OQ-21 (the sixth demo deal shipped as `chicago-uptown`, so
the set shows a clean run twice), and OQ-22 (closed Sept 2 at U9.7T on the third of the three
conditions it named for itself, with the record in
[`design/evaluator.md`](design/evaluator.md)).

**Left open on purpose: OQ-13.** It is the one thing U9 owed and did not deliver, because the
capture needs a live account and a screen. Everything it depends on is discharged. Its entry
says so at the bottom of this file rather than in a close-out note nobody re-reads.

**Retargeted, not closed: OQ-5.** U9 owned writing it up and did — twice. It never owned
closing it, because the condition is a case that does not exist.

**Opened: OQ-24, OQ-25, OQ-26, OQ-27.** All four are things U9 *decided* rather than things
it discovered — a fixed relaxation ladder, a county-grain rent forecast, a model-written lede
whose prose is unchecked, and one report serving two readers. Each is written with what would
falsify it, because a deferral recorded without a closing condition is indistinguishable from
one that was forgotten.

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

**The TRANSFER half CLOSED Sept 2, 2026 — leave-one-metro-out was measured, and it cost a
script.** `scripts/lomo_validation.py` holds each of the nine training metros out entirely,
fits on the other eight and scores the held-out rows, so every scored row comes from a market
absent from its model's training data. **Pooled $512/mo against the cross-validated $452 — a
transfer cost of $59, about 13% — and the model beats a per-fold predict-the-average baseline
in all nine held-out markets.** Per metro: Chicago 361 (k-fold 343), Cleveland 395 (357),
Los Angeles 607 (509), New York **875 (855)**.

**Two findings worth carrying, because neither was predictable from the k-fold table.** New
York has the *largest* absolute error and the *smallest* transfer cost — +2% — so its elevated
error is a property of that market rather than of how much New York the model has seen, which
is what a reader of `RENT_ESTIMATE_MARKET_ERROR_ELEVATED` would otherwise be left guessing.
And Los Angeles has the largest transfer cost, +19%, which is the one figure carrying a
confound: LA is 42% of the corpus, so its fold trains on 58% of the data and blends market
absence with a much smaller training set. Both effects push the same way, which is why the
whole LOMO column is stated as an **upper bound** rather than an estimate.

**The warning this entry has carried since OQ-12 was folded in is now load-bearing rather than
hypothetical, and the script enforces it**: LOMO must not be substituted for the per-metro
holdout breakdown the reports publish. Every market this system indexes is *in* the training
set, so the shipped figure is the right one; LOMO answers a different question, and the two
are printed side by side so they cannot be conflated. **Still open under this item:**
hyperparameter tuning and feature engineering. Both change the shipped model and would force a
re-record of every eval row — which is exactly why this half could be taken inside the freeze
and those two cannot.

---

## Retrieval

### OQ-24 · `TODO(retrieval)` · no unit — should *which* criterion to relax be a judgment rather than a fixed ladder?
**Raised Sept 2, 2026 at U9's close, out of maintenance item M6.** The Comps agent relaxes
in one fixed order — floor-area band, then radius, then bedroom tolerance — inherited from
U4 with a rationale measurement has since retired: it called floor area the weakest signal,
and the shipped rent model measures `square_feet` at **0.502** against `bedrooms` at
**0.300**, so the ladder concedes the strongest measured attribute first.

**Two questions live behind that and they must be taken in order.** Is the order wrong —
deterministic, and now tagged `TODO(retrieval)` at the site? And should the order be chosen
per deal at all? This entry is the second. It is the strongest candidate for a further
reasoning locus in this system, because *which* criterion to relax for **this** deal is a
real judgment with alternatives and a measurable outcome: a thin-but-dense ZIP wants the
radius held and the size band conceded, a subject with an unusual footprint wants the
opposite, and today both get the same answer.

**What deciding it needs, in order — proposed at U9.11 and awaiting the architect's
review**, since this entry exists precisely so the criteria are fixed before anyone builds
toward them:

1. **A quality metric that does not depend on a model being asked.** Comps feed a
   cross-check against the modelled rent, so *better comps* means a comp-derived rent that
   tracks the subject's actual rent more closely. Held-out corpus rows are subjects whose
   rent is **known**: drop one from the index, force the loop to fire, score
   `|comp median rent − actual rent|`. Deterministic, no model call, no new data — and it
   is the number U4's docstring asserted and never measured.
2. **Establish the deterministic ceiling first.** Score all **six** orderings of the three
   concessions on that metric. If the best fixed order captures the gain, this closes as a
   *reorder* — the `TODO(retrieval)` — and there is no locus to buy. **This is OQ-22's
   precedent applied**: the starting-point spike found a deterministic rule reproducing the
   model's modal answer and the model was not adopted.
3. **Only if per-deal variation beats the best fixed order does a locus have a case.** Then,
   declared before it is built, not after:
   - **Stability** — the same concession chosen on **≥7 of 8** repeats at a fixed deal. That
     bar is not invented here: the starting-point spike failed it at 5 of 8, which is why its
     mechanism was declined (OQ-17).
   - **Reproducibility** — it puts a model call in a node **every** deal reaches, so the comp
     set itself becomes cache-dependent rather than just the prose about it, and every eval
     row needs a recording. Both model calls this system has today sit *downstream* of
     retrieval; this one would sit above everything.
   - **Transparent degradation** — on model outage it must fall back to the fixed order and
     say which order it used, because a silently different comp set moves every number
     downstream of it.

**The likely outcome, stated in advance so the measurement can falsify it** rather than
confirm it: step 2 settles it and step 3 never runs, because the ladder is a three-way choice
over one static attribute set and there is little for a judgment to add over a measured order.
Written down because that is what OQ-20 asks of check B, and it is the discipline this project
uses.

**Closes when** step 1 exists and step 2 has been scored — as a reorder, or as a locus that
clears step 3. `agents/comps_retrieval.py`, [`tasks/maintenance.md`](tasks/maintenance.md) M6.

---

## Forecasting & reasoning

### OQ-5 · no unit — the ToT constants are provisional
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

**Written up Sept 2, 2026 at U9.10, and it stays open on an unmet condition rather than an
unowned one.** No further measurement is scheduled before the freeze; what follows is the
whole of what is known, so the final report can state it rather than re-derive it.

**A third measurement landed at U9.7T, and it is the sharpest of the three because it is
about how much the constants decide rather than about what value they should take.**
Reproducing `tot._rank`'s grouping across every committed recording:

| Level | Recorded levels | Decided by the model's scores | Decided by the tie-break |
| --- | --- | --- | --- |
| Depth 1 — `TOT_FRAMING_BEAM_WIDTH = 1` | 78 | **78 (100%)** | 0 |
| Depth 2 — `TOT_BEAM_WIDTH = 3` | 79 | 39 (49%) | **40 (51%)** |

**So the two levels are in different situations and the entry should stop treating the four
constants as one question.** Depth 1's values are special cases found by inspection and the
level they govern is decided by the evaluator every recorded time — the constant is doing
what it was set to do. Depth 2's `TOT_TIE_EPSILON` is **load-bearing on half of all
levels**: on those, it is this project's conservatism preference and not the model that
chooses which pairings reach the report. That is a defensible policy, it is now disclosed
in both the ledger and the scenario table (U9.7T), and it means a *tuning* question about
`TOT_TIE_EPSILON` is really a question about how often the search should defer to policy —
which is a design question, not a parameter sweep.

**One boundary was priced and declined.** Whether `within TOT_TIE_EPSILON` should be
inclusive rather than strict is decided by floating point at the boundary today: of the
2-decimal score pairs a nominal 0.05 apart, 26 land "tied" and 31 do not. Making it
inclusive widens the tie groups and would move **11 recorded depth-2 levels**, requiring a
re-record and a 30-row diff. Architect's call Sept 2: not now — the epsilon is
noise-dominated (above), so a re-record five days before the freeze would buy a different
arbitrary line rather than a better one. U9.7Te fixed the *sentence* that reported it and
left the comparison alone.

**Closing condition unchanged and unmet**, and it is worth stating why it is not a
formality: tuning needs a case whose correct branch is known by construction, and every
fixture this project has was authored by a pass that already knew the shipped values.

**Label retargeted U9 → no unit at U9's close, Sept 2, 2026.** U9 was the unit that owned
writing this up and it did — at U9.10, and again at U9.7T with the measurement above. It
never owned closing it, because the condition is a *case that does not exist* rather than a
task nobody scheduled. Carrying `U9` in the label past U9's close would say a closed unit
still owes something.


### OQ-25 · decision #21 · no unit — the forecast's rent bands are county-grain against a ZIP-grain estimate, and the fallback threshold is a judgment
**Raised Sept 2, 2026 at U9's close, out of what U9.3 built.** #21 itself is settled: rent
growth comes from Zillow ZORI, chosen by following #16's own architectural argument to where
#19 moved the system. **Two residuals came with it and neither was decided.**

**1. The grain mismatch, disclosed rather than resolved.** #19 anchors the rent *estimate* at
the subject's own **ZIP**; #21 reads growth at the **county**. The reason is coverage and it
was measured: ZIP 10307 — `staten-island`'s own ZIP, on the one demo deal whose forecast is
rent-only — carries no ZORI series at all, and 65–95% of ZIPs in this project's market
counties begin after 2018-01, so a ZIP-first design would have turned a one-sided forecast
into none. Where both tiers exist the answer barely moves (LA 90026 +0.68/+2.37/+3.86 against
its county's +1.25/+2.51/+4.76). **That is a good reason to ship county and not a
demonstration that the grain does not matter** — one ZIP is one observation. Closing it means
measuring the ZIP-versus-county band difference across every ZIP where both exist, then
deciding whether to prefer ZIP with a county fallback — the anchor's own shape — rather than
county throughout.

**2. `ZORI_GROWTH_MIN_SUSTAINED_STRETCHES` was set against a distribution, not against an
outcome.** The first rule tried — one contiguous twelve-month run — let Adams County IL
publish a five-year projection banded +9.18/+9.86/+10.51 off **14 months**, because **a thin
series does not look unreliable, it looks confident**: median band width runs 0.13pp at 1–3
distinct stretches against 6.15pp at 24–43. The shipped requirement is a full year of distinct
stretches and it drops 97 further counties to the FMR fallback. It sits on a smooth
distribution and is recorded as a judgment, but **nothing has measured what a wrong fallback
costs a forecast** — the same shape `MIN_QUALIFYING_COMPS` was in before U4 measured density.

**Neither is a defect and neither blocked the freeze.** They are the two places #21 chose on
coverage and on shape because no outcome measurement was available in the time it had.
**Closes when** both are decided. `tools/rent_growth.py`, `tools/growth_bands.py`,
`config.ZORI_GROWTH_MIN_SUSTAINED_STRETCHES`.

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


### OQ-26 · U9.4 · no unit — the written summary's figures are checked; its prose is not
**Raised Sept 1, 2026 at U9.4 as a residual, recorded here Sept 2 at U9's close.** The lede is
a model-written paragraph above the report. It is **additive by construction** — nothing below
it is removed or reworded by the model — and it quotes rounded reader-facing figures rather
than raw floats, so it adds no second instance of OQ-18's fragility. **The prose carries no
such guarantee.** It needed two prompt passes and then a structural change — dropping the
disclosure excerpts entirely — before it stopped mischaracterizing evidence, twice describing
rental comparables as sales. Iteration stopped there on U9.3's precedent: under OQ-17, further
tuning fits a single draw.

**The strongest mitigation available inside the freeze is already taken, and it is not an
answer.** U9.5's recording pass freezes one draw per row, so every committed report and every
replayed demo carries a lede that was read once and can be read again — run-to-run exposure
becomes a fixed artifact. **A live run has no such guarantee**, which is the paste box and any
fresh deal.

**Closes when** either the lede is constrained to a form that cannot mischaracterize — quoting
only figures and disclosure names the report already renders, which is nearer a template than
a summary — or a check exists that scores a generated lede against the report it sits above.
The second is the useful one and the harder one; the first is cheap and costs the thing the
lede exists for. `agents/summarizer._lede_section`, `config.SUMMARY_NARRATIVE_ENABLED`.

---

## Evaluation & demo

### OQ-27 · U9.4 · no unit — one report, two readers
**Deferred on timeline Sept 1, 2026 at U9.4; recorded here at U9's close so the next reader
sees a choice rather than an oversight.** U9.4's finding was that someone reading many of
these reports meets the same boilerplate every time and the pricing is buried. The fix taken
was **progressive detail in one document** — recommendation and headline figures first,
disclosures condensed with full text expandable, evidence below. **Two renderings, one
investor-facing and one internal, is the cleaner design and was not taken**, on schedule.

**Distinct from OQ-23**, which asks whether the report is too *long*. This asks who each part
is *for*. Their cheap fixes point in different directions — OQ-23's is to collapse more of the
middle, this one's is to split by audience — and taking the first forecloses very little of the
second.

**Adjacent to work that already exists**, which is part of why it is cheap to state and easy
to underestimate: [`design/personas.md`](design/personas.md) names four readers, and the
escalation routing rule already sends a *pause* to the right desk. Nothing yet sends a
*report* to the right reader.

**Closes when** the split is taken, or when the single rendering is defended on evidence
rather than on schedule — which is the same evidence OQ-23 asks for first: which sections a
reader opens when they are collapsed. `agents/summarizer.py`, `design/personas.md`.

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

### OQ-23 · no unit — is the report too long?
**Raised Sept 2, 2026 by the architect**, reading the three sample reports after U9.7T and
U9.8. The disclosure expanders work and are staying; the objection is to total length.
`los-angeles` runs 183 lines, `staten-island` 213, `overpriced` 203 — and every unit since
U9.3 has *added* to the middle of the report (two band tables, a why-shown column, a band
coverage note, a gross-multiple block) without anything being removed.

**Deliberately not acted on before the freeze**, and the risk of acting on it is specific:
almost everything a length pass would cut is a disclosure, and this system's whole argument
is that it discloses. A shorter report bought by dropping the caveat beside a number is the
failure §1 exists to prevent, not a fix for it. The cheap version — collapse more of the
middle into expanders — is presentation and could be done; the expensive and more useful
version is deciding what a reader of *many* of these actually re-reads, which needs a reader
who has read many of them and does not exist yet.

**What a pass should measure first**, so it does not start by cutting: which sections a
reader opens when they are collapsed. The surface already renders every `##` section as an
expander, so the question is answerable by watching one demo rather than by argument.
**Closes when** a length decision is taken with that evidence, or when the final report
records the length as a known property of a disclosure-first design.
`agents/summarizer.py`, `docs/sample_reports/`.

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

**The only entry U9 left open that U9 was expected to close, Sept 2, 2026.** Everything
the capture depends on is discharged and verified: the terminal prints four lines before
the report rather than ~190, the account identifier is redacted with a test guarding both
directions, the diagram regenerated byte-identical with the single `critic → planner` back
edge asserted, and the Streamlit sidebar now states whether the session is tracing — which
it did not before Sept 2, so a `LANGSMITH_TRACING=true` shell would have traced the demo
into the project named `default` with nothing on screen saying so. What remains needs a
live account and a screen, and the runbook with the exact commands is in
[`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9. **One correction to that runbook,
found Sept 2 while re-deriving the sample reports:** it says `> report.md` captures the
report alone because the status lines stay out of a redirect. They do not — `main.py`
prints all four, and the escalation payload, to **stdout**. A committed report is produced
by taking the file from its `# Deal Evaluation` heading onward.

