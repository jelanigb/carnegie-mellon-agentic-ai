# U7 — Critic / Reviewer — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#17) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

**Feeds Checkpoint 6.1** (due Aug 31, 2026 — this unit is pulled forward to land before
it). Builds the half of `agents/critic.py` that U2 deliberately stubbed: cross-agent
consistency checking, and the objections that make the rework cycle fire on its own.
Decision #6's *mechanism* lands here; its **numbers do not** — see Q3.

**Sequence, and why.** Checks first (U7.2, U7.3), then wiring (U7.4), because the wiring
has nothing to carry until the checks exist. Disclosures (U7.5) come after the wiring
even though they are independent of it, because U7.5 adds a sixth demo deal and U7.6 has
to re-measure the §6 demo table — doing the fixture change first means measuring once
rather than twice. U7.7 may not be built at all.

### Unit-level open questions

**Q1 — ANSWERED Aug 24, 2026: consume, do not reproduce.** The Critic does not re-check
rent-vs-comps; `agents/valuation_rent.py:247` already raises `RENT_DIVERGES_FROM_COMPS`
and duplicating it risks two agents disagreeing about one fact.

`agents/critic.py`'s `TODO(U7)` names four checks. Against the built system, **one is dead,
one is already built elsewhere, and two remain for the Critic**:

| Named check | Status | Evidence |
| --- | --- | --- |
| Rent estimate vs. the comp set's distribution | ⚠️ built elsewhere — **consume the flag** | `agents/valuation_rent.py:247`, using `comp_implied_rent_p25/median/p75` |
| Value estimate vs. listing price | ❌ **dead** | #15 made `value_estimate` permanently `None`. The TODO predates that decision |
| Scenario bands vs. the base they branch from | ✅ for the Critic to build | U7.2 |
| Comp-source concentration | ✅ for the Critic to build | U7.3 |

**But that list was written in U2, before `ValuationDetail` and `ForecastDetail` existed,
and it is not the universe of available checks.** Enumerating what upstream actually
writes to state today surfaces four more genuinely cross-agent pairs, none of which any
agent checks:

| # | Cross-agent pair | What it catches | Cost |
| --- | --- | --- | --- |
| **A** | `deal_terms.unit_rents` (Extractor) vs. `rent_estimate` (Valuation) | **The listing's claimed rents against the modelled rent** — the overstated-pro-forma case. Verified unbuilt: `unit_rents` is never compared to `rent_estimate` anywhere in `src/`. Distinct from `RENT_DIVERGES_FROM_COMPS`, which compares the model against *comps*, never against what the seller claimed | arithmetic |
| **B** | `deal_terms.price` (Extractor) vs. `valuation_detail.benchmark_median_sale_price` (Valuation) | Asking price against the market benchmark #15 deliberately carries "as a reference the asking price is read against" — nothing currently reads it against anything | arithmetic |
| **C** | `forecast_detail.projection_base_price` / `_rent` (Scenario) vs. `deal_terms.price` / `rent_estimate` | The forecast projecting from something other than the base it names. #15/#17 fixed those bases; nothing asserts it | exact equality |
| **E** | comps' bed/sqft distribution (Retrieval) vs. `deal_terms` (Extractor) | Comp drift after relaxation. `RELAXED_MATCH_CRITERIA` records *that* criteria were relaxed, never *how far* the comps ended up from the subject | distribution stats |

**A is the most valuable check in the set** and it is the one the original TODO never
named: it is the only place the system compares what the seller asserts against what the
system independently derived. That is the deal-evaluation task's central question.

**One trap, stated because #15 already documented it.** Check B will look inert on the
demo deals — `demo_deals.price_basis` calibrated their asking prices *to* that same Redfin
median, so the gap is ~$140 by construction. It is a real check that this repo's own
fixtures cannot exercise. U8 needs a case with a deliberately mispriced subject, or B
ships measured-but-unexercised and says so.

