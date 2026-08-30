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
provisional), the deal escalates. **But there are two further, independent grounds** —
a single critical flag escalates on its own however high the score, and a retryable
objection that survives the rework budget does the same. `chicago --no-retrieval` below
is the case that isolates the critical-flag rule from the score-based one; the eval
harness's `chicago-geocoder-outage` row isolates the rework-budget one. Mechanism in
`agents/critic.py`; both constants are marked provisional in `config.py` because U8's
eval batch is what tunes them against real evidence rather than against the six deals,
which were calibrated to run clean and can't stress-test a threshold themselves.

**One consequence of the arithmetic is worth seeing before reading the deals below.**
Because info-severity disclosures cost nothing and warns cost 0.15, the score is
effectively a count: one warn reports at 0.85, two report at 0.70, and **three warns
escalate at 0.55**. So the practical question the threshold asks is *"have three
independent things gone wrong?"* — and a market that supplies two warnings to every
listing in it (see New York, below) has spent most of that budget before the property
is examined at all.

---

## The demo deals

### Los Angeles — the clean baseline

`main.py --deal los-angeles` · confidence **0.85** · 7 disclosures (6 info, 1 warn) ·
**reports normally**

An Echo Park duplex, dense market, full 8-comp set. This is the "everything worked"
case — but even here, one warn-severity disclosure fires: Los Angeles County's rent
anchor falls back to the county-wide Fair Market Rent, and the report says so. That's
deliberate evidence in itself: **the clean row in this demo set is "reports with no
critical flag," not "raises zero flags."** A perfectly silent run doesn't exist in this
system by design — see the re-measurement note in `history/decision_log.md` under
"U7.8."

The six info-severity disclosures are mechanism, not weakness, and they cost the score
nothing: how the rent figure was anchored, that a **drift correction was applied to it**
(U8.4b — this deal's estimate is adjusted down by a factor of 0.74, because the federal
rent schedule for this ZIP rose 62% since the model's training vintage while observed
market rents rose 21%), which years were screened out of the rent bands, and so on.

### Chicago — the deal that used to escalate, and why it stopped

`main.py --deal chicago` · confidence **0.70** · 7 disclosures (5 info, 2 warn) ·
**reports normally**

A Logan Square two-flat with a full 8-comp set. **Through U8.5 this deal escalated at
0.55**, and it was the demo set's one example of "escalates on accumulated warnings
alone, with nothing actually broken" — a deliberately accepted outcome, on the principle
that you don't move a production threshold to make a demo pass.

It reports now, and the reason is a severity change made on evidence rather than a
threshold nudge. One of its three warns was a **near-tie between forecast scenarios**.
U8.6c found that flag was two different disclosures sharing one name: a tie between
*framings* (which years feed every band) discards a whole reading of the data and stays
warn-severity, but a tie between *scenario pairings* — which is what fired here —
changes nothing a reader sees, because both tied pairings appear in the scenario table
anyway and each scenario's label comes from its projected outcome, not its rank. It was
also being measured by a scorer whose repeat runs vary by more than the tie threshold
itself (see OQ-17). Charging 0.15 of confidence for it was pricing the model's own
noise as doubt about the deal, so the pairing variant is now info-severity.

**Worth stating plainly, because it is a real cost:** the demo set no longer has a
"escalates purely on accumulated warns" case. That property is now carried by the eval
harness's engineered fixtures instead.

### Staten Island / New York — the real-data degradation case

