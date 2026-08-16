# Changelog

**Chronological record of code changes.**
Author: Jelani Gould-Bailey · Last updated: Aug 15, 2026

## Why this file exists

The build is sequenced by dependency and technical risk rather than by the syllabus
calendar — see `implementation_plan.md` §6 for that decision and its rationale. Units
therefore land out of order relative to the order the program teaches and assesses the
material: retrieval (U4) shipped before the walking skeleton (U2), and code feeding
Checkpoint 6.1 exists before the checkpoints between them are due.

That trade is worth making, but it costs traceability: with unit order decoupled from
checkpoint order, nothing otherwise maps shipped code back to the requirement it
satisfies. This file is that map.

## What belongs here

**Code changes, not decisions.** Decisions live in `implementation_plan.md` — the §7
decisions log for open questions, and the per-unit sections for reasoning and findings.
A decision that has not produced code is not a changelog entry. Where a change needs
justification, the row cites the plan section rather than restating the argument.

**One conceptual change per row, however many files it touched.** A change spanning an
agent, a state field, and a config entry is one row naming all three; it is not three
rows. The unit of a row is the change, not the file.

## Conventions

- `##` heading per date the work was **done**. Newest date first.
- **Date added** is when the row was written, which is the same day for work logged as
  it lands and a later date for anything backfilled. Rows are ordered newest-first by
  that date, so retroactive entries are visibly retroactive rather than quietly folded
  into the original day's record.
- **Related checkpoint** names every checkpoint a change feeds, or `maintenance` for
  work that serves none — hygiene and defect repair are real work, and forcing a
  checkpoint onto them would make the column less trustworthy everywhere else.
- Work predating the unit numbering is labelled by the `implementation_plan.md` section
  that specifies it (`§2`, `§9`), so it stays findable by the same identifier the plan
  uses.

---

