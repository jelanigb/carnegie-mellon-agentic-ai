# Demo Deals

**What this document is:** a plain-language guide to the six synthetic listings the demo
runs on, and *why each one exists* — what it is built to show a reader, and what in the
system's output actually demonstrates it. Written so a reader doesn't have to reverse
that purpose out of `src/demo_deals.py` or `src/eval/cases.py` themselves.

**Scope, for now.** This covers the six `main.py --deal` listings plus the one ablation
run (`--no-retrieval`) that rides along with them. It does not walk through the ~15
engineered fixtures in `src/eval/cases.py` (`la-ordinary-duplex`, `chicago-five-bedroom`,
and so on) — those exist to trip one specific flag apiece for the U8 evaluation harness,
are already documented case-by-case in that file's docstrings, and are a separate kind of
evidence from the demo (see "How the demo deals relate to the eval harness" below).
Started Aug 29, 2026, alongside U8; **will be filled out further in U9** once the
Streamlit surface and the final report/video are actually built.

---

## Overview

The system evaluates small multi-family (2–4 unit) residential listings as investment
candidates. The demo deals (`src/demo_deals.py`) are six synthetic listings, each run
independently with `.venv/bin/python main.py --deal <key>` from `src/`. They are not
random examples — each one is built to land on a different point of the system's
operating range, from "everything works cleanly" to "the system can't do part of its job
and says so."

That range exists on purpose. The project's central design principle is **Transparent
Degradation**: when an agent has to proceed on incomplete or relaxed information, it
raises a named flag rather than silently absorbing the gap, and those flags propagate
downstream to the final report. A demo that only ever showed the clean path would prove
the pipeline runs; it would not prove degradation is disclosed rather than hidden. The
six deals together are what makes that second claim demonstrable.

**Every figure that can be anchored to something real, is.** The street address (and
therefore the geocode, county, and Fair Market Rent that county attracts) is real. Asking
prices are anchored to Redfin's median sale price for 2–4 unit properties in that metro;
stated rents are anchored to HUD's Fair Market Rent for the resolved county. What's
invented is that the property is for sale at all, its condition, amenities, and the
specific numbers within a stated tolerance. `src/scripts/verify_demo_calibration.py`
re-derives each figure from live sources and reports drift, so the committed values stay
checkable rather than just asserted. Full reasoning in `demo_deals.py`'s module
docstring.

**Where the six deals sit in the build.** They were originally U10 (a separate
end-to-end pass), folded into U8's eval harness on Aug 26, 2026 so the demo evidence and
the evaluation evidence come from one code path and can't disagree with each other — see
`eval/cases.py`'s `demo_cases()`. In that harness they're recorded as `BASELINE`
verdicts (a previously *measured* outcome, treated as a regression check) rather than
`PREDICTED` ones (a claim made before the run, which is what the harness's threshold
tuning is actually scored against) — see "How the demo deals relate to the eval harness"
below for why that distinction matters.

---

## How an outcome is decided: confidence and escalation

Every deal ends one of two ways: the Summarizer produces a normal report, or the Critic
routes the deal to `human_review` and pauses there. What decides which is worth knowing
before reading the six deals below, because it's the mechanism each one is chosen to
exercise.

The Critic aggregates every flag raised anywhere in the pipeline into a single confidence
score, starting at 1.0 and subtracting a penalty per flag by severity
(`config.FLAG_SEVERITY_PENALTY`, **provisional, tuned in U8**):

| Severity | Penalty |
| --- | --- |
| `info` | 0.0 |
| `warn` | 0.15 |
| `critical` | 0.40 |

If the score falls below `config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD` (**0.60**,
provisional), the deal escalates. **But a single critical flag escalates on its own,
independent of the score** — a deal can clear the 0.60 bar and still be sent to a human
if even one disclosure is severe enough. `chicago --no-retrieval` below is the case that
isolates this rule from the score-based one. Mechanism in `agents/critic.py`; both
constants are marked provisional in `config.py` because U8's eval batch is what tunes
them against real evidence rather than against the six deals, which were calibrated to
run clean and can't stress-test a threshold themselves.

---

## The demo deals

### Los Angeles — the clean baseline

`main.py --deal los-angeles` · confidence **0.70** · 4 disclosures (2 info, 2 warn) ·
**reports normally**

