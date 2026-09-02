**§8 of the plan of record — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#20) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the **decisions register in §7**,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

## 8. Engineering Standards

These are the standards every change set is held to in review. They are recorded here
rather than left implicit so that the bar is the same whether a given unit is written
in a focused session or across a fragmented week.

### Architecture

- **Follow the design conventions in §3**: node functions returning *partial* state
  updates, agents communicating only through shared state, a single typed state object,
  flags and retries
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

- **Reader-facing text carries no internal vocabulary** (added Aug 24, 2026). Section
  numbers (§2), decision numbers (#15), unit numbers (U7), `config` constant names and
  enum members are this repository's vocabulary, not the reader's. An investor reading
  the report, or an audience watching the demo, has no way to resolve any of them — and
  a citation the reader cannot follow is worse than no citation, because it looks like
  evidence while supplying none.

  **This applies to anything that reaches the report:** flag messages, objection text,
  Summarizer prose. It explicitly does **not** apply to docstrings and comments, which
  evolve alongside the implementation and are read by someone with the repository open.
  Those should keep citing precisely — that is where the traceability lives.

  The distinction is the audience, not the formality. Where a flag needs to explain the
  reasoning behind a threshold, it states the reasoning: not *"config.RENT_MODEL_FEATURES
  was relaxed"* but *"the comp set was widened on an attribute the rent estimate depends
  on — bedrooms, bathrooms or floor area"*. The second is longer and says more.

  Enforced for the Critic's objections by
  `tests/test_critic_interactions.py::test_objection_text_carries_no_internal_vocabulary`,
  which walks every reachable flag combination. Worth extending to the other agents'
  messages when one of them next changes.

- **Every commit appends to [`../history/changelog.md`](../history/changelog.md)** (added
  Aug 10, 2026 as *every unit closes by appending*; **changed Aug 26, 2026** — see below).
  A `##` heading per date the work was done, and beneath it a table of
  `date added | unit | work done | related checkpoint`.

  **Revised Aug 26, 2026: log at commit, not at unit close.** The original rule was
  written when a unit *was* a change set, so "at close" and "at commit" named the same
  moment. *How a unit is built* broke that: a unit is now six to eight commits, and
  deferring the log to the end means reconstructing all of them from `git log` — which is
  the exact work this file exists to prevent, merely moved later. Measured when the rule
  was changed: U7 had five commits landed across three days and **zero** rows. They were
  recoverable only because the reasoning was still sitting in `tasks/task_list_u7.md`;
  without that, the rows would have said "changed `critic.py`."

  Closing a unit is still a step, but it becomes a **review** of rows that already exist
  rather than a reconstruction — check that each subsection is represented, that findings
  which changed the design are among them, and that the checkpoint column is right.

  This exists because of §6's central sequencing decision. Ordering the build by
  dependency and technical risk instead of by the syllabus calendar is the right call and
  is defended at length there, but it has a cost that decision did not account for: once
  unit order is decoupled from checkpoint order, nothing maps shipped code back to the
  requirement it satisfies. U4 shipped before U2; code feeding Checkpoint 6.1 exists
  before 4.1 and 5.1 are due. Reconstructing that mapping from git history at report time
  is exactly the sort of late, avoidable work the code freeze exists to prevent.

  Three rules keep the file useful as it grows:

  1. **Code changes, not decisions.** Decisions belong in the §7 log and in the per-unit
     sections above. A decision that has not produced code is not a changelog entry.
     Logging both would duplicate the decisions log while diluting the one question this
     file answers — what was built, and for which checkpoint.
  2. **One conceptual change per row, however many files it touched.** A change spanning
     an agent, a state field, and a config entry is one row naming all three. A row per
     file would turn the file into a worse-formatted `git log`.
  3. **`maintenance` is a valid checkpoint value.** Hygiene and defect repair are real
     work; forcing a checkpoint onto them would make the column less trustworthy
     everywhere else.

  **The changelog is a separate file rather than another section here, and the split is
  by kind rather than by length.** This document is the *reasoning* record — why a
  decision was made, what was tested, what turned out to be wrong. The changelog is the
  *chronological* record — what code landed, when, and which checkpoint it serves. Two
  different questions, asked by readers in two different situations. Merging them would
  also mean this document grows a log section on every unit, and it is already long
  enough that new material competes with existing material for attention.

  Written with the change set it describes — not as a later reconciliation pass, which is
  the form of this task that reliably does not happen. When something is backfilled anyway,
  the `date added` column records when the row was written, so a retroactive entry is
  visibly retroactive rather than quietly folded into the original day's record.

- **An evidence artifact must state what its check could have returned had the system
  been behaving well** (added Aug 9, 2026). A verification whose negative result was
  structurally guaranteed proves nothing, however convincing the output looks — and a
  document that overstates its own verification commits exactly the error Transparent
  Degradation exists to prevent, one level up. The corpus-membership check in
  `retrieval_ablation_llm.py` is the worked example: it could never have matched, because
  the id formats are disjoint, and it now prints that fact next to its own result. This
  standard applies to every artifact feeding a checkpoint or the final report, including
  the U8 eval harness.

- **Deferred work is recorded as a tagged `TODO` at the site it affects**, not left in
  conversation. Format is `TODO(<scope>):` where scope is the unit that will address it
  (`U2`, `U5`) or a category (`security`, `geography`), so `grep -rn "TODO(U5)" src/`
  returns that unit's backlog directly. Each states what is missing, why it was
  deferred, and what it would take — a bare `TODO` marks a problem without helping
  anyone act on it. Current inventory:

  | Tag | Location | Item |
  |---|---|---|
  | ~~`TODO(U3)`~~ | `config.py` | ✅ **closed Aug 16, 2026** — decision #8 settled on `nvidia/nemotron-3-nano-30b-a3b` (paid) across four bake-off passes, and `verify_models_live()` guards the IDs at launch |
  | ~~`TODO(U3)`~~ | `extractor.py` | ✅ **closed Aug 16, 2026** — geocoding is called as an ordinary extraction step. The paired fixture update was resolved differently than planned: stubbing the Extractor's outbound calls makes the fixture's address inert, so the "move it to an ungeocodable address" half was unnecessary rather than done |
  | ~~`TODO(U5)`~~ | `state.py`, `build_comps_index.py` | ✅ **closed Aug 22, 2026** — `listed_epoch` indexed and decoded to `Comp.listed_date`. Landed in the same re-index as `location_precision`, since both are metadata changes and a corpus rebuild is the cost either way |
  | ~~`TODO(U5)`~~ | `county_crosswalk.py` | ✅ **moot as of Aug 15, 2026** — the principal-county approximation this described is gone; `county_fips` now resolves the exact county from the subject's coordinates. `FlagKind.COUNTY_FROM_PRINCIPAL_COUNTY` removed rather than left unraisable |
  | ~~`TODO(U7)`~~ | `critic.py` | ✅ **closed Aug 27, 2026** — cross-agent consistency checks built as three *interaction* checks (U7.2) and wired (U7.4); `_consistency_objections()` no longer returns empty. The four checks this named did not survive contact with the built system — see `agents/critic.py` for the accounting |
  | ~~`TODO(U7)`~~ | `critic.py` | ➡️ **became `TODO(U8)` Aug 27, 2026, and closed with the rest at U8.M** — confirming the critical-flag escalation rule was thought to require the tuned weights. It did not: the sweep found the critical weight **inert across its whole range including 0.00**, so the rule's independence is measured rather than contingent, and the confirmation arrived from the opposite direction to the one this row expected |
  | ~~`TODO(U2)`~~ | `hud_fmr.py` | ✅ **cleared Aug 10, 2026** — writes are atomic; the residual concurrency limit is documented on `_DiskCache` as accepted |
  | ~~`TODO(U8)`~~ | — | ✅ **all cleared Aug 31, 2026 at U8.M — nine sites at U8's start, zero now.** Each was replaced by what U8 measured rather than deleted. #6's threshold and weights are **held** on an 80-point sweep (`eval/results/sensitivity.md`) rather than tuned; pass-scoped flags shipped at U8.5; the demo-set county skew **dissolved** when #19's anchor resolved at ZIP tier everywhere; the critical-flag rule is isolated by five golden rows instead of one ablation invocation; the stated-rent threshold closed as **#20** (hold at `None`, do not delete); the rent-comp divergence confirmation and leave-one-metro-out closed at U8.2 and §6 1a. **One thing this row used to claim is corrected rather than carried:** "promoting checks A and B" was one item and is two. Check A closed on its own measurement as #20; **check B was never separately measured or decided** and is now tracked as [OQ-20](../open_questions.md#data--sources) with what closing it would take |
  | `TODO(cut-list)` | `valuation_rent.py` | **One site, down from three (Aug 30, 2026).** Only the descoped LLM rent fallback remains (§6 item 3, taken Aug 21). Model form was **spent** rather than deferred — U11.1 measured three candidates under cross-validation and gradient boosting was adopted; feature engineering, hyperparameter tuning and LOMO were **cut** to §6 item 1a the same day |
  | `TODO(security)` | `hud_fmr.py`, `llm_client.py`, `tracing.py` | Whether to drop on-disk credential fallbacks in favour of env-var-only. **Three sites since Sept 1, 2026** — `tracing.py` inherited the same trade when a LangSmith key first existed (OQ-10) |
  | ~~`TODO(security)`~~ | `diagnostics.py` | ✅ **closed Sept 2, 2026 at U9.M.** The account identifier is redacted from every line this channel prints, in both the JSON-field and bare-token forms, with the status, provider message and remedy hint left intact. **Redaction was taken over the env-gated verbosity switch this row offered as the alternative**, because a switch has to be remembered once before a capture that cannot be edited afterwards, and the run that exposes the identifier is by definition one where something has already gone wrong. Guarded by `tests/test_diagnostics_redaction.py`, including two near-miss cases — an over-broad pattern eats the detail this channel exists for, and fails just as silently |
  | `TODO(geography)` | `county_crosswalk.py`, `config.py` | New England town-based FMR verified for Boston only, not the other five states |
  | ~~`TODO(U9.M)`~~ | `summarizer.py` | ✅ **closed Sept 2, 2026 at M8, the same day it was raised — the shortest-lived row in this table, and that is the point of the format.** The scenario section now names the error band under the figure every row compounds: `staten-island` reads ±$855/mo, **32%** of the estimate, `los-angeles` 18% and `overpriced` 16%. Rendered as one sentence from `subject_metro_mae_dollars` with `model_mae_dollars` behind it, preferring the subject's own market for the same reason the Findings table does. **Language, not calculation** — no scenario is selected differently and no projection moved, which is why all 30 eval rows come back byte-identical and no re-record was needed |

  **Six live sites remain**, all genuinely deferred and none owned by a unit that has
  closed: `security` ×3, `geography` ×2, `cut-list` ×1. Reconciled against
  `grep -rn "TODO(" src/` on Sept 2, 2026.

  **This table drifted twice in one day, and both instances are the argument for the
  grep.** First: the count was unchanged from Aug 31 while the composition moved under it
  — `diagnostics.py` closed and `tracing.py` arrived with the third credential fallback —
  so a table read for its total would have shown nothing happening. Then, hours after that
  reconciliation, a parallel session raised M8 and added the `TODO(U9.M)` above, and the
  table was stale again before the day ended — and the same row closed hours after that,
  moving the count a third time. **None of the three drifts was anyone's oversight**; they
  are what happens to a hand-maintained index of a moving tree, which is why the rule is to
  regenerate this from `grep` at unit close rather than to edit it from memory.

  **This table is reviewed at unit close, and was found stale at U8 planning (Aug 28,
  2026).** It carried two `TODO(U7)` rows as open after U7 shipped, and listed none of the
  nine `TODO(U8)` or three `TODO(cut-list)` sites that existed in the tree. The inventory's
  whole value is that `grep -rn "TODO(U8)" src/` and this table agree; when they do not,
  the table is the one that misleads, because it is the one a reader consults instead of
  grepping. Regenerate it against a grep rather than editing it from memory.

  **A second failure mode, found at U8.M and not covered by that rule.** A `TODO` is not the
  only way this repository defers work — `config.py` marks a value `PROVISIONAL` and names
  the unit that will tune it, and **nothing reconciles those against closed units.** Six
  constants named U4 or U8 as their tuning owner after both had closed, including three that
  decision #5 had actually settled. A marker naming a closed unit reads as scheduled work and
  is really unowned work, which is worse than an honest gap because it looks handled. Grep
  `PROVISIONAL` at unit close alongside `TODO(`.

### Testing

Testing is scoped deliberately rather than exhaustively, and the scope is documented
here so the choice is legible.

**Tests are hermetic; live verification lives in `scripts/`** (added Aug 16, 2026). The
repo already worked this way and had never said so: `pull_fmr_sample.py`,
`pull_geocode_sample.py`, and `verify_county_geometry.py` all make real, unmocked calls
and are deliberately not part of `tests/`. U3 made the rule worth stating, because the
Extractor became the first agent with outbound dependencies on the pipeline's critical
path — a model call, a geocoder, and a 12 MB boundary file.

The split follows from what each artifact is for. A test answers "is our logic correct",
so an external service failing must not change its answer; every outbound call is
stubbed at the boundary, and the node under test runs for real inside them. A
verification script answers "does the integration actually work", where a failure *is*
the finding and must not be hidden behind a mock. Confusing the two produces the worst of
both: a suite that cries wolf when a provider is busy, and integrations nobody has
checked against reality.

Two consequences worth naming. Stubs are not a weaker test here but a sharper one — the
U2 fixture obtained its flags as a side effect of a listing that happened to omit a price
and coordinates that happened to be withheld, whereas each U3 case forces the exact
degradation it names. And the stubbing is autouse rather than opt-in, so a case added
later cannot reach the network by forgetting to ask not to.

Two things are tested unconditionally, because they are the project's load-bearing
claims:

1. **`test_flag_propagation.py`** — a flag raised in the Extractor survives every
   downstream node and appears in the rendered report. Transparent Degradation is the
   central design principle of this system; a silent flag loss would invalidate every
   output the system produces while leaving it looking correct. This test never gets cut.

   **Built in U2: 14 cases**, structured around the ways the guarantee can break rather
   than around the modules implementing it — first-node flag reaching the last node,
   flags from two agents coexisting, the reducer annotations still being present
   (including the negative case: `comps` must *not* have one), every flag rendered in
   full rather than counted, the rework cycle terminating and disclosing that it did,
   and the interrupt pausing and resuming with the reviewer's note in the report.

   **Extended in U3 to 24 cases.** Every degradation path the real Extractor can take is
   now forced and asserted to reach the report: an inferred field disclosed as an
   assumption, retry exhaustion writing no deal terms at all, an unreachable model, each
   of the four geography resolution tiers, the coordinate-conflict threshold *and its
   negative case* — a tolerance that fired on every supplied coordinate would be
   indistinguishable from a tolerance of zero — and the conversion of a transport failure
   into an error the agent can flag rather than an exception that kills the graph.

   Two constraints on the suite are deliberate. It **avoids the Chroma corpus** on every
   case but one: a must-never-fail test should fail only when the thing it tests is
   broken, and a dependency on a built index and a downloadable embedding model would
   let it fail for unrelated reasons. A test that cries wolf stops being consulted. The
   exception is a grounded Los Angeles run that skips cleanly when the index is absent —
   and its role is the same one §2 gives the LA row in the retrieval evidence: a suite
   where every case is degraded cannot show that the degradation signals mean anything.
2. **The `eval/` harness (U8)** — synthetic listings engineered to trigger each named
   flag, run as a batch with results tabulated. This functions as the system's
   behavioral test suite and as its evaluation evidence.

Broad unit-test coverage is **deferred, not dismissed.** With a fixed deadline, coverage
competes directly against the two suites above, and those carry far more information per
hour invested — they test system-level behavior against the design's actual claims
rather than restating implementation details. Additional coverage gets added
retroactively if the buffer week allows. This is a scheduling judgment about sequence,
and it is recorded as such rather than left as an unexplained gap.

### How a unit is built

Adopted Aug 24, 2026, after six units. The two failure modes it exists to prevent were both
observed rather than anticipated: units were reaching implementation on assumptions nobody
had checked, and they were landing as single change sets too large to review in one pass.

1. **Plan before coding.** The unit is decomposed into subsections in
   [`../tasks/`](../tasks/), one file per unit, each subsection scoped to be its own
   change set. Critical
   dependencies and open questions are raised at the *unit* level, naming the subsection
   they block, so they are answered up front rather than discovered mid-implementation.
   The plan is reviewed and approved before any code is written.
2. **Answer the blocking questions first.** A question that would change the design is
   settled — or explicitly deferred with its assumption labelled — before the subsection
   that depends on it starts. This is the same discipline §7's register applies to
   decisions, moved one level earlier.
3. **Land in reviewable pieces.** See *Change management* below.
4. **Log every commit as it lands.** A [`../history/changelog.md`](../history/changelog.md)
   row goes in with the change set, not at the end of the unit — the reasoning is cheap to
   write while it is still live and expensive to reconstruct afterward. See *Change
   management* above.
5. **Close the unit.** Review the changelog rows the unit produced rather than writing them;
   move any decision taken during the build into §7's register with its reasoning in
   [`../history/decision_log.md`](../history/decision_log.md); delete anything from
   [`../open_questions.md`](../open_questions.md) that the unit closed.

**Before a proposed check enters a plan, answer three questions about it.** Added Aug 24,
2026, after U7's planning pass proposed eight consistency checks and measurement killed
six. The pass had verified that each check's *input fields existed* — which establishes
only that the comparison is expressible, not that it is worth making:

1. **Can it fail?** Trace how each input is *populated*, not just that it exists. A field
   assigned directly from the thing it will be compared against cannot diverge from it.
   U7's projection-base check compared `forecast_detail.projection_base_price` to
   `deal_terms.price`, which is the value it is assigned from three lines earlier.
2. **Is it already made?** Grep every *consumer* of the fields, not only their producer.
   Two of U7's proposed checks were already computed and rendered in the Summarizer, and
   one was already raised as a flag by the agent that owns the data.
3. **Would it fire on the clean baseline?** If a check trips on the run that is supposed
   to raise nothing, it is measuring the fixture or the design rather than the deal. This
   question alone caught three of U7's six, and it costs one run to ask.

The general form is the standard this project already applies to evidence — *a check that
cannot fail is not a check* — moved one step earlier, to the plan rather than the result.
Reading a field list is not measurement; running the thing is.

The cost of this is a planning pass per unit. The measured justification for paying it is
in the units that did not have one: U5 discovered mid-build that its training-set size had
never been measured, and U6 disproved two of its own premises after the unit was specified.
Both were caught, but both were caught late, and late is where redesign is expensive.

### Change management

- **One logical change per change set**, self-contained, accompanied by a summary of what
  changed and where the reviewer's attention is most warranted. A unit is decomposed into
  commit-sized subsections in [`../tasks/`](../tasks/) *before* coding starts,
  and each lands on its own. A diff spanning five loosely related files costs more review
  time than the batching saves.
- **Maintenance lands separately from logic.** If a unit stops to extract enums, rename for
  consistency, move constants into `config.py`, or repath documentation, that work gets its
  own change set rather than riding along inside a behavioural one. Mixed diffs are where
  review attention goes to the wrong half.
- **Checking in a temporarily incomplete state is acceptable** when the completing change is
  already planned and named. Smaller, more frequent review beats an integrated whole that
  arrives too large to review carefully.

  Revised Aug 24, 2026, from *"one unit per change set"*. The original optimized for
  batching — fewer, larger reviews. That was the wrong objective: review throughput is the
  binding constraint on this project (§6), and it optimizes the other way. The failure the
  original guarded against was the *unrelated* five-file diff, and that guard is kept; what
  changed is that a unit is no longer assumed to be one related thing.
- **Test and development data should be synthetic or public.** "Public" means openly
  licensed or a public record — Census boundaries, HUD FMR, Redfin's published extracts,
  county assessor data — not merely publicly visible. Scraped listings are the case the
  distinction exists for: visible to anyone, proprietary to their platform, restricted by
  its terms. This is stricter than the program requires, by choice. A deviation gets
  recorded as a decision in §7 rather than taken quietly — decision #11 is the open
  example.

  Revised Aug 16, 2026, from an absolute — *"all test and development data **is**
  synthetic or public"*. Two reasons the norm is the better form. A claim about what the
  repository contains goes false the moment a deliberated exception lands, and a standard
  that lies about its own repo is worse than one that admits an exception and points at
  where it was recorded. And the absolute version stated a prohibition without defining
  the term it turned on: "public" is genuinely ambiguous between *openly licensed* and
  *publicly visible*, and scraped listings sit exactly on that seam. Naming the
  distinction is what the prohibition was doing implicitly, so stating it directly gives
  up nothing and travels better to a reader who was not in the conversation.