`main.py --deal staten-island` · confidence **0.00** · 10 disclosures (3 info, 6 warn,
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
observed on a deal that isn't already escalating for an unrelated reason. (It escalates
too, at 0.55, but for a visible and different reason: Brooklyn's corpus listings nearly
all share one placeholder coordinate, so it pays a spatial-concentration warn on top of
New York's two market-level ones. See the floor arithmetic below.)

**A third gap used to be listed here and turned out not to exist — the correction is
kept rather than quietly deleted, because believing it shaped this deal's design.**
Staten Island was described as having no price anchor at all, on the stated grounds that
"Redfin's sale-price extract doesn't cover the New York metro." Checked directly against
the file on Aug 29, 2026, that is false: the extract carries a New York series with 102
fully-populated months at 700–950 multi-family sales each. What excluded it was a filter
in this build's own loader, scoped to three metros before New York was ever a demo case
and never revisited (fixed in U8.4c). The listing's committed $875,000 asking price was
set without a benchmark *because of* that belief; it now measures about 11% below the
metro's multi-family median (~$981K), a plausible Staten Island discount, so the figure
stands as committed and the report benchmarks it like any other deal.

The distinction matters for the same reason it did when U8.2b fixed the FMR anchor
label: **"the source publishes nothing" and "this system never looked" read identically
in a report and are completely different facts.** What remains genuinely missing here is
the comp set — zero comparables, from a real and measured thinness — which is the gap
this deal exists to show.

**Why this matters for the demo as a whole:** every other case here (and every
engineered case in the U8 eval harness) proves the degradation mechanism fires when a
listing is built to trip it. This is the one that proves it fires when a *real* place is
genuinely under-covered by the data — reality, not the author, supplies the gap. See
`history/decision_log.md` ("why the eval harness is protected from the cut list") for
why this distinction is treated as important enough that U8 is never cut from schedule.

#### What New York costs *every* deal, before its own comps are counted

Measured during U8.6 (Aug 29, 2026). The investigation started from a question worth
repeating — *why should a rent-forecasting system struggle with the largest rental
market in the country?* — and the answer turned out to be partly real and partly this
project's own stale assumption. Both halves are recorded, because the second one was
believed for weeks.

**Two warn-severity disclosures fire for any New York deal**, before a single comp is
retrieved, because each is a property of the market rather than of the listing:

1. **The rent model's error is elevated market-wide.** About $1,048 mean absolute error
   in New York against ~$524 overall — 2.0x, past the 1.5x disclosure threshold. The
   rent-to-FMR structure the model learned from the national corpus generalizes worst
   here.
2. **The rent anchor is county-wide in all five boroughs.** HUD publishes no ZIP-level
   Fair Market Rent schedule for any New York county (U8.2b), and a county-wide figure
   is at its coarsest exactly here: Kings County prices Williamsburg and
   Brownsville/East New York with one number, and those are not one market.

**A third disclosure used to fire and no longer does, because it was never true.** Every
New York report carried "no price appreciation series" — and this document, and the
report text itself, attributed that to Redfin not covering the metro. Checked directly
on Aug 29, 2026: the extract carries a full New York series, 102 months at 700–950
multi-family sales each. The gap was a filter in this build's own code, scoped to three
metros before New York was ever a demo case and never revisited (U8.4c). It is fixed,
New York deals now get a price forecast and a sale-price benchmark like any other
market, and the standing cost is two warns rather than three.

**So the floor is 0.70, which reports.** Two market-level warns cost 0.30, leaving a New
York deal at the reporting threshold before anything about the property is considered —
where a third disclosure sends it to a human. Comp quality usually supplies that third,
and it varies enormously sub-metro, which is a genuine property of the corpus rather
than something engineered: Brooklyn's 89 corpus listings collapse onto essentially one
coordinate (87 of 89 share a single placeholder point), Staten Island holds 6 listings
at 1 coordinate, while Manhattan's 161 spread across 60 distinct coordinates. That is
why the Bedford-Stuyvesant eval fixture escalates at 0.55 on a *spatial concentration*
warn even with 8 comps, and why Staten Island escalates at 0.00 on no comps at all.

**The thresholds were held rather than tuned (architect's decision, Aug 29, 2026).** The
floor could be lifted by lowering the per-warn penalty or the threshold — both sit
inside ranges the eval batch measurably cannot distinguish from the shipped values — but
each of these disclosures is a serious, independent limitation, and it is their
*combination* that makes a human's look warranted. Production parameters are not moved
to make a demo read better. What did move was a wrong fact about the data. That is the
distinction this whole section is here to show: **the right response to "New York looks
bad" was to check whether the system's reasons were true, not to adjust the bar until
the complaint went away** — and one of the three reasons turned out not to be.

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

`main.py --deal overpriced` · confidence **0.70** · 5 disclosures (3 info, 2 warn) ·
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

`main.py --deal coord-conflict` · confidence **0.45** · 6 disclosures (3 info, 2 warn,
1 critical) · **escalates to human review**

The same Echo Park listing as the Los Angeles deal, but with coordinates supplied
directly that actually describe a property in Santa Monica, ~14 miles away. This
exercises one of the Critic's cross-agent consistency checks: it catches the case where
a subject's stated address and its supplied coordinates disagree about where the
property actually is — something neither the Extractor nor the geocoder would notice on
its own, since each only sees one half of the conflict.

### The ablation: isolating the critical-flag escalation rule

`main.py --deal chicago --no-retrieval` · confidence **0.60** (exactly) · 8 disclosures
(6 info, 1 warn, 1 critical) · **escalates to human review**

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