## Aug 15, 2026 — decision #10 follow-on, county resolution rewrite

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 15, 2026 | U3 (partial) | **County crosswalk replaced with a spatial join.** `tools/county_crosswalk.py` — `lookup_county_fips` now takes `(latitude, longitude)` and resolves the county via point-in-polygon geometry against Census's county boundaries (cached locally), replacing the hand-maintained 29-city `(cityname, state)` table. Prompted by reviewing a neighborhood-vs-city naming gap in decision #10 ("Wynwood" vs. "Miami"); the geometric fix turned out to strictly dominate a string-based one — see decision #10's follow-on detail, §7 | 2.1, 4.1 |
| Aug 15, 2026 | U3 (partial) | **Cost measured before committing.** `geopandas` installs in ~3.3s from prebuilt wheels (~31MB); the Census county boundary file loads in ~3.3s and is cached after the first pull. Corrects §2's original "not worth the dependency" judgment, which was never actually tested — see `data_strategy.md`'s Gap 1 | — |
| Aug 15, 2026 | U3 (partial) | **Live verification.** `scripts/verify_county_geometry.py` — reproduces all three inference-trio entityids exactly, resolves Miami-Dade County where the old table had no entry at all, and resolves the old table's two hand-special-cased cases (Richmond VA's independent-city status, Denver's consolidated city-county) correctly with no special code, each cross-checked against a live HUD `listCounties` call | 2.1 |
| Aug 15, 2026 | U3 (partial) | **New England flagged as future work, not solved.** A resolved point in one of the six New England states now returns `None` (HUD prices FMRs by town there, not county, and a county join can't produce that entityid) rather than a wrong value. `TODO(geography)` — same status the old table already carried for the region | — |
| Aug 15, 2026 | maintenance | **Retired flag kind.** `state.py` — `FlagKind.COUNTY_FROM_PRINCIPAL_COUNTY` removed rather than left permanently unraisable; the principal-county approximation it described no longer exists now that county resolution is exact. `requirements.txt` gains `geopandas` | 6.1 |

---

## Aug 11, 2026 — decision #10, geocoding

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 11, 2026 | U3 (partial) | **Geocoding client.** `tools/geocoding.py` — Census Geocoder primary (free, no key, parcel-accurate), corpus-derived city-centroid fallback computed from `kaggle_data.load_clean()` rather than a hand-maintained table. Closes decision #10 (§7); not yet called from `agents/extractor.py` — see that file's `TODO(U3)` | 2.1 |
| Aug 11, 2026 | U3 (partial) | **Live verification.** `scripts/pull_geocode_sample.py` — real calls proving all three paths: a complete address resolves via Census, a city/state-only input falls through to the centroid, and a corpus-uncovered city correctly resolves to neither | 2.1 |
| Aug 11, 2026 | U3 (partial) | **Two new flag kinds.** `state.py` — `COORDINATES_FROM_CITY_CENTROID` (warn) and `GEOCODING_UNAVAILABLE` (critical), added ahead of the code that raises them, same precedent as `COUNTY_FROM_PRINCIPAL_COUNTY` in U1 | 6.1 |
| Aug 11, 2026 | maintenance | **Shared normalization.** `tools/county_crosswalk.py` — `_normalize_city`/`_normalize_state` promoted to public `normalize_city`/`normalize_state` so `tools/geocoding.py`'s centroid fallback folds city names identically to the county crosswalk instead of risking two normalizers drifting apart | — |

---

## Aug 10, 2026 — U2, walking skeleton

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 10, 2026 | U2 | **Graph assembly.** `graph.py` — eight nodes wired on the pre-flight Planner topology, one `Critic → Planner` back edge, two conditional edges, compiled with a checkpointer; conditional-edge targets validated against `nodes.ALL_NODES` at import | 5.1 |
| Aug 10, 2026 | U2 | **Planner and routing.** `agents/planner.py` — writes the execution plan into state and owns both `route_*` functions; `state.py` gains `plan` and `planner_invocations`, the latter making the "at most `1 + rework_count` invocations" invariant assertable | 5.1 |
| Aug 10, 2026 | U2 | **Bounded rework cycle.** The counter increments on Planner re-entry rather than on Critic rejection, so escalation is not miscounted as rework; exhaustion routes to human review instead of raising `recursion_limit` | 5.1, 6.1 |
| Aug 10, 2026 | U2 | **Human-review escalation.** `agents/human_review.py` — `interrupt()` node surfacing confidence, warn/critical flags and unanswered questions; resumes from checkpoint into the Summarizer; `state.py` gains `human_review_note` | 6.1 |
| Aug 10, 2026 | U2 | **Critic confidence and escalation.** `agents/critic.py` — flag-severity aggregation using the `config.py` weights, escalation decision, and `_consistency_objections()` as a live seam for U7's cross-agent checks. Derived flags excluded from their own score to prevent feedback across rework passes | 6.1 |
| Aug 10, 2026 | U2 | **Escalation defect fixed.** A lone critical flag scored exactly at the 0.60 threshold and failed to escalate, so zero-comparable deals reported as ordinary results. `agents/critic.py` now escalates on low confidence **or** any critical flag; `agents/summarizer.py` banner reworded to stop attributing every escalation to the score. Regression test added (plan §6, finding 1) | 6.1 |
| Aug 10, 2026 | U2 | **Summarizer.** `agents/summarizer.py` — real markdown, disclosure-first: every flag rendered in full with its source agent and severity guidance, comp table with `listing_source`, source-concentration disclosure, and absence stated rather than omitted | 2.1, 6.1 |
| Aug 10, 2026 | U2 | **Stubbed specialists.** `agents/extractor.py` (deterministic regex parse, real `unresolved_field` flags and crosswalk county lookup), `agents/valuation_rent.py`, `agents/scenario_forecast.py`. Stubs emit no estimates, so no unanchored figure reaches the report; `state.stub_nodes` carries build status outside the flag stream | 5.1 |
| Aug 10, 2026 | U2 | **Flag-propagation test suite.** `tests/test_flag_propagation.py` (14 cases) and `tests/conftest.py`; `pytest` added to `requirements.txt`. Covers first-node-to-report propagation, multi-agent accumulation, all three reducer annotations incl. the negative case on `comps`, full-text rendering, cycle termination, and interrupt/resume | 6.1 |
| Aug 10, 2026 | U2 | **Generated architecture diagram.** `scripts/export_graph_diagram.py` renders `docs/diagrams/deal_evaluator_graph.{mmd,png}` from the compiled graph and asserts the topology — one back edge, two branching nodes, all declared nodes registered. The hand-drawn placeholder in `lang_graph_onboarding.md` §4 was deleted and replaced with the generated output | 5.1, 7.1 |
| Aug 10, 2026 | U2 | **Entrypoint.** `main.py` — five runnable paths (dense, moderate, thin, no-coordinates, retrieval-off), interrupt/resume handling, and a SQLite checkpointer | 5.1, 7.1 |
| Aug 10, 2026 | U2 | **Observability wiring.** `tools/tracing.py` — env-driven LangSmith project setup that reports on every run whether tracing is actually on, so a run believed captured and silently not captured is not a failure mode | 5.1 |
| Aug 10, 2026 | U2 | **Checkpoint serialization.** `graph.state_serde()` registers the six state types with LangGraph's msgpack allowlist, clearing deprecation warnings that would have blocked the resume path in a future version and switching deserialization to deny-by-default | 6.1, maintenance |
| Aug 10, 2026 | U2 | **HUD cache hardening.** `tools/hud_fmr.py` — `_DiskCache.set()` now writes to a temporary file and renames atomically, so a crash mid-write can no longer truncate the accumulated cache. Clears `TODO(U2)`; residual concurrency limit documented as accepted | maintenance |

---

## Aug 9, 2026 — U4, comps retrieval

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 10, 2026 | U4 | **Hybrid vector store.** `tools/vector_store.py` — Chroma client, embedding function, and `query_comps`: metadata filters for the hard constraints (bedrooms, geography), semantic similarity over description and amenity text for ranking. Radius search implemented as a bounding-box filter Chroma can express, then trimmed to the true circle by haversine | 3.1 |
| Aug 10, 2026 | U4 | **Comp index built.** `scripts/build_comps_index.py` — 3,880 listings across the inference trio plus New York, one document per listing and never chunked. New York is indexed deliberately as the sparse-comps case rather than excluded | 3.1 |
| Aug 10, 2026 | U4 | **Adaptive relaxation loop.** `agents/comps_retrieval.py` — the first real agent: relaxes exactly one criterion per pass, ordered by how much accuracy each concession costs (sqft band, then radius, then bedroom tolerance), each concession naming itself in a flag. Exits on the comp threshold or the iteration cap | 3.1, 2.1 |
| Aug 10, 2026 | U4 | **Sparse-comps degradation path.** The loop exits with a `sparse_comps` flag and whatever it found, rather than presenting a weak comp set as a strong one — critical severity at zero comps, warn otherwise | 3.1, 6.1 |
| Aug 10, 2026 | U4 | **X/Y/Z tuned against measured density.** `config.py` — initial radius raised from 1.0 to 2.0 mi after density curves showed every market but Los Angeles relaxing on the first pass, which made the relaxation flag fire on essentially every run and therefore carry no information. Y=8, Z=4 | 3.1 |
| Aug 10, 2026 | U4 | **Retrieval evidence script.** `scripts/retrieval_evidence.py` — three density cases (LA dense / Chicago moderate / Staten Island thin) plus the `RETRIEVAL_ENABLED` config-flag ablation, producing each of Checkpoint 3.1's required elements as an artifact rather than as prose | 3.1 |
| Aug 10, 2026 | U4 | **Ungrounded-LLM ablation.** `scripts/retrieval_ablation_llm.py` — two free-tier models asked for comps with no corpus access; 0 of 16 returned comps exist in the evidence base, and rent dispersion collapses from CV 19.7% to 3.1%/4.3%. Also the first live exercise of `tools/llm_client.py`, whose retry loop fired for real | 3.1 |
| Aug 10, 2026 | U4 | **Verification honesty fix.** `scripts/retrieval_ablation_llm.py` now reports `id_format_matches_corpus` alongside the corpus lookup, because corpus ids are 10-digit numerals and the models returned `LA001`-style ids — so zero of sixteen could have matched on format alone. The null result was structural, not earned (plan §8) | 3.1, 7.1 |
| Aug 10, 2026 | U4 | **`Comp.listing_source` surfaced.** `state.py` — carries the originating site so a citation points somewhere checkable, and so the 91%-single-aggregator concentration in this corpus is detectable rather than hidden behind a comp count | 3.1, 6.1 |

---

## Aug 8, 2026 — U1, foundation

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 10, 2026 | U1 | **State schema.** `state.py` — Pydantic v2 `DealState`/`DealTerms`/`Comp`/`Flag`, `flags` and `clarifying_questions` carrying `operator.add` reducers so flag loss is structurally impossible; geography fields grouped by provenance (observed / parsed / derived) | 5.1, 6.1 |
| Aug 10, 2026 | U1 | **Closed flag vocabulary.** `state.py` — `FlagKind` and `Severity` as `StrEnum` rather than string constants, so Pydantic rejects an unknown kind at construction and the set is enumerable for U8's coverage assertion | 6.1 |
| Aug 10, 2026 | U1 | **Tunable parameters centralized.** `config.py` — X/Y/Z retrieval loop, confidence threshold, `MAX_REWORKS`, severity weights, Redfin price floor, rent bounds, model IDs and embedding config, each carrying its evidence or a `PROVISIONAL` marker naming the unit that tunes it | 5.1 |
| Aug 10, 2026 | U1 | **Node name constants.** `nodes.py` — node names centralized so a typo in an edge definition fails at import rather than at invoke time | 5.1 |
| Aug 10, 2026 | U1 | **LLM client.** `tools/llm_client.py` — OpenRouter wrapper over the OpenAI-compatible SDK with `call_with_schema`: validates against a Pydantic model and re-prompts with the `ValidationError` text on failure, which is the mechanism the Extractor's clarification loop depends on | 2.1 |
| Aug 10, 2026 | U1 | **Corpus cleaning, single path.** `tools/kaggle_data.py` — cp1252 decoding, 84 exact-duplicate ids dropped, rent bounds applied, and word-boundary city matching that rolls "Cleveland Heights" into Cleveland while rejecting Queensbury-as-Queens and Bronxville-as-Bronx. Centralized so a data-quality decision is made once and cannot drift between the index, the regression, and the evidence scripts | 3.1 |
| Aug 10, 2026 | U1 | **County crosswalk.** `tools/county_crosswalk.py` — 29 `(city, state) → county FIPS` entries, every entityid read from a live HUD `listCounties` response rather than written from memory, plus `verify_against_hud()` to re-run that check. Bridges the corpus's missing county column, which the whole FMR anchoring strategy keys on | 4.1 |
| Aug 10, 2026 | U1 | **Redfin appreciation source.** `tools/redfin_data.py` — metro filtering at load, the $10,000 minimum-price floor, locally computed rolling-3 median, and optimistic/base/pessimistic growth bands returned as data with `includes_anomalous_period` and `tier` for the agent to convert into flags | 4.1 |
| Aug 10, 2026 | U1 | **Anomalous-period discontinuity fixed.** `tools/redfin_data.py` — excluding 2020–2022 leaves a gap that a naive `.rolling()` splices across, silently averaging 2019 onto 2023 and reporting it as consecutive months. The sustained-stretch calculation now segments on month adjacency first; the fix moved Chicago's excluded pessimistic band from −1.92% to −1.56% | 4.1 |
| Aug 10, 2026 | §9 | **HUD FMR API client.** `tools/hud_fmr.py` — auth, on-disk cache, client-side 60/min throttle, and normalization of the flat and Small Area FMR response shapes into one return shape so callers never branch on it. Bedroom lookups cap at 4BR and report it rather than raising | 4.1 |
| Aug 10, 2026 | §9 | **Live FMR smoke test.** `scripts/pull_fmr_sample.py` — real (not mocked) pulls for the candidate counties across two fiscal years, confirming both response shapes are genuinely exercised and that a repeat call hits the cache without a second HTTP request | 4.1 |
| Aug 10, 2026 | §2 | **Metro selection evidence.** `scripts/verify_metro_selection.py` — reproduces the density check across both datasets that overturned the original New York / Chicago / Philadelphia hypothesis and settled the inference trio on Chicago, Los Angeles, Cleveland | 3.1, 4.1 |