An Echo Park duplex, dense market, full 8-comp set. This is the "everything worked"
case — but even here, one disclosure fires: Los Angeles County doesn't publish a
Small Area (ZIP-level) Fair Market Rent, so the rent anchor falls back to the
county-wide figure, and the report says so. That's deliberate evidence in itself: **the
clean row in this demo set is "reports with no critical flag," not "raises zero
flags."** A perfectly silent run doesn't exist in this system by design — see the
re-measurement note in `history/decision_log.md` under "U7.8."

### Chicago — the deliberate escalation

`main.py --deal chicago` · confidence **0.55** · 9 disclosures (5 info, 4 warn) ·
**escalates to human review**

A Logan Square two-flat. Still finds a full comp set (8 comps) — this deal escalates
purely on accumulated warn-severity flags, not because anything is broken: a widened
comp search radius, comps that came back outside the target size band, and a
near-tied forecast between scenarios. **This outcome was accepted on purpose rather
than tuned away.** The threshold could be nudged to make Chicago pass, but that would
mean adjusting a production parameter to fit a demo's expected result instead of the
other way around — exactly the failure mode threshold-tuning exists to avoid.

### Staten Island / New York — the real-data degradation case

`main.py --deal staten-island` · confidence **0.00** · 9 disclosures (2 info, 6 warn,
1 critical) · **escalates to human review**

This is the one deal grounded in a real, *measured* market gap rather than a
constructed one, and it's worth walking through why New York needed a case like this at
all.

**New York almost wasn't in the demo at all.** The original metro shortlist hypothesis
was New York/Chicago/Philadelphia, reasoned from housing-stock knowledge (small
multi-family buildings concentrate in older Northeast/Midwest cities). Measured against
the actual rental corpus, New York had only 271 listings across all five boroughs — too
thin by the selection bar — so Chicago/Los Angeles/Cleveland became the inference trio
instead (`design/data_strategy.md` §"Metro Selection").

**But "271 citywide" turned out to be the wrong statistic.** A follow-up measurement
showed those 271 listings aren't spread thin across the metro — they cluster densely in
central Brooklyn (Bedford-Stuyvesant alone returns 38 comps within 3 miles), while
Staten Island holds only 6 listings in the *entire borough*. New York isn't uniformly
sparse; it's a metro where comp density swings enormously by neighborhood, and that's a
genuine property of the data — not something engineered for the demo
(`design/data_strategy.md` §"Sparsity is a property of sub-locations"). Staten Island —
specifically Tottenville, a far corner of the borough — is the sub-location where that
real thinness is worst, so it's the deal that demonstrates it: 4 relaxation iterations
(the retrieval agent keeps widening its search), radius maxed out at 8 miles, still zero
qualifying comps, `sparse_comps` fires at **critical** severity, and the deal escalates.

**A second, independent problem stacks on top of the comps gap:** New York's rent model
also predicts materially worse than the other three markets — about $1,048 mean
absolute error against ~$524 overall (roughly double), measured per-metro in U8.4. That's
a training/anchoring issue (the rent-to-FMR ratio New York properties actually show
doesn't generalize as cleanly from the national corpus), not a retrieval issue, so it's
present *even on New York listings that do have comps*. On the Staten Island deal itself
this second problem is invisible — the run is already escalating on zero comps, so the
rent-error disclosure never gets a moment to matter on its own. To show it firing
independently, a second fixture (`ny-bedstuy-triplex`, an eval-only case, not a
`--deal` key) was added in `eval/cases.py` at a real, Census-geocoded Bed-Stuy address
that *does* return 8 comps — specifically so the elevated-market-error flag can be
observed on a deal that isn't already escalating for an unrelated reason. (That fixture
still escalates — the floor arithmetic below explains why, as built, no New York deal
can report — but the flag is visible as its own line rather than lost under a zero-comp
collapse.)

