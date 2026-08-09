"""Evidence for Capstone Checkpoint 3.1 (RAG and Retrieval Design Integration).

Produces, from the built system rather than from description, each element the
checkpoint's completion criteria require:

  1. Retrieval integrated against an external data source  -> index stats
  2. Retrieval meaningfully influences output               -> Case A ablation
  3. Key design decisions (source, segmentation, result N)  -> printed inline
  4. A retrieval failure mode and its mitigation            -> Case B, on real data

Three cases, chosen to exercise three distinct behaviours:

  A — Los Angeles: dense. Retrieval clears its threshold on the first pass with no
      flags at all, establishing that the flags below are not simply always-on.
  B — Chicago: moderate. Retrieval falls short initially and relaxes once, raising a
      flag that names precisely what was conceded.
  C — Staten Island: genuinely thin (6 listings in the entire borough). Relaxation is
      exhausted and the loop exits with a sparse-comps flag rather than presenting a
      weak result as a strong one.

Case C corrects an assumption recorded earlier in §2. New York was expected to serve as
the sparse-comps case on the strength of its low borough-wide listing count, but
measurement showed the corpus clusters densely in central Brooklyn — Bedford-Stuyvesant
returns 38 comps within 3 miles. Sparsity in this data is a property of specific
sub-locations, not of the metro. Staten Island is genuinely thin; Bed-Stuy is not.

Run: .venv/bin/python scripts/retrieval_evidence.py
"""

from __future__ import annotations

import statistics
from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents.comps_retrieval import comps_retrieval_agent
from state import DealState, DealTerms
from tools import vector_store

# Subject properties. Coordinates are real locations; the deal terms are synthetic,
# per the program's requirement that no real listing data be used.
SUBJECTS = {
    "A — Los Angeles (dense: expect clean success)": DealTerms(
        full_address="[synthetic] 2-unit duplex, Echo Park, Los Angeles CA",
        price=1_150_000, unit_count=2, bedrooms=2, bathrooms=1.0,
        square_footage=950, city="Los Angeles", state="CA",
        latitude=34.0522, longitude=-118.2437,
    ),
    "B — Chicago (moderate: expect one relaxation)": DealTerms(
        full_address="[synthetic] 2-flat, Logan Square, Chicago IL",
        price=525_000, unit_count=2, bedrooms=2, bathrooms=1.0,
        square_footage=950, city="Chicago", state="IL",
        latitude=41.9227, longitude=-87.6982,
    ),
    "C — Staten Island (thin: expect sparse-comps failure)": DealTerms(
        full_address="[synthetic] 3-unit building, Tottenville, Staten Island NY",
        price=890_000, unit_count=3, bedrooms=2, bathrooms=1.0,
        square_footage=900, city="Staten Island", state="NY",
        latitude=40.5083, longitude=-74.2422,
    ),
}


def run(subject: DealTerms) -> DealState:
    state = DealState(raw_listing_text="[synthetic subject]", deal_terms=subject)
    update = comps_retrieval_agent(state)
    # Apply the partial update the way LangGraph's reducers will: flags accumulate.
    return state.model_copy(update={
        **{k: v for k, v in update.items() if k != "flags"},
        "flags": state.flags + update["flags"],
    })


def comp_rent_estimate(state: DealState) -> float | None:
    """Similarity-weighted mean rent across the retrieved comps.

    Deliberately simple — this is the retrieval checkpoint, not the valuation
    checkpoint. It exists so the effect of retrieval on a downstream number is visible.
    """
    if not state.comps:
        return None
    weights = [c.similarity_score for c in state.comps]
    if sum(weights) <= 0:
        return statistics.mean(c.rent for c in state.comps)
    return sum(c.rent * w for c, w in zip(state.comps, weights)) / sum(weights)


