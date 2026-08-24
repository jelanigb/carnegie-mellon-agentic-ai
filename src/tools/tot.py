"""Beam search over an enumerated hypothesis space (§7 decisions #12, #14).

The search half of this project's Tree-of-Thought work, kept separate from the domain
logic that uses it. Two consumers by design: the Scenario/Forecast agent (U6) and the
Critic's cross-agent consistency checks (U7, decision #12).

**Candidates are enumerated, not sampled, and that is a measured choice rather than a
simplification.** The Tree-of-Thought paper offers two ways to produce thoughts - sample
them i.i.d. from a chain-of-thought prompt when the space is rich, or *propose* them
when the space is constrained enough that sampling mostly returns duplicates. U6's space
is the constrained case and small enough to write down: four framings (two rent
treatments x two price treatments x one appreciation series), then nine band pairings
under each. Asking a model for five hypotheses over a four-point space would make it
invent growth rates, and every figure in this system has to trace to a measured source.

Three consequences follow, all of them improvements:

  * **Nothing is sampled, so nothing is invented.** The model's job is to *judge*
    enumerated options, not to produce numbers.
  * **The branching factor is data-determined** rather than tuned. It is a property of
    how many treatments the evidence supports, not a knob.
  * **The pipeline stays deterministic end to end.** `config.TOT_TEMPERATURE` exists for
    a sampling step this design does not have; the evaluator scores at
    `config.LLM_TEMPERATURE` (0.0) like every other node.

**Pruning is recorded, never silent.** Every candidate leaves a ledger row whether it
survived or not, because the failure this design most needs to defend against is an
evaluator that systematically undervalues a correct-but-unusual branch: it produces
confident, well-formed, wrong output and looks exactly like one working properly. U2
already produced a defect of that shape (a critical flag landing confidence at exactly
0.60, and `0.60 < 0.60` is false), which is the precedent this guards against one layer
up.

This module holds no domain knowledge. It does not know what a forecast is; it takes an
expander, a hard-constraint check, and a scorer, and runs the beam.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


@dataclass(frozen=True)
class Candidate:
    """One hypothesis, plus what the search concluded about it.

    `payload` is whatever the caller's domain needs - this module never inspects it.
    `summary` is the one-line description that reaches the report, so it is written for
    a reader rather than for a log.
    """

    id: str
    depth: int
    payload: Any
    summary: str
    parent: Optional[str] = None
    score: Optional[float] = None
    prune_reason: Optional[str] = None

    @property
    def survived(self) -> bool:
        return self.prune_reason is None


@dataclass
class SearchResult:
    """Survivors, the full ledger, and the two numbers the report needs about the run."""

    survivors: list[Candidate] = field(default_factory=list)
    ledger: list[Candidate] = field(default_factory=list)
    depth_reached: int = 0
    # Gap between the best and second-best final scores. Below `TOT_TIE_EPSILON` the
    # selection was near-arbitrary and the caller is expected to disclose that.
    top_two_score_gap: Optional[float] = None
    # The same gap per level. Depth 1's matters on its own: a near-tie there means the
    # whole forecast rests on a near-arbitrary reading of the data, which is a larger
    # claim than two scenarios scoring alike.
    score_gap_by_depth: dict[int, float] = field(default_factory=dict)
    # Set when the beam emptied. Not a failure - it means no hypothesis survived contact
    # with the data, which is a reportable finding rather than a reason to lower the bar.
    exhausted_reason: Optional[str] = None

    @property
    def n_pruned(self) -> int:
        return sum(1 for c in self.ledger if not c.survived)


# Expand one level: given the surviving parents (empty at depth 1), return the
# candidates for this depth. The caller enumerates; this module never generates.
Expander = Callable[[int, Sequence[Candidate]], list[Candidate]]

# Return a prune reason for a candidate that violates a hard constraint, or None to let
# it through to scoring. Runs before any model call because it is free and decisive.
HardCheck = Callable[[Candidate], Optional[str]]

# Score a whole level at once, returning one (score, rationale) per candidate. Batched
# rather than per-candidate so a level costs one model call instead of `b` of them.
Scorer = Callable[[int, Sequence[Candidate]], Sequence[tuple[float, str]]]


def beam_search(
    expand: Expander,
    hard_check: HardCheck,
    score: Scorer,
    beam_width: int | dict[int, int] = config.TOT_BEAM_WIDTH,
    max_depth: int = config.TOT_MAX_DEPTH,
    prune_threshold: float | dict[int, float] = config.TOT_PRUNE_THRESHOLD,
    tie_epsilon: float = config.TOT_TIE_EPSILON,
    conservatism_key: Optional[Callable[[Candidate], float]] = None,
) -> SearchResult:
    """Run the beam, recording every candidate's fate.

    Beam search rather than BFS or DFS, per decision #12. BFS over the full space costs
    evaluations the budget does not justify for a three-output forecast; DFS commits to
    a framing before comparing it against the alternatives, which reintroduces exactly
    the premature commitment Tree-of-Thought is here to prevent. Beam keeps cross-branch
    comparison at every level at a cost bounded by `beam_width x` the enumeration.

    `beam_width` accepts a per-depth mapping, because the levels are not the same kind
    of decision. U6 keeps **one** framing but **three** pairings: the framing is which
    treatment of the data the whole forecast rests on, and carrying three of those
    forward would produce three scenarios resting on different treatments, which are not
    commensurable and cannot share one provenance statement. All candidates at a level
    are still scored and compared before the cut — that comparison is the search; the
    width only controls how many survive it.

    `prune_threshold` is per-depth for the same reason. A threshold answers "did this
    hypothesis survive contact with the data?", which is a real question about a pairing
    and a category error about a framing: framings are enumerated from the treatments the
    evidence actually supports, so every one of them is defensible by construction and
    the level's job is to *select*, not to filter. U6 therefore sets depth 1 to 0.0. Left
    uniform, an evaluator applying general skepticism scored all four Los Angeles framings
    below 0.40 and emptied the beam on a deal with both series fully available.

    `conservatism_key` breaks ties. Scores within `tie_epsilon` are treated as equal, and
    the more conservative candidate wins - for an investment tool the cost of being wrong
    is asymmetric, and a coin flip between two hypotheses is a decision the system should
    not make silently. The caller still gets `top_two_score_gap` so it can disclose that
    the tie happened.
    """
    result = SearchResult()
    parents: list[Candidate] = []
    width_for = (
        (lambda d: beam_width.get(d, config.TOT_BEAM_WIDTH))
        if isinstance(beam_width, dict)
        else (lambda d: beam_width)
    )
    threshold_for = (
        (lambda d: prune_threshold.get(d, config.TOT_PRUNE_THRESHOLD))
        if isinstance(prune_threshold, dict)
        else (lambda d: prune_threshold)
    )

    for depth in range(1, max_depth + 1):
        candidates = expand(depth, parents)
        if not candidates:
            # A level with nothing to expand is the natural end of an enumerated
            # search, not an error: depth 3 exists to reconcile, and there is nothing
            # to reconcile if depth 2 already produced the final set.
            break

        result.depth_reached = depth

        # Free checks first. A candidate that violates a hard constraint never reaches
        # the model, which is both cheaper and more defensible than asking a model to
        # rediscover arithmetic.
        live: list[Candidate] = []
        for candidate in candidates:
            reason = hard_check(candidate)
            if reason is None:
                live.append(candidate)
            else:
                result.ledger.append(replace(candidate, prune_reason=reason))

        if not live:
            result.exhausted_reason = (
                f"Every candidate at depth {depth} failed a hard constraint, so the "
                f"search has nothing left to score. No hypothesis survived contact with "
                f"the data."
            )
            result.survivors = []
            return result

        scored = [
            replace(candidate, score=value, summary=rationale or candidate.summary)
            for candidate, (value, rationale) in zip(live, score(depth, live))
        ]

        threshold = threshold_for(depth)
        below = [c for c in scored if (c.score or 0.0) < threshold]
        above = [c for c in scored if (c.score or 0.0) >= threshold]
        for candidate in below:
            result.ledger.append(
                replace(
                    candidate,
                    prune_reason=(
                        f"Scored {candidate.score:.2f}, below the "
                        f"{threshold:.2f} threshold this project requires before "
                        f"a hypothesis is carried forward."
                    ),
                )
            )

        if not above:
            result.exhausted_reason = (
                f"Every candidate at depth {depth} scored below the "
                f"{threshold:.2f} threshold. The beam is empty, which is a finding "
                f"about the evidence rather than a reason to lower the bar."
            )
            result.survivors = []
            return result

        width = width_for(depth)
        ranked = _rank(above, tie_epsilon, conservatism_key)
        survivors, cut = ranked[:width], ranked[width:]
        for candidate in cut:
            result.ledger.append(
                replace(
                    candidate,
                    prune_reason=(
                        f"Scored {candidate.score:.2f}, outside the top {width} at "
                        f"this level."
                    ),
                )
            )
        result.ledger.extend(survivors)

        if len(ranked) >= 2:
            gap = (ranked[0].score or 0.0) - (ranked[1].score or 0.0)
            result.top_two_score_gap = gap
            result.score_gap_by_depth[depth] = gap

        parents = survivors

    result.survivors = parents
    return result


def _rank(
    candidates: list[Candidate],
    tie_epsilon: float,
    conservatism_key: Optional[Callable[[Candidate], float]],
) -> list[Candidate]:
    """Sort by score, resolving near-ties toward the more conservative candidate.

    Two candidates within `tie_epsilon` are not meaningfully distinguished by the
    evaluator, so ordering them by score would be reading signal out of noise. Sorting
    the tied group by `conservatism_key` makes the resolution a stated policy instead.
    """
    ordered = sorted(candidates, key=lambda c: -(c.score or 0.0))
    if conservatism_key is None:
        return ordered

    resolved: list[Candidate] = []
    group: list[Candidate] = []
    for candidate in ordered:
        if group and abs((group[0].score or 0.0) - (candidate.score or 0.0)) > tie_epsilon:
            resolved.extend(sorted(group, key=conservatism_key))
            group = []
        group.append(candidate)
    resolved.extend(sorted(group, key=conservatism_key))
    return resolved