**Consequence for Checkpoint 6.1: none.** 6.1 is a 400–600 word written safety plan
(risks, guardrails, evaluation metrics, human-intervention criteria, trade-offs). It does
not grade the count of consistency checks. Consuming rather than duplicating is *itself*
rationale for criterion 6 (trade-offs: single source of truth over redundant validation),
and the check inventory above supplies the guardrail section either way. The 6.1 exposure
is not "how many checks" — it is that the escalation criteria and the evaluation metrics
must be **stated and defensible**, which is U7.6 and U8.

**Q4 — NEW, blocks U7.5. Measured Aug 24, 2026, before building anything.** Checks A and B
were both specified against fixtures that cannot test them, and in opposite directions.

**B is already half-built and reads as inert.** `agents/summarizer.py:239–245` already
computes the asking-price drift against the benchmark and renders it as prose — *"This
listing asks $1,049,000 — 0% above that benchmark."* The arithmetic exists; what does not
exist is an objection raised from it. And it prints **0%** because #11 set the demo asking
prices *from* that same Redfin median (`demo_deals.py:128`,
`price_basis="redfin_metro_median:Los Angeles"`): median $1,048,866, demo asks $1,049,000,
a $134 rounding artifact. Of the five demo deals, three carry that basis and two carry
`price_basis=None` (Redfin does not cover New York), so **B is unexercisable on all five**.

**A is worse, and fires in the opposite direction.** Measured directly against the shipped
model (`rent_model.predict_ratio`, then `ratio × FMR` exactly as `valuation_rent.py:449`
does it):

| Deal | model ratio | FY2026 FMR | model estimate | stated rents (avg) | A would report |
| --- | --- | --- | --- | --- | --- |
| `los-angeles` | 1.404 | $2,903 | $4,075 | $2,900 | **−28.8%** |
| `chicago` | 1.404 | $1,781 | $2,500 | $1,775 | **−29.0%** |
| `staten-island` | 1.365 | $2,910 | $3,973 | $2,908 | **−26.8%** |

**The cause is a percentile mismatch, not a property of any listing.** FMR is a
40th-percentile rent; the Kaggle corpus rents at ~1.40× FMR, so the model predicts
market-typical rent while #11 calibrated the demo rents to FMR *itself*. `demo_deals.py`
already states the consequence — *"a listing calibrated to it sits at the affordable end of
its market by construction"* — but nothing priced what that does to a check comparing the
two. **A as specified would measure the demo calibration, not the deal**, and it would
raise an objection on **every** demo deal including `los-angeles`, whose zero-flag clean run
is what makes the other rows in §6's table mean anything.

**The report currently hides this.** `summarizer.py` renders `rent_estimate` but never the
listing's stated `unit_rents`, so a 29% gap between what the seller claims and what the
system estimates is invisible in the output today. That is a Transparent Degradation gap
independent of U7.

**The open question is empirical: is 1.40 the market's rent/FMR ratio, or corpus selection
bias?** The corpus is professionally-marketed apartment listings; FMR covers all
standard-quality units, so the model may be over-predicting rather than the demo
under-stating. **Nothing in this project can currently distinguish those.** The instrument
that could is Zillow ZORI — market-observed, ZIP-level, already adopted as the independent
check by #16 and still unbuilt (OQ-6).

**Recommendation, sized for the Aug 31 checkpoint:**

1. **Build C, D and F as Critic checks now** (U7.2, U7.3). Their semantics are unambiguous
   and no fixture artifact touches them. These are what make `critic_rejected` reachable.
2. **A and B are not Critic checks in U7. They are Summarizer disclosures.** This is not a
   new mechanism — it is the pattern B already follows: `summarizer.py:239–245` computes
   the price drift, renders it as prose, and raises **no flag and no objection**. A gets the
   same treatment with a new line rendering stated rent against estimated rent, which also
   closes the disclosure gap found above. Neither touches `_consistency_objections()`,
   `critic_rejected`, `confidence_score`, or routing, so **the `los-angeles` clean run keeps
   its 1.00 confidence and its zero disclosures.**
3. **Add one deliberately mispriced demo deal**, `price_basis` naming the offset as
   deliberate, so B's rendered drift is non-trivial on at least one deal and 6.1 can
   describe a disclosure that actually says something.
