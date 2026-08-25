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

**Feeds Checkpoint 6.1.** Builds the half of `agents/critic.py` that U2 deliberately
stubbed: cross-agent consistency checking, the objections that make the rework cycle fire
on its own, and the tuning of decision #6.

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
must be **stated and defensible**, which is U7.5 and U8.

**Q4 — NEW, blocks U7.2. Measured Aug 24, 2026, before building anything.** Checks A and B
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

1. **Build C, D and F as Critic checks now** (U7.3, U7.4). Their semantics are unambiguous
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
threshold are tuned against the eval batch — but **U8 builds that batch**. Either U7.4
tunes against the five demo deals (weak, and they were calibrated to be clean), or it
slips to U8. **Recommendation: slip the tuning to U8, land the mechanism in U7**, and say
so in the register rather than tuning against inputs that cannot exercise the range.

### U7.1 — Correct the U7 docstrings to the system that exists *(maintenance)*

No logic. `agents/critic.py`'s module docstring and both `TODO(U7)` comments describe four
checks and a `value_estimate` that #15 removed. Rewrite to Q1's findings — including that
rent-vs-comps is consumed, not reproduced — so the file stops advertising a design the
build abandoned. Lands first so the behavioural diffs that follow are read against an
accurate description.

### U7.2 — Disclosures: listing claims against derived estimates *(A + B)*

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

### U7.3 — Checks: forecast coherence *(C + D)*

- **C.** `forecast_detail.projection_base_price` == `deal_terms.price` and
  `projection_base_rent` == `rent_estimate`. Exact equality against the bases #15 and #17
  fixed. Cheap, and it catches a class of defect nothing else would see.
- **D.** Band monotonicity (optimistic ≥ base ≥ pessimistic, on both series) and coherence
  with the disclosed screening. The motivating case is real and from U6: an optimistic rent
  of +19.03%/yr printed beneath a basis block stating FY2024 had been screened out —
  19.03% *is* Chicago's FY2024 figure.

### U7.4 — Checks: comp-set quality *(E + F)*

- **F.** Comp-source concentration via `Comp.listing_source`. Eight comps from one feed are
  not eight independent observations; the corpus is 91% RentDigs.com. **Must not
  double-count with `COMPS_SPATIALLY_CONCENTRATED`**, which is a different concentration
  and already exists.
- **E.** Comp attribute drift: the comps' bed/sqft distribution against `deal_terms`.
  `RELAXED_MATCH_CRITERIA` records *that* relaxation happened, never *how far* it went.

Lowest-value pair of the three; cut here first if U7 runs long.

### U7.5 — Wire the objections in, and make the rework cycle fire on its own

Populate `_consistency_objections()` from U7.2–U7.4 and consume Valuation's
`RENT_DIVERGES_FROM_COMPS` rather than recomputing it. This is the behavioural change:
`critic_rejected` becomes reachable and the `Critic → Planner` back edge carries traffic
for the first time.

**Three things are mandatory here.**

1. **Bounded-cycle regression tests.** `MAX_REWORKS` stops being theoretical.
2. **Decide which objections are worth a rework at all.** A rework re-runs the pipeline, so
   an objection a second pass cannot possibly resolve — B, a mispriced listing — should
   escalate rather than loop. Objections that warrant rework and objections that warrant
   human review are different sets; conflating them spends the budget on deals it cannot
   help.
3. **Mind the routing precedence.** `planner.route_after_critic` checks
   `needs_human_review` **before** `critic_rejected`, deliberately (a deal a human should
   see reaches a human rather than being quietly re-run first). Consequence: a deal
   carrying any critical flag escalates and **never reworks**. So the rework path is only
   reachable for a deal with an objection, no critical flag, and confidence above
   threshold — which is *none of the current demo deals*. Exercising this path needs a
   purpose-built case, and U7.8's tests must construct one rather than assuming an
   existing demo deal will reach it.

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
and every new `FlagKind` U7.2–U7.4 adds; re-measure the §6 demo table; append to
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
