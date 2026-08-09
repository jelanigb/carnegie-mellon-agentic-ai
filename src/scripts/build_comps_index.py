"""One-off: build the Chroma comp index from the Kaggle rental corpus.

Indexes the inference metros (§2: Chicago, Los Angeles, Cleveland) plus New York, which
is carried deliberately as a sparse-comps case — its 283 listings are too thin for a
credible comp set, and that is the point. It exercises the full degradation path on a
real market rather than a constructed one.

One document per listing, never chunked (see tools/vector_store.py for the reasoning).

Run: .venv/bin/python scripts/build_comps_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools import kaggle_data, vector_store

# state code -> city name patterns. New York rolls up its boroughs, which appear as
# separate cityname values. Matching is word-boundary (see tools/kaggle_data.py):
# "Cleveland" must catch "Cleveland Heights" while "Queens" must not catch
# "Queensbury" and "Bronx" must not catch "Bronxville".
INDEXED_MARKETS: dict[str, list[str]] = {
    "IL": ["Chicago"],
    "CA": ["Los Angeles"],
    "OH": ["Cleveland"],
    "NY": ["New York", "Brooklyn", "Queens", "Bronx", "Staten Island", "Manhattan"],
}

# Chroma's embedding step is the bottleneck; batching keeps memory flat and gives
# visible progress on a multi-thousand-row load.
BATCH_SIZE = 500


def load_listings() -> pd.DataFrame:
    df = kaggle_data.load_clean()
    print(f"  dropped {df.attrs['rows_deduped']} duplicate-id rows, "
          f"{df.attrs['rows_dropped']:,} rows total after cleaning")
    return kaggle_data.filter_markets(df, INDEXED_MARKETS)


def main() -> None:
    print(f"Reading {kaggle_data.KAGGLE_PATH.name} ...")
    listings = load_listings()
    print(f"  {len(listings):,} listings across indexed markets\n")

    print("  by market:")
    for (state, city), n in (
        listings.groupby(["state", "cityname"]).size().sort_values(ascending=False).head(15).items()
    ):
        print(f"    {city}, {state:<4} {n:>6,}")

    client = vector_store.get_client()
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
        print(f"\nDropped existing collection '{config.CHROMA_COLLECTION}'.")
    except Exception:
        pass

    collection = vector_store.get_collection(create=True)
    print(f"Embedding with {config.EMBEDDING_MODEL} (first run downloads the model)...\n")

    total = len(listings)
    for start in range(0, total, BATCH_SIZE):
        batch = listings.iloc[start : start + BATCH_SIZE]

        documents = [
            vector_store.listing_document(r.get("title", ""), r.get("body", ""), r.get("amenities", ""))
            for _, r in batch.iterrows()
        ]
        metadatas = [
            {
                "price": float(r["price"]),
                "bedrooms": int(r["bedrooms"]),
                "bathrooms": float(r["bathrooms"]),
                "square_feet": float(r["square_feet"]),
                "latitude": float(r["latitude"]),
                "longitude": float(r["longitude"]),
                "cityname": str(r["cityname"]),
                "state": str(r["state"]),
                # Originating site, so a retrieved comp can be cited rather than merely
                # asserted, and so source concentration is visible downstream.
                "source": str(r.get("source", "") or "unknown"),
                # TODO(U5): also index `r["time"]` (Unix timestamp) as a listed-date
                # metadata field, so Comp.listed_date can be populated and each comp
                # normalized against the FMR for its own year. See state.Comp.
            }
            for _, r in batch.iterrows()
        ]
        ids = [str(r["id"]) for _, r in batch.iterrows()]

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f"  indexed {min(start + BATCH_SIZE, total):>6,} / {total:,}")

    print(f"\nDone. Collection '{config.CHROMA_COLLECTION}' holds {collection.count():,} listings.")
    print(f"Persisted to {config.CHROMA_PERSIST_DIR}")


if __name__ == "__main__":
    main()
