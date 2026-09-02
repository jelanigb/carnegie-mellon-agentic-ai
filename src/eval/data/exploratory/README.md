# Exploratory recordings — evidence for spikes, not part of any replay

Committed model calls and result files from **spikes**: investigations run to decide whether a
design is worth building, whose conclusion is a document rather than a change to the pipeline.

**Nothing here is on a replay path.** `config.EVAL_RECORDINGS_DIR` points at the sibling
`llm_recordings/` directory specifically, so the eval harness cannot reach this one. Deleting
this directory would break no test and change no report — it would only destroy the evidence
behind a decision.

## Why commit it at all

A spike's conclusion is usually a *negative* result, and a negative result nobody can re-check
is an assertion. The measurement that killed the model-scored starting-point treatment was
eight repeat calls per deal showing 62% agreement on the easy case; that number is either
reproducible from the recordings or it is a claim in a document. This directory is what makes
it the first thing.

It is also the only durable copy. These calls ran with `LLM_CACHE_MODE=off` against a model
served by four rotating providers, so re-running the spike does not reproduce them — it draws a
fresh sample.

## Layout

    exploratory/
      llm_recordings/   one file per model call, same schema as eval/data/llm_recordings/
      results/          the per-tier output the spike script wrote

## What is here now

**`forecast_starting_point`** — Sept 2, 2026. Does OQ-22's re-purposed depth-2 level work?
Written up in [`docs/design/forecast_starting_point_spike.md`](../../../../docs/design/forecast_starting_point_spike.md);
reproduce with `scripts/spike_starting_point.py`.

| File | What it holds |
| --- | --- |
| `results/tier0_band_widths.json` | Arithmetic only. The starting-point treatment measures ~2× the width of the growth bands it would sit beside, on both deals. |
| `results/tier1_framing_search.json` | One live search per deal, full branch ledger. The evaluator chooses `point` for `los-angeles` and `full` for `staten-island`, with its own rationales. |
| `results/tier2_variance.json` | **The disqualifying measurement.** Eight repeat searches per deal, cache off. `los-angeles` 5/8 modal, `staten-island` 7/8. |
| `results/tier2_variance.log` | The same run's console output, kept because its `[diagnostic]` lines name the serving provider and engine build per call — the evidence for OQ-17's variance being fleet heterogeneity rather than sampling. |
| `results/tier3_rule.json` | The deterministic rule over the same evidence, across every demo deal. No model call. |
| `llm_recordings/` | 22 calls from the Tier 1 searches. **Tier 2 is not here**: it ran with the cache off by design, so its calls were never written. Its evidence is the two `tier2_variance.*` files. |

## Adding to this directory

One subdirectory per spike once there is a second, and a row in the table above. Recordings
carry a full prompt and response — scan for credentials and personal data before committing,
the same as anywhere else in this public repo.
