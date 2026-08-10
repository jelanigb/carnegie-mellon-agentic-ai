"""Extractor agent — **U2 STUB**. The real implementation is U3.

What is real here and what is not, stated plainly because a stub that looks finished is
worse than no stub at all:

- **Real:** the clarifying-question and `unresolved_field` flag behaviour for missing
  required fields, and the county derivation via `tools/county_crosswalk.py`. Both are
  ordinary Python and both are load-bearing for the walking skeleton's flag-propagation
  proof, so building them now costs nothing and U3 keeps them.
- **Stubbed:** the parse itself. U3 replaces the regex below with a real LLM call
  through `llm_client.call_with_schema`, with the Pydantic validate-then-retry loop
  described in Checkpoint 2.1 Loop 1. This stub cannot run that call — decision #8 (§7)
  is open and all four configured model IDs are confirmed dead — and U2 does not need
  it to. The skeleton's job is to prove the graph carries state and flags correctly,
  which a deterministic parse demonstrates *better* than a stochastic one.

The regex parse is deliberately shallow: it recognizes a small set of unambiguous
patterns and gives up rather than guessing. Guessing is precisely what U3 is for, and a
stub that half-guesses would generate assumption flags this build cannot justify.

Reason/Act/Observe/Decide (the loop U3 inherits):

- **Reason.** Decide which deal terms the listing text plausibly contains, and which
  required fields are at risk of being absent.
- **Act.** Parse the text into a `DealTerms` object, then derive county FIPS from the
  parsed city/state via the crosswalk.
- **Observe.** Check the result against `config.REQUIRED_DEAL_FIELDS`. A missing field
  is an observation, not a failure.
- **Decide.** Emit a clarifying question and an `unresolved_field` flag for each
  missing required field, so the gap travels downstream attached to the estimate it
  weakens rather than being resolved silently. U3 adds the retry branch: on a schema
  validation failure, re-prompt with the `ValidationError` text, bounded by
  `config.MAX_EXTRACTION_RETRIES`, escalating with `extraction_retry_exhausted`.
"""

from __future__ import annotations

import re
from typing import Optional

import config
from state import DealState, DealTerms, FlagKind, Severity, flag
from tools import county_crosswalk

AGENT = "extractor"

# Patterns chosen for being unambiguous in isolation. Anything requiring context to
# disambiguate is left to U3's LLM call rather than approximated here.
_PRICE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")
_UNITS = re.compile(r"(\d+)[\s-]*(?:unit|family|flat|plex)\b", re.IGNORECASE)
_BEDS = re.compile(r"(\d+)\s*(?:bed|bd|br)\b", re.IGNORECASE)
_BATHS = re.compile(r"(\d+(?:\.\d)?)\s*(?:bath|ba)\b", re.IGNORECASE)
_SQFT = re.compile(r"([\d,]+)\s*(?:sq\.?\s?ft|sqft|square feet)", re.IGNORECASE)
# "123 Main St, Chicago, IL 60647" — street / city / two-letter state / optional ZIP.
_ADDRESS = re.compile(
    r"(?P<street>\d+[^,\n]{3,60}?),\s*"
    r"(?P<city>[A-Za-z][A-Za-z .'-]{1,40}?),\s*"
    r"(?P<state>[A-Z]{2})"
    r"(?:\s+(?P<zip>\d{5}))?"
)


def _to_float(raw: Optional[str]) -> Optional[float]:
    return float(raw.replace(",", "")) if raw else None


def _parse_listing(text: str) -> DealTerms:
    """Deterministic best-effort parse. Returns whatever it is sure of, nothing more."""
    terms = DealTerms()

    price = _PRICE.search(text)
    if price:
        terms.price = _to_float(price.group(1))

    units = _UNITS.search(text)
    if units:
        terms.unit_count = int(units.group(1))

    beds = _BEDS.search(text)
    if beds:
        terms.bedrooms = int(beds.group(1))

    baths = _BATHS.search(text)
    if baths:
        terms.bathrooms = float(baths.group(1))

    sqft = _SQFT.search(text)
    if sqft:
        terms.square_footage = _to_float(sqft.group(1))

    address = _ADDRESS.search(text)
    if address:
        terms.full_address = address.group(0).strip()
        terms.street_address = address.group("street").strip()
        terms.city = address.group("city").strip()
        terms.state = address.group("state").strip()
        terms.zip_code = address.group("zip")

    return terms


def extractor_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    parsed = _parse_listing(state.raw_listing_text)

    # Stub affordance, and the one place this node deviates from what U3 will do: a
    # field already present in state is left alone rather than overwritten. It exists
    # because the corpus has no geocoder (see the TODO below) and the walking skeleton
    # still needs one path that reaches real retrieval, so a caller can supply known
    # coordinates the way `scripts/retrieval_evidence.py` already does. U3 removes this
    # merge — a real extractor's output should not depend on what was in state before
    # it ran.
    existing = state.deal_terms.model_dump(exclude_none=True)
    terms = DealTerms(**{**parsed.model_dump(exclude_none=True), **existing})

    flags = []
    questions = []

    # TODO(U3): nothing in this system derives latitude/longitude, and
    # `vector_store.query_comps` hard-requires them — a subject property without
    # coordinates cannot be compared to anything, so the pipeline degrades to zero comps
    # regardless of how good the extraction was. §5 lists them as DERIVED "by lookup",
    # but no lookup exists: the crosswalk resolves county only, and the evidence scripts
    # hardcode real coordinates for their synthetic subjects. This is decision #10 in §7
    # (geocoding source), raised rather than resolved here per §8. Options are a
    # geocoding API call, a city-centroid table with a disclosed-approximation flag, or
    # requiring coordinates on the input.

    if terms.county_fips is None:
        terms.county_fips = county_crosswalk.lookup_county_fips(terms.city, terms.state)

    for field_name in config.REQUIRED_DEAL_FIELDS:
        if getattr(terms, field_name) is not None:
            continue
        readable = field_name.replace("_", " ")
        questions.append(f"What is the {readable} for this property?")
        flags.append(
            flag(
                AGENT,
                FlagKind.UNRESOLVED_FIELD,
                f"Required field '{field_name}' could not be extracted from the "
                f"listing text. Downstream estimates proceed without it.",
                Severity.WARN,
            )
        )

    return {
        "deal_terms": terms,
        "clarifying_questions": questions,
        "extraction_attempts": state.extraction_attempts + 1,
        "flags": flags,
        "stub_nodes": [AGENT],
    }
