# `eval/` — the evaluation harness (U8) and the data it runs on

**The harness landed Aug 28, 2026 (U8.1):** `cases.py` holds the case type and the case
set, `runner.py` executes the batch through the real compiled graph and writes
`results/results.md`. The directory and the recording mechanism predate it — they landed
during U3, because both are useful to every unit in between: recorded model responses make
a development loop fast and an evaluation reproducible, and neither benefit had to wait for
the cases to be written.

```bash
.venv/bin/python -m eval.runner                 # every case
.venv/bin/python -m eval.runner --tier golden   # replays recordings; no live calls
.venv/bin/python -m eval.runner --case los-angeles --live   # what a fresh run does
.venv/bin/python -m eval.runner --case chicago
.venv/bin/python -m eval.runner --tier golden --record   # re-record, deliberately
```

**A case declares what the system should do with it, before the run.** That is what makes
the batch usable for tuning decision #6 rather than only for demonstration, and `cases.py`
carries the reasoning — including why a demo deal's *measured* outcome is kept separate
from an engineered case's *predicted* one, and why only the second may be scored.

See `docs/implementation_plan.md` §6 for what U8 is for, and §8 of
`docs/engineering_standards.md` for why this is one of the two test suites that never
gets cut.

## Layout

| Path | Contents | In git? |
| --- | --- | --- |
| `cases.py` | **The case set** and the `EvalCase` type. | Yes |
| `runner.py` | **The batch runner**, results table and flag-coverage census. | Yes |
| `data/golden_fixtures.py` | **Inputs.** The golden `DealTerms` fixtures, each stating what was engineered and what is real. | Yes |
| `data/llm_recordings/` | **Inputs.** Recorded model responses, replayed by `tools/llm_cache.py` in `replay` mode. | Yes |
| `data/geocode_cache.json` | **Inputs.** Census Geocoder results for every address the batch touches, so the *other* live call a replay case makes is reproducible too (U8.6e). | Yes |
| `results/` | **Outputs.** Result tables produced by a harness run. | Yes |

All three are committed, and the reason is the same for each: the final report quotes
these numbers, and a figure whose inputs and outputs cannot be re-derived from a fresh
clone is an assertion rather than evidence. The development-time response cache is a
separate store under `data/processed/llm_cache/` (gitignored), so iterating on a prompt
does not churn the committed recordings — review attention is this project's scarcest
resource and should not be spent on files nobody needs to read.

## Three tiers of case, because most flags do not come from the model

Of the flag kinds in `state.FlagKind`, the substantial majority — sparse comps, radius
relaxation, the FMR bedroom cap, anomalous-period inclusion, rework exhaustion — are
raised *downstream* of extraction. Routing those cases through a live model would make
them slower, non-reproducible, and no more truthful.

