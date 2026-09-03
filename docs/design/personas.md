**§9 of the plan of record — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#22) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the decisions register in §7,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

## Personas, journeys, and the escalation routing rule

**Settled Aug 31, 2026 by the architect, at U9.2.** No persona, user journey, or
intended-user definition existed anywhere in this repository before this document; it was
skipped, not documented elsewhere. Checkpoint 7.1 asks for "the intended user" directly,
so this is a report input as much as a design one, and
[`tasks/task_list_u9.md`](../tasks/task_list_u9.md) §U9.2 carries the full reasoning this
document was built from.

### The four personas

| | Persona | Relationship to the system | Reads |
| --- | --- | --- | --- |
| **a** | **IT / operations** | Confirms the system is working as intended | Eval batches, logs, traces — never an individual deal |
| **b** | **Real-estate agent** — *the core internal user* | Reviews deals before they reach an investor | The full report, including its evidence |
| **c** | **Investor** — *the external customer* | Holds capital, makes the buy decision | The recommendation and the figures behind it |
| **d** | **Another agent** — *future, unsupported today* | Calls this system for an evaluation on a human's behalf | The state object, via a protocol |

**(a)** never opens a report. Their evidence is the evaluation harness
(`src/eval/results/`), the flag-coverage census it produces, and whatever tracing is
configured (`tools/tracing.py`) — the question they're answering is "is the system
behaving the way it's supposed to," not "is this deal good."

**(b)** is who `agents/human_review.py`'s pause is written for. They read the report the
Summarizer produces in full, including every disclosure, because their job is to decide
whether the deal — and the system's own evidence about it — is ready to go in front of
(c).

**(c)** reads the least and needs the most legible surface: the recommendation, the
headline figures, and enough of the reasoning behind them to trust or challenge it. They
are the audience §8's "no internal vocabulary" rule is written for — a flag kind, a
`config` constant, a unit number means nothing to them, and reader-facing text has to
carry the reasoning in plain words instead.

**(d) is not speculative, and it's worth saying why.** The MCP reference server
(`mcp_server.py`, decision #13) already exposes this project's read-only tools — the HUD
FMR client and the Redfin appreciation series — to an external host. The unbuilt half is
the inverse of that: exposing *the evaluation itself*, the full seven-agent pipeline, as a
callable capability another agent could invoke on a human's behalf. Naming that as the
concrete next step is a stronger answer to "what's next" than a generic "future work"
line, precisely because half of the plumbing for it is already built and tested.

### Escalation routes by flag type — not to one desk

**Chosen over routing every escalation to persona (b), because it is what the flags
already mean.** A geocoder outage and a sparse comp set both lower the Critic's
confidence score the same way and can both pause a deal at `human_review`, but they call
for different people to look at the pause:

- **Infrastructure flags → (a) IT.** The geocoder was unreachable, the extraction model
  was unreachable, no rent index or growth series covers this county. Nothing about the
  deal is in question — the system could not do its job, and re-running the same deal
  once the resource is back may be all that's needed.
- **Deal-substance flags → (b) the agent.** Sparse comps, a comp set widened onto a
  different kind of unit, a rent estimate that diverges from its own cross-check. The
  system worked correctly and found something in this specific deal a person should
  judge.

This needed a routing rule rather than a note in the Summarizer, because it changes what
the human-review payload says: `agents/human_review.py`'s `interrupt()` now names which
desk (or desks) a pause is waiting on, derived from the *kinds* of flag that caused the
escalation — `state.desk_of`, beside `state.scope_of` which already does the analogous
classification for whether a disclosure is about this property or its market (U8.6d).
Both are judgment calls made once, at the vocabulary, rather than re-derived per message —
see `state.py`'s `_INFRASTRUCTURE_KINDS` for the classification and the caveats it
documents (a handful of flag kinds cover more than one underlying cause, and the kind-level
split does not perfectly separate them — the same limitation `scope_of` already accepts).

The desk names surface in the `interrupt()` payload's `waiting_on` field, read by whoever
resumes the pause (`main.py` today; a person via a note box once
[`tasks/task_list_u9.md`](../tasks/task_list_u9.md) §U9.7's Streamlit surface exists) —
not in the rendered report. The report is generated *after* the pause resolves, for
persona (c) rather than (a)/(b), and a desk name is exactly the kind of internal routing
detail §8 says reader-facing text should not carry.

### What this document does not settle

**The two axes a report conflates — "can the system stand behind its own numbers" versus
"is this a good deal" — are a report-rendering question, not a routing one, and are
designed at [`tasks/task_list_u9.md`](../tasks/task_list_u9.md) §U9.4, not here.** They
share a premise with this document (a reader needs to know *what kind* of escalation
they're looking at before they can act on it) but touch a different surface: this document
is about who a pause is routed to before a report exists; §U9.4 is about what the finished
report says to persona (c) once one does.