4. **Promote A and B to Critic checks in U8**, once ZORI settles whether 1.40 or ~1.00 is
   the right rent/FMR baseline — closing OQ-6 and A's threshold in one step. Park A's
   threshold in `config.py` as `None` with a comment naming U8, so the promotion is a
   value change rather than a redesign.

Rejected: tuning A's threshold above the ~29% structural offset. That buries a fixture
artifact inside a production threshold, which inverts what the threshold is for.

Rejected: a `CRITIC_CHECKS_ENFORCED` boolean gate. It would add a config switch to
reproduce behaviour the Summarizer already has by simply not raising a flag. A gate that
is never flipped in the shipped configuration is dead weight.

**Q2 — ANSWERED Aug 24, 2026: measure first, build only if it changes an outcome.**
Does the Critic run a ToT search over its checks, per decision #12?
#12 adopted ToT here on the grounds that the checks "differ in cost and are not
independent." With Q1 resolving to two checks, both cheap and both local to state, **that
premise may no longer hold** — a search over two cheap independent checks is decoration,
and this project has an explicit standard against that
([`open_questions.md`](../open_questions.md) OQ-2, and the U6 precedent where
`scripts/forecast_evidence.py` had to *prove* the search was load-bearing).
**Revised after Q1's enumeration.** With six candidate checks rather than two, and with
their costs genuinely differing (A/C are arithmetic, B needs the benchmark, E needs
distribution stats over the comp set), **#12's premise is back in play** — "the checks
differ in cost and are not independent" is defensible again. A and B are *not* independent:
both compare an Extractor claim against a Valuation output, and a subject that is
mispriced will often also be misrented.

**Recommendation unchanged: measure first.** If the search cannot be shown to change an
outcome, retire #12's Critic half on evidence — a better result for the report than a
search that does nothing, and the same call U6 made about `AppreciationTier`.

**Q3 — ANSWERED Aug 24, 2026: land the mechanism in U7, leave the numbers to U8**, and
record the split in §7's register. Decision #6's weights and the 0.60
threshold are tuned against the eval batch — but **U8 builds that batch**. Either U7.6
tunes against the five demo deals (weak, and they were calibrated to be clean), or it
slips to U8. **Recommendation: slip the tuning to U8, land the mechanism in U7**, and say
so in the register rather than tuning against inputs that cannot exercise the range.

**Q5 — NEW, blocks U7.2 and U7.3. Measured Aug 24, 2026. This is a unit-level question,
not a subsection one: six of the eight candidate checks are dead or already built, and
U7's premise needs restating before any of them is written.**

| Check | Verdict | Evidence |
| --- | --- | --- |
| Rent vs. comp distribution | built in Valuation | `valuation_rent.py:247` (Q1) |
| Value vs. listing price | dead | #15 made `value_estimate` permanently `None` (Q1) |
| **C** projection base | **unfalsifiable** | `scenario_forecast.py:670–672` assigns `projection_base_price=terms.price` directly, and `planner._PIPELINE` is a fixed tuple, so Scenario always re-runs whenever Extractor does. The check compares a field to the variable it was assigned from |
| **D** band monotonicity, combined | **structural** | `_to_scenarios` sorts by `_outcome_rank` then labels by rank. Cannot fail by construction |
| **D** band monotonicity, per-series | **fires on intended behaviour** | Verified live on `los-angeles`: pessimistic carries price +4.50%/yr, optimistic −0.80%/yr. The report *already explains this*: "a single column need not fall in label order — the pessimistic case can carry the higher projected price and still be the worse outcome overall." Flagging it would contradict the system's own disclosure |
| **D** screening coherence | **structurally impossible** | #17 set `TOT_FRAMING_BEAM_WIDTH = 1`, so every scenario descends from one framing and shares one screening decision. The U6 motivating case cannot recur |
| **F** comp-source concentration | **already built** | `summarizer.py:143–158`, with a 0.75 threshold and three-way branching. Promoting it to an objection would fire on both dense demo deals — measured: `los-angeles` 8/8 from RentDigs.com, `chicago` 6/8 — including the clean baseline |
| **E** comp attribute drift | **survives** | The relaxation flags record which tolerance was loosened, never the realized drift of the returned comps. Genuinely unbuilt, and it cannot fire on a deal that never relaxed |

