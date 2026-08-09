# Multi-Family Residential Deal Evaluator — Implementation Plan

**Technical plan of record.**
Author: Jelani Gould-Bailey · Last updated: Aug 8, 2026

## How this project is built

This is the engineering plan for a capstone system built during CMU's Agentic AI
executive education program. It is written as a working document: architecture,
sequencing, data strategy, and the reasoning behind each decision, updated as
assumptions get tested against real data.

**Working model.** I set the architecture, data strategy, and execution sequence, and
I review every change. Implementation is executed with Claude Code against the
specifications in this document. This mirrors how I work as an engineering manager —
the leverage is in the design decisions, the data reasoning, and the review standard,
and this document is where that work lives. Sections §2 (data strategy), §3 (stack
rationale), §5 (state design), and §6 (sequencing) are the substance of the project;
the code is the expression of them.

Two conventions follow from that and are enforced throughout: every non-obvious
decision is recorded here *with its reasoning*, and every assumption is labeled as an
assumption until it has been checked against data. §2 contains a worked example of the
second — a metro-selection hypothesis I held confidently, tested, and found to be
wrong.

> **Aug 8, 2026 — major revision.** Three changes. (1) **Sequencing is now driven by
> dependency and risk rather than the syllabus calendar.** The program's weekly
> checkpoints assess a written design update alongside a working agent update; they do
> not require that a given capability be built only in the week its module is taught.
> Ordering the build by dependency and technical risk is therefore both permitted and
> better engineering — see §6. (2) **LangGraph is adopted immediately** rather than
> migrated to later; the earlier staged plan existed only to track the syllabus, and
> with that constraint gone it would have meant building the orchestration layer twice
> (§3). (3) §2's metro hypothesis was tested against both datasets and replaced.

---

## 1. Project Summary

This is a capstone project for a CMU Agentic AI executive education program. The system
is a **seven-agent pipeline** that evaluates small multi-family (2–4 unit) residential
properties as investment candidates:

1. **Planner** — inspects the deal, decides which downstream steps are needed, routes
   between agents, governs retries/escalation.
2. **Extractor** — parses an unstructured listing into structured deal terms; generates
   clarifying questions on missing fields; flags assumptions when no answer is available.
3. **Comps/Retrieval** — RAG-based comp finder over a rental listings corpus; adaptively
   relaxes search criteria (radius, match strictness) if matches are sparse, and flags
   when it does.
4. **Valuation & Rent** — rent regression model + comps-based value estimate.
5. **Scenario/Forecast** — Tree-of-Thought reasoning over rent-growth/appreciation
   scenarios (optimistic/base/pessimistic), informed by metro-level housing trend data.
6. **Critic/Reviewer** — checks consistency across upstream outputs, aggregates all flags
   into an overall confidence score, can route low-confidence deals to a
   "needs human review" state.
7. **Summarizer** — produces the final investor-facing report; required to surface all
   upstream flags prominently, not just bottom-line numbers.

**Unifying design principle — "Transparent Degradation":** whenever an agent proceeds on
incomplete or relaxed information (a widened comp radius, an unresolved clarifying
question, a low-confidence estimate), it attaches a named flag to its output. Flags
propagate downstream through the Critic to the Summarizer, so the final report always
discloses *when and how* the system deviated from the ideal path rather than silently
absorbing the gap. This principle should be visible in code, not just in the report —
every agent function should be able to append to a shared `flags` list in state, and nothing
should quietly overwrite or drop a flag on its way downstream.

**Data sources (finalized):**
- **Kaggle apartment rental dataset** — unit-level features (beds/baths, sqft, location,
  amenities, rent) for comps retrieval and rent-structure regression training.
  Candidate: https://www.kaggle.com/datasets/shashanks1202/apartment-rent-data
  (verify column fit against the comps schema below; confirm/parse the `time` column,
  likely a Unix timestamp — dataset is known to be ~2017–2019 vintage).
- **HUD Fair Market Rents (FMR)** — free, public, county-level, annual, rent-specific
  time series. Used to anchor the Kaggle-derived rent structure to current dollars.
  API: https://www.huduser.gov/portal/dataset/fmr-api.html (free account + bearer token
  required — set this up before Week 4).
- **Redfin Data Center — Housing Market Tracker, filtered to `property_type =
  Multi-Family (2-4 Unit)`** — free, public, time series (median sale price, days on
  market, inventory) available down to neighborhood/ZIP/city/county/state, filterable
  by property type. This is the sole appreciation source (see §2 — Redfin Home Price
  Index does not cover multi-family and is not used). https://www.redfin.com/news/data-center/downloads/

---

## 2. Data Strategy: Reconciling Kaggle/Redfin Vintage and Category Mismatch

Two problems surfaced while planning the data layer, and both are resolved the same way:
ground every dollar figure in a *dated, purpose-matched* source rather than trusting a
single dataset to do more than it can.

### Problem 1 — the Kaggle rent data has no reliable current date
The Kaggle apartment dataset is a single historical scrape (~2017–2019). Any rent
estimate trained directly on it is calibrated to that era's price level, not today's.
Left uncorrected, a "$1,450/month" prediction is a 2018 number in a 2026 costume, and
every downstream valuation and scenario built on it inherits that bias.

### Problem 2 — Redfin measures price, not rent
Redfin's data (Housing Market Tracker, RHPI) tracks home *sale* prices. Home price
appreciation and rent growth diverge meaningfully over multi-year windows — most
visibly 2020–2022, when price growth far outpaced rent growth as low rates pulled
buyers in. Using Redfin's price trend to adjust a *rent* number would import
interest-rate-driven price dynamics into a quantity they don't actually explain.

### Resolution: separate "structure" from "level," and match each quantity to a same-kind source

**Rent-level anchoring (Valuation & Rent agent):**
1. Train the regression on rent *normalized by that row's local HUD FMR at the time it
   was recorded* (rent ÷ FMR-for-that-county-and-year), not raw dollars. The model
   learns a structural relationship — "this bed/bath/sqft/amenity combination rents at
   ~1.15× the local FMR" — that ages far more slowly than a dollar figure.
2. At prediction time, multiply the model's output ratio by *today's* HUD FMR for the
   subject property's county. This produces a current-dollar estimate anchored to a
   real, dated reference point instead of an implicit 2018 price level.
3. Flag every estimate that used this anchoring path (`kind="rent_anchored_to_fmr"`,
   `severity="info"`) so the report can disclose the mechanism, and flag separately
   (`kind="fmr_unavailable_for_county"`, `severity="warn"`) if HUD has no FMR entry for
   the subject county and a coarser (state/national) fallback had to be used.