**One more gap — and its cause was misdiagnosed until Aug 29, 2026:** unlike every
other deal here, Staten Island's asking price has no market anchor and its forecast
covers only the rent side. This document (and the report's own disclosure text) used to
attribute that to Redfin — "Redfin's sale-price extract doesn't cover the New York
metro" — and a direct check of the data found that to be false: the raw extract carries
a "New York, NY metro area" series with 102 fully-populated months at 700–950
multi-family sales per month. What actually excludes New York is the build's own load
filter (`tools/redfin_data.py`'s `TARGET_METROS`), written when the plan scoped the
price series to the three inference metros — before New York entered the demo as the
sparse-comps case, and never revisited after. Whether to widen that scope is an open
decision; until it is taken, "no price series for New York" is a fact about this build's
scoping, not about Redfin's coverage. That distinction matters for the same reason it
did when U8.2b fixed the FMR anchor label: "the source publishes nothing" and "this
system doesn't look" read identically in a report and are different facts. No comps, no
appreciation series, and no price benchmark: this deal remains the one place the demo
shows what happens when nothing is available to anchor to — with the middle gap now
correctly attributed to the build rather than to the source.

**Why this matters for the demo as a whole:** every other case here (and every
engineered case in the U8 eval harness) proves the degradation mechanism fires when a
listing is built to trip it. This is the one that proves it fires when a *real* place is
genuinely under-covered by the data — reality, not the author, supplies the gap. See
`history/decision_log.md` ("why the eval harness is protected from the cut list") for
why this distinction is treated as important enough that U8 is never cut from schedule.

#### Why *every* New York deal escalates — not just this one

Measured during U8.6 (Aug 29, 2026): three warn-severity disclosures fire for **any**
New York deal, before a single comp is retrieved, because each is a property of the
market rather than of the listing:

1. **The rent model's error is elevated market-wide.** About $1,048 mean absolute error
   in New York against ~$524 overall — 2.0x, past the 1.5x disclosure threshold. The
   rent-to-FMR structure the model learned from the national corpus generalizes worst
   here.
2. **The rent anchor is county-wide in all five boroughs.** HUD publishes no ZIP-level
   Fair Market Rent schedule for any New York county (U8.2b), and a county-wide figure
   is at its coarsest exactly here — Kings County prices Williamsburg and
   Brownsville/East New York with a single number.
3. **No price side.** As built, the system has no sale-price appreciation series or
   benchmark for New York (see the scoping finding above), so every New York forecast
   covers only the rent half of the deal.

Three warns cost 0.45 of confidence (0.15 each), landing every New York deal at 0.55 —
below the 0.60 threshold — **before its comps enter the picture.** Comp quality then
decides only how far below that floor a deal lands, and it varies enormously
sub-metro, which is a genuine property of the corpus rather than an engineered one:
Brooklyn's 89 corpus listings collapse onto essentially one coordinate (87 of 89 share
a single placeholder point), while Manhattan's 161 spread across 60 distinct
coordinates, and Staten Island holds 6 listings at 1 coordinate. Staten Island's
zero-comp escalation is the extreme end of that spread, not the cause of the pattern.

**Held as policy rather than tuned away (architect's decision, Aug 29, 2026).** The
floor could be removed by lowering the per-warn penalty or the threshold — both sit
inside ranges the eval batch measurably cannot distinguish from the shipped values —
but each of the three disclosures is a serious, independent limitation, and it is their
*combination* that makes a human look warranted. This is the same principle as
Chicago's 0.55 above: production parameters are not adjusted to make a demo read
better. Most people would expect a rent-forecasting system to handle New York easily;
that it escalates every New York deal, and can say precisely why in three sentences, is
the demo's clearest showcase of Transparent Degradation doing its job. (If the
price-series scoping decision above is later taken, the third warn stops firing and a
well-sited New York deal could clear the bar honestly — by closing a real gap rather
than lowering the bar.)

### No Geography — nowhere to anchor to

`main.py --deal no-geography` · confidence **0.00** · 5 disclosures (1 warn, 4
critical) · **escalates to human review**

A listing at a fictional address (Tallow Bend, WY) that resolves through neither the
Census geocoder nor the corpus's city-centroid fallback. With no coordinates, there's no
county, so no Fair Market Rent, no comps, and no appreciation series — every downstream
number is unavailable rather than approximate. This is the totally-ungrounded case, one
level worse than Staten Island: Staten Island still resolves a *place* and fails to find
comps there; this deal fails to resolve a place at all. The listing's own price figure
is stated as illustrative for exactly this reason — there's no benchmark it could be
checked against.

### Overpriced — exercising the price-benchmark disclosure

`main.py --deal overpriced` · confidence **0.70** · 4 disclosures (2 info, 2 warn) ·
**reports normally**

Identical in almost every respect to the Los Angeles deal — same market, same unit mix,
same FMR-anchored rents — except the asking price is set 55% above the Redfin metro
median on purpose (`price_premium_to_basis=0.55` in `demo_deals.py`). This exists to
solve a specific problem: every *other* demo listing is calibrated exactly to its
benchmark, so the report's "asking price vs. market benchmark" disclosure reads 0% on
all of them — a real check the demo set otherwise has no listing that can exercise. This
deal isn't a claim that this Los Feliz property actually trades at this price; it's a
fixture built to make that one disclosure show something.

### Coordinate Conflict — supplied coordinates disagree with the address

`main.py --deal coord-conflict` · confidence **0.05** · 5 disclosures (1 info, 2 warn,
2 critical) · **escalates to human review**

The same Echo Park listing as the Los Angeles deal, but with coordinates supplied
directly that actually describe a property in Santa Monica, ~14 miles away. This
exercises one of the Critic's cross-agent consistency checks: it catches the case where
a subject's stated address and its supplied coordinates disagree about where the
property actually is — something neither the Extractor nor the geocoder would notice on
its own, since each only sees one half of the conflict.

### The ablation: isolating the critical-flag escalation rule

`main.py --deal chicago --no-retrieval` · confidence **0.60** (exactly) · 6 disclosures
(4 info, 1 warn, 1 critical) · **escalates to human review**

Not a seventh listing — the Chicago deal run with retrieval switched off, which is the
U4 ablation demonstrating what the system does without its comps step at all. It's
included here because it's the one live run that isolates the *critical-flag* escalation
rule from the *score* rule described above: `retrieval_disabled` costs 0.40, landing the
score at exactly 0.60 — not below the 0.60 threshold, so the score alone would **not**
escalate this deal. It escalates anyway, because `retrieval_disabled` is critical
severity and that rule fires independent of the score. None of the other six deals
happens to land on that exact boundary, which is why this run earns a place in the demo
set even though it isn't a distinct listing.

---

## How the demo deals relate to the eval harness

The demo deals answer "does the system behave sensibly on a handful of representative,
real-world-anchored cases." The U8 eval harness (`src/eval/cases.py`,
`src/eval/README.md`) answers a different question — "does every specific degradation
path in the system actually fire, on a listing built to trip exactly that path and
nothing else" — with roughly 15 engineered fixtures, each targeting one named flag.

