"""Chroma-backed comp retrieval over the Kaggle rental corpus.

Design notes: docs/implementation_plan.md §2 (retrieval design decisions) and the U4
acceptance criteria in §6.

Retrieval here is deliberately **hybrid**, and the split is the central design decision:

- **Hard constraints run as metadata filters.** Bedroom count and geography are not
  fuzzy notions. A two-bedroom in the subject's neighborhood is either in the candidate
  set or it is not, and asking an embedding model to approximate that relationship
  would trade a correct answer for a plausible one. Chroma's `where` clause handles
  these exactly.

- **Semantic similarity runs over free text only.** Description and amenity text is
  where "renovated", "in-unit laundry", "garden level", and "walk-up" carry meaning
  that no structured column captures and no exact match would find. This is the part
  of the problem embeddings are actually good at.

Pure vector search over what is fundamentally structured data would be the wrong tool,
and would produce comps that are semantically similar but geographically irrelevant.
Pure SQL-style filtering would miss the qualitative dimension entirely. The failure
mode each half protects against is different, so both are present.

Segmentation: one document per listing, never chunked. Listings are short,
self-contained records whose fields are mutually dependent — splitting one would
separate a rent figure from the bed/bath/sqft context that makes it interpretable, and
could surface half a comparable as a match.
"""

from __future__ import annotations

import math
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

import config
from state import Comp, DealTerms

# Mean radius of the Earth. Used for the haversine distance and for converting a
# search radius in miles into a latitude/longitude bounding box.
_EARTH_RADIUS_MILES = 3958.8

# Chroma's `where` clause only does flat range comparisons — no native radius query —
# so a radius search is simulated in two passes: `_bounding_box` uses approximate trig
# to turn the radius into a 2D lat/lon rectangle Chroma can filter on, then
# `haversine_miles` uses exact spherical trig to trim that rectangle down to the true
# circle on the Earth's curved (3D) surface.


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Chroma cannot express a radius query, so the bounding box
    below narrows the candidate set and this computes the exact distance afterward.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def _bounding_box(lat: float, lon: float, radius_miles: float) -> tuple[float, float, float, float]:
    """Lat/lon box guaranteed to contain every point within `radius_miles`.

    Deliberately generous — it over-selects, and the exact haversine filter afterward
    removes the corners. The alternative (querying without a geographic bound) would
    make the vector search do work it cannot do correctly.
    """
    lat_delta = radius_miles / 69.0
    # Longitude degrees compress toward the poles. Guard against the cosine collapsing
    # near ±90°, which would produce an unbounded box.
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_miles / (69.0 * cos_lat)
    return lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta


def get_client() -> chromadb.ClientAPI:
    config.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_PERSIST_DIR))


def get_embedding_function():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config.EMBEDDING_MODEL
    )


def get_collection(create: bool = False):
    client = get_client()
    if create:
        return client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            embedding_function=get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
    return client.get_collection(
        name=config.CHROMA_COLLECTION,
        embedding_function=get_embedding_function(),
    )


def query_comps(
    subject: DealTerms,
    radius_miles: float,
    bedroom_tolerance: int = 0,
    sqft_tolerance_pct: Optional[float] = None,
    n_results: int = 10,
    collection=None,
) -> list[Comp]:
    """Retrieve comparable listings for a subject property.

    Hard constraints (geography, bedroom count, optional sqft band) are applied as
    metadata filters; semantic ranking over description/amenity text orders whatever
    survives them. Returns at most `n_results` comps sorted by similarity.

    Returns an empty list rather than raising when nothing qualifies — a shortfall is
    an observation the calling loop must act on, not an error state.
    """
    if subject.latitude is None or subject.longitude is None:
        raise ValueError("Subject property requires latitude/longitude for comp retrieval.")

    collection = collection or get_collection()

    lat_min, lat_max, lon_min, lon_max = _bounding_box(
        subject.latitude, subject.longitude, radius_miles
    )

    conditions: list[dict] = [
        {"latitude": {"$gte": lat_min}},
        {"latitude": {"$lte": lat_max}},
        {"longitude": {"$gte": lon_min}},
        {"longitude": {"$lte": lon_max}},
    ]

    if subject.bedrooms is not None:
        conditions.append({"bedrooms": {"$gte": subject.bedrooms - bedroom_tolerance}})
        conditions.append({"bedrooms": {"$lte": subject.bedrooms + bedroom_tolerance}})

    if sqft_tolerance_pct is not None and subject.square_footage:
        lo = subject.square_footage * (1 - sqft_tolerance_pct)
        hi = subject.square_footage * (1 + sqft_tolerance_pct)
        conditions.append({"square_feet": {"$gte": lo}})
        conditions.append({"square_feet": {"$lte": hi}})

    where_clause = {"$and": conditions}

    # Over-fetch: the bounding box admits corner points outside the true radius, which
    # the haversine filter below removes. Without headroom, that filter could empty an
    # otherwise adequate result set.
    query_text = _subject_query_text(subject)
    raw = collection.query(
        query_texts=[query_text],
        n_results=min(n_results * 5, 200),
        where=where_clause,
    )

    ids = raw["ids"][0]
    metas = raw["metadatas"][0]
    distances = raw["distances"][0]

    comps: list[Comp] = []
    for listing_id, meta, dist in zip(ids, metas, distances):
        miles = haversine_miles(
            subject.latitude, subject.longitude, meta["latitude"], meta["longitude"]
        )
        if miles > radius_miles:
            continue
        comps.append(
            Comp(
                listing_id=str(listing_id),
                # Chroma returns cosine distance; similarity is its complement.
                similarity_score=round(1.0 - float(dist), 4),
                rent=float(meta["price"]),
                beds=int(meta["bedrooms"]),
                baths=float(meta["bathrooms"]),
                square_feet=float(meta["square_feet"]),
                distance_miles=round(miles, 3),
                listing_source=meta.get("source"),
            )
        )
        if len(comps) >= n_results:
            break

    return comps


def _subject_query_text(subject: DealTerms) -> str:
    """Build the semantic query for a subject property.

    Only qualitative attributes belong here — the quantitative ones are already handled
    exactly by the metadata filter, and repeating them in the embedded text would let
    fuzzy matching reintroduce error into constraints that were previously exact.
    """
    parts = []
    if subject.bedrooms is not None:
        parts.append(f"{subject.bedrooms} bedroom")
    if subject.bathrooms is not None:
        parts.append(f"{subject.bathrooms} bathroom")
    parts.append("apartment for rent")
    if subject.city:
        parts.append(f"in {subject.city}")
    return " ".join(parts)


def listing_document(title: str, body: str, amenities: str) -> str:
    """The text embedded for one listing.

    Structured fields are excluded on purpose: they are carried as metadata and matched
    exactly, so including them here would add noise to the semantic signal without
    improving retrieval.
    """
    return " ".join(p for p in (title, body, amenities) if p and str(p) != "nan").strip()