**The pattern, which is the actual finding.** U5 and U6 each built their consistency checks
*into the agent that owns the data*, and the Summarizer built the cross-agent *disclosures*.
The Critic's job description was written in U2, when those agents were stubs and it looked
like the only place such checks could live. It is now largely done — and done in a better
place, next to the data that makes each check computable.

**What is left that only the Critic can do.** It is the one node that sees every agent's
flags at once. Individual agents raise flags about their own step; **only the Critic can
judge whether a combination of them undermines the result.** The gap is concrete and
visible in the code: `RENT_DIVERGES_FROM_COMPS` ends by telling the reader *"Check the comp
disclosures above — a set concentrated in one location or drawn from one aggregator can sit
well away from its own metro."* Nothing checks that for them. Turning that sentence into a
determination is a real check, is uniquely the Critic's, and cannot fire on a clean deal.

**Recommendation — restate U7 around flag interaction rather than flag re-derivation:**

1. **Drop C, D and F.** Record each as retired-on-evidence; do not write a check that cannot
   fail or that contradicts a disclosure the system already makes.
2. **Keep E**, the one surviving attribute check.
3. **Add interaction checks** as the unit's substance — e.g. `SPARSE_COMPS` or a relaxation
   flag co-occurring with `RENT_DIVERGES_FROM_COMPS` means the divergence signal is itself
   unreliable rather than informative; `COORDINATES_FROM_CITY_CENTROID` with a tight
   distance column means the distances imply precision the geocode does not have.
4. This **preserves decision #12's premise** (checks that differ in cost and are not
   independent — interaction checks are by definition not independent) and gives Checkpoint
   6.1 guardrail content that is real rather than inherited.

**Needs a decision because it changes what U7 is**, not just what it contains.

**Q6 — NEW, blocks nothing yet but affects every interaction check. Measured Aug 25, 2026,
immediately after U7.4b made rework actually loop.**

**Nothing in state distinguishes "raised this pass" from "ever raised."** `DealState.flags`
carries an `operator.add` reducer, deliberately, so the raw run history stays inspectable.
Every check in `_interaction_objections` reads that accumulated list as if it described the
current pass.

Demonstrated: pass 1 has a geocoder outage and a rent divergence. The rework re-runs
extraction, **the geocoder answers, coordinates resolve to a parcel, and the divergence
clears** — neither agent raises anything new. The Critic nevertheless raises I3 again, sets
`critic_rejected=True`, loops again, and tells the reader *"the comps were retrieved around
the city's center of listing density rather than around this property"* — which is now
**false**.

The loop still terminates on `MAX_REWORKS`, so this is not a safety problem. It is a
correctness problem in reader-facing text, and it is the third time this unit has hit the
same root cause: append-only flags read as current truth. The confidence-decay defect in
U7.4 was the first, `_geocode_is_worth_retrying`'s documented staleness the second.

**Three ways out:**

1. **Pass-scope the flags.** Stamp each `Flag` with the `planner_invocations` value that
   produced it, and have the Critic evaluate only the current pass. General, fixes all
   three checks at once. **The wrinkle:** an agent skipped on a rework raises nothing, and
   absence would then read as "cleared" when it means "not re-examined". Resolvable —
   `state.plan` records which agents ran — but that is real logic, not a one-liner.
2. **Record coordinate provenance on `DealTerms`.** A closed enum saying how the current
   coordinates were derived. Narrow, cheap, and fixes I3 only; I1 and I2 keep the defect.
3. **Accept and document.** Bounded by `MAX_REWORKS`, and every affected path escalates to
   a human who sees the flag list. Cheapest, and it leaves a statement in the report that
   is wrong.

