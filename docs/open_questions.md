# Open Questions

**Everything unresolved, and nothing else.** Closed decisions are in
[`implementation_plan.md`](implementation_plan.md) §7 (the register) and
[`history/decision_log.md`](history/decision_log.md) (the reasoning). This file is loaded
at the start of every session, so it is kept short on purpose — an entry that closes gets
**deleted** from here and its verdict written into the §7 register, not struck through.

**Grouped by the part of the system it affects.** Each entry names the unit that must
close it and what closing it looks like. `OQ-n` numbers are stable handles for
conversation; they are not decision numbers.

Last reviewed: Aug 28, 2026 — at U8 planning ([`tasks/task_list_u8.md`](tasks/task_list_u8.md)).

---

## Orchestration & control flow

### OQ-1 · decision #6 · U8 — confidence threshold and severity weights
**The mechanism half closed in U7** (weights and threshold in `config`, critical-flag
escalation independent of the score, no decay across rework laps, all measured on the real
pipeline by `scripts/confidence_evidence.py`). **The numbers did not, deliberately:** the
demo deals were calibrated to run clean, so tuning against them would fit the threshold to
the fixtures. **Closes when** U8 tunes threshold 0.60 and the severity weights against the
eval batch. **Do not re-derive:** a critical flag already escalates on its own ground,
independent of the score (U2 finding 1) — that guarantee is deliberately separate from the
weights *because* the weights were always going to move. What U8 should measure first is
recorded as `TODO(U8)` at `critic.confidence_from_flags`.

**One sub-question added Aug 30, 2026, and one closed by argument rather than by
measurement.** *Added:* `fmr_anchor_county_level` is a **cause** of
`rent_estimate_market_error_elevated` — county-level anchoring is part of why New York's
holdout error is double — so the score charges 0.15 for the cause and 0.15 again for the
effect. That is the double-counting `confidence_from_flags`'s own de-duplication rule
exists to prevent, one level up. **Measure at U8.6** whether collapsing that causal pair
moves any verdict; the other market-scoped flags are independent axes (drift is a bias;
spatial concentration is about the comp check rather than the estimate) and are not part
of this question. *Closed:* whether market-scoped flags should be scored separately from
deal-scoped ones — **no.** They degrade this deal's own numbers, so scoring them apart
would let an unreliable estimate report as confident. The market/deal split is worth
having as a **disclosure** structure instead; full reasoning and the rejected two-score
design in [`tasks/task_list_u8.md`](tasks/task_list_u8.md) §U8.6d.

### OQ-15 · U8, cut list 2a — pass-scoped flags
`DealState.flags` is append-only, so nothing separates *raised this pass* from *ever
raised*, and every Critic interaction check reads the accumulated list as current truth. A
rework that succeeds still re-raises the objection it was sent back to fix. **Closes when**
each flag is stamped with the `planner_invocations` that produced it and the Critic
evaluates only the current pass — noting that an agent skipped on a rework raises nothing,
so absence must not be read as *cleared* when it means *not re-examined*; `state.plan`
records which agents ran. **Accepted knowingly for U7** — bounded by `MAX_REWORKS`, and
every affected path escalates to a human. `agents/critic.py`, `agents/planner.py`.

**Related, and raised Aug 28, 2026 by U8.2 — see OQ-16 below.** The same subsection now
also owns the question of whether escalation should preempt a retry at all.

**Taken Aug 28, 2026 at U8.5, and the cut list's price on it was wrong.** §6 described it
as "a §5 change touching every agent that raises a flag", which was estimated rather than
measured. Measured: **37 `flag()` sites across five agents, every one inside a node
function that already holds `state`**, six helpers that would take a pass index as an
argument, one central `state.flag()` constructor — one mechanical commit plus the Critic
filter. It lands *before* U8.6, because the eval batch contains rework laps and a stale
objection in a published results table is worse than the same sentence in one demo report.

