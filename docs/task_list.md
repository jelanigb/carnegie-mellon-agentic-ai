# Task List

**Per-unit work breakdown, written before coding starts and approved before it does.**
Part of the workflow in
[`design/engineering_standards.md`](design/engineering_standards.md#how-a-unit-is-built).

Conventions:

- **Each `###` subsection is one change set** — one commit, reviewable on its own.
- **Maintenance is its own subsection**, never folded into a behavioural one.
- **Unit-level open questions come first** and name the subsection they block. Anything
  that would change the design gets answered before that subsection starts, not during it.
- A subsection may land the system in a **temporarily incomplete state** if the completing
  subsection is named here.
- Closed units are trimmed to a one-line pointer at the changelog once they land.

---

## U7 — Critic / Reviewer

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
([`open_questions.md`](open_questions.md) OQ-2, and the U6 precedent where
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

### U7.2 — Interaction checks: when disclosures compound *(the unit's substance)*

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

**These escalate; they do not rework.** Re-running the pipeline cannot produce a better
geocode or a denser market. See U7.4.

### U7.3 — Check: comp attribute drift *(E — the one surviving attribute check)*

The relaxation flags record *which tolerance was loosened* — "dropped the square-footage
band", "loosened bedroom tolerance from ±0 to ±1" — but never the **realized drift** of the
comps that came back. A reader is told the criteria widened, not that the returned set
averages 1,400 sqft against a 950 sqft subject.

Compares `state.comps` against `deal_terms`, so it is cross-agent. **Cannot fire on a deal
that never relaxed**, which is what keeps it off the clean baseline. Threshold to
`config.py`. Feeds I1 above rather than duplicating it: drift is the measurement, I1 is the
consequence for the divergence signal.

### U7.4 — Wire the objections in, and make the rework cycle fire on its own

Populate `_consistency_objections()` from U7.2 and U7.3 and consume Valuation's
`RENT_DIVERGES_FROM_COMPS` rather than recomputing it. This is the behavioural change:
`critic_rejected` becomes reachable and the `Critic → Planner` back edge carries traffic
for the first time.

**Three things are mandatory here.**

1. **Bounded-cycle regression tests.** `MAX_REWORKS` stops being theoretical.
2. **One case genuinely warrants rework, and it is not obvious.**
   `tools/geocoding.py:225–238` catches a `GeocodingError` — the Census *request* failing,
   as distinct from running and finding no match — and falls through to the corpus
   centroid. Both paths raise the same `COORDINATES_FROM_CITY_CENTROID` flag. U3 caught
   this and logged the distinction to diagnostics, with the comment stating plainly that
   *"the resulting flag says the same thing either way."*

   That matters here: **a centroid fallback caused by a Census outage is retryable, and a
   rework pass would re-run the Extractor and re-attempt the geocode.** A fallback caused
   by an address with no street number is not retryable and should escalate. This is the
   clearest case in the system where rework is the right response rather than escalation —
   and the Critic cannot currently tell the two apart, because the flag does not carry the
   cause. Either the flag gains a distinguishing detail, or rework is not offered here.
3. **Decide which objections are worth a rework at all.** A rework re-runs the pipeline, so
   an objection a second pass cannot possibly resolve — B, a mispriced listing — should
   escalate rather than loop. Objections that warrant rework and objections that warrant
   human review are different sets; conflating them spends the budget on deals it cannot
   help.
3. **Two defects in `critic.py` that block interaction checks**, both found while
   designing U7.2 and neither visible from the plan:
   - ✅ **Resolved in U7.1b** — the retryable case is now `GEOCODER_SERVICE_UNAVAILABLE`
     and the unresolvable one stays `COORDINATES_FROM_CITY_CENTROID`, so the Critic can
     branch without parsing message text.
   - **`critic.py:155` reads `state.flags`**, the *incoming* accumulated list, not the
     local `flags` list the Critic is building this pass. A CRITICAL the Critic raises
     itself would not trigger its own escalation. U7.2's mechanism depends on this being
     fixed.
   - **`_DERIVED_KINDS` excludes only `LOW_CONFIDENCE_ESTIMATE` and
     `REWORK_LIMIT_REACHED`.** `CRITIC_INCONSISTENCY` is not in it, so on a rework lap the
     Critic's own objection would count against the score — the exact self-driving-down
     defect that set exists to prevent. It should join.
4. **Mind the routing precedence.** `planner.route_after_critic` checks
   `needs_human_review` **before** `critic_rejected`, deliberately (a deal a human should
   see reaches a human rather than being quietly re-run first). Consequence: a deal
   carrying any critical flag escalates and **never reworks**. So the rework path is only
   reachable for a deal with an objection, no critical flag, and confidence above
   threshold — which is *none of the current demo deals*. Exercising this path needs a
   purpose-built case, and U7.8's tests must construct one rather than assuming an
   existing demo deal will reach it.

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
[`history/changelog.md`](history/changelog.md); move decisions into §7's register with
reasoning in [`history/decision_log.md`](history/decision_log.md); delete closed entries
from [`open_questions.md`](open_questions.md).

---

## Maintenance — not tied to a unit

### M1 — Name the decision at every citation site

~50 code comments cite decisions bare (`decision #9`, `§7 decision #4`). A reader who does
not already know what #9 was has to leave the file to find out. Append a short gloss at
each site — `decision #9 (Planner topology)` — matching the names now in §7's register.
Comment-only; no logic. Sites: `graph.py`, `config.py`, `state.py`, `critic.py`, `tot.py`,
`planner.py`, `mcp_server.py`, `llm_client.py`, `fmr_history.py`, `geocoding.py`,
`county_crosswalk.py`, `main.py`, and six scripts.