**Recommendation: (1), but not inside U7.** It is a §5 state-schema change and it touches
every agent that raises a flag, which makes it its own unit of work rather than a
subsection. For U7, take (3) *knowingly* — the affected text only appears on a rework lap,
which by construction escalates to human review — and open (1) as scheduled work.
**Needs a decision: this is a state-design call, not an implementation detail.**

### U7.1 ✅ — Correct the U7 docstrings to the system that exists *(maintenance)*

No logic. `agents/critic.py`'s module docstring and both `TODO(U7)` comments describe four
checks and a `value_estimate` that #15 removed. Rewrite to Q1's findings — including that
rent-vs-comps is consumed, not reproduced — so the file stops advertising a design the
build abandoned. Lands first so the behavioural diffs that follow are read against an
accurate description.

### U7.1b ✅ — Distinguish a retryable geocode failure from an unresolvable address

Enabling change for U7.4, landed separately because it is behavioural. `tools/geocoding.py`
caught a failed Census *request* and fell through to the corpus centroid raising the same
flag as an address that simply had nothing to resolve to. U3 logged the distinction to
diagnostics and left the flag identical, noting *"the resulting flag says the same thing
either way."*

- `GeocodeResult.primary_unavailable` now carries the cause. `GeocodeSource` is unchanged
  and deliberately gains no third member — it answers "which tier produced the
  coordinate", and the tier is the same either way.
- New `FlagKind.GEOCODER_SERVICE_UNAVAILABLE` (WARN), raised instead of
  `COORDINATES_FROM_CITY_CENTROID` when the call could not be made. A distinct kind rather
  than a detail in the message, because the Critic routes on it — parsing prose to decide
  routing is how a message edit silently becomes a behaviour change.
- `tests/test_flag_propagation.py` at 37 cases, asserting the new flag reaches the report
  **and** that the address-side flag does not also fire.
- **Creates an obligation for U8:** `set(FlagKind)` coverage now has one more member, and
  a service outage is awkward to trip from listing text alone. It may need injection
  rather than a synthetic listing.

### U7.2 ✅ — Interaction checks: when disclosures compound *(the unit's substance)*

**Q5 resolved: C, D and F are retired on evidence. This replaces them.**

The Critic is the only node that sees every agent's flags at once. Agents flag their own
step; only the Critic can judge whether a *combination* changes what the result means.
This is not extra penalty — `confidence_from_flags` is a sum, and a sum can only say
*more doubt*. An interaction says something a sum cannot: **this measurement does not mean
what it appears to mean.**

**Where the gap actually is, with real weights** (`info 0.00`, `warn 0.15`,
`critical 0.40`, threshold `0.60`): one warn → 0.85, two warns → 0.70, three warns → 0.55
which *already* escalates, and any critical escalates on its own ground. **So the window
is exactly two warns, plus any number of INFO flags, which cost literally nothing.**

Candidate interactions, strongest first. Each is a pure function of `state.flags` plus the
detail objects, so all are hermetically unit-testable with no LLM, network, corpus or
model:

| # | Combination | Why the combination changes the meaning |
| --- | --- | --- |
| **I1** | `RELAXED_MATCH_CRITERIA` (bedroom tolerance loosened) + `RENT_DIVERGES_FROM_COMPS` | The comps now span bedroom counts the subject does not have, and bedroom count is the dominant rent driver. The comp median is for a *different unit type*, so divergence from it is expected rather than informative |
| **I2** | `COMPS_SPATIALLY_CONCENTRATED` + `RENT_DIVERGES_FROM_COMPS` | The comp median is a point sample from one location. #15 measured one Chicago coordinate carrying 150 listings spanning $760–$6,995 (CV 48.7%), so that median is a weak statistic to diverge *from* |
| **I3** | `COORDINATES_FROM_CITY_CENTROID` + `RENT_DIVERGES_FROM_COMPS` | Comps shifted to a city-density-centre sample while the model, being location-blind below the county, did not move at all. **Degrades rather than voids** the cross-check — see the note below |

