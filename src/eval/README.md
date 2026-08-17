# `eval/` — the evaluation harness (U8) and the data it runs on

The harness itself is **U8** and is not built yet. This directory and the mechanism
behind it landed early, during U3, because both are useful to every unit in between:
recorded model responses make a development loop fast and an evaluation reproducible,
and neither benefit has to wait for the cases to be written.

See `docs/implementation_plan.md` §6 for what U8 is for, and §8 of
`docs/engineering_standards.md` for why this is one of the two test suites that never
gets cut.

## Layout

| Path | Contents | In git? |
| --- | --- | --- |
| `data/` | **Inputs.** Golden `DealTerms` fixtures and the synthetic listings they came from. | Yes |
| `data/llm_recordings/` | **Inputs.** Recorded model responses, replayed by `tools/llm_cache.py` in `replay` mode. | Yes |
| `results/` | **Outputs.** Result tables produced by a harness run. | Yes |

All three are committed, and the reason is the same for each: the final report quotes
these numbers, and a figure whose inputs and outputs cannot be re-derived from a fresh
clone is an assertion rather than evidence. The development-time response cache is a
separate store under `data/processed/llm_cache/` (gitignored), so iterating on a prompt
does not churn the committed recordings — review attention is this project's scarcest
resource and should not be spent on files nobody needs to read.

## Two tiers of case, because most flags do not come from the model

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

A run of tier 1 or 2 makes **no model calls at all**, which is why the harness is
quota-independent and fast. That is also a limitation, and per §8 the results table must
say so rather than implying every row exercised the full system end to end — at least
one live end-to-end run belongs alongside it, so "works against a real model" is
demonstrated rather than assumed.

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
