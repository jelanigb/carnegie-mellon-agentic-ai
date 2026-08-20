# Changelog

### Section Links

- [§1](implementation_plan.md#1-project-summary)
- [§2](implementation_plan.md#2-data-strategy-reconciling-kaggleredfin-vintage-and-category-mismatch)
- [§3](implementation_plan.md#3-stack-decision-langgraph-from-day-one)
- [§4](implementation_plan.md#4-proposed-repository-structure)
- [§5](implementation_plan.md#5-state-schema-design-target-for-statepy)
- [§6](implementation_plan.md#6-execution-order)
- [§7](implementation_plan.md#7-immediate-next-actions)
- [§8](implementation_plan.md#8-engineering-standards)
- [§9](implementation_plan.md#9-current-build-hud-fmr-api-client-toolshud_fmrpy)

**Chronological record of code changes.**
Author: Jelani Gould-Bailey · Last updated: Aug 19, 2026

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

## Aug 19, 2026 — invariant rewording

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 19, 2026 | maintenance | **"No agent calls another agent directly" reworded to "Agents communicate only through shared state."** `docs/architecture.md` §3 (canonical), `engineering_standards.md`, `implementation_plan.md` ×2, `src/graph.py`, `src/agents/critic.py`, plus the private onboarding notes and `claude.md`. The original phrasing paired the prohibition with "routing lives in edges," which read as though routing were the communication channel — it is not. Data moves through `DealState`; a `route_*` function returns only the *name* of the next node and carries no payload. Same invariant, stated as what it actually is | maintenance |

## Aug 18, 2026 — decisions #12–#14, MCP reference server

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 18, 2026 | U6 (partial) | **MCP reference server over the read-only data layer (decision #13).** `mcp_server.py` — four tools: `get_fmr`, `get_growth_bands`, `get_appreciation_history`, `list_available_metros`, all annotated `readOnlyHint`. Wraps `tools/hud_fmr.py` and `tools/redfin_data.py` without modifying either. Two consumers: the U6 ToT evaluator's per-branch evidence pulls, and any MCP host during evaluation and the Week 7 demo. **The pipeline does not import it** — the honest case is portability and a second consumer, not capability, since LangChain `@tool` would give in-process dynamic tool selection with no protocol hop. Recorded that way in the module docstring rather than overstated | 4.1 |
| Aug 18, 2026 | U6 (partial) | **Tool returns carry provenance, not just values.** Every tool returns what a caller would need to disclose the result — `used_msa_fallback` and `is_safmr` on FMR, `includes_anomalous_period` and `optimistic_stretch_in_anomalous_period` on growth bands. Unknown metros and HUD 404s return `available: false` with a reason and the valid alternatives rather than raising, so a missing tool degrades instead of killing the server | 4.1 |
| Aug 18, 2026 | U6 (partial) | **ToT tunables named ahead of the unit that consumes them (decisions #12, #14).** `config.py` — `TOT_BRANCHING_FACTOR`, `TOT_MAX_DEPTH`, `TOT_BEAM_WIDTH`, `TOT_PRUNE_THRESHOLD`, `TOT_TIE_EPSILON`, `TOT_TEMPERATURE`, `TOT_PERSIST_FULL_TREE`, plus `MCP_SERVER_NAME` and `MCP_APPRECIATION_HISTORY_PERIODS`. All provisional and tuned in U8. `TOT_TEMPERATURE = 0.7` is the documented exception to `LLM_TEMPERATURE = 0.0`, whose comment already read `# deterministic by default; ToT overrides` | 4.1 |
| Aug 18, 2026 | maintenance | **`mcp>=2.0` added to `requirements.txt`**, noted as a server-process dependency rather than a runtime dependency of `main.py`. The 2.0 SDK exposes `MCPServer`, not the older `FastMCP` | maintenance |

## Aug 16, 2026 — review follow-ups: diagnostics, response cache, eval scaffolding, decision #8 closed

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 16, 2026 | U3 | **Demo listings calibrated against real market data (decision #11).** `demo_deals.py` — the deals move out of `main.py` into a module carrying each figure *and* its basis: asking price anchored to Redfin's median sale price for Multi-Family (2-4 unit) in that metro, stated rents to HUD FY2026 FMR for the county the listing's own address geocodes to. An import-time check fails if a structured figure and the prose it mirrors diverge. Pipeline behaviour across all five deals is unchanged — the figures were already roughly right; what they lacked was provenance | 2.1, 4.1 |
| Aug 16, 2026 | U3 | **Calibration is verified, not asserted.** `scripts/verify_demo_calibration.py` — re-derives every figure from live Redfin and HUD, exercising the real geocoding and county-resolution path rather than a county written into the fixture. Two deals are expected to report NO BASIS (`staten-island`'s price, since Redfin has no New York coverage; all of `no-geography`) and the script prints those as results rather than skipping them, so a case that quietly acquires a basis is visible | 4.1 |
| Aug 16, 2026 | U3 | **Decision #8 closed: `nvidia/nemotron-3-nano-30b-a3b`, paid variant.** `config.py` — selected on four bake-off passes. Correctness ties across all seven candidates on the paid tier (3/3 valid, 23/23 fields, correct assumptions, no schema retries), so the choice came down to latency and price; this one is perfect on every pass, cheapest of its family, second-fastest overall. Alternatives and their trade-offs recorded in the config comment so the choice stays reviewable | 2.1 |
| Aug 16, 2026 | U3 | **Bake-off no longer confounds availability with capability.** `scripts/extraction_evidence.py` — 429s back off `(5, 15, 30)` and are counted in their own column rather than scoring as extraction failures, which is what made `gemma-4-31b` look incapable when it was queued. Adds `--tier paid\|free`, and forces the response cache **off** for this section, since a replayed response would report the recording's latency as today's | 2.1 |
| Aug 16, 2026 | U3 | **Free vs. paid variants of one model name are not the same deployment.** `gemma-4-26b` scored a spurious assumption on both free passes and neither paid pass, identical prompt — recorded in §7 because it means a free-tier measurement is not evidence about the paid variant, or the reverse | 2.1 |
| Aug 16, 2026 | U3 | **Whole pipeline re-measured on the real Extractor.** All five demo deals plus the retrieval ablation, live end to end (§6). Los Angeles still runs clean at confidence 1.00 with zero disclosures, and Staten Island still finds zero comps — the two properties the real-address change was protecting | 5.1, 2.1 |
| Aug 16, 2026 | maintenance | **Full error detail to stdout, sanitized detail to the report.** `tools/diagnostics.py` + nine call sites — the U3 sanitizer keeps account identifiers out of published reports, which also discarded the metadata a person debugging actually needs. Both audiences now get the right text from the same failure. The largest gain was not the LLM path: `tools/geocoding.py` was swallowing `GeocodingError` entirely, so "Census was down" and "Census found no match" produced identical output despite calling for opposite responses | maintenance |
| Aug 16, 2026 | maintenance | **Model response cache.** `tools/llm_cache.py` + `config.py` — one file per entry, atomic writes, keyed on model/system/prompt/temperature. Three modes, and `replay` is the load-bearing one: a miss raises rather than falling through to a live call, so an evaluation cannot silently re-sample half its cases and report the mixture as one result. Cached at the transport layer so a replayed run reproduces the schema-retry loop faithfully rather than skipping it. Measured: 0.06 ms per hit against 9.9–23 s per live call | 6.1 |
| Aug 16, 2026 | U8 (partial) | **Eval scaffolding and the two-tier case design.** `src/eval/README.md`, `data/`, `data/llm_recordings/`, `results/` — most flag kinds are raised downstream of extraction, so most eval cases supply a complete `DealTerms` and skip the Extractor entirely, which needs no new mechanism because decision #9's pre-flight Planner already routes past extraction when the terms are complete. Only extraction and geography flags need recorded model responses. Harness and cases remain U8 | 6.1 |

---

## Aug 16, 2026 — U3, the real Extractor

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 16, 2026 | U3 | **Extractor built for real.** `agents/extractor.py` — the regex stub is replaced by a schema-validated LLM call through `call_with_schema`, with `ListingExtraction` kept deliberately separate from `DealTerms` so derived geography is never a field the model can fill. The regex is deleted rather than kept as a fallback: a second parser that runs only on failure is one nobody reviews, and it would become the primary path the first time a free-tier model went down | 2.1 |
| Aug 16, 2026 | U3 | **Assumption disclosure, and the prompt rule that makes it mean something.** The model fills an inferred field *and* names it in `assumptions` with a basis, which becomes an `assumed_field_value` flag rendered verbatim. First run over-flagged — "Three-unit building" and "three-family home" were reported as inferences — so the rule was made operational rather than enumerative: a phrase carrying the number states it; only a numberless type word (`duplex`, `triplex`) is an inference. Verified all three cases correct after the change | 2.1, 6.1 |
| Aug 16, 2026 | U3 | **Geocoding wired in, four-tier.** `agents/extractor.py._resolve_geography` — Census parcel match outranks caller-supplied coordinates (the report prints the address, so retrieval must be anchored to it); supplied coordinates are used when the address will not resolve; a city centroid is used when nothing was supplied; nothing resolves to a critical flag. The conflict check runs only against a parcel match, never a centroid, which would otherwise manufacture conflicts out of metro-scale distance. Closes the `TODO(U3)` in `extractor.py` | 2.1 |
| Aug 16, 2026 | U3 | **New flag kind: `supplied_coordinates_conflict`** (critical). `state.py`, `config.py` — a supplied coordinate more than `COORDINATE_CONFLICT_THRESHOLD_MILES` from the address's geocode escalates rather than being resolved, because the system cannot tell which input was meant. Both coordinates are written into the flag so a reviewer sees what was discarded | 6.1 |
| Aug 16, 2026 | U3 | **New flag kind: `extraction_unavailable`** (critical). `state.py` — kept distinct from `extraction_retry_exhausted` because "no model was reached" and "the model never produced valid output" call for different responses from whoever reads the report | 6.1 |
| Aug 16, 2026 | U3 | **Model liveness check.** `tools/llm_client.verify_models_live()` + `main.py` — configured IDs are checked against the live catalogue before the graph is built, so a dead ID fails at launch rather than mid-extraction. Answers the staleness lesson §7 recorded when all four IDs died in six days. `config.py` model constants repointed to a verified-live value | 5.1 |
| Aug 16, 2026 | maintenance | **A rate limit crashed the pipeline; now it degrades.** `tools/llm_client.py` — SDK exceptions are funnelled into `LlmError`, which the Extractor already flags on. Before this, a 429 (`openai.RateLimitError`, not an `LlmError`) propagated out of the node and killed the graph. Found by exhausting the free tier's 50-request daily cap during the bake-off, then verified end to end: the run escalated with a critical flag and a full report instead of a traceback | 6.1 |
| Aug 16, 2026 | maintenance | **Provider error text sanitized before it reaches a report.** `tools/llm_client._transport_failure` — `str(exc)` on an OpenRouter error is the whole JSON body, including the calling account's `user_id`, and flags are rendered verbatim into reports that are portfolio artifacts. Now only the provider's own message and HTTP status are kept | maintenance |
| Aug 16, 2026 | U3 | **Evidence and bake-off in one script.** `scripts/extraction_evidence.py` — three synthetic listings, each engineered to fire a different branch of Loop 1 (clean / term-of-art assumption / missing-and-ambiguous, the last also trapping per-unit-vs-building bedroom counts), plus `--bakeoff` across every free candidate in the live catalogue with schema-validity, retries, wall-clock and hand-checked field accuracy | 2.1 |
| Aug 16, 2026 | U3 | **Flag-propagation suite extended to 24 cases, and made hermetic on purpose.** `tests/test_flag_propagation.py` — an autouse fixture stubs the Extractor's three outbound calls (model, geocoder, county boundary file) for every case, so each U3 flag is now *forced* rather than obtained as a side effect of a listing that happened to omit a price. Ten new cases cover assumption, retry exhaustion, unreachable model, all four geography tiers, the conflict threshold and its negative case, and transport-failure conversion | 6.1 |
| Aug 16, 2026 | U3 | **Demo deals rebuilt on real addresses.** `main.py` — invented street addresses resolve to no parcel and fall back to a city centroid, so every run would have raised a geography flag and §6's clean-LA-run evidence would have been lost. Deal terms remain entirely invented. `--deal no-coords` retired for `--deal no-geography` (an address verified to resolve through neither tier) and `--deal coord-conflict` added; `--coords` now means "check against the address", not "trust" | 5.1, 2.1 |

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
