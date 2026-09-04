# Project Stats

**Last updated on 2026-09-03.**

Assembled for the final report. Every figure below is derived from the repository at
commit `4037df6` (branch `main`) and each row states how it was produced, so the numbers
can be re-derived rather than trusted. Where a number also appears in
[`design/data_sources.md`](design/data_sources.md) and the two disagree, the value here
is the one computed from code and is the one to trust.

---

## 1. Lines of code

All 84 Git-tracked `.py` files. `.md` and every other extension are excluded. Blank
lines are excluded from every figure. Each line is classified once, in this order of
precedence: blank → comment-only (`#`) → docstring (inside a `"""…"""` used as a bare
statement) → code.

| Measure | Lines | What it is |
| --- | --- | --- |
| **Total (excluding blanks)** | **25,372** | code + docstrings + comment-only lines |
| **Code + docstrings** | **21,416** | the above minus 3,956 comment-only lines |
| **Code only** | **14,894** | the above minus 6,522 docstring lines |

So of every 3 non-blank lines in the codebase, roughly 1 is a comment and 1 is
docstring prose — a direct consequence of the standard that "docstrings carry the
reasoning." (For reference, the files also contain 4,213 blank lines; raw physical line
count is 29,585.)

### By area

| Area | Files | Total (excl. blanks) | Code + docstrings | Code only |
| --- | --- | --- | --- | --- |
| `src/scripts/` — evidence & index-build scripts | 32 | 6,858 | 6,405 | 4,813 |
| `src/agents/` — the 7 pipeline agents | 9 | 5,389 | 4,587 | 3,208 |
| `src/tools/` — data clients, model, crosswalks, infra | 22 | 4,975 | 4,499 | 2,724 |
| `src/` root — `graph`, `state`, `nodes`, `config`, `main`, `app`, `demo_deals`, `mcp_server` | 8 | 3,885 | 2,128 | 1,370 |
| `src/tests/` | 8 | 2,535 | 2,316 | 1,572 |
| `src/eval/` — harness + cases + fixtures | 5 | 1,730 | 1,481 | 1,207 |
| **Total** | **84** | **25,372** | **21,416** | **14,894** |

**The shipped pipeline** — agents + tools + eval + `src/` root, excluding one-off
scripts and tests — is **44 files: 15,979 total / 12,695 code + docstrings / 8,509 code
only**.

*Method:* every line in every tracked `.py` file classified in Python (`str.strip()` →
empty = blank, leading `#` = comment-only, else code); docstring lines identified with
the `tokenize` module, with blank lines inside a docstring counted as blank, not
docstring.

---

## 2. Project files

| Scope | Files |
| --- | --- |
| **Excluding generated LLM recordings** | **126** |
| All Git-tracked files | 535 |

`docs/private/` and `ignore/` are gitignored, so they contribute nothing to either
count. Of the 535 tracked files, **409 are generated LLM interaction recordings**
(`src/eval/data/llm_recordings/` 383, `src/eval/data/exploratory/` 26) used to replay the
eval harness offline; the 126 figure is everything else.

### By extension (all 535)

| Ext | Count | | Ext | Count |
| --- | --- | --- | --- | --- |
| `.json` | 412 | | `.gitkeep` | 2 |
| `.py` | 84 | | `.txt` / `.png` / `.mmd` / `.log` / `.joblib` / `.gitignore` / (none) | 1 each |
| `.md` | 30 | | | |

### By top-level directory

| Dir | Files |
| --- | --- |
| `src/` | 504 |
| `docs/` (27 tracked; `docs/private/` gitignored) | 27 |
| repo root (`README.md`, `LICENSE`, `.gitignore`, `data/.gitkeep`) | 4 |

*Method:* `git ls-files`, grouped by extension and first path segment.

---

## 3. Git commits

| Measure | Value |
| --- | --- |
| **Total commits** | **165** |
| Authored by Jelani Gould-Bailey | 165 (164 as `jelanigb` + 1 as `Jelani Gould-Bailey` — same person, two configured names) |
| First commit | 2026-08-08 |
| Latest commit | 2026-09-03 |
| Active span | 27 days |
| Days with at least one commit | 18 |
| Busiest days | Aug 30 (32), Sep 2 (32), Sep 1 (20) |

*Method:* `git rev-list --count HEAD`, `git shortlog -sn --all`, `git log --date=short`.

---

## 4. Eval cases and demo deals