**A correction carried into this plan.** I3 was first described as making the cross-check
"void". That is too strong, and the reason matters: **the rent model is location-blind
below the county** (§2) — its features are beds/baths/sqft against a county FMR anchor, so
the subject's coordinates do not affect the estimate at all. They affect only which comps
are retrieved. So I3 means the comps moved and the model did not, which tells you *which*
branch of the divergence flag's own either/or is likely — not that the comparison is
worthless. I1 is the stronger case and should be built first.

**Mechanism.** Raise `CRITIC_INCONSISTENCY` at CRITICAL, reusing U2's existing rule (any
critical flag escalates regardless of score) rather than inventing a second escalation
ground. The deal escalates at 0.70, which is exactly the branch `critic.py` already has
wording for: *"clears the threshold, but a critical-severity disclosure was raised."*

**As built.** `Objection(message, severity, retryable)` NamedTuple plus
`_interaction_objections(state)`, both in `agents/critic.py`. **Not wired** —
`_consistency_objections()` is untouched and still returns `[]`, so the load-bearing
bounded-cycle injection in `test_flag_propagation.py:525` keeps testing exactly what it
tested. U7.4 joins them and updates that seam deliberately.

Two design points settled while writing it:

- **I1 needs no flag split.** `RELAXED_MATCH_CRITERIA` covers both relaxations the
  retrieval loop makes — dropping the square-footage band and loosening bedroom tolerance
  — and both matter for one reason: `config.RENT_MODEL_FEATURES` is
  `("bedrooms", "bathrooms", "square_feet")`, so either widens the comp set along a
  dimension the model prices on. The kind alone is sufficient, and the semantics are
  tighter than the bedroom-specific version originally planned.
- **`RELAXED_SEARCH_RADIUS` deliberately does not trigger I1.** Widening the radius leaves
  the attribute filters intact, so the comp set still describes the same kind of unit.
  Conflating them would fire I1 on ordinary thin-market deals. Asserted in a test.

`tests/test_critic_interactions.py`, 8 cases, hermetic — no LLM, network, corpus or model.
Kept out of `test_flag_propagation.py` on purpose: that suite proves a flag *survives* the
pipeline, these prove a combination is *read* correctly. Different guarantee.

**These escalate; they do not rework** — except I3's service-outage variant, which sets
`retryable=True`. Re-running cannot densify a thin market or add a street number, but it
can re-attempt a Census call. See U7.4.

### U7.3 — Check: comp attribute drift *(E — the one surviving attribute check)*

The relaxation flags record *which tolerance was loosened* — "dropped the square-footage
band", "loosened bedroom tolerance from ±0 to ±1" — but never the **realized drift** of the
comps that came back. A reader is told the criteria widened, not that the returned set
averages 1,400 sqft against a 950 sqft subject.

Compares `state.comps` against `deal_terms`, so it is cross-agent. **Cannot fire on a deal
that never relaxed**, which is what keeps it off the clean baseline. Threshold to
`config.py`. Feeds I1 above rather than duplicating it: drift is the measurement, I1 is the
consequence for the divergence signal.

### U7.4 ✅ — Wire the objections in, and make the rework cycle fire on its own

`_consistency_objections()` now returns `list[Objection]` and delegates to
`_interaction_objections()`. The `Critic → Planner` back edge carries traffic for the
first time.

**`critic_rejected` changed meaning, and that is the substance of this change set.** It
was `bool(objections)` — "something is wrong". It is now `any(o.retryable ...)` —
"another pass could fix this". A rework re-runs the whole pipeline, so it is worth
spending only where a second pass can change the input. A thin market stays thin; an
address with no street number stays unresolvable; a comp set relaxed onto a different unit
type will relax the same way again. Only an unreachable geocoder may answer next time.
Non-retryable objections still escalate, through their severity.

Measured end to end, `critic_agent` + `route_after_critic`:

| Flags present | Confidence | Route |
| --- | --- | --- |
| none | 1.00 | summarizer |
| divergence alone | 0.85 | summarizer |
| divergence + relaxed criteria (I1) | **0.70** | **human_review** |
| divergence + concentrated comps (I2) | **0.70** | **human_review** |
| divergence + centroid fallback (I3) | 0.70 | summarizer, with the objection disclosed |
| divergence + geocoder outage (I3) | 0.70 | **planner — the rework path** |

