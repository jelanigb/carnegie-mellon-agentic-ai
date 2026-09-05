# `data/` — what a fresh clone is missing, and how to get it

**This directory is gitignored** apart from this file and the trained rent model, so a
clone arrives with neither the source datasets nor the artifacts built from them. That is
deliberate: the corpus expands to 97 MB, the vector index to 51 MB, and both are either
third-party data better cited than vendored or artifacts a script rebuilds in minutes.

**Most reviewers do not need any of this.** The evaluation harness is the exception to
the whole directory — its inputs are committed in full, so

```bash
cd src && .venv/bin/python -m eval.runner --tier golden
```

reproduces every figure the report quotes with **no downloads, no API keys and no network
calls**. The committed sample reports in `docs/sample_reports/` show real output for the
same reason. Follow the rest of this file only if you want to run the pipeline on a new
listing yourself.

---

## What has to be fetched by hand

Three files. Everything else on this page fetches itself.

| # | File | Size | Source | License |
| --- | --- | --- | --- | --- |
| 1 | `apartments_for_rent_classified_100K.csv` | 97 MB | [Apartment for Rent Classified](https://archive.ics.uci.edu/dataset/555/apartment+for+rent+classified), UCI ML Repository (dataset 555) | **CC BY 4.0** |
| 2 | `Zip_zori_uc_sfrcondomfr_sm_month.csv` | 9.5 MB | [Zillow Research — ZORI](https://www.zillow.com/research/data/) | Zillow's terms of use |
| 3 | `redfin_property_types_monthly_all_metros_multi_family_2_4_units_2018_Jan_to_2026_Jun.csv` | 18 MB | [Redfin Data Center](https://www.redfin.com/news/data-center/) | Redfin's terms of use |

**1 — the rental corpus.** Powers comp retrieval *and* rent-model training. Download the
`apartments_for_rent_classified_100K` archive from UCI, extract it, and place the CSV at
`data/` under exactly that filename. It is semicolon-delimited and cp1252-encoded;
`tools/kaggle_data.load_clean()` is the only supported entry point and handles both.
Attribution is required under CC BY 4.0 — credit the UCI ML Repository dataset above.

**2 — the Zillow rent index.** Every rent estimate is anchored to it. One command:

```bash
cd src && .venv/bin/python -c "from tools import zori; zori.download()"
```

**3 — the Redfin sale-price series.** Feeds the price-appreciation forecast. Redfin's Data
Center has no direct file URL, so this one is a manual export: choose the **monthly
metro-level** table, filter to **Property Type = Multi-Family (2-4 Units)**, cover
**Jan 2018 – Jun 2026**, and save it to `data/` under the filename in the table above.
`tools/redfin_data.py` filters the 943-metro extract down to the four this project uses.

## What fetches itself

| File | Size | How |
| --- | --- | --- |
| `raw/census_zcta_boundaries.zip` | 64 MB | Auto-downloaded on first coordinate→ZIP lookup ([Census GENZ2020 cartographic](https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip), public domain) |
| `raw/census_county_boundaries.zip` | 11 MB | Auto-downloaded on first coordinate→county lookup ([Census GENZ2023](https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip), public domain) |
| `raw/hud_fmr_cache.json` | grows to ~4 MB | Populated from the [HUD FMR API](https://www.huduser.gov/portal/dataset/fmr-api.html) as areas are requested; needs a free `HUD_FMR_TOKEN` |
| `processed/chroma/` | 51 MB | **Built, not downloaded** — see below |
| `processed/checkpoints.sqlite` | grows | LangGraph checkpointer, created on first run |
| `processed/llm_cache/` | grows | Development response cache; separate from the committed eval recordings |

## What is already committed

| File | Why it ships |
| --- | --- |
| `processed/rent_model.joblib` (140 KB) | Derived weights, not the corpus, so no license restriction — and committing it means scoring a listing works without a training pass |
| `src/tools/data/zip_sale_benchmarks.json` | ZIP-level sale medians from public county-assessor records |
| `src/tools/data/fmr_cohort_panel.json` | The FMR history panel behind the rent-growth fallback |
| `src/eval/data/` | Golden fixtures, recorded model responses, and the geocoder cache — the inputs behind every published figure |

## Building the Chroma index

**The vector index is not a download.** It is built from file 1 above, which is why the
corpus is the only retrieval dependency you have to fetch:

```bash
cd src
.venv/bin/python scripts/build_comps_index.py
```

This reads the corpus, filters to the four indexed markets (Chicago, Los Angeles,
Cleveland, New York), embeds one document per listing with
`sentence-transformers/all-MiniLM-L6-v2` running locally, and writes 3,880 documents to
`data/processed/chroma/`. It needs no API key — the embedding model downloads once from
Hugging Face on first use — and takes a few minutes on a laptop.

Rebuild the rent model the same way if you want to reproduce it rather than use the
committed artifact:

```bash
.venv/bin/python scripts/train_rent_model.py
```

## Full setup, start to finish

```bash
cd src
python -m venv .venv && .venv/bin/pip install -r requirements.txt

export OPENROUTER_API_KEY=...    # LLM access
export HUD_FMR_TOKEN=...         # free HUD account

# 1. corpus: download from UCI, extract, place at data/apartments_for_rent_classified_100K.csv
# 2. rent index:
.venv/bin/python -c "from tools import zori; zori.download()"
# 3. Redfin: manual export per the instructions above

.venv/bin/python scripts/build_comps_index.py     # builds the vector index
.venv/bin/python main.py --deal los-angeles       # a full run
```

The two Census boundary files download themselves the first time a coordinate is
resolved, so the first run is slower than the ones after it.
