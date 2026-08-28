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

### OQ-15 · U8, cut list 2a — pass-scoped flags
`DealState.flags` is append-only, so nothing separates *raised this pass* from *ever
raised*, and every Critic interaction check reads the accumulated list as current truth. A
rework that succeeds still re-raises the objection it was sent back to fix. **Closes when**
each flag is stamped with the `planner_invocations` that produced it and the Critic
evaluates only the current pass — noting that an agent skipped on a rework raises nothing,
so absence must not be read as *cleared* when it means *not re-examined*; `state.plan`
records which agents ran. **Accepted knowingly for U7** — bounded by `MAX_REWORKS`, and
every affected path escalates to a human. `agents/critic.py`, `agents/planner.py`.

**Taken Aug 28, 2026 at U8.5, and the cut list's price on it was wrong.** §6 described it
as "a §5 change touching every agent that raises a flag", which was estimated rather than
measured. Measured: **37 `flag()` sites across five agents, every one inside a node
function that already holds `state`**, six helpers that would take a pass index as an
argument, one central `state.flag()` constructor — one mechanical commit plus the Critic
filter. It lands *before* U8.6, because the eval batch contains rework laps and a stale
objection in a published results table is worse than the same sentence in one demo report.

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

**Scheduled Aug 28, 2026 — first in U8, not last.** It had no unit for two units. It moves
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

---

## Evaluation & demo

### OQ-12 · U8 — two items, and they separated at U8 planning
`config.py:309` wants a leave-one-metro-out run as evaluation rather than the current
in-sample split; `config.py:386` needs confirmation that anything still trips the flag it
guards. Both are `TODO(U8)` at the site.

**Split Aug 28, 2026.** The second half closes at **U8.2** — a case built to sit on the far
side of the divergence line, which U8.1's coverage census requires anyway since a flag
nothing can raise would corrupt it.

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
