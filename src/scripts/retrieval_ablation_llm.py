"""Checkpoint 3.1 evidence: what the system produces with *no* retrieval at all.

Companion to scripts/retrieval_evidence.py. That script measures retrieval working;
this one measures the alternative it was chosen over.

Why this exists
---------------
Checkpoint 2.1 justified retrieval against one named failure: "fabricated grounding
presented at full confidence" — a model asked for comps "would likely generate
addresses, square footages, and rents that are plausible for that market and are not
real," then compute a valuation from them and report it without qualification.

The config-flag ablation in retrieval_evidence.py does not actually demonstrate that.
Setting RETRIEVAL_ENABLED=False makes the retrieval node return zero comps, so the
pipeline degrades to "no estimate available" — an *absence*, not a fabrication. That is
the designed behaviour and it is the right behaviour, but it means the fabrication claim
was inherited from 2.1 as an argument rather than observed as a result.

This script observes it. The model is asked for comparable listings for the same subject
property used in Case A, with no retrieval and no corpus access, and is asked to fill
**the same schema the real retrieval path fills** — listing_id, source, and all. Every
identifier it returns is then looked up in the Chroma collection. The question "does this
comp exist?" therefore gets a checked answer rather than an asserted one.

Model selection note (decision #8, docs/implementation_plan.md §7)
-----------------------------------------------------------------
**As of Aug 9, 2026**, when this script was written, `config.MODEL_*` still held the
unverified placeholders that `TODO(U3)` warned about, and that TODO turned out to be
correct: `meta-llama/llama-3.3-70b-instruct:free` no longer exists on OpenRouter's free
tier (the model is present, but paid-only; there is no free Llama variant at all). Rather
than silently repoint config.py — §8 requires decisions of that kind to be raised, not
resolved by assumption — the models used here are named locally and verified live at run
time.

**That premise closed on Aug 16, 2026 and this note is kept as history, corrected to the
past tense (Aug 28, 2026).** Decision #8 settled `config.MODEL_*` on a real model across
four bake-off passes and `verify_models_live()` now guards the IDs at launch, so the
sentence above described the tree accurately when written and stopped doing so a week
later. The local model names are **not** changed to follow config: this script's ablation
runs two models of deliberately different sizes, which is a property of the experiment
rather than of the pipeline's model choice.

Two are run, not one, and deliberately of different sizes. A single small model
fabricating is weak evidence, since it invites the reply that a better model would not.

Run: .venv/bin/python scripts/retrieval_ablation_llm.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, Field

import config
from scripts.retrieval_evidence import SUBJECTS, comp_rent_estimate, run
from state import DealTerms
from tools import diagnostics, vector_store
from tools.llm_client import LlmClient, LlmError, SchemaValidationExhausted

# Verified live against https://openrouter.ai/api/v1/models on Aug 9, 2026. Both
# responded to a smoke call. Sized differently on purpose (see module docstring).
#
# **Deliberately still `:free`, and deliberately not repointed** when decision #8 moved
# the rest of the build to paid variants on Aug 16, 2026. The Checkpoint 3.1 result this
# script produced — 0 of 16 returned comps existing in the corpus, rent dispersion
# collapsing from CV 19.7% to 3.1%/4.3% — is quoted in the plan and the report as a
# measurement of *these two models*. Swapping them would leave a documented figure that
# no runnable code reproduces, which is a worse outcome than an ablation that is
# occasionally rate-limited.
#
# Consequence worth knowing before re-running: `:free` variants are served from
# provider-shared pools, so a re-run can 429 where the original did not. That is an
# availability property of the tier, not a change in the finding (see decision #8's
# detail in §7). Re-run rather than repoint.
MODELS = [
    ("openai/gpt-oss-20b:free", "20B"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "120B"),
]

# Case A from retrieval_evidence.py. Using the identical subject is what makes this an
# ablation rather than a separate demo — the only variable that changes is whether the
# comps came from the corpus or from the model.
SUBJECT_KEY = "A — Los Angeles (dense: expect clean success)"


class LlmComp(BaseModel):
    """Deliberately mirrors state.Comp's citable fields.

    listing_id and source are requested because the real path supplies them and because
    they are what makes a comp checkable. Asking the model for them is not entrapment:
    it is asking for exactly what the schema the system actually uses requires.
    """

    listing_id: str = Field(description="Identifier of the source listing")
    source: str = Field(description="Originating site or feed for this listing")
    address: str
    rent: float
    beds: int
    baths: float
    square_feet: float
    distance_miles: float


class LlmCompSet(BaseModel):
    comps: list[LlmComp]
    rent_estimate: float = Field(description="Estimated monthly rent for the subject")
    confidence: str = Field(description="Your confidence in this estimate: low, medium, or high")


# Phrased the way the ungrounded system would phrase it, mirroring Loop 2's framing from
# Checkpoint 2.1 minus the datastore. No instruction to invent, and none to refrain —
# adding either would be putting the result in the model's mouth.
PROMPT_SYSTEM = (
    "You are an experienced real-estate agent preparing a rental comparables analysis "
    "for an investor."
)


def build_prompt(subject: DealTerms) -> str:
    return (
        f"Find {config.MIN_QUALIFYING_COMPS} comparable rental listings for this "
        f"subject property and estimate its monthly rent.\n\n"
        f"Subject property:\n"
        f"  location   : {subject.city}, {subject.state}\n"
        f"  coordinates: {subject.latitude}, {subject.longitude} (Echo Park)\n"
        f"  bedrooms   : {subject.bedrooms}\n"
        f"  bathrooms  : {subject.bathrooms}\n"
        f"  square feet: {subject.square_footage}\n\n"
        f"For each comparable, give its listing id, the source site it came from, its "
        f"address, monthly rent, beds, baths, square footage, and its distance in miles "
        f"from the subject property."
    )


def verify_against_corpus(comps: list[LlmComp], collection) -> dict[str, bool]:
    """Look up each returned listing_id in the Chroma collection.

    Read the scope of this check carefully; it is narrower than it first appears.

    It answers exactly one question: **is this comp a record in the system's evidence
    base?** That is the question that matters for grounding, because the corpus is the
    only comp source the pipeline has — a comp not in it cannot have been retrieved and
    cannot be cited. For every ungrounded run to date the answer is no for every comp.

    It does **not** establish that the property does not exist in the world, and on its
    own it is weak evidence of invention: corpus ids are uniformly 10-digit numerals
    (verified — `id` is all-numeric, length 10, across the whole extract), while the
    models return ids like `LA001` and `ECHO12345`. Those can never match, so a null
    result here is structurally guaranteed rather than earned. `id_format_matches_corpus`
    below makes that limitation visible in the output instead of leaving a reader to
    infer more from the lookup than it supports.

    Address cross-checking is not a usable second signal either: the corpus `address`
    column is ~95% null for Los Angeles, so absence there means nothing.

    What actually establishes invention is argued in the write-up, not here: no
    resolvable citation (brand name, no URL, no id that resolves on the named site),
    self-evidently synthetic id and street-number patterns, and the rent-dispersion
    collapse measured in the summary.
    """
    found: dict[str, bool] = {}
    for c in comps:
        try:
            hit = collection.get(ids=[str(c.listing_id)])
            found[c.listing_id] = bool(hit["ids"])
        except Exception as exc:  # noqa: BLE001 — a malformed id is a result, not a bug
            # Recorded rather than swallowed for the reason §8 added the
            # "state what the check could have returned" standard, and this is the exact
            # artifact that prompted it: a lookup failing for a *mechanical* reason
            # would otherwise be counted as evidence of fabrication.
            diagnostics.log_exception(
                f"retrieval_ablation_llm: corpus lookup for id {c.listing_id!r} raised; "
                f"scoring it as not-found",
                exc,
            )
            found[c.listing_id] = False
    return found


def id_format_matches_corpus(listing_id: str) -> bool:
    """Could this id match a corpus record at all, ignoring whether it does?

    Corpus ids are 10-digit numerals without exception. An id failing this test was
    never a candidate for a match, which is what keeps the lookup above from being
    over-read as proof of fabrication.
    """
    return listing_id.isdigit() and len(listing_id) == 10


def report_llm_run(model: str, label: str, result: LlmCompSet, attempts: int, collection) -> dict:
    print(f"\n{'=' * 78}")
    print(f"UNGROUNDED — {model}  ({label})")
    print(f"{'=' * 78}")
    print(f"schema attempts    : {attempts} (cap {config.MAX_EXTRACTION_RETRIES})")
    print(f"comps returned     : {len(result.comps)}")
    print(f"rent estimate      : ${result.rent_estimate:,.0f}/mo")
    print(f"stated confidence  : {result.confidence}")

    verified = verify_against_corpus(result.comps, collection)
    real = sum(verified.values())
    well_formed = sum(id_format_matches_corpus(c.listing_id) for c in result.comps)

    print(f"\n  {'listing_id':<20}{'rent':>8}{'beds':>6}{'sqft':>7}{'mi':>7}  "
          f"{'source':<18}{'id fmt ok?':<12}{'in corpus?':<12}")
    for c in result.comps:
        mark = "YES" if verified[c.listing_id] else "NO"
        fmt = "yes" if id_format_matches_corpus(c.listing_id) else "no — cannot match"
        print(f"  {c.listing_id[:19]:<20}{c.rent:>8.0f}{c.beds:>6}{c.square_feet:>7.0f}"
              f"{c.distance_miles:>7.2f}  {c.source[:17]:<18}{fmt:<12}{mark:<12}")

    print(f"\n  addresses returned (no URL or resolvable id was supplied for any):")
    for c in result.comps:
        print(f"    {c.address}")

    print(f"\n  IN EVIDENCE BASE   : {real} / {len(result.comps)}")
    print(f"  ids that could even match corpus format: {well_formed} / {len(result.comps)}"
          f"  <- when 0, the line above is structural, not earned")
    print(f"  flags raised       : 0 — the model has no mechanism for raising one")

    return {
        "model": model,
        "label": label,
        "n_comps": len(result.comps),
        "n_verifiable": real,
        "rent_estimate": result.rent_estimate,
        "confidence": result.confidence,
    }


def main() -> None:
    subject = SUBJECTS[SUBJECT_KEY]
    collection = vector_store.get_collection()

    print("=" * 78)
    print("CHECKPOINT 3.1 — ABLATION: UNGROUNDED (NO RETRIEVAL) vs. GROUNDED")
    print("=" * 78)
    print(f"\nsubject            : {subject.full_address}")
    print(f"corpus available   : {collection.count():,} listings "
          f"(NOT used by the ungrounded runs below)")
    print(f"temperature        : {config.LLM_TEMPERATURE} (deterministic)")

    # ---- Ungrounded: the model answers from its weights alone ----
    summaries = []
    for model, label in MODELS:
        client = LlmClient()
        try:
            result, attempts = client.call_with_schema(
                prompt=build_prompt(subject),
                schema=LlmCompSet,
                model=model,
                system=PROMPT_SYSTEM,
            )
        except (LlmError, SchemaValidationExhausted) as exc:
            print(f"\n{model}: could not produce schema-valid output — {exc}")
            continue
        summaries.append(report_llm_run(model, label, result, attempts, collection))

    # ---- Grounded: the same subject through the real retrieval path ----
    grounded = run(subject)
    grounded_est = comp_rent_estimate(grounded)

    print(f"\n{'=' * 78}")
    print("GROUNDED — Chroma retrieval over the Kaggle corpus")
    print(f"{'=' * 78}")
    print(f"comps returned     : {len(grounded.comps)}")
    print(f"rent estimate      : ${grounded_est:,.0f}/mo")
    print(f"  {'listing_id':<20}{'rent':>8}{'beds':>6}{'sqft':>7}{'mi':>7}  "
          f"{'source':<18}{'id fmt ok?':<12}{'in corpus?':<12}")
    for c in grounded.comps:
        fmt = "yes" if id_format_matches_corpus(c.listing_id) else "no"
        print(f"  {c.listing_id:<20}{c.rent:>8.0f}{c.beds:>6}{c.square_feet:>7.0f}"
              f"{c.distance_miles:>7.2f}  {(c.listing_source or 'unknown')[:17]:<18}"
              f"{fmt:<12}{'YES':<12}")
    print(f"\n  IN EVIDENCE BASE   : {len(grounded.comps)} / {len(grounded.comps)}")
    print(f"  flags raised       : {len(grounded.flags)}")

    # ---- Side by side ----
    print(f"\n\n{'=' * 78}")
    print("SUMMARY")
    print(f"{'=' * 78}")
    print(f"  {'configuration':<42}{'comps':>7}{'verifiable':>12}{'rent est':>12}")
    for s in summaries:
        print(f"  {'ungrounded LLM — ' + s['label']:<42}{s['n_comps']:>7}"
              f"{s['n_verifiable']:>12}{'$%.0f' % s['rent_estimate']:>12}")
    print(f"  {'grounded retrieval (Chroma)':<42}{len(grounded.comps):>7}"
          f"{len(grounded.comps):>12}{'$%.0f' % grounded_est:>12}")
    print(f"  {'retrieval disabled (config flag)':<42}{0:>7}{0:>12}{'n/a':>12}")


if __name__ == "__main__":
    main()