**Appreciation forecasting (Scenario/Forecast agent):**
- Use the Housing Market Tracker filtered to `property_type = Multi-Family (2-4 Unit)`
  as the appreciation/trend series — this matches the asset class directly rather than
  relying on a blended series dominated by single-family transaction volume. Small
  multi-family is bought by a different buyer pool (investors pricing off cap rates)
  than single-family (owner-occupants), so an asset-matched trend line is a real
  accuracy improvement, not just a nice-to-have.
- Redfin Home Price Index (RHPI) is **not used** — it covers single-family homes only
  and has no multi-family series, so it can't substitute or supplement here.
- **Geographic level: metro is the primary tier, not ZIP.** Redfin's `REGION TYPE`
  offers ZIP, metro, and other levels directly (no manual ZIP→county rollup needed).
  For the target inference metros (**Chicago, Los Angeles, Cleveland** — see the metro
  selection subsection below), metro-level `HOMES SOLD` medians are 362 / 302 / 149 per
  period, versus ZIP-level counts that are frequently single digits with wild YoY swings
  from small denominators. Metro-level is directionally what the Scenario/Forecast agent needs
  (bands for optimistic/base/pessimistic), not sub-market precision, so the added
  stability outweighs the lost granularity. Revised three-tier design, with the tier
  used flagged (`kind="appreciation_source"`, `severity="info"` for tiers 1–2,
  `"warn"` for tier 3):
  1. **Metro-level, multi-family filtered (default — build this now).** Adequate
     sample for any of the target metros; this is the only tier required for the
     pipeline to work end-to-end.
  2. **ZIP-level, multi-family filtered (deferred / stretch goal).** Would apply only
     when the subject ZIP clears a minimum-sample gate (e.g. `HOMES SOLD` ≥ ~8–10 for
     the period). Not built in the current phase — the ZIP extract already pulled
     shows single-digit sample counts and YoY swings in the thousands of percent even
     within a large metro (NY), so this tier would clear its own usability gate rarely
     enough that it isn't worth building alongside the core pipeline. Documented as
     future work, the same way cross-deal episodic memory was deferred in Checkpoint
     2.1 — real, but not blocking.
  3. **Metro-level, all-residential, unfiltered (fallback).** For the rare case where
     even metro-level multi-family volume is too thin — unlikely for the target metros
     but kept for robustness against edge cases or future metro additions.
- **Use a consistent period frequency — rolling 3-month, not single-month.** Rolling
  3-month windows smooth out the single-month sample-size noise seen even at metro level
  for smaller markets, and consistency matters more than granularity here since the
  pipeline compares periods to each other. *(Implementation note, Aug 8: the extract on
  disk is `Monthly`. Compute the rolling window in `tools/redfin_data.py` rather than
  re-downloading — see "Two data gaps" below.)*
- **Apply a minimum-price floor before any sample-size logic runs.** Raw extracts
  contain implausible `MEDIAN SALE PRICE NSA` values ($1, $100, $975) — near-certainly
  non-arm's-length transfers (quitclaim deeds, corrective deeds, nominal-consideration
  transfers) rather than real market sales. Drop any period below a floor (start around
  $10,000–$20,000 and adjust after inspecting the target metros' actual distributions)
  before it can corrupt a median or a YoY calculation.
- **Pull roughly 2018–present**, not just the last year or two. This window is sized
  for the Scenario/Forecast agent's own needs — real historical variance to ground its
  optimistic/base/pessimistic branches (e.g. base = long-run average growth, optimistic
  = best sustained stretch observed, pessimistic = worst) — and is **independent of
  Kaggle's ~2017–2019 vintage**; the two datasets don't need matching date ranges,
  since HUD FMR is what bridges Kaggle's vintage to today (see rent-level anchoring
  above), not Redfin's date range. 2018–present just needs to capture a pre-COVID
  baseline alongside the anomalous period, rather than only the anomaly; reaching back
  to Kaggle's exact start year isn't required.
- **Flag the 2020–2022 window explicitly wherever it feeds an average or scenario
  band** (`kind="anomalous_period_included"`, `severity="info"`). Near-zero interest
  rates pulled price growth well above trend during this stretch; blending it in
  silently risks skewing "base case" toward an unusual few years rather than normal
  market behavior. Flagging it keeps the choice visible and defensible either way.
- Redfin data is never used to adjust rent dollars — only price/appreciation.
- Filter to the target metros immediately on load — Redfin data is only used for
  per-deal inference lookups (never for training), so it only ever needs to cover the
  2–3 inference metros, not a national pull.

**Out of scope for now:** Investor Home Purchases and Existing Home Sales datasets —
no clear role in the current agent design; documented as potential future enrichment
(e.g., a market-competitiveness signal) rather than built now.

### Metro Scope: Training vs. Inference

Two different scopes are needed, and they shouldn't be the same size:

- **Inference/demo scope: 2–3 metros.** Kept small deliberately — enough to show the
  system working on genuinely different markets without turning metro selection into
  its own research project. This is the set actual pipeline runs and checkpoint demos
  will use.
- **Training scope: broader than the inference set, but not the full nationwide
  Kaggle dataset.** The regression predicts a *ratio to local FMR*, not a raw dollar
  figure, so it benefits from more diverse training data — restricting training to only
  2–3 metros risks overfitting to those markets' specific feature/price relationships.
  At the same time, because the Kaggle dataset is a single-vintage scrape, the HUD FMR
  pull needed to normalize the training target is bounded by *the number of distinct
  counties represented*, not by the number of training rows — so widening the training
  set doesn't meaningfully raise the FMR API cost. The practical constraint is data
  cleaning and county/FIPS mapping effort, not FMR access. A curated shortlist of
  roughly 5–8 metros (rather than the full dataset) keeps that cleanup bounded while
  still giving the regression meaningfully more diversity than 2–3 metros alone. The
  2–3 inference metros should be a subset of this training shortlist, so they're
  guaranteed adequate comp density and a validated data pipeline.
- **Before finalizing metro choices:** run a quick `groupby` count on the Kaggle
  dataset by city/metro to confirm actual listing density — the candidates below are
  based on known housing-stock patterns, not on this dataset's specific coverage, and
  need to be checked against it directly. **Done — see the metro selection subsection
  below; the inference trio is settled and the training shortlist is decision #4 in §7.**

### Metro Selection: hypothesis tested and replaced (Aug 8, 2026)

**The original hypothesis was New York, Chicago, Philadelphia**, reasoned from
housing-stock knowledge: small multi-family (2–4 unit) stock concentrates in the
Northeast and older Midwest/Rust Belt cities plus parts of California — New York's
outer-borough brownstones, Chicago's two-/three-flats, Philadelphia's duplexed
rowhomes, alongside Providence, Cleveland, Milwaukee, Buffalo, Detroit, and Los
Angeles. That reasoning was sound about *housing stock* but said nothing about
*whether the two datasets actually cover those markets*.

