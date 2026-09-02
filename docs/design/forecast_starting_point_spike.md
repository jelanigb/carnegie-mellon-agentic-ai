# Spike — what OQ-22's re-purposed forecast would actually produce

> **Status: a spike, not a build.** Nothing here is wired into the pipeline. It exists so the
> deferred design in [OQ-22](../open_questions.md) can be *read* before the freeze decides
> whether to build it. Run it with `scripts/spike_starting_point.py`.
>
> **Every number below is checked in.** The model calls and per-tier results live in
> [`src/eval/data/exploratory/`](../../src/eval/data/exploratory/README.md), off any replay
> path. Tier 2 ran with the cache off against a model served by four rotating providers, so
> re-running the spike draws a fresh sample rather than reproducing it — those files are the
> only durable copy of the measurement that decided this.
>
> **Run overnight Sept 1–2, 2026, unsupervised, at the architect's direction.** Every judgment
> call made without review is listed under [Decisions taken without review](#decisions-taken-without-review)
> at the foot of this document.

## The question

OQ-22 defers a redesign of the forecast's depth-2 level. Today that level asks *which band
pairing is most likely*, which needs a joint rent/price distribution this project's data
cannot supply — the measured correlation has r² under 0.10 with an unstable sign, and #21
removed the directional prior without replacing it. OQ-22's proposed replacement:

> Stop asking which pairing is most likely… Ask instead: **which projections does this deal's
> evidence support showing, and how wide should the starting point be?**

with the worked contrast being `los-angeles` (8 comps, corroborated within 1%, own-ZIP
anchor) against `staten-island` (0 comps, nothing cross-checked, county-wide anchor). Both get
the same three growth bands today and are projected five years forward with equal apparent
confidence.

The spike answers three questions in order, each cheap enough to abandon on:

| Tier | Question | Cost |
| --- | --- | --- |
| 0 | How wide is the starting-point treatment against the growth bands beside it? | arithmetic |
| 1 | Can the evaluator answer the new question at all? | one search per deal |
| 2 | Is its answer stable across identical calls? | N searches per deal |

Tier 2 is the one that can kill the design: OQ-17 has already measured this model's scores
moving materially between identical calls, and a treatment that swings the headline number by
~2× has to be reproducible.

---

## Finding 1 — the treatment is twice the width of the thing it sits beside

Tier 0, arithmetic on real state, no model call. Five-year projections from each deal's own
rent estimate and its own metro-level holdout error:

| | `los-angeles` | `staten-island` |
| --- | --- | --- |
| Rent estimate | $2,861/mo | $2,654/mo |
| Metro holdout error | ±$509 (**18%** of the estimate) | ±$855 (**32%** of the estimate) |
| Growth bands | +1.25 / +2.51 / +4.76 %/yr | +3.93 / +6.77 / +10.45 %/yr |
| Yr-5 range, growth bands alone | $3,045 – $3,609 (width **$564**) | $3,218 – $4,362 (width **$1,144**) |
| Yr-5 range, starting point alone | $2,662 – $3,815 (width **$1,152**) | $2,495 – $4,869 (width **$2,374**) |
| Yr-5 range, both | $2,503 – $4,251 | $2,181 – $5,768 |
| **Starting point ÷ growth bands** | **2.04×** | **2.08×** |

**The ratio is ~2 on both deals, and that is the finding.** Under the re-purposing the
scenario section stops being mostly a growth forecast and becomes mostly a display of what the
system does not know about *today's* rent. That is arguably the honest answer — Staten
Island's error band is ±32% against a 43% five-year band spread, so three growth scenarios off
a point estimate there are false precision — but it is a change in what the section **is**, not
a refinement of what it shows. It deserves an explicit decision rather than arriving as a
side effect.

---

## Finding 2 — the evaluator answers the new question correctly, first try

Tier 1, one live search per deal, `--shape framing`. The model was given the estimate's error,
the comp count, the cross-check divergence and the anchor resolution — **none of which reaches
the forecast prompt today** — and asked to choose a starting-point treatment.

| | chosen treatment | the model's own reason |
| --- | --- | --- |
| `los-angeles` | **`point`** | "High sample sizes and a corroborated point rent estimate make this the most defensible treatment for the deal." |
| `staten-island` | **`full`** | "Uses the full error margin to reflect high uncertainty in the rent estimate." |

That is OQ-22's predicted behavior, reached unprompted by any per-deal hint: the corroborated
estimate is compounded as a point, the uncorroborated one from the edges of its measured
error. `staten-island`'s reported rent row becomes **$2,495 – $4,869** in year 5 where today it
is a single $3,218.

**Two consequences the entry does not mention.**

**`staten-island` collapses to one row.** Under the full-band treatment 19 of 21 candidates
scored below the 0.40 prune threshold, leaving only base/base. That is arguably the design
working — it is OQ-22's own alternative phrasing, *"declines the optimistic case as
unsupported"* — but a one-row "5-year outlook" is a large change to the section, and the
row-naming path already has a documented opinion about two-row and one-row outcomes.

**A one-row outlook is not obviously worse than three false ones**, and this is the honest
statement of the trade: today that deal shows three rows whose spread is narrower than the
error bar on the number all three compound from.

---

## Finding 3 — putting the treatment at depth 1 corrupts the window decision

This is the spike's most useful negative result, and it argues against the shape I chose first.

`--shape framing` puts the starting-point treatment on the depth-1 candidates, giving 4 × 3 =
12 framings and one surviving treatment for the whole forecast. The reasoning was that "how
far do we trust this estimate?" is a property of the *deal*, identical across all nine
pairings, so asking it nine times at depth 2 asks one question nine times. Depth 1 is also the
level measured clean — see Finding 5.

**But both deals flipped their window treatment.**

| | shipped run | spike, `--shape framing` |
| --- | --- | --- |
| `los-angeles` | `f-11` — 2020–2022 held out of both | **`f-00`** — kept in both |
| `staten-island` | `f-01` — held out of price only | **`f-00`** — kept in both |

The window question and the starting-point question are independent, and scoring them on one
axis makes the model trade them against each other. `los-angeles`'s winning rationale —
*"High sample sizes and a corroborated point rent estimate"* — is visibly one clause about the
window and one about the starting point, and the clause that used to decide the level (what
the exclusion **costs each series here**, which `_DEPTH_INSTRUCTIONS[1]` spends a paragraph
teaching) has been crowded out by the cheaper "more observations is better" argument that
`f-00` always wins.

That is a regression in the level the project had working. **If the re-purposing is built, the
starting-point treatment should not join depth 1.** Either it joins depth 2 as OQ-22 literally
proposed, or it becomes its own level.

---

## Finding 4 — the re-purposing is cheaper than OQ-22 estimated, in one specific way

OQ-22 sizes the work as *"the prompt changes from 'score this pairing's plausibility' to
'score what this evidence supports showing'"*. **That change already shipped.**
`_DEPTH_INSTRUCTIONS[2]` reads:

> **You are choosing which projections are worth showing a reader, not ranking which is most
> likely to happen.** Those are different questions and getting them confused empties the
> table…

What was never supplied is the *evidence* to answer it. `_context_block` passes the deal's
address, the asking price, the point rent estimate, flag **names**, and the correlation
warning. It does not pass the model's holdout error, the metro-specific error, the comp count,
the cross-check divergence, or the anchor resolution — every one of which is already on
`ValuationDetail` when the forecast node runs.

So the gap between today and the re-purposing is narrower than the entry assumes: an evidence
block in the context, a treatment axis, and a projection that reads it. The entry's other cost
estimates stand — `Scenario`/`ForecastDetail` fields, the scenario assembly, and a full
re-record.

---

## Finding 5 — depth 1 is decided by the model; depth 2 is decided by policy half the time

Measured across the committed recordings in `eval/data/llm_recordings/`, reproducing
`tot._rank`'s tie grouping exactly. Not part of the re-purposing question, but it is the
strongest argument for why depth 2 is the level worth changing:

| Level | Recorded levels | Decided on the model's scores | Decided by the conservatism tie-break |
| --- | --- | --- | --- |
| Depth 1 — which framing | 78 | **78 (100%)** | 0 |
| Depth 2 — which pairings | 79 | 39 (49%) | **40 (51%)** |

On 51% of recorded depth-2 levels the beam's cut falls *inside* a tie group 2–6 candidates
wide, so `tot._rank`'s "prefer the lower combined growth assumption" chooses which pairings
reach the report — not the evaluator. `los-angeles` is one of these: `basebase` won outright at
0.96, and the other two rows came out of a four-way group at 0.85/0.85/0.80/0.80.

**The ledger did not say so** when this was measured: a candidate cut by the tie-break was
recorded as `Scored 0.80, outside the top 3 at this level`, indistinguishable from being
outscored. **U9.7T has since landed that fix**, so the ledger now names the conservatism
tie-break where it decided. The measurement above stands as the reason it was worth doing, and
it is repeated here because it is the same level this design would replace: a level whose
survivors are chosen by policy half the time is a thin place to add a second judgment.

---

## Finding 6 — the model is served by four different backends, which is where OQ-17's variance comes from

Incidental, but it explains a standing open question. The diagnostic line
`llm_client.complete: … answered by <provider>` shows single runs being served by **DeepInfra,
Nebius, Novita and Crusoe**, with `system_fingerprint` values spanning `none`,
`vllm-0.22.0-b08c96cd`, `vllm-0.24.0-tp2-99b8a850` and `vllm-0.24.0-tp4-2eac015f` — different
engine versions and different tensor-parallel widths.

Temperature is 0.0 everywhere. **The variance OQ-17 measures is therefore not sampling noise;
it is fleet heterogeneity**, and no temperature setting can remove it. This is worth recording
against OQ-17 independently of what happens to the forecast.

---

## Finding 7 — the evaluator cannot hold the answer steady, and that is disqualifying

Tier 2: the same search run 8 times per deal with `LLM_CACHE_MODE=off`, so every call actually
reaches the API. Temperature is 0.0 throughout.

| | modal treatment | distribution over 8 runs | **stability** | top score |
| --- | --- | --- | --- | --- |
| `los-angeles` | `point` | **point 5, full 2, half 1** | **5/8 (62%)** | mean 0.906, σ 0.058, range 0.80–1.00 |
| `staten-island` | `full` | full 7, half 1 | 7/8 (88%) | mean 0.819, σ 0.139, range 0.60–1.00 |

**`los-angeles` is the easy case and it is the unstable one.** Eight comparables corroborate
that estimate to within 0.5% at postal-code resolution, and the evaluator still chose the full
error band twice in eight runs. Those two runs would print a year-5 rent of **$2,503 – $4,251**
where the other six print **$3,239** — from the same prompt, the same temperature, and the same
committed data.

Finding 6 explains the mechanism: the calls are served by four different providers on three
different engine builds. This is not sampling noise that a temperature setting can remove.

**Against the criterion this tier was built to apply, the design fails.** A treatment that
swings the headline number ~2× cannot be decided by something that changes its mind 38% of the
time on the deal where the evidence is least ambiguous. Tier 1 was encouraging precisely
because a single run looks decisive; that is the trap Tier 2 exists to catch.

---

## Finding 8 — the same decision, made by a rule, is free, stable, and better

The evidence the model was reasoning from — comp count, cross-check divergence, anchor
resolution — is already deterministic and already on `ValuationDetail` before the forecast
runs. So Tier 3 asks the same question of the same evidence with no model call:

> `full` if the anchor is county-wide or nothing cross-checks the estimate; `point` if at least
> 3 comparables agree within 10% at postal-code resolution; `half` otherwise.

Across all eight demo deals, replayed, zero API calls:

| Deal | comps cross-checked | divergence | anchor | rule |
| --- | --- | --- | --- | --- |
| `los-angeles` | 8 | −0.50% | zip | **point** |
| `los-angeles-current` | 8 | −0.50% | zip | **point** |
| `chicago-uptown` | 8 | +0.02% | zip | **point** |
| `overpriced` | 8 | −6.06% | zip | **point** |
| `coord-conflict` | 8 | −0.50% | zip | **point** |
| `chicago` | 8 | **−16.57%** | zip | **half** |
| `staten-island` | **0** | — | **county** | **full** |
| `no-geography` | — | — | — | *no bands; no forecast either way* |

**It agrees with the model's modal answer on both deals the model was asked**, and it never
changes its mind. `chicago` is the case that earns the third treatment: 8 comparables that land
16.6% away are real partial corroboration, and a two-way point/full choice would have to call
that either fully corroborated or wholly unchecked.

This is `critic.cross_check`'s pattern from U9.4 inverted. There the model annotates a
deterministic verdict it cannot move; here a rule replaces a judgment the model cannot hold
steady. Both keep the reported number reproducible, which is what OQ-17 costs this project
everywhere else.

**Two honest limits.** The thresholds (3 comps, 10%) are *stated, not tuned* — no fixture in
this project declares a correct starting point, so tuning them against the demo deals would
score the rule against a reading of itself. And a rule cannot weigh evidence a threshold does
not name: source concentration, comp age, listing-vs-collected rents. The model could in
principle; it just does not do so reproducibly.

---

## Recommendation

**Build OQ-22's question. Do not build its mechanism.**

The re-purposing is right about the problem. Two deals that differ this much in how well their
rent estimate is corroborated should not be projected forward with equal apparent confidence,
and Tier 1 shows the framing produces exactly the intended behavior. What Tier 2 shows is that
an LLM cannot be the thing that decides it: 62% stability on the easy deal, on a choice worth
~2× the growth bands.

So the recommendation is to keep the question and change who answers it:

1. **The starting-point treatment is computed, not scored** — `rule_starting_point()` in the
   spike, promoted to `agents/valuation_rent.py` or a small helper beside it, reading fields
   that already exist. Deterministic, free, and it agrees with the model where the model
   agrees with itself.
2. **It does not touch the search.** No prompt change, no candidate payload change — and
   therefore, importantly, **no re-record.** The treatment applies at projection time. This is
   what makes it a small change set rather than OQ-22's "full change set of new design": a
   state field, a projection that reads it, and a sentence in the report.
3. **Depth 2 stays as it is for now.** OQ-22's deeper question — whether a pairing level
   deserves its evidence at all — is untouched by this and stays open. What changes is that it
   is no longer *also* carrying the starting-point question, which it was never going to hold
   steady.
4. **If the pairing level is later re-pointed anyway, the treatment must not go at depth 1.**
   Finding 3 measured that cost: both deals flipped their window treatment and the level's real
   argument got crowded out.

**Schedule.** This is not a freeze-week change. It is smaller than OQ-22 assumed — the prompt
half already shipped (Finding 4), and the rule needs no re-record — but it still adds a state
field, a projection path and report prose, and U9.9's capture pass has a stronger claim on the
remaining days. **Recommend: land it after the freeze, and cite this document as the reason
the design changed shape.** The spike's own value does not depend on the build happening —
a measured reason not to ship the model-scored version is the more useful artifact.

**What to fix regardless, and cheaply:** the report currently projects every deal from a point
estimate with no acknowledgment that `staten-island`'s carries a ±32% error band. Even without
the treatment, one sentence beneath the scenario table stating the error band the projection
compounds from would close the worst of the gap this spike was investigating.

---

## Decisions taken without review

Made unsupervised overnight Sept 1–2, 2026, listed so they can be overturned rather than
inherited.

1. **Three starting-point treatments, not two** — `point` (0×), `half` (0.5×), `full` (1.0×)
   as multipliers on the model's holdout error. A two-way choice cannot express the middle
   case (a deal with three comps at 12% divergence), and the multiplier keeps every figure
   traceable to a measured quantity rather than a chosen dollar amount.
2. **The error used is the metro-specific holdout error where one exists**, falling back to the
   pooled figure. `staten-island`'s ±$855 against the ±$452 pooled average is the entire reason
   the treatment differs by deal, and the pooled figure would wash that out.
3. **Tested the `framing` shape first, and it was the wrong call** — see Finding 3. The
   `pairing` shape is OQ-22's literal reading and the spike now argues for it.
4. **The spike scores against upstream-only flags.** A finished `DealState` carries the
   Critic's and Summarizer's flags too; handing those to the evaluator would give the spike
   evidence the real forecast node never had.
5. **Every live call ran with `LLM_CACHE_DIR` pointed at a scratchpad** and Tier 2 additionally
   with `LLM_CACHE_MODE=off`. Nothing entered `eval/data/llm_recordings/`; `git status` on that
   directory is clean.
6. **No shipped file was modified.** The other session held U9.7T/U9.8/U9.9 in this tree while
   this ran, and several of those touch `scenario_forecast.py`, `summarizer.py` and `tot.py`.
   This spike adds only new files — including no edit to `changelog.md` or `open_questions.md`,
   whose proposed edits are listed below rather than applied. The spike script was re-checked
   against their landed work afterwards and still runs.

7. **A ratio/percent bug in the first draft of the rule, found and fixed.**
   `ValuationDetail.divergence_pct` and `config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT` (0.30) both
   carry a `_pct` suffix while holding **ratios**; the shipped pair is internally consistent and
   renders with `:.0%`, so this is a naming looseness rather than a defect. The spike's first
   rule compared that ratio against `10.0` and the divergence test was silently inert — every
   deal read as fully corroborated. Fixing it is what surfaced `chicago` as the `half` case, so
   the three-treatment design is justified by a deal rather than by argument. Worth a one-line
   note against the field names; not worth a change in freeze week.
8. **The spike runs against a git worktree at HEAD, not the live tree.** Mid-run, the other
   session's in-flight `_row_name` edit broke every import of `scenario_forecast`. The worktree
   isolates both directions. It needs `data/` symlinked in — without it the ZORI and Redfin
   series are unreachable, LA silently falls back to the HUD FMR schedule and produces no rent
   estimate at all, and every replay cache-misses. Recorded because the failure looks like a
   code problem and is a path problem.

## Proposed edits, not applied

Left for the architect because the files belong to another session's work in progress:

- **OQ-22** — record Findings 1, 3 and 4: the ~2× width ratio, that the treatment must not go
  at depth 1, and that the prompt half of the change already shipped so the remaining cost is
  an evidence block plus a treatment axis.
- **OQ-22 and `design/evaluator.md`** — both argue the pairing level must survive because the
  forecast's search is *"the only reasoning locus in the build."* **That expired Sept 1** when
  U9.4 landed `critic.cross_check`, which the U9 status table already calls the second locus.
  Deleting or re-pointing depth 2 no longer costs the system its only demonstration of
  reasoning.
- **OQ-17** — record Finding 6: the variance has a named mechanism, and it is provider fleet
  heterogeneity rather than sampling.
- **`changelog.md`** — no row. This spike changed no shipped behavior.
- **A one-sentence report fix worth taking regardless of what happens to this design**, from
  the Recommendation above: state the error band the projection compounds from beneath the
  scenario table. `staten-island` is projected five years forward from a number carrying a
  ±32% error the section never mentions.