**BUILT Aug 29, 2026, at U8.5's first two commits — clears both `TODO(U8)` markers.**
`Flag.planner_invocations` and `DealState.flag()` stamp every flag with the pass that
raised it; `critic._kinds` judges an agent that ran this pass on this pass alone, and an
agent skipped this pass on its last examination, never as cleared; `state.plan` is the
signal for which. New tests in `test_critic_interactions.py`/`test_flag_propagation.py`
assert the mechanism directly, since **the batch did not contain a rework lap at the
time this landed** — OQ-16's fault-injection extension, closed below the same day,
supplies the first one.

### OQ-16 · U8.5 — should a critical objection preempt a retry that could clear it?
**Raised Aug 28, 2026 by U8.2, from a measurement rather than a reading.**
`planner.route_after_critic` checks escalation before rework, unconditionally. So a retry is
only ever spent on a deal degraded enough to draw a retryable objection and clean enough not
to be escalated first — **exactly two warn-severity disclosures, no critical, on every lap.**
U8.2 searched for a listing in that window across 9 indexed markets × 16 configurations and
**found none**, so `FlagKind.REWORK_LIMIT_REACHED` is uncovered and the bounded-retry path is
unexercised by the batch that exists to exercise every path.

The window is empty for structural reasons, not for want of searching: divergence and comp
dispersion trade off directly (both track how thin the matching supply is), so every
configuration that diverges enough to object also concentrates enough to raise a *critical*
objection; Los Angeles and Cleveland are excluded before any fixture is written because the
county-anchoring warn already makes three; and the only six candidates were in New York,
which U8.2b's fix moves into the same excluded set.

**Closes when** U8.5 decides one of: leave it, and state in the report that the retry path is
reachable in principle but not by any listing this build can be shown; or reorder so a
*retryable* objection is spent before escalation, on the argument that a pass which could
clear the objection should be taken before a human is asked; or make the fault injection
richer so the path is exercised without a listing. **The first is a legitimate answer** — the
cycle is bounded and every path ends at human review — but it should be chosen rather than
inherited. `agents/planner.py:181`, [`tasks/task_list_u8.md`](tasks/task_list_u8.md) §U8.2.

**Decided Aug 29, 2026 by the architect: richer fault injection, `route_after_critic`
unchanged.** `agents/planner.py:181` stays escalation-before-rework, unconditionally — every
currently-retryable objection (I3, on a geocoder outage) is WARN-severity, and the criticals
U8.2's search found co-occurring with it (I1/I2) are structural facts a rework cannot fix, so
reordering would spend a rework pass on a lap that could not help before escalating anyway
one lap later. Instead, `eval/`'s existing `Fault`/`EvalCase.injects` mechanism (already used
for `GEOCODER_OUTAGE` and `LLM_UNAVAILABLE`) gets extended so a case can force exactly the
two-warn/no-critical window without needing a real listing — closing eval coverage on
`REWORK_LIMIT_REACHED` without touching production routing.

**BUILT Aug 29, 2026. Coverage: 28 → 29 of 29 kinds — every `FlagKind` this system
defines is now raised by some case.** `EvalCase.geocoder_fallback_override` forces the
outage's fallback to a chosen point (the address's own real Census geocode, so only the
outage is simulated, not a change in geography) instead of the real corpus-wide centroid
U8.2 already showed never both diverges and stays clear of a third warn or a critical.
`chicago-geocoder-outage` (U8.2) updated in place with it rather than duplicated; 2
reworks, confidence 0.70, escalates on `budget_exhausted` alone, reproduces identically
across three replay runs.