The two CRITICAL rows are the point: **0.70 clears the 0.60 threshold and they escalate
anyway**, which is the compounding case a summed score cannot express.

**Both defects fixed.** `has_critical` now reads `(*state.flags, *flags)`, so a CRITICAL
the Critic raises triggers its own escalation — until now nothing it raised could.
`CRITIC_INCONSISTENCY` joined `_DERIVED_KINDS`: an objection is a conclusion *about* other
flags, so scoring it charges the same observation twice and compounds on every lap.

**A third defect surfaced, and it mattered more than either.** `state.flags` is
append-only across laps by design, and a rework re-runs every upstream agent, so each
re-raises what it raised before. Summed naively, a deal scored 0.70, then **0.40** on lap
one — which is below the 0.60 threshold, so `route_after_critic` sent it to human review
and lap two never happened. `MAX_REWORKS = 2` was therefore effectively 1, and
**`REWORK_LIMIT_REACHED` could not fire through the graph**: reaching it needs a retryable
objection still standing at `rework_count >= MAX_REWORKS`, and the score collapsed one lap
early every time. (Verified rather than reasoned: calling the Critic directly at lap two
*does* raise it — the router is what never gets there.) The cycle was still bounded, but by
an arithmetic accident rather than by the explicit counter §3 requires, and the two
agreeing on the outcome is what kept it hidden. Latent since U2; only reachable because
this change set made rework fire at all.

`confidence_from_flags` now de-duplicates on `(source_agent, kind, detail)`. Not on kind
alone — one retrieval pass can legitimately raise `RELAXED_MATCH_CRITERIA` twice for two
different relaxations, and both should be charged. After the fix: 0.70 held flat across
three laps, rework fired twice, `REWORK_LIMIT_REACHED` fired on the third.

**Tests at 48.** Two regressions added, each falsified in the direction it guards — the
decay test fails under a naive sum, the distinct-observations test fails under
de-duplication by kind alone. The bounded-cycle injection in `test_flag_propagation.py`
gained `retryable=True`, deliberately: injecting a non-retryable objection would now test
the escalation route that test exists to exclude.

**Still true, and U7.8 owes a case for it:** the rework path needs an objection, no
critical flag, and confidence above threshold — which no current demo deal produces.

### U7.4b ✅ — Force Extractor re-entry so a retryable objection can actually be retried

**Defect found reviewing U7.4, after it was written. The rework path U7.4 built does
nothing.**

`planner_agent` adds the Extractor to the plan only `if not
deal_terms_are_complete(state.deal_terms)`, and
`config.REQUIRED_DEAL_FIELDS = ("full_address", "price", "unit_count")` — **coordinates
are not among them.** Pass 1 populates all three, so on a rework lap the Extractor is
skipped. Measured through the real Planner:

```
plan on first entry    : ['extractor', 'comps_retrieval', 'valuation_rent', 'scenario_forecast', 'critic']
plan on rework re-entry: ['comps_retrieval', 'valuation_rent', 'scenario_forecast', 'critic']
```

So the single objection U7.4 marks `retryable` — I3 with `GEOCODER_SERVICE_UNAVAILABLE`,
justified as *"re-running the Extractor re-attempts the Census call"* — **never re-attempts
it.** The centroid coordinates persist, retrieval returns the same comps, the divergence is
identical, and the same objection is raised again. The cycle burns both laps and escalates
with nothing changed.

That is exactly the failure the `retryable` distinction exists to prevent, and `critic.py`
says so in its own words: looping on an unfixable objection *"burns the budget and arrives
back here one full pipeline later with the same objection."* The one case marked retryable
does precisely that.

**Not a safety problem** — the cycle terminates and escalates correctly, which is why U7.4
ships as-is. It is a *usefulness* problem: the back edge currently demonstrates nothing,
which matters for Checkpoint 6.1's guardrail story and for 5.1's claim that the rework edge
is this system's two-way communication.

**Chosen fix: force Extractor re-entry.** Rejected the alternative — dropping `retryable`
and letting I3-outage escalate like the others — because it is simpler but removes the only
justification the back edge has.

