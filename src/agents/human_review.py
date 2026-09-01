"""Human-review escalation — the graph's `interrupt()` node.

Not a specialist agent, which is why §4's tree did not originally list it: it makes no
estimate and reaches no conclusion. It is the point where the system stops and says the
machine should not be the last word on this deal. §3 names `interrupt()` as one of the
two strongest reasons LangGraph was adopted, and Checkpoint 6.1 is about exactly this
capability, so it is wired into the skeleton from the first graph rather than added
later against a system that never had a pause in it.

**How the pause works.** `interrupt()` raises out of the node, LangGraph persists the
run to the checkpointer, and `invoke` returns with an `__interrupt__` payload instead of
a finished state. Nothing is lost and nothing is re-run: a later
`invoke(Command(resume=...), same_thread_id)` restarts *this node* with the reviewer's
input as `interrupt()`'s return value and continues from there. This is the behaviour
that requires a checkpointer and a `thread_id` — without them the pause has nowhere to
live (`graph.py` supplies both).

**What is surfaced.** The payload carries the reasons for escalation, not the whole
state object: the confidence score, every flag at warn or critical, and any unanswered
clarifying questions. A reviewer needs the grounds for the decision they are being
asked to make. Dumping full state would bury those under fields they cannot act on.

**Which desk it's waiting on (U9.2).** Not every escalation calls for the same reader.
A geocoder outage and a sparse comp set both lower confidence the same way, but the
first means the system couldn't do its job and the second means it did its job and
found something a person should weigh — see `docs/design/personas.md` for the full
routing rule and the personas it names. `_routing_desks` derives the desk(s) from the
flag *kinds* that caused this escalation (`state.desk_of`, alongside `state.scope_of`
above it), and the payload's `waiting_on` names them in plain language rather than
leaving a reader to infer it from the flag list.

**Where the review goes.** Straight on to the Summarizer, never around it. A deal that
needed human judgement still produces a report, and that report still carries every
flag that caused the escalation plus the reviewer's own note. Routing a reviewed deal
past the Summarizer would mean the one case most in need of a written record is the
only case that produces none.
"""

from __future__ import annotations

from langgraph.types import interrupt

from state import DealState, DealStatus, FlagKind, ReviewDesk, Severity, desk_of

AGENT = "human_review"

# Escalation-mechanism kinds carry no diagnostic content of their own — they say "the
# pipeline decided to escalate," not why. Excluded from desk routing for the same reason
# `agents/critic.py`'s `_DERIVED_KINDS` excludes them from the confidence score: counting
# a consequence flag as its own cause would blur a purely infrastructure escalation (a
# geocoder outage on its own) into a false "mixed" reading.
_ROUTING_EXCLUDED_KINDS = frozenset(
    {FlagKind.LOW_CONFIDENCE_ESTIMATE, FlagKind.REWORK_LIMIT_REACHED}
)

# Plain-language labels for the interrupt payload — see `docs/design/personas.md` for
# the personas these name and the reasoning behind the routing rule.
_DESK_LABEL = {
    ReviewDesk.IT: (
        "IT / operations — a system resource this run needed (a service, a model, a "
        "market's data) was unavailable, and nothing about the deal itself is in "
        "question"
    ),
    ReviewDesk.REAL_ESTATE_AGENT: (
        "the reviewing real-estate agent — the system ran to completion and found "
        "something in this specific deal that needs a person's judgment"
    ),
}


def _routing_desks(state: DealState) -> list[ReviewDesk]:
    """Which desk(s) this escalation is waiting on, from the flags that caused it.

    IT-desk kinds are named first when both are present: an infrastructure gap is the
    one thing a reviewer cannot act around regardless of what else the deal shows.
    """
    kinds = {
        f.kind
        for f in state.flags
        if f.severity in (Severity.WARN, Severity.CRITICAL)
        and f.kind not in _ROUTING_EXCLUDED_KINDS
    }
    present = {desk_of(kind) for kind in kinds}
    order = (ReviewDesk.IT, ReviewDesk.REAL_ESTATE_AGENT)
    return [desk for desk in order if desk in present]


def human_review_node(state: DealState) -> dict:
    """Node function: pauses the graph and returns a partial update on resume."""
    desks = _routing_desks(state) or [ReviewDesk.REAL_ESTATE_AGENT]
    reviewer_note = interrupt(
        {
            "reason": "Confidence below threshold or rework budget exhausted.",
            "waiting_on": [_DESK_LABEL[desk] for desk in desks],
            "confidence_score": state.confidence_score,
            "address": state.deal_terms.full_address,
            "unanswered_questions": state.clarifying_questions,
            "flags": [
                {"kind": f.kind, "severity": f.severity, "detail": f.detail}
                for f in state.flags
                if f.severity in (Severity.WARN, Severity.CRITICAL)
            ],
        }
    )

    # `status` is set to needs_review and left that way even though the run continues to
    # a report. The report is the record of a reviewed deal, not evidence that the deal
    # cleared review on its own — overwriting the status at the Summarizer would erase
    # the distinction between "the system was confident" and "a human signed off".
    return {
        "status": DealStatus.NEEDS_REVIEW,
        "human_review_note": str(reviewer_note) if reviewer_note is not None else None,
    }
