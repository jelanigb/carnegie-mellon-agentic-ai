# Open Questions

**Everything unresolved, and nothing else.** Closed decisions are in
[`implementation_plan.md`](implementation_plan.md) §7 (the register) and
[`history/decision_log.md`](history/decision_log.md) (the reasoning). This file is loaded
at the start of every session, so it is kept short on purpose — an entry that closes gets
**deleted** from here and its verdict written into the §7 register, not struck through.

**Grouped by the part of the system it affects.** Each entry names the unit that must
close it and what closing it looks like. `OQ-n` numbers are stable handles for
conversation; they are not decision numbers.

Last reviewed: Aug 24, 2026 — before U7.

---

## Orchestration & control flow

### OQ-1 · decision #6 · U7 — confidence threshold and severity weights
Both are provisional: threshold 0.60, weights unmeasured. **Closes when** U7 tunes them
against the eval batch. **Do not re-derive:** a critical flag already escalates on its own
ground, independent of the score (U2 finding 1) — that guarantee is deliberately separate
from the weights *because* the weights were always going to move. `agents/critic.py:114`.

### OQ-15 · U8, cut list 2a — pass-scoped flags
`DealState.flags` is append-only, so nothing separates *raised this pass* from *ever
raised*, and every Critic interaction check reads the accumulated list as current truth. A
rework that succeeds still re-raises the objection it was sent back to fix. **Closes when**
each flag is stamped with the `planner_invocations` that produced it and the Critic
evaluates only the current pass — noting that an agent skipped on a rework raises nothing,
so absence must not be read as *cleared* when it means *not re-examined*; `state.plan`
records which agents ran. **Accepted knowingly for U7** — bounded by `MAX_REWORKS`, and
every affected path escalates to a human. `agents/critic.py`, `agents/planner.py`.

### OQ-2 · decision #12 · U7 — which consistency checks, and the search over them
Four checks are named in `agents/critic.py:82` but unbuilt. #12 adopted ToT here on the
grounds that the checks differ in cost and are not independent. **Closes when** U7 defines
the check set and its search space. **Blocking for U7** — it decides whether the Critic
makes an LLM call at all, which OQ-5 and OQ-7 both depend on.

---

## Rent & valuation

### OQ-3 · U7/U8 — New York rents predict at roughly twice the trio's error
~$1,065 MAE against ~$518, under every training set tested; no shortlist fixes it. New York
is in `build_comps_index.INDEXED_MARKETS`, so a Staten Island subject reaches the rent model
and gets an estimate half as reliable as a Los Angeles one. **This is a disclosure
requirement, not a modelling problem** — it needs a flag, and U8 needs a case that trips it.

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
— treat those as findings, not defaults. `config.py:675`.

### OQ-6 · deferred, no unit — Zillow ZORI as the independent rent check
#16 adopted ZORI as the validation series and it has not been built. It is the only
available test of **the rent model's largest unverified assumption** — that rent-to-FMR
structure is stable across the ~7 years between corpus and today. **Closes when** a ZORI
pull lands and the ratio is measured at both ends. `config.py:430`.

---

## Data & sources

### OQ-7 · decision #11 · U8, cut list position 2 — public-record for-sale ground truth
County assessor open data (Cook, LA County, NYC) is chosen, admissible under §8's "public"
definition, and unbuilt. It is what would let the *value* estimate be scored rather than
only demonstrated. **Closes when** U8 ingests it — or, if cut, when the gap is written up
explicitly. Cut before the LLM fallback deliberately: it attaches a new data source to the
one unit that must not slip.

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

### OQ-9 · decision #8 · U7/U9 — Critic and Summarizer model roles
Both currently hold the extraction model's value, and neither makes an LLM call yet, so the
setting is untested rather than chosen. **Closes when** each role first calls a model —
U7 for the Critic (see OQ-2), U9 for the Summarizer.

### OQ-10 · `TODO(security)` · no unit — the on-disk token fallback
Keys fall back to plaintext files in `ignore/` when the env var is unset. **The question is
whether to drop the fallback and require the env var.** Affects `tools/hud_fmr.py:24`,
`tools/llm_client.py:41`, and `tools/diagnostics.py:36` (which deliberately prints the
account identifier). Raise before any public demo.

### OQ-11 · U6 leftover → U7 — `query_comps` as an MCP tool
`mcp_server.py:43` notes the tool was not added because the ToT evaluator's
comp-distribution check did not need it. **The Critic's check (OQ-2) may.** Decide when
OQ-2 does.

---

## Evaluation & demo

### OQ-12 · U8 — two flags that need an eval case
`config.py:286` wants a leave-one-metro-out run as evaluation rather than the current
in-sample split; `config.py:363` needs confirmation that anything still trips the flag it
guards. Both are `TODO(U8)` at the site.

### OQ-13 · no unit — LangSmith account
Wiring is done and env-driven; every run prints whether tracing is on, so a silently
uncaptured run is not a failure mode. **Not a build blocker.** It *is* a blocker on
Checkpoint 5.1's trace evidence, and free-tier traces expire after 14 days — so set it up
close to the write-up, not long before. No key present in `ignore/` as of Aug 24, 2026.

### OQ-14 · U7, U9 — checkpoint criteria as build artifacts
Where a checkpoint publishes completion criteria, the unit is specified to *produce* each
one rather than write it up afterward. U4 did this (see the acceptance-criteria table in
[`history/decision_log.md`](history/decision_log.md#retrieval)). **Apply the same treatment
to 5.1 and 6.1** as their criteria are published.
