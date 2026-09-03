# The presentation, the script, and the report

**The Checkpoint 7.1 deliverables, written down so they are not assembled at midnight.**
Section numbers (§1–§9) and decision numbers (#1–#21) refer to
[`implementation_plan.md`](implementation_plan.md).

**Split out of [`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9 on Sept 2, 2026**, by
the architect's call. It was drafted there because U9.9 owns the capture, but a script is a
document you open repeatedly while recording and a task list is not — and the task list is
also the wrong place for something that outlives the unit.

**What is here and what is not.** This file holds the *deliverables*: the slide outline, the
narration script, the demo beat sheet, the report's source map, and the elevator pitch. The
**capture runbook stays in [`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9** — the
exact commands for traces, screenshots and the diagram, plus the prerequisite table showing
what is already discharged. Deliberately not duplicated here: two copies of a command list
diverge the first time either is edited, which is the same argument the demo surface is built
on (it renders the report rather than re-laying-out the evidence).

**Three graded artifacts, one optional.**

| | Deliverable | Where it stands |
| --- | --- | --- |
| **1** | Capture — traces, screenshots, diagram, terminal recordings | Runbook in §U9.9. Needs a live account and a screen |
| **2** | The 8–10 minute presentation video | Outline, timing and script draft below |
| **3** | The 1,000–1,500 word final report | Section-by-section source map below |
| — | *Optional* 90-second elevator pitch | Draft below. Ungraded, and the entry to the showcase |

---

## Two reference points, read Sept 2 — and the one thing both of them left open

Two completed capstones from the cohort (`private/capstone_reference/`). Both are good,
both are worth watching, and **both landed at roughly 12½ minutes against a 10-minute
limit.** That is the first thing to copy in the negative: the outline below is timed to
**9:30** so there is somewhere to lose thirty seconds live.

**What both do well and this presentation should do too:** open with the problem in plain
language before any architecture; build the architecture diagram in layers rather than
showing it whole; put a live demo in the middle; and close on a design lesson rather than a
feature list. Crosscheck's closing line — *"making the model sound helpful was not the hard
part; the hard part was designing boundaries around the model"* — is the right register.

**And the thing both of them name as their own weakest point is this project's strongest.**
Crosscheck: *"the main limitation right now is still evaluation — I do not have an automated
scoring benchmark for the briefing quality. Right now I'm just spot checking it."* Grid
Coordinator reports two scenario plots against a no-agent baseline and no held-out set. **A
30-case batch whose expected verdict is declared before the first run, with 30 of 30
disclosure kinds raised and a published sensitivity sweep, is the differentiator** — it
should get a slide of its own and it should not be rushed.

**One thing to be careful about, because it cuts the other way.** Both presenters had a
system a stranger can evaluate in one glance — 82% of damage avoided, a no-go on an icing
forecast. This system's output is a *report*, and reports do not read well on a screen share.
The demo beats below are built around that: show the two verdicts, the review pause, and the
search's own reasoning — three things that are legible in seconds — and let the report scroll
behind the narration rather than trying to read it aloud.

## The slide outline, timed to 9:30

Eight slides, matching the seven-part planning outline in
`private/capstone_reference/templates/`, with the demo inserted at position 6.

| # | Slide | Template section | Time | Running |
| --- | --- | --- | --- | --- |
| 1 | Title — what it is, in one sentence | 1. Opening | 0:20 | 0:20 |
| 2 | The problem, the user, and why an agent | 1–2 | 0:50 | 1:10 |
| 3 | What it produces: **the two axes** | 1. Goal | 0:50 | 2:00 |
| 4 | Architecture — seven agents, two invariants | 3 | 1:20 | 3:20 |
| 5 | Key design decisions — **three premises measured and disproved** | 4 | 1:30 | 4:50 |
| 6 | **Live demo** | — | 2:20 | 7:10 |
| 7 | Evaluation and results | 5 | 1:20 | 8:30 |
| 8 | Limitations, repository, closing reflection | 6–7 | 1:00 | 9:30 |

**If it runs long, cut in this order** — decided now so the decision is not made at 11pm:
(1) the anchor paragraph on slide 5, which is the least surprising of the three premises;
(2) the fault-selector demo beat; (3) the second half of slide 2's "why an agent". **Do not
cut the two-axes slide or the evaluation slide** — the first is the design argument and the
second is the differentiator.

## Script draft — first pass, for the architect to edit

**Roughly 1,150 narrated words ≈ 8:10 at a measured 140 wpm, plus demo screen time.** Written
in the architect's voice, narrating as architect rather than in persona, per the demo shape
settled Aug 31. Bracketed lines are stage directions, not narration.

---

**[1 · Title · 0:20]**

I'm Jelani Gould-Bailey. My capstone is a Multi-Family Deal Evaluator — a seven-agent
pipeline that evaluates small residential rental buildings, two to four units, as investment
candidates.

The thing I want you to take away is not that it produces a number. It's that it tells you
how much to trust the number — and that it refuses to hand you one when it can't stand
behind it.

**[2 · The problem and the user · 0:50]**

Small multi-family is where most individual real-estate investors start, and it has the worst
data of any segment. The institutional tools are built for single-family homes or for large
apartment complexes. In between, an investor or their agent reconciles a listing, a rent
guess and a market trend by hand, from public sources that disagree about vintage, about
geography, and about what even counts as a comparable.

The user I built for is the real-estate agent who screens deals before they reach an
investor. They read the whole report, including the evidence, because their job is to decide
whether the deal — and the system's own confidence in it — is ready to put in front of a
client.

Why an agent and not a spreadsheet? Because the arithmetic isn't the hard part. The hard part
is what to do when the evidence runs thin. Widen the comparable search, or report that you
couldn't? Trust the listing's stated rent, or the model's? Those are sequential decisions
where each one changes the next — and every one of them needs to be disclosed.

**[3 · The two axes · 0:50]**

Every run produces one report and two separate verdicts. Keeping them separate is the design
decision I would defend hardest.

Axis one: *can the system stand behind its own numbers?* That's a confidence score, and below
a threshold, a pause for human review. It is a statement about the **software**.

Axis two: *is this a good deal?* That's a recommendation — proceed, proceed with caution, do
not proceed, or no recommendation at all. It is a statement about the **property**.

They are different questions and they can point in opposite directions. Here is Staten
Island. The system escalates, because it found **zero** qualifying comparables in that
market. And the asking price is **seventeen percent below** the typical sale for that ZIP.
Before I separated these, the report put a red escalation banner over a deal that was cheap —
telling the reader the reverse of what the evidence said.

**[4 · Architecture · 1:20]**
*[Build the diagram in layers — do not show it whole.]*

Seven agents, orchestrated as a LangGraph state graph with a SQLite checkpointer.

The **Planner** runs pre-flight: it inspects the deal and decides which downstream steps are
needed. The **Extractor** parses an unstructured listing into typed deal terms and geocodes
the address — and where it has to assume something, it says so. **Retrieval** is RAG over a
rental corpus in a vector store; when matches are sparse it relaxes its criteria one step at
a time and flags each concession it makes. **Valuation** runs a gradient-boosted rent model
anchored to a market rent index at the subject's own ZIP code. **Forecast** is the
Tree-of-Thought step. The **Critic** checks consistency *across* agents, scores confidence,
and can either send the deal back to the Planner — a bounded cycle — or escalate it to a
human. The **Summarizer** renders the report.

Two structural rules hold this together. **Agents never call each other**; they communicate
only through one typed state object. And **every agent can append to a shared disclosure
list, but nothing can remove from it.**

That second rule is the principle the whole system is built on. I called it Transparent
Degradation: when the system proceeds on thin evidence, it attaches a named flag, and that
flag survives to the report. It isn't a style guideline — the flag kinds come from a closed
enum, and a dedicated test suite asserts that a flag raised in the Extractor survives every
downstream node and appears in the final output.

**[5 · Key design decisions · 1:30]**

Four decisions, and I've picked the ones where measurement changed my mind.

**The reasoning structure.** The forecast is Tree-of-Thought over an *enumerated* space
rather than a sampled one — four ways of reading the market history, then nine pairings of
rent and price bands. Enumerating keeps the pipeline deterministic, and deterministic is what
makes it evaluable.

**But the evaluator was being told something false.** It was instructed that rent and price
move opposite each other in these markets. I finally measured it. Pooled correlation: minus
0.32 — which looks like strong support. Except that is the *HUD rent schedule* against Redfin
prices. Against actual **market** rent, the same prices give **plus 0.22**. The sign was a
property of the data series, not of the market, and r-squared never exceeded 0.10. So the
premise was false, the evidence for it was an artifact of an administrative schedule, and I
re-sourced the entire rent-growth series.

**The rent anchor.** The model learns a ratio — this unit's rent against its area's typical
rent — from 2018-19 listings, and applies that ratio to today. That only works if the anchor
tracks the market. Measured: the HUD schedule had risen **52 percent** since the corpus
vintage while market rent rose **33**. Eighteen points of drift, and the model was
over-predicting because of it. Moving to a ZIP-level market index cut New York's error from
**$981 a month to $855**, and Chicago's from **$454 to $343**.

**And a second place where a model exercises judgment.** Once I retired Tree-of-Thought from
the Critic — on evidence; the checks that shipped are pure functions with nothing to search
over — the forecast was the *only* node where a model made a judgment call. So the
recommendation now carries a cross-check: the model reads the same state and reaches its own
verdict independently. It can **never move** the rule's verdict, only annotate it. When they
disagree, the report says so and does not resolve it. The disagreement is the product.

**[6 · Live demo · 2:20]**
*[Beat sheet below. Narrate over it; do not read the report aloud.]*

**[7 · Evaluation and results · 1:20]**

Thirty cases through the compiled graph, in three tiers. **Twenty-three of them declare the
expected verdict before the first run** — that is what makes this an evaluation rather than a
demonstration. Agreement is **20 of 23**, and every mismatch is triaged in the results file
rather than explained away.

The coverage number I care about most: the system defines **thirty** distinct disclosure
kinds, and this batch raises **all thirty**. None uncovered — and none unreachable, meaning
there is no flag in the code that no case can trigger.

For the escalation threshold I published a **sensitivity sweep** instead of a tuned number.
Across 160 grid points, 63 decide the batch identically, and through the shipped setting the
threshold moves from 0.30 to 0.70 without a single verdict changing. That is a claim about
**robustness, not optimality** — and the write-up says exactly that, because a batch that
cannot separate two settings is not evidence that one of them is better.

The rent model is cross-validated and reported **per metro** rather than pooled, because the
pooled figure hides the result: $855 a month of error in New York against $343 in Chicago. A
reader looking at a New York deal deserves to know which of those they're holding.

**[8 · Limitations, repository, close · 1:00]**

Limitations, stated the way the system states its own. The rent corpus is 2018-19, so the
model's core assumption — that a unit's rent ratio to its area is stable over seven years —
is a floor I tested over thirteen months, not a demonstration over seven years. The comp
corpus is location-blind below the county level for 92 percent of its rows. Live model calls
are **not reproducible even at temperature zero** — I measured that, it's a property of the
serving stack rather than of my code, and it's why the demo replays from committed recordings
by default. And one report currently serves two very different readers.

The repository is public at **[URL]**. It has the README, the full seven-agent
implementation, the evaluation harness with every input committed so the results re-derive
from a fresh clone, three sample reports, and a decision log — twenty-one numbered decisions
with their reasoning, including the ones I got wrong first.

The takeaway. Every significant improvement on this project came from measuring a premise I
had been holding confidently: the metro selection, the rent anchor, the forecast's
correlation. All three survived for weeks because nothing forced them to be checked. Building
a system that discloses its own uncertainty turned out to be the same discipline as building
it honestly.

Thank you.

---

## The demo beat sheet — 2:20, in this order

**Run the surface in replay** (`.venv/bin/streamlit run app.py`, from `src/`), which is its default — the full command set, including the tracing switch, is in [`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9. Every
figure below is deterministic, so the beats can be rehearsed and re-shot.

| Beat | On screen | Say | Time |
| --- | --- | --- | --- |
| **a** | `los-angeles`, the status strip and verdict block | "A clean run: confidence 1.00, four informational disclosures, eight comparables. Both verdict lines agree — the system stands behind its numbers, and the deal is worth proceeding on." | 0:25 |
| **b** | Scroll to the forecast's search block | "This is the search, rendered as the two questions it actually asked. Step one: which reading of the history? Four considered, one chosen. Step two: which band combinations are worth showing? Nine considered, three kept. The winner's score is shown, not just the discarded branches." | 0:30 |
| **c** | Switch to `staten-island` — it pauses | "The run stops here. This is a real interrupt — the graph is checkpointed and waiting, not printing a message. And it names the desk it routed to: this one goes to the reviewing agent rather than to IT, because these flags are about the deal, not the infrastructure." *[type a note, Release]* "The note reaches the report verbatim." | 0:45 |
| **d** | `overpriced` | "Reports cleanly at 1.00 — and recommends *proceed with caution*, because the asking price is 55 percent above what actually sold in that ZIP. And here is the cross-check I mentioned, disagreeing with the rule on the same evidence, disclosed rather than resolved." | 0:25 |
| **e** | The fault selector, open | "The three simulated failures are declared before they run and name themselves in the report — so a demonstration can never be mistaken for an incident." | 0:15 |

**Beats c and d are the two that must survive a cut.** (c) is the human-in-the-loop evidence
7.1 asks for and the one thing no terminal recording can produce; (d) is the only deal where
the two axes disagree *and* the two reasoning loci disagree, on one screen.

## The final report — section-by-section source map

**1,000–1,500 words across ten template sections is ~120 words each.** Every one has its
evidence in this repository already; the work is compression, not composition.

| Template section | Source | Watch for |
| --- | --- | --- |
| 1. Project title | — | — |
| 2. Problem and user | `design/personas.md` — the four personas and the routing rule | Name persona (b) as the primary; (c) is who the report's language rule is written for |
| 3. Goal, scope, constraints | §1, and §6's hard constraint | The scope boundary worth stating: **no property-level value estimate** (#15), deliberately |
| 4. Final architecture | README's seven-agent list + `design/architecture.md` + the diagram | The two invariants (state-only communication, append-only flags) are the architecture, not decoration |
| 5. Design evolution | `history/decision_log.md`, grouped by area | **Lead with premises disproved, not with a week-by-week list** — that is what distinguishes this from a syllabus recap |
| 6. Implementation overview | README "Setup", `requirements.txt` | LangGraph + SQLite checkpointer, ChromaDB + sentence-transformers, scikit-learn, OpenRouter, Streamlit, LangSmith, MCP |
| 7. Evaluation and results | `eval/results/results.md`, `sensitivity.md`, `eval/README.md` | **30 rows / 23 predicted / 20 of 23 / 30 of 30 flag kinds.** Quote the file, not §6's U8 row, which states U8's figures at U8's close |
| 8. Safety, reliability, human oversight | `human_review.py`, `design/personas.md` routing rule, the three declared faults, `test_flag_propagation.py` | Transparent Degradation belongs here as much as in the architecture section |
| 9. Limitations and next steps | `open_questions.md` — OQ-19, OQ-17, OQ-23, OQ-26, OQ-27, and §2's location-blindness | **The next step worth naming is persona (d)**: the MCP server already exposes this project's read-only tools; the unbuilt half is exposing the *evaluation itself* as a callable capability. Half the plumbing exists |
| 10. GitHub repository | The repo | Must be **public** before submission — confirm |

## The optional 90-second elevator pitch

Ungraded, and it is the entry to the showcase. Four beats, ~200 words:

> Small multi-family — two-to-four-unit rental buildings — is where most individual property
> investors start, and it has the worst data of any segment of real estate. I built a
> seven-agent pipeline that evaluates one of these listings end to end: it extracts the deal
> terms, finds comparable rentals, models the rent, forecasts five years, and writes an
> investor-facing report.
>
> What makes it different is what it does when the evidence runs thin. Every agent that
> proceeds on relaxed or incomplete information attaches a named disclosure, and nothing
> downstream can remove it — so the report always says where the system had to compromise. If
> too much has been compromised, it doesn't publish. It stops and asks a human, and it names
> which desk should look at it.
>
> It separates two questions most tools merge: *can I stand behind these numbers*, and *is
> this a good deal*. On one of my demo listings those point in opposite directions — the
> system escalates for lack of comparables on a property priced seventeen percent below its
> market.
>
> The takeaway: I got more out of measuring the premises I was confident about than out of
> any model I chose. Three of them turned out to be wrong.

## What still needs a decision before recording

Both were raised Sept 2 and neither blocks starting. Restated here with the two reference
capstones now read.

- **Whether the video's live run is genuinely live.** A live run is the honest demonstration
  and it is exposed to OQ-17: roughly 1 in 15–20 live attempts on this model lands a different
  forecast pairing, and `los-angeles` has escalated on a live re-run before. **Recommendation
  unchanged, and the reference capstones support it** — Crosscheck ran live and had to say
  *"this part could be a little bit slow, so I'll speed it up in the recording"* mid-demo.
  Narrate one live run to establish the system is real, and make every *claim* from replay.
- **Whether the paste box appears at all.** It is the one path that forces a live call by
  construction, and it demonstrates the system takes real input rather than only canned deals.
  **At 9:30 there is no room for it in the video.** Better use: keep it for the live Q&A or the
  showcase session, where an unrehearsed input is worth more than a rehearsed one.
