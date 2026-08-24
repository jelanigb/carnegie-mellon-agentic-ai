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

**Q1 — blocks U7.3, and it is the one that decides the unit's shape.**
`agents/critic.py`'s `TODO(U7)` names four consistency checks. Reviewed against the
built system before planning this unit, **only two of the four are still live**:

| Named check | Status | Evidence |
| --- | --- | --- |
| Rent estimate vs. the comp set's distribution | ⚠️ **already built, in another agent** | `agents/valuation_rent.py:247` raises `RENT_DIVERGES_FROM_COMPS` as U5's Observe step, using `comp_implied_rent_p25/median/p75` |
| Scenario bands vs. the base they branch from | ✅ live | `ForecastDetail.projection_base_price` / `projection_base_rent` and `Scenario` bands both populated by U6 |
| Value estimate vs. listing price | ❌ **dead** | Decision #15 made `value_estimate` permanently `None`; nothing writes it. The TODO predates that decision |
| Comp-source concentration | ✅ live, unbuilt | `Comp.listing_source` exists for exactly this; corpus is 91% RentDigs.com |

**The question:** does the Critic re-check rent-vs-comps independently, or does it consume
the flag Valuation already raises? Re-checking duplicates logic across two agents and
risks the two disagreeing; consuming it means the Critic's "cross-agent" claim rests on two
checks rather than four. **Recommendation: consume, don't duplicate** — and narrow the
docstring rather than leaving it describing a system that no longer exists. Needs a
decision because it changes what U7 can claim at Checkpoint 6.1.

**Q2 — blocks U7.5.** Does the Critic run a ToT search over its checks, per decision #12?
#12 adopted ToT here on the grounds that the checks "differ in cost and are not
independent." With Q1 resolving to two checks, both cheap and both local to state, **that
premise may no longer hold** — a search over two cheap independent checks is decoration,
and this project has an explicit standard against that
([`open_questions.md`](open_questions.md) OQ-2, and the U6 precedent where
`scripts/forecast_evidence.py` had to *prove* the search was load-bearing).
**Recommendation: measure first** — if the search cannot be shown to change an outcome,
record that #12's Critic half was retired on evidence, which is a better result for the
report than a search that does nothing. This is the same call U6 made about
`AppreciationTier`.

**Q3 — blocks U7.4, non-blocking for everything else.** Decision #6's weights and the 0.60
threshold are tuned against the eval batch — but **U8 builds that batch**. Either U7.4
tunes against the five demo deals (weak, and they were calibrated to be clean), or it
slips to U8. **Recommendation: slip the tuning to U8, land the mechanism in U7**, and say
so in the register rather than tuning against inputs that cannot exercise the range.

### U7.1 — Correct the U7 docstrings to the system that exists *(maintenance)*

No logic. `agents/critic.py`'s module docstring and both `TODO(U7)` comments describe four
checks and a `value_estimate` that decision #15 removed. Rewrite to the Q1 findings so the
file stops advertising a design the build abandoned. Lands first so the behavioural diffs
that follow are read against an accurate description.

### U7.2 — Consistency check: scenario bands against their projection base

Pure function over `ForecastDetail` + `Scenario`, no LLM call. Objection when a band is
inconsistent with the base it branches from or with the disclosed screening (the U6
precedent: an optimistic rent of +19.03%/yr printed beneath a basis block saying FY2024 was
screened out — that exact contradiction is the check's motivating case). Unit tests over
constructed `DealState`s; no pipeline wiring yet.

### U7.3 — Consistency check: comp-source concentration

Uses `Comp.listing_source`. Eight comps from one feed are not eight independent
observations. Threshold to `config.py`. Note the interaction with
`COMPS_SPATIALLY_CONCENTRATED`, which is a *different* concentration and already exists —
these must not double-count.

### U7.4 — Wire the objections in, and make the rework cycle fire on its own

Populate `_consistency_objections()` from U7.2 and U7.3. This is the behavioural change:
`critic_rejected` becomes reachable, and the `Critic → Planner` back edge starts carrying
traffic for the first time. **Bounded-cycle regression tests are mandatory here**, and
`MAX_REWORKS` stops being theoretical. Depends on Q1.

### U7.5 — Confidence weights and threshold *(decision #6)*

Mechanism only if Q3 resolves as recommended: make the weights and threshold tunable and
evidenced, and leave the numbers to U8. **Do not re-derive the critical-flag escalation
rule** — it is deliberately independent of the weights (see `critic.py`'s comment and
OQ-1). Evidence script in `scripts/`, following the U5/U6 pattern.

### U7.6 — ToT over the checks *(gated on Q2 — may not be built)*

Only if Q2's measurement shows the search changes an outcome. If it does not, this
subsection becomes a documentation change instead: retire #12's Critic half on evidence,
and remove the now-unused `TOT_*` constants that `config.py:675` retains solely for it.

### U7.7 — Close-out

Extend `tests/test_flag_propagation.py` for `CRITIC_INCONSISTENCY` and
`REWORK_LIMIT_REACHED`; append to [`history/changelog.md`](history/changelog.md); move
decisions taken during the build into §7's register with reasoning in
[`history/decision_log.md`](history/decision_log.md); delete closed entries from
[`open_questions.md`](open_questions.md).

---

## Maintenance — not tied to a unit

### M1 — Name the decision at every citation site

~50 code comments cite decisions bare (`decision #9`, `§7 decision #4`). A reader who does
not already know what #9 was has to leave the file to find out. Append a short gloss at
each site — `decision #9 (Planner topology)` — matching the names now in §7's register.
Comment-only; no logic. Sites: `graph.py`, `config.py`, `state.py`, `critic.py`, `tot.py`,
`planner.py`, `mcp_server.py`, `llm_client.py`, `fmr_history.py`, `geocoding.py`,
`county_crosswalk.py`, `main.py`, and six scripts.