1. **Golden fixtures (most cases).** A complete `DealTerms` object is supplied directly
   and the Extractor is skipped. This needs no new mechanism: the pre-flight Planner
   (decision #9) already routes past extraction when `deal_terms_are_complete()` holds,
   so a fixture is simply a deal that arrives already extracted.
2. **Recorded extractions (extraction and geography flags only).** The handful of flags
   that genuinely originate in the Extractor need it to actually run, so those cases
   replay recorded responses via `LLM_CACHE_MODE=replay`.

3. **Demo deals (`live` tier).** The six deals in `demo_deals.py` plus the U4 ablation,
   run as unscored baselines — they carry a *measured* verdict rather than a predicted
   one, so they check for regression rather than tuning anything.

**No tier makes a live model call as of U9.5, demo deals included.** Reaching a model is
now something someone typed: `--record` freezes a run into the committed store, `--live`
runs without writing one. This is a change from U8, where the third tier was the only one
whose name meant what it said — and that was a reproducibility hole rather than a design.
`live` rows fell through to `LLM_CACHE_MODE=read_write` against the *gitignored*
development cache, so a demo row was served from a developer's working store when warm and
called the model when not. **Its cost was concrete**: the published `staten-island` row
said 1 comp where the build produces 0, a stale extraction surviving in the results table
as a number nothing could re-derive. `runner._case_environment` carries the full account.

So every one of the 28 rows now re-derives from a fresh clone, which is what this
directory's own standard has always asked for. That is also a limitation, and per §8 the
results table must say so rather than implying every row exercised the full system end to
end — at least one live end-to-end run belongs alongside it, so "works against a real
model" is demonstrated rather than assumed. `--live` is how that run is taken, and U9.9
captures it.

**"No model calls" is scoped to the LLM specifically, not to network access generally —
worth stating because tier 2 does not otherwise look offline.** Any replay case whose
listing carries a real address reaches `agents.extractor._resolve_geography`, which calls
the live Census geocoder: only `LLM_CACHE_MODE` is overridden for these tiers, and
geocoding was never behind that cache. Most of the time this is a fast, reliable call whose
outcome does not matter to the case, but `coordinates_from_city_centroid` (U8.3) is the
first case whose *target* depends on it: it needs Census to run and cleanly find no match,
verified live before the case was written rather than assumed stable.
`Fault.GEOCODER_OUTAGE` exists for the different, non-reproducible-on-demand case — a
request that fails outright — and does not apply here, because a clean no-match is a
naturally-reachable path in the first place.

**"Whose outcome does not matter to the case" was the assumption, and it was wrong
(Aug 30, 2026).** When the Census times out, the run raises
`GEOCODER_SERVICE_UNAVAILABLE` — correctly — and that flag joins the set
`scenario_forecast._context_block` embeds in the evaluator prompt. A changed prompt has no
recording, so the case dies with a `CacheMiss` that reads exactly like a prompt someone
edited on purpose. It happened to about one case per full batch run, **a different one each
time**, which is a very good disguise: it sent the first investigation looking for state
leakage between cases rather than for a flaky network call. So a live dependency *upstream*
of the recorded call had quietly falsified this tier's whole claim.

`tools/geocoding.py` now keeps a disk cache, committed to `data/geocode_cache.json` beside
the recordings and for the same reason they are committed: an evaluation a fresh clone
cannot reproduce is not evidence. Only outcomes the Census actually returned are stored —
a match or a clean no-match — never a timeout, since caching a failure would freeze a
transient outage into a permanent one and erase the retryable/non-retryable distinction the
two centroid flags exist to carry. Verified over five consecutive full replay runs, clean
once the cache is warm.

**That sentence was wrong from U8.1 until U8.2, and the correction is worth keeping rather
than quietly editing.** It read "no model calls at all", which was true of the *Extractor*
and false of the run. `agents/scenario_forecast` builds an `LlmClient` and calls it twice
per Tree-of-Thought level on every invocation, whatever tier the case is — a golden fixture
skips the parse, not the pipeline. So until U8.2 every golden row was a live call: ~4 per
case, ~30 seconds, quota-dependent, and not reproducible from a fresh clone.
`config.EVAL_RECORDINGS_DIR` had been defined since U3 and **nothing in the repository
read it**.

What makes the claim true now is `runner._case_environment`, which points
`config.LLM_CACHE_DIR` at the committed store and sets `replay` for **every** tier, the
same module-level override the runner already used for the retrieval ablation. A missing
recording is then a `CacheMiss` rather than a live call. The correction is recorded here
because the failure mode is instructive: the property was asserted in prose, nothing
enforced it, and it stayed asserted through a unit that depended on it.

**And it happened twice.** U8.2 fixed it for the two offline tiers and left the third
outside the override; U9.5 found that exception still standing a unit later, having
silently published a `staten-island` comp count no clone could reproduce. The lesson is
not "assert less" but that a claim about reproducibility should be enforced where it is
made, for every case it is made about — a partial fix reads exactly like a complete one
from the prose.

## Declared faults

Some degradation paths cannot be reached by any listing or any recording. The system's
bounded-retry cycle is the clearest case: it spends a pass only on an objection marked
retryable, and the only retryable objection is gated on the address lookup having been
*unreachable* — a live network failure that a fixture (which carries its own coordinates
and never calls the geocoder) cannot produce and a recording (which replays model calls,
not HTTP requests generally) cannot replay.

So a case may declare a fault for the harness to simulate, via `EvalCase.injects`. Two
properties make that honest rather than a fixture quietly patching a module:

1. **The declaration is data on the case**, so it appears in the results table's tier
   column and in the report. A reader can tell a simulated outage from a real one.
2. **The injection enters at the same seam the real failure does** — the geocoder request
   raises, and the pipeline's own branch decides that this is a service outage rather than
   an unresolvable address. Nothing forces a flag, so the branch under test still runs.

`Fault.EXTRACTION_UNAVAILABLE`'s sibling, added U8.3, is the same reasoning applied to the
model rather than the geocoder: `FlagKind.EXTRACTION_UNAVAILABLE` needs
`LlmClient.complete` to fail before there is a response, so there is nothing a recording
could ever replay. `Fault.LLM_UNAVAILABLE` patches `LlmClient.complete` at the class —
`_extract_terms` builds a fresh instance per call — and stays patched for the rest of the
case rather than being unwound after one call, so a later `LlmClient` (`scenario_forecast`
builds its own) hits the same outage. That is not scope creep; it is what an actually-down
model does to every later call in the same run.

## Recording and replaying

```bash
# Record: real calls, results written to the committed store.
LLM_CACHE_MODE=read_write .venv/bin/python scripts/extraction_evidence.py

# Replay: no network, no spend, and a miss is a hard error rather than a live call.
LLM_CACHE_MODE=replay .venv/bin/python scripts/extraction_evidence.py
```

A `CacheMiss` under `replay` means a prompt changed since the recordings were made. The
correct responses are to re-record deliberately or to fix the prompt — never to fall
through to a live call, which would mix fresh samples into a result set presented as
reproducible and report the mixture as one number.

**One case's recordings are hand-authored rather than recorded from a live call.**
`FlagKind.EXTRACTION_RETRY_EXHAUSTED` needs three straight schema-validation failures, and
`ListingExtraction` has no required fields — an ordinary or even a fairly odd model
response validates, so provoking the failure live and on demand is not a property this
harness can assert. `scripts/record_retry_exhausted_fixture.py` writes the three cache
entries directly, using the real prompt-construction code so the keys match what
`call_with_schema`'s retry loop will actually look up, and verifying each response against
the real schema before writing it. This is not a lesser form of evidence than a recorded
live call — the cache does not distinguish the two — but it is a different one, and the
case's note says so.