Deciding which optional steps run is squarely the Planner's job under #9 (*"its real
degrees of freedom are which optional steps to skip, retry/rework routing, and
escalation"*), so this does not cross the routing boundary the Critic is held to.

Scope:

- `planner_agent` includes the Extractor on a re-entry when the accumulated flags carry a
  retryable geocode failure, in addition to the existing incompleteness test.
- **Do not** add coordinates to `REQUIRED_DEAL_FIELDS`. It would not work — the centroid
  fallback populates `latitude`/`longitude`, so completeness stays true — and it would
  change first-pass behaviour for a question that is only about re-entry.
- Watch the interaction with `planner_invocations` and `rework_count`: #9's invariant is
  `planner_invocations == 1 + rework_count`, and this must not disturb it.
- Test that a second pass with a now-reachable geocoder resolves to a parcel and clears the
  objection, and that a *persistent* outage still terminates on `MAX_REWORKS`.

**As built.** `_geocode_is_worth_retrying(state)` in `agents/planner.py`; extraction is
re-planned when it or the incompleteness test says so. Measured:

| Rework state | Extraction re-planned |
| --- | --- |
| no geocode flag | no |
| `COORDINATES_FROM_CITY_CENTROID` (address unresolvable) | **no** — retrying a certainty |
| `GEOCODER_SERVICE_UNAVAILABLE` (geocoder down) | **yes** |

#9's invariant `planner_invocations == 1 + rework_count` verified to hold across all three.
Two tests added, the first falsified against the old Planner. Tests at 50.

The Planner docstring's claim that a rework "only needs comps re-run" was the written form
of this defect and is corrected in place — U7.4 had built a rework path on the opposite
assumption, and the code agreed with the docstring rather than with the plan.


### U7.5 — Disclosures: listing claims against derived estimates *(A + B)*

**Not Critic checks — Summarizer disclosures**, per Q4. No flags, no objections, no effect
on confidence or routing.

- **A (new).** Render the listing's stated `unit_rents` against `rent_estimate` in the
  valuation section. The report currently shows the estimate and never the claim, so a ~29%
  gap is invisible today. Note the unit-mix problem: the estimate is per-unit for the
  subject's bedroom count and `unit_rents` is a list — state the comparison basis rather
  than leaving it implicit. Carry the disclosure that the baseline is unsettled pending
  market-rent validation (OQ-6).
- **B (exists).** `summarizer.py:239–245` already renders the price drift. Work here is the
  **deliberately mispriced demo deal** that makes it non-trivial, plus handling
  `benchmark_unavailable_reason` in the prose.
- **Config.** A's threshold lands in `config.py` as `None` with a `TODO(U8)` naming ZORI, so
  U8 promotes by setting a value.

### U7.6 — Confidence weights and threshold *(decision #6)*

Mechanism only, per Q3: make weights and threshold tunable and evidenced, leave the numbers
to U8. **Do not re-derive the critical-flag escalation rule** — it is deliberately
independent of the weights (OQ-1, and the comment in `critic.py`). Evidence script in
`scripts/`, following the U5/U6 pattern.

Note the new checks change the score's inputs, so the existing provisional weights will
produce different confidence on the same deals than they do today. Expect the demo table
in §6 to move; re-measure it rather than assuming it held.

### U7.7 — ToT over the checks *(gated on Q2 — may not be built)*

Only if measurement shows the search changes an outcome. If it does not, this becomes a
documentation change: retire #12's Critic half on evidence and remove the `TOT_*` constants
`config.py:675` retains solely for it.

### U7.8 — Close-out

Extend `tests/test_flag_propagation.py` for `CRITIC_INCONSISTENCY`, `REWORK_LIMIT_REACHED`,
and every new `FlagKind` U7.2 and U7.3 add; re-measure the §6 demo table; append to
[`history/changelog.md`](../history/changelog.md); move decisions into §7's register with
reasoning in [`history/decision_log.md`](../history/decision_log.md); delete closed entries
from [`open_questions.md`](../open_questions.md).