The two are kept structurally separate inside the harness: the demo deals carry a
`BASELINE` verdict (a previously measured outcome, so re-running them is a regression
check — did the number move), while the engineered cases carry a `PREDICTED` verdict (a
claim made about the case before it was run, which is what U8.6's confidence-threshold
tuning is actually allowed to score against). Scoring a threshold against the demo deals
would be circular, since they were calibrated to run clean rather than to probe the
threshold. Full reasoning in `eval/cases.py`'s module docstring.

---

## Looking ahead: the rest of the demo (U9, not yet built)

The pieces above exist and are evidenced. These are the remaining demo-surface pieces
U9 is scoped to build, noted here as a placeholder so this document grows into a
complete demo guide rather than needing a second one later.

- **Streamlit app.** The intended interactive demo surface — a listing goes in, the
  report (with every disclosure) comes out. Decision #3 in the plan's register. It's
  kept in scope deliberately (§6's cut list, position 4) *because* a fallback exists if
  the schedule forces it: a terminal recording plus LangSmith traces of the same six
  deals, which is already what U8's harness produces as a byproduct.
- **Final report and video.** Due Sept 7, 2026, after the Sept 4 code freeze. Expected to
  draw its evidence largely from U8's harness output — the demo deals' reports, the
  eval batch's results table, and the graph diagram generated from the compiled graph —
  rather than being written separately from scratch.
- **LangSmith traces.** Each demo deal run with tracing enabled
  (`LANGSMITH_TRACING=true`) produces a trace of the full seven-agent pipeline, useful
  for showing the actual agent-to-agent flow rather than just its final output.

This section will be expanded with real detail — screenshots, app structure, what the
video walks through — once U9 starts.