The plan called for confirming it with a `groupby` before building. **That check has
now been run against both datasets, and the hypothesis did not survive it.**

Reproduce with `src/scripts/verify_metro_selection.py`. Bars are provisional and stated
in the script: ≥500 Kaggle listings, ≥100 median sales per period.

| Metro | Kaggle rent listings | Redfin 2–4 unit sales (median/period) | Verdict |
|---|---|---|---|
| **Los Angeles** | 2,433 | 302 | ✅ passes both |
| Newark / Jersey City | 561 | 746 | ✅ passes both — see note |
| **Chicago** | 634 | 362 | ✅ passes both |
| **Cleveland** | 608 | 149 | ✅ passes both |
| Boston | 600 | 258 | ⚠️ passes both, but town-based FMR |
| Cincinnati | 798 | 62 | ❌ sales volume too thin |
| **New York** | 283 (incl. all boroughs) | 746 | ❌ comps too thin |
| Pittsburgh | 250 | 76 | ❌ weak on both |
| **Philadelphia** | 230 | 43 | ❌ weak on both |
| Milwaukee | 99 | 170 | ❌ comps too thin |
| Detroit | 84 | 66 | ❌ weak on both |
| Buffalo | 24 | 118 | ❌ comps too thin |

New York has the highest 2–4 unit transaction volume of any metro in the extract, but
only 283 Kaggle rent listings across all five boroughs — too thin to build a credible
comp corpus, and comps are the grounding mechanism the whole design depends on.
Philadelphia is weak on both axes and can support neither half of the pipeline.
Milwaukee, Buffalo, and Detroit are classic small-multifamily markets that the
housing-stock reasoning correctly identified but that this particular Kaggle scrape
barely covers — a reminder that corpus coverage and market characteristics are
independent questions.

**Documented alternate — Newark / Jersey City.** This pairing clears both bars (561
listings; it shares the New York CBSA, hence the 746 sales figure) and would offer
New York metro exposure with an adequate comp corpus. Essex and Hudson counties are
county-based FMR, so it carries no New England complication. It is not in the selected
trio because Chicago, LA, and Cleveland already provide three structurally different
markets, and because the shared CBSA means its appreciation series would duplicate
New York's rather than add an independent one. Recorded here as a viable substitute if
one of the three proves problematic later.

**Final trio: Chicago, Los Angeles, Cleveland.** Each is strong on both datasets, each
is a genuine 2–4 unit market (LA and Cleveland were both already named in the original
candidate list), and all three sit in standard **county-based FMR states** — Cook
County IL, Los Angeles County CA, Cuyahoga County OH — so `tools/hud_fmr.py` needs no
New England town-based branch. Boston remains excluded for exactly that reason: HUD
defines FMR areas by *town* in the six New England states (CT, ME, MA, NH, RI, VT).

**Why this correction is documented rather than quietly applied.** The original
hypothesis was reasoned from real domain knowledge and was confidently held — and it
was wrong in a way that would have degraded every downstream component had it gone
unchecked. Recording the hypothesis, the test, and the correction is the same
discipline the system itself implements: the failure worth guarding against is not
being wrong, but being wrong without disclosing it.

**SAFMR status (verified against the live API, see §9):** Cook County returns the
Small Area FMR list shape; New York County returns the flat shape. LA County is very
likely SAFMR (large, high-cost) and Cuyahoga likely flat — **to be confirmed in Unit 1
with a real call**, not assumed. Either way the client already handles both shapes, so
this is a verification task rather than a build task.

### Two data gaps found during the same check

**Gap 1 — the Kaggle dataset has no county or ZIP column.** Actual columns are
`id, category, title, body, amenities, bathrooms, bedrooms, currency, fee, has_photo,
pets_allowed, price, price_display, price_type, square_feet, address, cityname, state,
latitude, longitude, source, time`. The entire FMR normalization strategy keys on
`county_fips`, so this gap sits directly underneath the rent model and was previously
invisible in this plan.

*Resolution:* since training is scoped to a curated ~5–8 metro shortlist anyway, build
a hand-verified `(cityname, state) → county_fips` crosswalk for those cities — roughly
30–50 entries, no new dependencies, about an hour. A lat/lon → FIPS spatial join
against Census TIGER shapefiles (via `geopandas`) is the scale-up path if the full
100K rows are ever needed; **not worth the dependency now.**

**Gap 2 — the Redfin extract on disk is `Monthly`, not `Rolling 3 Months`** as §2
specifies (verified: `FREQUENCY` is uniformly `Monthly`, `REGION TYPE` uniformly
`Metro`, 943 distinct metros, 102 periods each, Jan 2018 – Jun 2026). Do **not**
re-download — compute a trailing 3-period rolling median in pandas at load time in
`tools/redfin_data.py`. Same result, and it keeps the smoothing window as a tunable in
`config.py` rather than baked into a file.

**Kaggle vintage confirmed:** the `time` column is a Unix timestamp spanning **Dec 2018
– Dec 2019**. FY2019/FY2020 is therefore the correct FMR normalization year, confirming
the §9 smoke test's choice of `year=2019`.

### HUD FMR API: Implementation Notes