| Measure | Value |
| --- | --- |
| **Total eval cases** (`cases.all_cases()`) | **30** |
| — Golden-tier (complete `DealTerms` supplied, Extractor skipped) | 15 |
| — Replay-tier (Extractor runs against recorded LLM responses) | 6 |
| — Live-tier (real model call) | 9 |
| Scoring cases (`PREDICTED` verdicts, count toward U8.6 agreement) | 23 |
| Regression-check cases (`BASELINE` verdicts) | 7 |
| Engineered cases (`ENGINEERED_CASES`) | 21 |
| Distinct golden fixtures behind the golden-tier cases | 14 (LA 3, Chicago-Uptown 5, Cleveland 3, New York 3) |
| Distinct flag kinds targeted by engineered cases | 17 |
| **Demo deals** (`demo_deals.DEMO_DEALS`) | **8** |

The 8 demo deals: `los-angeles`, `los-angeles-current`, `chicago`, `staten-island`,
`no-geography`, `overpriced`, `chicago-uptown`, `coord-conflict`. The harness also runs a
9th live case, `chicago--no-retrieval` (the U4 ablation), giving the 9 live-tier cases
above.

*Method:* imported `eval.cases` and `demo_deals` and counted the registries directly.

---

## 5. Data points in the source files

### Rent / listings corpora

| Source | Count | Note |
| --- | --- | --- |
| Kaggle rent corpus — raw rows | 99,492 | `apartments_for_rent_classified_100K.csv` |
| Kaggle rent corpus — after `load_clean()` | 98,844 | de-duplicated, core-field-complete, rent-bounded |
| Zillow ZORI — ZIP-level rent series | 8,543 | `Zip_zori_uc_sfrcondomfr_sm_month.csv`, national, monthly since 2015-01 |
| Redfin sale-median series — metros nationally | 943 | filtered to 4 (New York, Chicago, Los Angeles, Cleveland) → 408 metro-month rows |
| Comps indexed in ChromaDB | 3,880 | one document per listing, 4 markets, 166 distinct ZCTAs |

### Geography

| Source | Count | Note |
| --- | --- | --- |
| Census ZCTA boundary polygons | 33,791 | `cb_2020_us_zcta520_500k`, coordinate → 5-digit ZIP |
| Census county boundaries | all US counties | `cb_2023_us_county_500k`, TIGER/Line 2023, coordinate → county FIPS |
| HUD FMR — geographic key | county (`entityid`) | SAFMR ZIP schedules for the 3 inference counties: LA 474, Cuyahoga 126, Cook 370 (FY2026) |

### Benchmarks and panels

| Source | Count | Note |
| --- | --- | --- |
| ZIP-level sale-price benchmarks | 304 ZIPs | New York 164 (27,309 sales) + Chicago 140 (17,672 sales), county-assessor records since 2023. Decision #11's writeup quotes 18,251 for Chicago; the committed table sums to 17,672 and is the figure the system reads |
| FMR cohort panel (U6 rent-growth screen) | 10 HUD FMR areas | `fmr_cohort_panel.json`, FY2017–FY2026 |

### Metro scopes — four separate lists, deliberately not the same set

`config.py` keeps four different metro lists, each answering a different question. Their
sizes are 3, 4, 8 and 4; the point is *which* metros are in each, so every list is spelled
out below rather than left as a count.

| List (`config.py` name) | Size | The metros in it | What membership decides |
| --- | --- | --- | --- |
| Inference metros (`INFERENCE_METROS`) | 3 | Chicago, Los Angeles, Cleveland | The markets the pipeline is built to price end-to-end |
| Redfin target metros (`REDFIN_TARGET_METROS`) | 4 | Chicago, Los Angeles, Cleveland, **New York** | Which markets get a Redfin sale-price appreciation series and a metro-level benchmark |
| Training metros (`TRAINING_METROS`) | 8 metros across 6 states (14 city-name patterns) | CA: Los Angeles · OH: Cincinnati, Cleveland · IL: Chicago · NJ: Newark, Jersey City · NY: New York, Brooklyn, Queens, Bronx, Staten Island, Manhattan · PA: Pittsburgh, Philadelphia | Which Kaggle listings the rent regression learns from — a deliberate superset of the inference trio, because the model predicts a *ratio* and benefits from markets it will never price |
| Indexed markets (`INDEXED_MARKETS`) | 4 | Chicago, Los Angeles, Cleveland, **New York** | Which markets' listings sit in the Chroma comp index — New York added on purpose as the sparse-comps test case |

*Method:* `wc -l` on the CSVs, `json.load` on the committed tables, `config.py` for the
scope lists.

---

## 6. Rent model