def report(label: str, state: DealState) -> None:
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    print(f"subject            : {state.deal_terms.full_address}")
    print(f"retrieval enabled  : {config.RETRIEVAL_ENABLED}")
    print(f"iterations used    : {state.retrieval_iterations} "
          f"(cap Z={config.MAX_RETRIEVAL_ITERATIONS})")
    if state.retrieval_iterations:
        print(f"final radius       : {state.search_radius_miles:.1f} mi "
              f"(initial X={config.INITIAL_SEARCH_RADIUS_MILES})")
    else:
        print(f"final radius       : n/a — retrieval did not run")
    print(f"comps retrieved    : {len(state.comps)} "
          f"(threshold Y={config.MIN_QUALIFYING_COMPS})")

    est = comp_rent_estimate(state)
    print(f"comp-based rent    : {'$%.0f/mo' % est if est else 'UNAVAILABLE — no comps'}")

    if state.comps:
        print(f"\n  {'listing_id':<14}{'rent':>8}{'beds':>6}{'sqft':>7}{'mi':>7}{'sim':>7}"
              f"  {'source':<16}")
        for c in state.comps[:8]:
            print(f"  {c.listing_id:<14}{c.rent:>8.0f}{c.beds:>6}"
                  f"{c.square_feet:>7.0f}{c.distance_miles:>7.2f}{c.similarity_score:>7.3f}"
                  f"  {c.listing_source or 'unknown':<16}")

        # Source concentration. Eight comps drawn from one aggregator are less
        # independent than eight comps from several, and the report should be able to
        # say so rather than presenting the count alone.
        sources = Counter(c.listing_source or "unknown" for c in state.comps)
        top_source, top_n = sources.most_common(1)[0]
        print(f"\n  comp sources       : {len(sources)} distinct; "
              f"{top_n}/{len(state.comps)} from {top_source}")

    print(f"\n  flags raised ({len(state.flags)}):")
    if not state.flags:
        print("    (none — retrieval met its threshold on the first pass)")
    for f in state.flags:
        print(f"    [{f.severity.upper():<8}] {f.kind}")
        print(f"               {f.detail}")


def main() -> None:
    collection = vector_store.get_collection()
    print("=" * 78)
    print("CHECKPOINT 3.1 — RETRIEVAL EVIDENCE")
    print("=" * 78)
    print("\nDesign decisions (see docs/implementation_plan.md §2):")
    print(f"  data source        : Kaggle apartment rental corpus, Dec 2018 - Dec 2019")
    print(f"  indexed listings   : {collection.count():,} (Chicago, LA, Cleveland, NYC)")
    print(f"  segmentation       : one document per listing, NOT chunked")
    print(f"  embedded text      : title + description + amenities (free text only)")
    print(f"  hard constraints   : bedrooms, geography, sqft band -> metadata filters")
    print(f"  embedding model    : {config.EMBEDDING_MODEL}")
    print(f"  results retrieved  : Y = {config.MIN_QUALIFYING_COMPS} (config.MIN_QUALIFYING_COMPS)")

    for label, subject in SUBJECTS.items():
        report(f"CASE {label}", run(subject))

    # ---- Ablation: identical input, retrieval disabled ----
    print(f"\n\n{'#' * 78}")
    print("# ABLATION — same subject, retrieval disabled")
    print(f"{'#' * 78}")
    ablation_label = "A — Los Angeles (dense: expect clean success)"
    config.RETRIEVAL_ENABLED = False
    try:
        ungrounded = run(SUBJECTS[ablation_label])
        report("A — Los Angeles, RETRIEVAL DISABLED", ungrounded)
    finally:
        config.RETRIEVAL_ENABLED = True

    print(f"\n{'=' * 78}")
    print("Interpretation: with retrieval enabled the estimate is derived from real,")
    print("citable listings near the subject. With it disabled the pipeline has no")
    print("grounded basis for a rent figure at all — the failure Checkpoint 2.1")
    print("identified as 'fabricated grounding presented at full confidence'.")
    print("=" * 78)


if __name__ == "__main__":
    main()
