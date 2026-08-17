**Part of the plan of record — see [`implementation_plan.md`](implementation_plan.md) §8.**

## 8. Engineering Standards

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

These are the standards every change set is held to in review. They are recorded here
rather than left implicit so that the bar is the same whether a given unit is written
in a focused session or across a fragmented week.

### Architecture

- **Follow the design conventions in §3**: node functions returning *partial* state
  updates, no agent-to-agent calls, a single typed state object, flags and retries
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

- **Every unit closes by appending to `docs/changelog.md`** (added Aug 10, 2026). A `##`
  heading per date the work was done, and beneath it a table of
  `date added | unit | work done | related checkpoint`.

  This exists because of §6's central sequencing decision. Ordering the build by
  dependency and technical risk instead of by the syllabus calendar is the right call and
  is defended at length there, but it has a cost that decision did not account for: once
  unit order is decoupled from checkpoint order, nothing maps shipped code back to the
  requirement it satisfies. U4 shipped before U2; code feeding Checkpoint 6.1 exists
  before 4.1 and 5.1 are due. Reconstructing that mapping from git history at report time
  is exactly the sort of late, avoidable work the Week 7 freeze exists to prevent.

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

  Written as part of finishing the unit, alongside the updates to this document — not as
  a later reconciliation pass, which is the form of this task that reliably does not
  happen. When something is backfilled anyway, the `date added` column records when the
  row was written, so a retroactive entry is visibly retroactive rather than quietly
  folded into the original day's record.

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
  | `TODO(U5)` | `state.py`, `build_comps_index.py` | Index the `time` column so `Comp.listed_date` allows per-row FMR normalization |
  | ~~`TODO(U5)`~~ | `county_crosswalk.py` | ✅ **moot as of Aug 15, 2026** — the principal-county approximation this described is gone; `county_fips` now resolves the exact county from the subject's coordinates. `FlagKind.COUNTY_FROM_PRINCIPAL_COUNTY` removed rather than left unraisable |
  | `TODO(U7)` | `critic.py` | Cross-agent consistency checks — `_consistency_objections()` returns empty until then |
  | `TODO(U7)` | `critic.py` | Confirm the critical-flag escalation rule when the severity weights are tuned (§6, finding 1) |
  | ~~`TODO(U2)`~~ | `hud_fmr.py` | ✅ **cleared Aug 10, 2026** — writes are atomic; the residual concurrency limit is documented on `_DiskCache` as accepted |
  | `TODO(security)` | `hud_fmr.py`, `llm_client.py` | Whether to drop on-disk credential fallbacks in favour of env-var-only |
  | `TODO(security)` | `diagnostics.py` | Full error text to stdout deliberately includes the account identifier the report strips. Correct for a terminal, wrong for a recording — and Week 7's deliverable is a terminal capture. Redact that one field, or gate verbosity behind an env var defaulting quiet before recording |
  | `TODO(geography)` | `county_crosswalk.py` | New England town-based FMR verified for Boston only, not the other five states |

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

### Change management

- **One unit per change set**, self-contained, accompanied by a summary of what changed
  and where the reviewer's attention is most warranted. A diff spanning five loosely
  related files costs more review time than the batching saves.
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