The rent estimator (U11, decisions #18 / #19). CLAUDE.md's one-line stack description
still says "scikit-learn LR model" — that is stale; it became a gradient-boosted tree
ensemble on 2026-08-30.

### Form

| Property | Value |
| --- | --- |
| Estimator | `sklearn.ensemble.GradientBoostingRegressor`, library defaults |
| Hyperparameters | `n_estimators=100`, `max_depth=3`, `learning_rate=0.1`, `loss='squared_error'` |
| Features | `bedrooms`, `bathrooms`, `square_feet` (3 structural features; no market identifier, by design) |
| Target | rent ÷ anchor **ratio**, where anchor = ZORI ZIP rent level × HUD FMR bedroom step |
| Artifact | `data/processed/rent_model.joblib`, trained 2026-08-30 |

### Training frame

| Measure | Value |
| --- | --- |
| Rows in shortlist | 5,717 |
| Rows trained / scored | 5,701 |
| Dropped: missing anchor / outside ratio bounds / unresolved county | 15 / 1 / 0 |
| Counties · fiscal years | 13 · FY2019–FY2020 |
| Distinct ZCTAs | 166 |
| Anchor tier: ZIP-anchored / county-anchored | 4,173 / 1,528 |
| Validation | 5-fold CV (every row scored once out-of-fold), then refit on all rows |

### Accuracy (out-of-fold, from the persisted `TrainingReport`)

| Metric | Model | Mean-ratio baseline |
| --- | --- | --- |
| **MAE (dollars)** | **$452.40** | $589.61 |
| **MAE (rent/anchor ratio)** | **0.269** | 0.357 |
| **R²** | **0.409** | — |
| In-fold MAE (dollars) | $430.95 | — |
| Train/holdout gap | $21.45 | — |

The model beats the mean-ratio baseline by **23.3%** on dollar MAE.

### MAE by metro

| Metro | MAE (dollars) | Holdout n |
| --- | --- | --- |
| Chicago | $343.36 | 630 |
| Cleveland | $356.97 | 606 |
| Los Angeles | $508.98 | 2,372 |
| New York | $855.34 | 264 |

### Feature importances

| Feature | Importance |
| --- | --- |
| `square_feet` | 0.502 |
| `bedrooms` | 0.300 |
| `bathrooms` | 0.198 |

### Input-domain guard

Estimates are refused when a subject falls outside the training data's shape:
`square_feet` 130–9,175, `bedrooms` 0–6, `bathrooms` 1.0–5.5, and — the load-bearing
one — square-feet-per-bedroom outside **150–1,481** (the 0.1 / 99.9 percentiles of the
training frame).

### Model-form comparison (5-fold CV, 5,686 rows, `scripts/model_form_probe.py`)

| Form | CV MAE | R² | Train/holdout gap |
| --- | --- | --- | --- |
| LinearRegression | $513.67 | 0.263 | $0.32 |
| RandomForest | $428.83 | 0.454 | $140.41 |
| **GradientBoosting (chosen)** | $450.71 | 0.427 | $18.34 |

Random forest scored lowest on error and was **not** taken — its $140 train-vs-holdout
gap is the overfitting risk. Gradient boosting gives up 5% of error for a ~8x tighter
gap and the smallest fold-to-fold spread.

*Method:* `joblib.load('data/processed/rent_model.joblib')`, reading the `report` dict
that is persisted with the model; comparison table from `config.py`'s
`RENT_MODEL_ESTIMATOR` note.

---

## 7. Pipeline shape

| Measure | Value |
| --- | --- |
| Agents | 7 (Planner, Extractor, Comps/Retrieval, Valuation/Rent, Scenario/Forecast, Critic, Summarizer) |
| LangGraph nodes | 8 (the 7 agents + Human-Review pause) |
| Graph back edges | 1 (Critic → rework re-entry), asserted on every diagram export |
| Typed flag kinds (`state.FlagKind`) | 30 |
| Decisions in the §7 register | 22 (#1–#22) |
| Units delivered | 11 (U1–U11) |
| pytest tests collected | 107 |
| Changelog | 52 dated entries, 445 rows |

*Method:* `state.FlagKind` member count, `grep` on `graph.py` / `implementation_plan.md`
/ `changelog.md`, `pytest --collect-only`.

---

## Other stats worth considering for the report

- **Cost against budget.** The project constraint is a $100 ceiling; a tally of actual
  OpenRouter + any paid API spend to date would show headroom. Not derivable from the
  repo — needs the OpenRouter dashboard.
- **Replay determinism.** Share of eval cases that run with zero live model calls
  (golden + replay = 21 of 30, 70%) — the figure behind "a demo costs no quota."
- **Disclosure coverage.** How many of the 30 `FlagKind`s are exercised by at least one
  test or eval case vs. only reachable in principle.
- **Decision churn.** 22 decisions across 27 days, several re-opened (#16 superseded by
  #21, #6/#20/#22 held on measurement) — a "decisions revisited" count would speak to
  the "correcting past mistakes is worth it" working principle.
- **Doc-to-code ratio.** ~30 tracked `.md` files / `docs/` totals vs. 14,894 lines of
  actual code — the project is documentation-heavy by design.