**Building it surfaced a second, real defect, fixed alongside it and worth naming here
since it is not really an eval-harness problem:** `extractor._supplied_coordinates` was
reading a *previous pass's* centroid fallback as if a caller had deliberately supplied
it, which silently swapped `GEOCODER_SERVICE_UNAVAILABLE` for a different, non-retryable
kind on the second pass — stopping a third attempt from ever being planned and
misdescribing pipeline-derived coordinates as caller-given. Fixed by restricting
`_supplied_coordinates` to the deal's first pass, safe given this system's one retry path
today (see that function's docstring for the full argument). Full detail:
[`tasks/task_list_u8.md`](tasks/task_list_u8.md) §U8.5.

---

## Rent & valuation

### OQ-3 · U8 — New York rents predict at roughly twice the trio's error
~$1,065 MAE against ~$518, under every training set tested; no shortlist fixes it. New York
is in `build_comps_index.INDEXED_MARKETS`, so a Staten Island subject reaches the rent model
and gets an estimate half as reliable as a Los Angeles one. **This is a disclosure
requirement, not a modelling problem** — it needs a flag, and U8 needs a case that trips it.
**Retargeted from U7/U8 to U8 on Aug 27, 2026:** U7 planned no subsection for it and built
none, so carrying U7 in the label overstated what was scheduled. The `staten-island` demo
deal reaches human review today for a different reason — zero comps — which means the
error is disclosed on that one deal by accident rather than by a check.

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

### OQ-4 · cut list 1a — rent-model feature engineering and model form
Measured: ~17% of rent error is available to model form alone, no new data. Deferred
deliberately. **Closes only if** schedule allows and proper validation replaces the single
split. `config.py:272`, `agents/valuation_rent.py:78`.

---

## Forecasting & reasoning

### OQ-5 · U8 — the ToT constants are provisional
`TOT_BRANCHING_FACTOR`, `TOT_MAX_DEPTH`, `TOT_BEAM_WIDTH`, `TOT_PRUNE_THRESHOLD` were set
by reading output, not by tuning. **Closes when** U8's synthetic cases supply a
known-correct branch to tune against. Note the framing-level values are already special
cases found by inspection (`TOT_FRAMING_BEAM_WIDTH = 1`, `TOT_FRAMING_PRUNE_THRESHOLD = 0.0`)
— treat those as findings, not defaults. `config.py:663`.

### OQ-6 · **U8.0** — Zillow ZORI as the independent rent check
#16 adopted ZORI as the validation series and it has not been built. It is the only
available test of **the rent model's largest unverified assumption** — that rent-to-FMR
structure is stable across the ~7 years between corpus and today. **Closes when** a ZORI
pull lands and the ratio is measured at both ends. `config.py:430`.

**BUILT Aug 28, 2026 (U8.0). The assumption does not hold.** ZORI/FMR fell from 1.186 at
the corpus vintage to 1.046 today — **−11.8%** — and the decomposition says why: **market
rent rose +33.5% while the FMR schedule rose +51.9%.** The denominator outran the market by
18.5 points. So **the shipped rent model over-predicts**, by roughly 15–35% depending on
subset. This also supplies the attribution `config.py`'s cohort-shift screen explicitly
deferred as undeterminable from FMR alone.

**BUILT Aug 29, 2026 (U8.4b) — the correction is now applied and disclosed.**
`tools/rent_drift.py` computes the subject ZIP's own
`(ZORI today / ZORI vintage) × (FMR vintage / FMR today)` and multiplies both the
estimate *and* the comp-implied figures by it (both carry the same drift, so the factor
cancels out of the divergence check). Measured factors 0.744 (LA 90026) to 0.934
(Bed-Stuy 11216) — a wider spread than U8.0's ZIP-anchored-only measurement, because the
county-anchored metros drifted hardest. Two new flag kinds disclose the correction and
its absence; ZORI reaches 7 of 10 fixture ZIPs, and where it does not, the WARN says the
estimate likely reads high rather than shipping the bias silently.

**Closes as measured, but opens two follow-ons rather than none:** U8.4b applies a per-ZCTA
correction at prediction time, and §6 cut-list item 6 carries re-anchoring the model on ZORI
outright — supported by measurement (ZORI covers 5,662 of 5,686 corpus ZIPs and normalizes
geography better, per-city mean spread 0.172 against FMR's 0.257) but costing a U5 rewrite
and 27% of training rows. Q5's veto branch fired: checks A and B are **not** promoted.
Reproduce both with `scripts/zori_evidence.py` and `--anchor-comparison`.

**Why it ran first, recorded because the reasoning generalizes.** It had no unit for two units. It moves
to the *front* on dependency rather than on enthusiasm: three deferred items are gated on
this one number (promoting Critic checks A and B at `agents/critic.py:187`, the stated-rent
emphasis threshold at `config.py:413`, and by extension what the eval batch scores), and a
measurement that can change what U8.6 tunes has to land before the tuning. **Source
verified reachable the same day** — ZIP-level, monthly from 2015-01, carrying `CountyName`,
so the ratio can be measured at both ends of the vintage gap and joined to FMR at the
anchor's own grain. **The measurement can veto as well as unlock:** ~1.0 means the rent
model over-predicts and A must *not* be promoted; ~1.4 means the model is right and A gets
a threshold above #11's known calibration offset. Both are results.

---

## Data & sources

### OQ-7 · decision #11 · **U8.8, drop-dead Mon Sept 1** — public-record sub-metro price benchmark
County assessor open data (Cook, LA County, NYC) is chosen, admissible under §8's "public"
definition, and unbuilt. **Closes when** U8.8 ingests it — or, if cut at the drop-dead
date, when the gap is written up explicitly.

**Respecified Aug 28, 2026, because this entry's own premise was stale.** It read "what
would let the *value* estimate be scored" — but **#15 made `value_estimate` permanently
`None`** in U6, so there is no value estimate to score. Nor can assessor data score the
demo deals' asking prices: those listings are synthetic, and #11 set the asking price
*from* the Redfin metro median, so there is no real asking price and no real sale to score
it against. What the dataset actually delivers is a **sub-metro sale-price benchmark**
replacing the metro median in `ValuationDetail.benchmark_median_sale_price` — the
price-side counterpart to ZIP-resolution rent anchoring, and what makes check B local.

**Taken rather than cut, with the risk carried by a date.** It is the one U8 item whose
cost is not bounded in advance — an address-to-parcel join is the same class of work as
U3's geocoding tiers — so it sits *behind* the harness core, and the cut, if taken, is
taken Sept 1 with three days in hand rather than on the freeze morning.

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
Keys fall back to plaintext files in `ignore/` when the env var is unset. **The question is
whether to drop the fallback and require the env var.** Affects `tools/hud_fmr.py:24`,
`tools/llm_client.py:41`, and `tools/diagnostics.py:36` (which deliberately prints the
account identifier). Raise before any public demo.

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

### OQ-18 · U8 — a replay row missed its recordings once, and the cause is not established
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

### OQ-12 · U8 — two items, and they separated at U8 planning
`config.py:309` wants a leave-one-metro-out run as evaluation rather than the current
in-sample split; `config.py:386` needs confirmation that anything still trips the flag it
guards. Both are `TODO(U8)` at the site.

**Split Aug 28, 2026.** The second half closes at **U8.2** — a case built to sit on the far
side of the divergence line, which U8.1's coverage census requires anyway since a flag
nothing can raise would corrupt it.

**Second half CLOSED Aug 28, 2026 at U8.2.** `chicago-uptown-duplex` trips it, and how it
does so matters more than that it does: **nothing about the property is engineered.** An
ordinary two-bedroom duplex whose comps match it on bedrooms and floor area, in a market
whose ZIP-level rents are high, still puts the model 48% above the comp median. The flag is
detecting a genuine disagreement between the two inputs rather than a manufactured one, so
it is available as a signal rather than dead. `config.py:386` may keep its threshold; the
`TODO(U8)` there is cleared at U8.M.

**The first half was nearly closed by accident and should not be.** U8.4's New York
disclosure (OQ-3) needs a per-market error figure, and folding LOMO into it looked like one
run closing two items. It is the wrong instrument: **LOMO measures transfer to a market the
model never saw, and New York is in the training set**, so a LOMO figure would overstate the
error a Staten Island subject actually faces. U8.4 uses a per-metro breakdown of the
existing holdout residuals instead. LOMO stays open as what it always was — a *transfer*
measurement and a real limitation of the reported MAE — scheduled to U8.9's report artifacts
if the schedule holds. [`tasks/task_list_u8.md`](tasks/task_list_u8.md) Q2(b).

### OQ-13 · no unit — LangSmith account
Wiring is done and env-driven; every run prints whether tracing is on, so a silently
uncaptured run is not a failure mode. **Not a build blocker.** It *is* a blocker on
Checkpoint 5.1's trace evidence, and free-tier traces expire after 14 days — so set it up
close to the write-up, not long before. No key present in `ignore/` as of Aug 24, 2026.

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
