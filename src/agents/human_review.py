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

**Where the review goes.** Straight on to the Summarizer, never around it. A deal that
needed human judgement still produces a report, and that report still carries every
flag that caused the escalation plus the reviewer's own note. Routing a reviewed deal
past the Summarizer would mean the one case most in need of a written record is the
only case that produces none.
"""

from __future__ import annotations

from langgraph.types import interrupt

from state import DealState, DealStatus, Severity

AGENT = "human_review"


def human_review_node(state: DealState) -> dict:
    """Node function: pauses the graph and returns a partial update on resume."""
    reviewer_note = interrupt(
        {
            "reason": "Confidence below threshold or rework budget exhausted.",
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