Concrete details for `tools/hud_fmr.py`, from the API docs
(https://www.huduser.gov/portal/dataset/fmr-api.html):

- **`year` is a single fiscal year per call, and must be pulled per (county, year)
  pair, not once overall.** Two distinct kinds of pulls are needed: (1) the Kaggle
  vintage year(s) for training normalization — if Kaggle rows span more than one year,
  that's multiple distinct `year` values, not one blanket value; (2) a current anchor
  year for inference. Don't hardcode the current year — call once *without* the `year`
  parameter (defaults to latest available) and read the `year` field back from the
  response, so the code doesn't go stale if this is still running months from now.
- **`entityid` for a county is the 10-digit FIPS-style code** (e.g. `5100199999`),
  obtained via `fmr/listCounties/{state}` — this is exactly what `DealTerms.county_fips`
  is meant to hold, so no reformatting should be needed between the Extractor's output
  and the FMR lookup.
- **Handle the Small Area FMR (SAFMR) response shape.** For metros where HUD publishes
  ZIP-level FMRs, `basicdata` comes back as a *list* keyed by `zip_code` (plus one entry
  literally named `"MSA level"` for the metro-wide aggregate) instead of a single flat
  object. Confirmed for Cook County (Chicago); **Los Angeles and Cuyahoga counties are
  unverified and get a real call in U1** rather than an assumed shape. Code should: look
  for an entry matching the subject property's ZIP; fall back to the `"MSA level"` entry
  if no ZIP-specific match exists.
- **Bedroom sizes cap at Four-Bedroom.** No API field exists beyond 4BR. If the
  Extractor ever produces a 5+ bedroom unit, fall back to the 4BR figure and flag it
  (`kind="fmr_bedroom_cap_exceeded"`, `severity="info"`) rather than erroring.
- **Auth and rate limit**, as already planned: bearer token in the `Authorization`
  header, 60 requests/minute — reinforces why local caching (fips + year → result) in
  `tools/hud_fmr.py` matters, since a training set spanning many counties means many
  distinct calls during development.

---

## 3. Stack Decision: LangGraph from day one

**Revised (Aug 8, 2026).** This section previously specified plain Python now with a
LangGraph migration staged for Week 6. That staging existed to keep the build aligned
with the order the syllabus introduced concepts. Once sequencing was freed to follow
dependency and risk instead (see the revision note at the top), the staged approach
became strictly dominated: it is the only available option that requires building the
orchestration layer twice, and it spends the scarcest resource on the project —
review-and-integration time — on a rewrite that produces no new capability.

**Decision: adopt LangGraph immediately; the plain-Python orchestration layer is not
built at all.** The four design conventions written to make the migration cheap (below)
were good conventions independent of the migration, so they survive intact — LangGraph
now enforces most of them structurally rather than by discipline.

### The stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** — `StateGraph`, conditional edges, checkpointer | See below |
| State schema | **Pydantic v2** (not dataclasses) | `ValidationError` text feeds the Extractor's retry prompt; dataclasses give nothing there |
| LLM calls | OpenRouter (`:free` tier models) via the OpenAI-compatible SDK | Program-endorsed, $0 |
| Observability | **LangSmith** free Developer tier | Multi-step agent loops are impractical to debug from logs alone; traces also document actual system behavior |
| Retrieval / RAG | `sentence-transformers` (local) + `ChromaDB`, **hybrid**: metadata filters for hard constraints, embeddings for description/amenity text | Free, local, and a more honest design than pure vector search over structured data |
| Regression | `pandas` + `numpy` + `scikit-learn` | Existing strength; lowest-surprise component |
| State persistence | LangGraph checkpointer (SQLite) | Comes with the framework; also enables `interrupt()` |
| Demo surface | **Streamlit**, run locally | ~50 lines; far better on video than a terminal recording |
| Dev environment | VS Code + Claude Code | — |

**Total cost: $0.** Streamlit is open-source and free to run locally; Community Cloud
is only relevant for public hosting, which this project does not require — the demo app
stays local. LangGraph is MIT-licensed. LangSmith's free tier covers a solo developer's
usage. OpenRouter `:free`
models, HUD, Redfin, and Kaggle are all free. Against the $100 project budget, the only
plausible spend is ~$10–20 of OpenRouter credits *if* free-tier rate limits become a
real time sink — but the capstone brief says *"you are expected to design your capstone
and test it using freely available model access,"* so free models are the default and
paid credits are a documented contingency, not the plan.

> ⚠️ **LangSmith free-tier traces expire after 14 days.** Capture screenshots for the
> report as you go; do not assume Week 4 traces will still be viewable in Week 7.

### Rationale

1. **Reducers make Transparent Degradation structural rather than disciplinary.**
   Declaring `flags: Annotated[list[Flag], operator.add]` means a node returning flags
   *appends* rather than overwrites. Flag loss — the failure that would defeat this
   project's central design principle — becomes impossible by construction rather than
   a convention upheld in code review. This is the strongest single argument for the
   framework on this project: the architecture and the tool agree on what must never
   happen, and the tool enforces it.
2. **`interrupt()` is the human-review escalation.** The system needs to pause, surface
   partial state to a human, and resume from that point. That is a first-class
   LangGraph primitive and a genuinely error-prone thing to hand-roll correctly.
3. **The architecture diagram is generated from the graph.**
   `graph.get_graph().draw_mermaid_png()` renders the real topology from the real code,
   so documentation cannot silently drift from the system it describes.
4. **Conditional edges are the Planner.** Routing across seven agents plus a bounded
   Critic → Planner rework cycle is precisely the shape the library exists to express.

**Trade-off accepted:** a framework dependency and its learning curve, on a project
with a fixed deadline. Mitigated by writing the onboarding material up front
(`docs/private/lang_graph_onboarding.md`) and by keeping all agent logic in plain
functions that hold no framework-specific code — if LangGraph became a liability, the
nodes would port to a hand-rolled loop without touching the reasoning logic.

### Design conventions

- Every agent is a **node function**: state in, **partial state update** out. Note
  *partial* — returning the whole mutated state object is the most common LangGraph
  error.
- **No agent calls another agent directly.** Routing lives in edges and `route_*`
  functions, never inside a specialist.
- **State is a single typed object** (§5), never scattered across variables.
- **Flags and retries are state-encoded, not control-flow-encoded.** Conditional edges
  read state to route; anything outside state is invisible to the graph.

New addition: **every cycle must be bounded by an explicit counter in state**, not by
LangGraph's `recursion_limit`. Hitting the limit raises an opaque exception; a counter
lets the system escalate to human review gracefully, which is the behavior Checkpoint
2.1 actually specified.

> **Onboarding:** see `docs/private/lang_graph_onboarding.md` — a crash course written
> for reviewing this code rather than writing it, including a code-review checklist and
> a text-first reading path. Work through it before reviewing Unit 2.

---

## 4. Proposed Repository Structure

**Note (Aug 8, 2026):** the repo already exists with `data/`, `docs/`, and `ignore/`
(secrets, gitignored) at the top level, so `src/` — not a new `deal-evaluator/`
wrapper — is the project root for all application code below. Paths in the rest of
this doc that reference `tools/`, `agents/`, `config.py`, etc. are relative to `src/`.

```
carnegie_mellon_agentic_repo/
├── data/                          # gitignored — Kaggle CSV, Redfin CSVs, cached HUD FMR responses
│   ├── raw/
│   └── processed/
├── docs/
│   └── private/                   # gitignored — capstone docs, this implementation plan
├── ignore/                        # gitignored — secrets (HUD FMR bearer token, etc.)
└── src/                           # project root for all application code
    ├── README.md
    ├── requirements.txt
    ├── .venv/                     # gitignored — dedicated virtualenv
    ├── config.py                  # X/Y/Z loop parameters, model names, thresholds
    ├── state.py                   # DealState / Flag / DealTerms / Comp — Pydantic (see §5)
    ├── graph.py                   # StateGraph assembly: nodes, edges, routing, compile()
    ├── nodes.py                   # node-name string constants (avoids silent typo bugs)
    ├── agents/
    │   ├── __init__.py
    │   ├── planner.py             # route_* functions — the conditional edges
    │   ├── extractor.py
    │   ├── comps_retrieval.py
    │   ├── valuation_rent.py
    │   ├── scenario_forecast.py
    │   ├── critic.py
    │   └── summarizer.py
    ├── tools/
    │   ├── __init__.py
    │   ├── llm_client.py          # thin OpenRouter wrapper, model selection
    │   ├── vector_store.py        # Chroma setup + embedding + hybrid query helpers
    │   ├── rent_model.py          # sklearn regression: train/load/predict (FMR-normalized target)
    │   ├── hud_fmr.py             # HUD FMR API client ✅ built (§9)
    │   ├── county_crosswalk.py    # (cityname, state) → county_fips for the metro shortlist
    │   └── redfin_data.py         # load + query Housing Market Tracker CSVs (rolling-3 computed here)
    ├── scripts/
    │   ├── pull_fmr_sample.py     # ✅ built — real HUD pull smoke test
    │   ├── verify_metro_selection.py # ✅ built — reproduces the §2 metro evidence
    │   ├── build_comps_index.py   # one-off: embed + load Chroma
    │   ├── train_rent_model.py    # one-off: fit + report holdout MAE
    │   └── export_graph_diagram.py # writes the mermaid architecture diagram for the report
    ├── notebooks/
    │   └── 01_data_exploration.ipynb
    ├── eval/
    │   ├── listings/              # synthetic listings, each engineered to trip a known flag
    │   ├── expected.yaml          # listing → expected flags / status
    │   └── run_eval.py            # batch runner → results table for the report
    ├── tests/
    │   └── test_flag_propagation.py  # the one test that must never fail
    ├── app.py                     # Streamlit demo UI (local only)
    └── main.py                    # entrypoint: run full pipeline on one listing
```

---

## 5. State Schema (design target for `state.py`)

**Changed Aug 8, 2026: Pydantic v2 instead of dataclasses**, and `flags` now carries a
LangGraph reducer. Both changes are load-bearing:

- **Pydantic** because the Extractor's clarification loop (Checkpoint 2.1, Loop 1)
  needs to observe *how* a parse was malformed and reformulate. A Pydantic
  `ValidationError` is structured, human-readable text that can be injected directly
  into the retry prompt. A dataclass just raises `TypeError` or silently accepts
  garbage.
- **`Annotated[list[Flag], operator.add]`** because without a reducer, any node
  returning `{"flags": [...]}` *overwrites* the accumulated list. That would silently
  destroy Transparent Degradation the first time two agents both raised flags. With
  it, each node returns only the flags it personally raised and accumulation is
  guaranteed by the framework.

```python
import operator
from typing import Annotated, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Flag(BaseModel):
    source_agent: str          # e.g. "comps_retrieval", "valuation_rent"
    kind: str                  # e.g. "relaxed_search_radius", "unresolved_field",
                                # "low_confidence_estimate", "fallback_used",
                                # "rent_anchored_to_fmr", "fmr_unavailable_for_county",
                                # "appreciation_source"
    detail: str                # human-readable explanation
    severity: Literal["info", "warn", "critical"]

class DealTerms(BaseModel):
    address: Optional[str] = None
    price: Optional[float] = None
    unit_count: Optional[int] = None
    unit_rents: list[float] = Field(default_factory=list)
    square_footage: Optional[float] = None
    city: Optional[str] = None           # crosswalk input (Kaggle has no county/ZIP)
    state: Optional[str] = None          # crosswalk input
    zip_code: Optional[str] = None       # optional; enables SAFMR ZIP-level lookup
    county_fips: Optional[str] = None    # needed to key HUD FMR + Redfin lookups
    # ... additional fields as extraction schema is finalized

class Comp(BaseModel):
    listing_id: str
    similarity_score: float
    rent: float
    beds: int
    baths: float
    square_feet: float
    distance_miles: float

class DealState(BaseModel):
    # inputs
    raw_listing_text: str

    # extraction
    deal_terms: DealTerms = Field(default_factory=DealTerms)
    clarifying_questions: Annotated[list[str], operator.add] = Field(default_factory=list)

    # retrieval
    comps: list[Comp] = Field(default_factory=list)
    search_radius_miles: float = 1.0   # X, widened on relaxation
    retrieval_iterations: int = 0

    # valuation
    rent_estimate: Optional[float] = None
    rent_estimate_ratio_to_fmr: Optional[float] = None  # model's raw structural output
    fmr_anchor_used: Optional[float] = None              # today's FMR figure applied
    value_estimate: Optional[float] = None
    rent_estimate_source: Literal["regression_model", "llm_fallback", None] = None

    # forecast
    # "zip_multifamily" is a documented future option (deferred — see §2); not
    # produced by the current build.
    appreciation_source: Literal[
        "metro_multifamily", "zip_multifamily", "metro_all_residential", None
    ] = None
    scenarios: dict = Field(default_factory=dict)  # optimistic/base/pessimistic branches

    # review
    confidence_score: Optional[float] = None
    needs_human_review: bool = False
    critic_rejected: bool = False
    rework_count: int = 0               # bounds the Critic → Planner cycle (§3)

    # cross-cutting
    flags: Annotated[list[Flag], operator.add] = Field(default_factory=list)
    status: Literal["in_progress", "needs_review", "complete", "failed"] = "in_progress"
    created_at: datetime = Field(default_factory=datetime.now)
```

Note which fields do and don't get reducers. `flags` and `clarifying_questions`
accumulate across multiple nodes, so both need `operator.add`. `comps` is written by
exactly one node (each retrieval iteration *replaces* the working set rather than
appending to it), so a reducer there would be wrong — it would pile up stale
candidates from relaxed passes alongside the final set.

This is a starting point — field names get refined once the Extractor's actual output
schema is confirmed (Unit 3, §6).

---

## 6. Execution Order

Revised Aug 8, 2026, around three principles.

**1. Walking skeleton first.** The previous ordering built the Summarizer last, in the
final week — meaning the component that produces the system's actual output would have
been the least exercised and the most schedule-exposed. Inverted: all seven agents are
stubbed and wired into a running graph in Week 4. From that point there is always a
working end-to-end system, and every subsequent unit replaces one stub with a real
implementation — a small, bounded, independently reviewable change. This converts the
dominant schedule risk from *"will the pieces integrate?"* (discovered late, expensive)
to *"how good is each piece?"* (discovered continuously, cheap).

**2. Within the build phase, order by technical risk rather than pipeline position.**
Retrieval is built before the rent regression even though it sits later in the data
flow, because Chroma and embeddings are the least familiar components in the stack
while the regression is the most familiar. Unknowns get front-loaded into the weeks
that still have recovery room.

**3. Work is decomposed into review-sized units, not calendar weeks.** The binding
constraint on this project is ~5–6 hrs/week of design and review capacity. Each unit
below is scoped to roughly 2–3 hours of review — two per week, with the buffer week
absorbing four. A corollary worth stating because ignoring it is expensive: a design
decision deferred past the unit that needs it blocks implementation *and* consumes
review capacity on re-establishing context. The decisions log in §7 exists to close
those out early.

### The units

| Unit | Build target | Feeds checkpoint |
|---|---|---|
| **Week 4 — Foundation & Skeleton** | | |
| **U1** | `state.py` (Pydantic + reducers), `config.py`, `llm_client.py`, `county_crosswalk.py`; batch FMR pull for Cook/LA/Cuyahoga × {2019, latest}; confirm SAFMR shape for LA + Cuyahoga | — |
| **U2** | **Walking skeleton.** All 7 nodes stubbed, `graph.py` wired incl. Critic→Planner cycle and `human_review` interrupt; Summarizer emits real markdown; flag propagation proven end-to-end; mermaid diagram exported; LangSmith tracing on | **5.1** (fully) |
| **Week 5 — Input & Retrieval** | | |
| **U3** | Extractor: real LLM call, Pydantic validate→retry loop, clarifying questions, assumption flags, bounded escalation; 3 synthetic listings | 2.1 evidence |
| **U4** | Comps/Retrieval: Chroma index over Chicago/LA/Cleveland, one document per listing, hybrid metadata-filter + embedding query, top-`Y` results, adaptive relaxation loop, sparse-comps flag, **retrieval-off ablation behind a config flag** (see acceptance criteria below) | **3.1** |
| **Week 6 — Estimation & Forecast** | | |
| **U5** | Rent model: FMR-normalized regression, holdout MAE, Valuation agent, LLM fallback path + `rent_anchored_to_fmr` / `fmr_unavailable_for_county` flags | — |
| **U6** | Scenario/Forecast: `redfin_data.py` (rolling-3, min-price floor), ToT branching over optimistic/base/pessimistic, `anomalous_period_included` flag | **4.1** |
| **Buffer week — Guardrails, Eval, Demo** | | |
| **U7** | Critic: cross-agent consistency checks, confidence scoring, bounded rework cycle, human-review escalation via `interrupt()` | **6.1** |
| **U8** | Eval harness: 8–10 synthetic listings each engineered to trip a *specific* flag; batch runner → results table | **6.1** + report |
| **U9** | Summarizer polish + Streamlit demo app | report + video |
| **U10** | End-to-end runs across all three metros; capture traces, screenshots, diagrams | report + video |
| **Week 7 — Deliverables** | | |
| — | **Code frozen.** Final report + 8–10 min video. | **7.1** |

### Notes on the sequence

**Multi-agent coordination is working by Week 4 rather than Week 6.** This is the
direct payoff of ordering by dependency: the coordination design gets described from a
running graph and real traces rather than from a design sketch. Each weekly checkpoint
asks for a written design update alongside a working agent update, so building the
capability before writing about it improves both halves of the submission.

**Retrieval design decisions (U4).** Each rental listing is embedded as a **single
document, not chunked.** Listings are short, self-contained records whose fields are
mutually dependent — splitting one would separate a rent figure from the bed/bath/sqft
context that makes it interpretable, and could surface half a comparable as a match.
Chunking earns its keep on long documents with independent sections; this corpus has
neither property. Structured fields (beds, baths, sqft, geography) are carried as
metadata for hard filtering; the embedded text covers description and amenity free-text,
where semantic similarity adds signal over exact matching. **Result count is `Y` from
`config.py`** — the retrieval loop's exit condition is "at least Y qualifying comps,"
which makes the number of retrieved results a tuned parameter rather than an arbitrary
constant.

**U4 acceptance criteria.** The retrieval checkpoint is assessed against five specific
elements, so U4 is specified to produce each one as an artifact rather than leaving them
to be written up after the fact:

| Required element | Where U4 produces it |
|---|---|
| Architectural decision on whether retrieval is required, with justification | §2 of Checkpoint 2.1 already argues this: the failure mode being defended against is fabricated comps presented at full confidence. Restated with the built system as evidence. |
| Evidence a semantic retrieval mechanism is integrated against an external source | Chroma index over the Kaggle corpus; index build script + row counts per metro |
| Demonstration that retrieval meaningfully influences output | **Ablation run — see below** |
| Key design decisions: source selection, segmentation/chunking, number of results | The paragraph above: one-document-per-listing, hybrid metadata + embedding, top-`Y` |
| One retrieval failure mode + how the design manages it | Sparse comps in thin sub-markets → adaptive relaxation loop, bounded by `Z` iterations, with `relaxed_search_radius` and sparse-comps flags disclosed in the report |

**The ablation falls out of the walking skeleton for free.** U2 leaves a stubbed
retrieval node in place; U4 replaces it. Running the same listing through both versions
produces a direct before/after comparison — ungrounded estimate versus comp-grounded
estimate, on identical inputs — which is exactly the "output comparison" the criteria
ask for. Keep the stub reachable behind a config flag rather than deleting it in U4;
it costs nothing and it is the cleanest available evidence that retrieval changes
system behavior. LangSmith traces of both runs supply the same evidence in a second
form.

**U8 is the highest-leverage unit in the plan.** A set of synthetic listings each
engineered to trigger a specific named flag — missing price, 5+ bedroom unit (FMR
bedroom cap), a county with no FMR entry, a location with no qualifying comps, an
internally inconsistent listing — serves three purposes at once: it is the evaluation
results section of the final report, the guardrails evidence for the safety checkpoint,
and the clearest available demonstration that Transparent Degradation works end to end.
It is protected from the cut list for that reason.

### Cut list, in order

If the schedule slips, shed scope in this order rather than improvising:

1. **ZIP-tier appreciation** (already deferred in §2 — keep it deferred).
2. **LLM rent fallback path** — document as designed-but-unbuilt; Checkpoint 2.1
   already anticipated this exact trade.
3. **Streamlit app** — fall back to a terminal recording plus LangSmith traces.
4. **Critic rework-loop depth** — reduce to single-pass review with escalation,
   keeping the cycle in the graph but capping `MAX_REWORKS = 1`.

**Never cut:** the flag propagation test (U2), the eval harness (U8), or the Week 7
report reserve.

### The hard constraint

**Week 7 is reserved entirely for the report and video, with the code frozen.** The
realistic failure mode for a fixed-deadline project like this is arriving at the final
week still integrating, and shipping a rushed write-up of a system nobody has time to
evaluate. A frozen build a week out guarantees there is something coherent to measure,
document, and demonstrate. Any unit unfinished at that point ships as-is and is
documented explicitly as future work — stating a known limitation is better engineering
communication than concealing it, and it is consistent with the Transparent Degradation
principle the system itself implements.

---

## 7. Immediate Next Actions

### Decisions log

Each of these blocks implementation downstream; they are listed in the order they are
needed. Target: all closed during Week 4.

| # | Decision | Status |
|---|---|---|
| 1 | Orchestration framework | ✅ LangGraph, day one |
| 2 | Inference metro trio | ✅ Chicago, LA, Cleveland |
| 3 | Demo surface | ✅ Streamlit, local, scheduled U9 |
| 4 | Training metro shortlist (~5–8, superset of the trio) | ⬜ ranked density list now available from `verify_metro_selection.py`; selection pending |
| 5 | X / Y / Z loop parameters (radius, comp threshold, iteration cap) | ⬜ pick provisional values in U1, tune in U4 |
| 6 | Confidence threshold for human-review escalation | ⬜ U1 provisional, tune in U7 |
| 7 | Redfin minimum-price floor (§2 suggests $10–20k) | ⬜ set after inspecting the three metros' distributions |
| 8 | OpenRouter model per role (dev / extraction / critic / summarizer) | ⬜ U1 |

Each weekly checkpoint publishes explicit completion criteria. Where those exist, the
corresponding unit is specified to produce each required element as a build artifact
rather than as a write-up authored afterward — see the U4 acceptance criteria in §6 for
the pattern. Apply the same treatment to 4.1, 5.1, and 6.1 as their criteria are
published.

### U1 — specification

1. `requirements.txt`: add `langgraph`, `langsmith`, `pydantic`, `numpy`,
   `scikit-learn`, `chromadb`, `sentence-transformers`, `openai` (as the
   OpenAI-compatible OpenRouter client), `streamlit`. `requests`, `python-dotenv`, and
   `pandas` are already present.
2. `state.py` — `Flag`, `DealTerms`, `Comp`, `DealState` per §5, Pydantic with
   reducers on `flags` and `clarifying_questions`.
3. `config.py` — X/Y/Z, confidence threshold, `MAX_REWORKS`, model names per role,
   Redfin price floor, rolling window. Provisional values are fine; the point is that
   nothing is hardcoded in an agent.
4. `nodes.py` — node-name constants.
5. `tools/llm_client.py` — thin OpenRouter wrapper, model selection per call, plus a
   `call_with_schema()` helper that validates against a Pydantic model and retries
   with the `ValidationError` text on failure. This helper is the backbone of U3.
6. `tools/county_crosswalk.py` — `(cityname, state) → county_fips` for the metro
   shortlist. Hand-verified against `fmr/listCounties/{state}`.
7. Finalize decision #4 (training shortlist) from the ranked output of
   `scripts/verify_metro_selection.py`, constrained to metros whose counties are
   FMR-mappable via the crosswalk in item 6.
8. Batch FMR pull for Cook / Los Angeles / Cuyahoga × {2019, latest}; **confirm
   whether LA and Cuyahoga return SAFMR or flat shapes** rather than assuming.
9. LangSmith account + `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` env vars.

Already built and verified against real data, requiring no rework: `tools/hud_fmr.py`
and `scripts/pull_fmr_sample.py` (§9), and `scripts/verify_metro_selection.py`, which
reproduces the §2 metro evidence.

### Prerequisite reading (before U2 review)

`docs/private/lang_graph_onboarding.md` §§1–6, plus the hands-on exercise — roughly
3 hours. This sits on the critical path: the review standard applied to Weeks 4–6 is
only as good as the reviewer's fluency in the framework, and §6 of that document is the
checklist applied to every unit.

---

## 8. Engineering Standards

These are the standards every change set is held to in review. They are recorded here
rather than left implicit so that the bar is the same whether a given unit is written
in a focused session or across a fragmented week.

### Architecture

- **Follow the design conventions in §3**: node functions returning *partial* state
  updates, no agent-to-agent calls, a single typed state object, flags and retries
  encoded in state, every cycle bounded by an explicit counter. LangGraph enforces
  several of these structurally; the partial-update rule and the bounded-cycle rule
  remain a review responsibility.
- **Never let Redfin data touch a rent dollar figure**, and never let unanchored Kaggle
  dollar figures reach the Summarizer — every rent number passes through FMR
  normalization first. This is the code-level expression of the rent-level anchoring
  design in §2, and it is the kind of invariant that degrades silently if unwatched.
- **`config.py` is the single home for tunable parameters** — search radius X, comp
  count threshold Y, iteration cap Z, confidence threshold, `MAX_REWORKS`, Redfin price
  floor. These are tuned across U4–U7; a value hardcoded inside an agent is a defect,
  not a shortcut.

### Documentation

- **Every agent function carries a docstring stating its Reason/Act/Observe/Decide
  loop**, matching the structure specified in the Checkpoint 2.1 design. The reasoning
  loop is a design commitment, and keeping it stated at the point of implementation is
  what keeps the code and the design document from diverging.
- **Decisions are surfaced, not guessed.** Anything that belongs in the §7 decisions log
  gets raised for a decision rather than resolved by assumption. Such decisions are
  inexpensive to make deliberately and expensive to unwind once code depends on them.

### Testing

Testing is scoped deliberately rather than exhaustively, and the scope is documented
here so the choice is legible.

Two things are tested unconditionally, because they are the project's load-bearing
claims:

1. **`test_flag_propagation.py`** — a flag raised in the Extractor survives every
   downstream node and appears in the rendered report. Transparent Degradation is the
   central design principle of this system; a silent flag loss would invalidate every
   output the system produces while leaving it looking correct. This test never gets cut.
2. **The `eval/` harness (U8)** — synthetic listings engineered to trigger each named
   flag, run as a batch with results tabulated. This functions as the system's
   behavioral test suite and as its evaluation evidence.

Broad unit-test coverage is **deferred, not dismissed.** With a fixed deadline, coverage
competes directly against the two suites above, and those carry far more information per
hour invested — they test system-level behavior against the design's actual claims
rather than restating implementation details. Additional coverage gets added
retroactively if the buffer week allows. This is a scheduling judgment about sequence,
and it is recorded as such rather than left as an unexplained gap.

### Change management

- **One unit per change set**, self-contained, accompanied by a summary of what changed
  and where the reviewer's attention is most warranted. A diff spanning five loosely
  related files costs more review time than the batching saves.
- **All test and development data is synthetic or public**, per program requirements.
  No scraped or proprietary listings enter this repository at any point.

---

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**Status:** built and verified against the live API, Aug 8, 2026. `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py`, `requirements.txt`, and a dedicated `.venv/` all exist
under `src/` as planned below.

**What the real pull found (corrects an assumption in §2):** the smoke test ran
`get_fmr` for all three candidate counties at both `year=2019` (Kaggle vintage) and
`year=None` (resolved to 2026, the current FY) —

| County | entityid | SAFMR? | 2BR FMR, 2019 | 2BR FMR, 2026 |
|---|---|---|---|---|
| New York County, NY | `3606199999` | **No** — flat shape | $1,831 | $2,910 |
| Cook County, IL | `1703199999` | **Yes** — SAFMR list shape | $1,212 | $1,781 |
| Philadelphia County, PA | `4210199999` | **Yes** — SAFMR list shape | $1,200 | $1,810 |

§2 had hypothesized New York was the likely SAFMR metro among the three — reality is
the opposite: New York is flat, and Chicago/Philadelphia are the SAFMR ones. Both
correctly fell back to the `"MSA level"` entry (metro-level default, no `zip_code`
passed), confirming the SAFMR branch is genuinely exercised, not just written
defensively. Cache verified too: an immediate repeat call returned in 0.000s (cache
hit, no second HTTP request).

> **Note (Aug 8, 2026, later the same day):** the inference trio subsequently changed
> to **Chicago, Los Angeles, Cleveland** (see §2 — the NY/Philadelphia hypothesis
> failed a data-density check). This table is retained as-is because it remains valid
> evidence that the client works and that both response shapes are handled — Cook
> County is in the final trio, and the New York/Philadelphia rows still prove the flat
> and SAFMR branches respectively. **U1 re-runs this smoke test for Los Angeles County,
> CA and Cuyahoga County, OH** to confirm their shapes; they are currently unverified
> assumptions (LA likely SAFMR, Cuyahoga likely flat).

**Scope:** deliberately narrow — just the client and a real smoke-test pull, so a
working HUD data pull exists as soon as possible. Explicitly **not** included here:
`config.py`, `state.py`, `agents/`, `tests/`, or the rest of the scaffold — those are
U1 (§7). Kaggle and Redfin data already sit in `data/` (repo root) and don't depend on
any of this.

**Files added:**
```
src/
├── requirements.txt          # requests, python-dotenv
├── .venv/                    # gitignored — dedicated virtualenv for this project
├── tools/
│   ├── __init__.py
│   └── hud_fmr.py            # the client
└── scripts/
    └── pull_fmr_sample.py    # runnable smoke test — a real pull, not a mock
```

**Auth:** the bearer token already exists at `ignore/fmr_key` (repo root, gitignored,
confirmed to be a raw JWT with no `KEY=` prefix). `hud_fmr.py` resolves the token as:
`HUD_FMR_TOKEN` env var if set, else read `ignore/fmr_key` relative to the repo root.
No `.env` file is required for this to work; the env var is only an override.

**Base URL:** `https://www.huduser.gov/hudapi/public`

**Endpoints wrapped:**

| Function | Endpoint | Purpose |
|---|---|---|
| `list_states()` | `GET /fmr/listStates` | state code ↔ name lookup |
| `list_counties(state_code)` | `GET /fmr/listCounties/{state_code}` | county name → 10-digit FIPS `entityid` lookup |
| `get_fmr(entityid, year=None)` | `GET /fmr/data/{entityid}?year={year}` | raw FMR record for one county/metro + one fiscal year; omitting `year` returns the latest available and the response's own `year` field is read back rather than assumed |
| `get_fmr_for_bedroom(entityid, bedrooms, year=None, zip_code=None)` | wraps `get_fmr` | single rent figure for a given bedroom count |

**Behavior:**

1. **SAFMR response-shape handling — metro-level by default.** `get_fmr` inspects
   whether the response's `basicdata` is a flat dict (ordinary metro/county) or a
   list (Small Area FMR — ZIP-keyed entries plus one `"MSA level"` entry), per §2's
   HUD FMR API notes. Both shapes are normalized into one consistent return shape so
   callers never need to branch on it. **`zip_code` defaults to `None`, so the result
   is always metro-level**, matching the Kaggle and Redfin data (§2) — for a
   non-SAFMR county there's only ever one metro-wide record anyway, and for a SAFMR
   county the client falls back to the `"MSA level"` entry and reports
   `used_msa_fallback=True`. Passing an explicit `zip_code` (if it matches an entry)
   is supported so the SAFMR branch neither errors nor silently misparses, though no
   current caller uses it. It is retained deliberately: ZIP-level lookup is the natural
   extension point if the deferred ZIP-tier work in §2 is ever taken up, and the branch
   is cheaper to keep correct now than to reconstruct later.
2. **Bedroom cap.** `get_fmr_for_bedroom` caps at `four_bedroom` for `bedrooms >= 4`
   and returns `bedroom_cap_exceeded=True` in the result rather than raising. Turning
   this into an actual `Flag` (`kind="fmr_bedroom_cap_exceeded"`) is the Valuation &
   Rent agent's job once `state.py` exists — out of scope for this client.
3. **Year resolution.** Every result carries the `year` HUD actually returned, never
   the caller's requested year, so downstream code can't silently assume a stale or
   wrong year was honored.
4. **Local caching.** On-disk JSON cache at `data/raw/hud_fmr_cache.json` (repo root,
   already gitignored), keyed by `(endpoint, entityid, year)`. Avoids re-hitting the
   API for repeat lookups during dev and later training-data prep.
5. **Rate limiting.** A client-side throttle enforces HUD's 60 requests/minute cap
   (simple minimum interval between calls); cache hits bypass the throttle entirely
   since they never hit the network.
6. **Errors.** A small `HudFmrApiError` is raised on non-200 responses (status +
   body included). No silent state/national-average fallback is implemented yet —
   that logic belongs to the Valuation & Rent agent's flag-aware design in §2, which
   needs `Flag`/`DealState` to exist first.

**Smoke test (`scripts/pull_fmr_sample.py`):** pulls real FMR data for 2-3 counties
across the candidate metros (New York City, Cook County/Chicago, Philadelphia County)
across two years — one Kaggle-vintage year (e.g. 2018) and the current/latest year
(via `year=None`) — and prints/saves the parsed result. This is meant to produce
visible proof the client authenticates correctly and actually exercises both response
shapes, not just pass a unit test against fixture data.

**Verification before calling this done:**
- Real (not mocked) calls to `list_counties` and `get_fmr` succeed against the live
  API using the token in `ignore/fmr_key`.
- At least one of the three candidate counties returns a SAFMR (list) shape,
  confirming that code path is actually exercised.
- Running the same query twice hits the on-disk cache on the second call (no second
  HTTP request — verified via a log line or timing), and the cache file lands in
  `data/raw/`, not committed to git.
