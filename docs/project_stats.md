# Project Stats

**Last updated on 2026-09-07 — final, at project submission.**

Assembled for the final report. Every figure below is derived from the repository at
commit `a3c2179` (branch `main`, 2026-09-06) and each row states how it was produced, so
the numbers can be re-derived rather than trusted. Where a number also appears in
[`design/data_sources.md`](design/data_sources.md) and the two disagree, the value here
is the one computed from code and is the one to trust.

Everything is measured against the **committed** tree, not the working tree, so a fresh
clone reproduces it. (At the time of measurement the working tree carried three
uncommitted edits — 13 comment lines in `agents/critic.py`, a geocode-cache append, and
one document — none of which are counted below.)

**Figures corrected since the 2026-09-03 revision** are marked ⚠ and explained where they
appear. Three of them are corrections to the *method*, not growth in the project, so the
new number is lower than the old one; the final report should quote this file, not the
previous one.

---

## 1. Lines of code

All 85 Git-tracked `.py` files. `.md` and every other extension are excluded. Blank
lines are excluded from every figure. Each line is classified once, in this order of
precedence: blank → comment-only (`#`) → docstring (inside a `"""…"""` used as a bare
statement) → code.

| Measure | Lines | What it is |
| --- | --- | --- |
| **Total (excluding blanks)** | **25,950** | code + docstrings + comment-only lines |
| **Code + docstrings** | **21,946** | the above minus 4,004 comment-only lines |
| **Code only** | **15,312** | the above minus 6,634 docstring lines |

So **roughly 2 of every 5 non-blank lines in the codebase are prose** — 15.4% comment,
25.6% docstring, 59.0% code — a direct consequence of the standard that "docstrings carry
the reasoning." (For reference, the files also contain 4,348 blank lines; raw physical
line count is 30,298.)

⚠ The previous revision described this ratio as "of every 3 non-blank lines, roughly 1 is
a comment and 1 is docstring" — that overstated it. The underlying counts were right; the
sentence summarizing them was not.

### By area

| Area | Files | Total (excl. blanks) | Code + docstrings | Code only |
| --- | --- | --- | --- | --- |
| `src/scripts/` — evidence & index-build scripts | 32 | 6,890 | 6,435 | 4,829 |
| `src/agents/` — the 7 pipeline agents | 9 | 5,409 | 4,606 | 3,217 |
| `src/tools/` — data clients, model, crosswalks, infra | 22 | 5,001 | 4,504 | 2,726 |
| `src/` root — `graph`, `state`, `nodes`, `config`, `main`, `app`, `demo_deals`, `mcp_server` | 8 | 4,090 | 2,324 | 1,496 |
| `src/tests/` | 8 | 2,535 | 2,316 | 1,572 |
| `src/eval/` — harness + cases + fixtures | 5 | 1,730 | 1,481 | 1,207 |
| `docs/diagrams/` — `agent_logic_flow_gen.py` | 1 | 295 | 280 | 265 |
| **Total** | **85** | **25,950** | **21,946** | **15,312** |

**The shipped pipeline** — agents + tools + eval + `src/` root, excluding one-off
scripts, tests and the diagram generator — is **44 files: 16,230 total / 12,915 code +
docstrings / 8,646 code only**.

`src/` root is the densest commentary in the project: 1,766 comment-only lines against
1,496 of code, because `config.py` carries the reasoning for every tunable parameter
beside it.

*Method:* every line in every tracked `.py` file classified in Python (`str.strip()` →
empty = blank, leading `#` = comment-only, else code); docstring lines identified with
the `tokenize` module — a `STRING` token at bracket depth 0 that opens a logical line —
with blank lines inside a docstring counted as blank, not docstring. Verified against the
2026-09-03 revision: this method reproduces that revision's per-area figures exactly on
the files that have not changed since.

---

## 2. Project files

| Scope | Files |
| --- | --- |
| **Excluding generated LLM recordings** | **132** |
| All Git-tracked files | 544 |

`data/` and `ignore/` are gitignored, so they contribute almost nothing to either count.
Of the 544 tracked files, **412 are generated LLM interaction recordings**
(`src/eval/data/llm_recordings/` 384, `src/eval/data/exploratory/` 28) used to replay the
eval harness offline; the 132 figure is everything else.

### By extension (all 544)

| Ext | Count | | Ext | Count |
| --- | --- | --- | --- | --- |
| `.json` | 412 | | `.png` / `.mmd` / `.gitkeep` | 2 each |
| `.py` | 85 | | `.txt` / `.toml` / `.log` / `.joblib` / `.gitignore` / (none) | 1 each |
| `.md` | 35 | | | |

Only 3 of the 412 `.json` files are hand-maintained data tables rather than recordings:
`tools/data/zip_sale_benchmarks.json`, `tools/data/fmr_cohort_panel.json`, and
`eval/data/geocode_cache.json`.

### By top-level directory

| Dir | Files |
| --- | --- |
| `src/` | 505 |
| `docs/` | 34 |
| repo root (`README.md`, `LICENSE`, `.gitignore`) | 3 |
| `data/` (`README.md`, `processed/rent_model.joblib`) | 2 |

⚠ **One of the 34 `docs/` files should not be tracked.**
`docs/private/checkpoints/final/capstone_demo_text.md` entered the repository in commit
`cc09afe` and is on `origin/main`. `docs/private/` *is* listed in `.gitignore`, but
`.gitignore` has no effect on a file that has already been added, so the rule did not
catch it. Every other `docs/private/` file is correctly absent. See the note at the end of
this document.

### Documentation volume

| Measure | Value |
| --- | --- |
| Tracked `.md` files (excluding the private one above) | 34 |
| Lines of Markdown | 16,381 |
| Words of Markdown | 208,497 |
| — of which under `docs/` (29 files) | 15,667 lines / 200,706 words |

**Doc-to-code ratio: 208,497 words of prose against 15,312 lines of code** — roughly 13.6
words of documentation per line of code, before counting the 10,638 comment and docstring
lines inside the code itself. The project is documentation-heavy by design.

*Method:* `git ls-files`, grouped by extension and first path segment; `wc -lw` over the
tracked `.md` set. The Markdown volume is the only figure here measured against the
working tree rather than `a3c2179`, because it counts this revision of this file.

---

## 3. Git commits

| Measure | Value |
| --- | --- |
| **Total commits** | **183** |
| Authored by Jelani Gould-Bailey | 183 (182 as `jelanigb` + 1 as `Jelani Gould-Bailey` — same person, two configured names) |
| First commit | 2026-08-08 |
| Latest commit | 2026-09-06 |
| Active span | 30 days |
| Days with at least one commit | 21 |
| Busiest days | Sep 2 (32), Aug 30 (32), Sep 1 (20), Aug 29 (14), Aug 31 (14) |
| Median commits on an active day | 4 |

Commits are heavily clustered: the five busiest days carry 112 of 183 commits (61%),
which is what a "small, self-contained change sets" working model looks like when review
happens in sittings rather than continuously.

*Method:* `git rev-list --count HEAD`, `git shortlog -sn HEAD`, `git log --date=short`.
Note that `git shortlog -sn --all` reports 190 because it includes commits reachable only
from other refs; 183 is the count on `main`.

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
| Distinct golden fixtures behind the golden-tier cases | 14 (LA 3, Chicago 5, Cleveland 3, New York 3) |
| Distinct flag kinds named as targets — all cases | 17 |
| Distinct flag kinds named as targets — engineered cases only | 16 |
| **Demo deals** (`demo_deals.DEMO_DEALS`) | **8** |

⚠ The previous revision reported "17" against the *engineered* cases. 17 is the figure
across all 30 cases; the 21 engineered cases name 16 of them. The seventeenth,
`extraction_unavailable`, is targeted only by the `cleveland-model-outage` replay case.

The 8 demo deals: `los-angeles`, `los-angeles-current`, `chicago`, `staten-island`,
`no-geography`, `overpriced`, `chicago-uptown`, `coord-conflict`. The harness also runs a
9th live case, `chicago--no-retrieval` (the U4 ablation), giving the 9 live-tier cases
above.

### What the final batch produced (`eval/results/results.md`, run 2026-09-06)

| Measure | Value |
| --- | --- |
| **Verdict agreement** (predicted cases) | **20 / 23** |
| Regression against the published U7.8 baselines | 6 / 7 |
| **Flag coverage** | **30 of 30 flag kinds raised** — 0 uncovered, 0 unreachable |
| **Replay determinism** — cases that run with zero live model calls | **21 of 30 (70%)** (golden 15 + replay 6) |
| Rows where the model's independent verdict differed from the rule's, and the report disclosed the disagreement (⚖) | 11 of 30 |
| Rows escalated by a rule the confidence score alone would not have escalated († / ‡) | 7 of 30 |

The last two rows are the ones worth quoting: they are the direct evidence that the second
reasoning locus and the critical-flag/rework-budget rules each do something the confidence
score does not.

*Method:* imported `eval.cases` and `demo_deals` and counted the registries directly;
verdict, coverage and marker counts read from `eval/results/results.md`.

---

## 5. Data points in the source files

### Rent / listings corpora

| Source | Count | Note |
| --- | --- | --- |
| Kaggle rent corpus — raw rows | 99,492 | `apartments_for_rent_classified_100K.csv` |
| Kaggle rent corpus — after `load_clean()` | 98,844 | de-duplicated, core-field-complete, rent-bounded |
| Zillow ZORI — ZIP-level rent series | 8,543 | `Zip_zori_uc_sfrcondomfr_sm_month.csv`, national, monthly since 2015-01 |
| Redfin sale-median series — metros nationally | 943 | 85,310 raw metro-month rows, filtered to 4 metros → 408 rows |
| Comps indexed in ChromaDB | 3,880 | one document per listing, 4 markets |

The comp index by state: **CA 2,372 · IL 631 · OH 606 · NY 271**, across 10 distinct city
names. **448 of the 3,880 comps carry address-level coordinates; 3,432 are area-level** —
the ratio the `comps_spatially_concentrated` and location-precision disclosures exist to
report.

### Geography

| Source | Count | Note |
| --- | --- | --- |
| Census ZCTA boundary polygons | 33,791 | `cb_2020_us_zcta520_500k`, coordinate → 5-digit ZIP |
| Census county boundaries | all US counties | `cb_2023_us_county_500k`, TIGER/Line 2023, coordinate → county FIPS |
| HUD FMR — geographic key | county (`entityid`) | SAFMR ZIP schedules for the 3 inference counties: **LA 475, Cook 371, Cuyahoga 127** (FY2026) |

⚠ The previous revision gave the HUD counts as 474 / 370 / 126 — each exactly one low.
Re-counted from the cached FY2026 `basicdata` responses, they are 475 / 371 / 127, and
every entry carries a distinct `zip_code` (no summary row inflating the count).

### Benchmarks and panels

| Source | Count | Note |
| --- | --- | --- |
| ZIP-level sale-price benchmarks | 304 ZIPs | New York 164 (27,309 sales) + Chicago 140 (17,672 sales), county-assessor records since 2023-01-01, table built 2026-08-30 |
| — of those, live at the shipped `SALE_BENCHMARK_MIN_SALES = 20` | 222 ZIPs | New York 136 (27,112 sales) + Chicago 86 (17,250 sales) |
| FMR cohort panel (U6 rent-growth screen) | 10 HUD FMR areas | `fmr_cohort_panel.json`, FY2017–FY2026 |

The 82 ZIPs between the two rows are in the committed table but below the minimum-sales
threshold, so `sale_benchmarks.lookup()` declines them and the report says why. The
threshold is applied at lookup rather than at build time precisely so this row can move
without rebuilding from three municipal APIs.

Decision #11's writeup quotes 18,251 sales for Chicago; the committed table sums to
**17,672** and is the figure the system reads.

### Metro scopes — four separate lists, deliberately not the same set

`config.py` keeps four different metro lists, each answering a different question. The
point is *which* metros are in each, so every list is spelled out below rather than left
as a count.

| List (`config.py` name) | Size | The metros in it | What membership decides |
| --- | --- | --- | --- |
| Inference metros (`INFERENCE_METROS`) | 3 | Chicago, Los Angeles, Cleveland | The markets the pipeline is built to price end-to-end |
| Redfin target metros (`REDFIN_TARGET_METROS`) | 4 | Chicago, Los Angeles, Cleveland, **New York** | Which markets get a Redfin sale-price appreciation series and a metro-level benchmark |
| Training metros (`TRAINING_METROS`) | 6 states · 14 city-name patterns | CA: Los Angeles · OH: Cincinnati, Cleveland · IL: Chicago · NJ: Newark, Jersey City · NY: New York, Brooklyn, Queens, Bronx, Staten Island, Manhattan · PA: Pittsburgh, Philadelphia | Which Kaggle listings the rent regression learns from — a deliberate superset of the inference trio, because the model predicts a *ratio* and benefits from markets it will never price |
| Indexed markets (`INDEXED_MARKETS`) | 4 markets · 9 city-name patterns | Chicago, Los Angeles, Cleveland, **New York** (+ its five boroughs as separate patterns) | Which markets' listings sit in the Chroma comp index — New York added on purpose as the sparse-comps test case |

⚠ The previous revision described `TRAINING_METROS` as "8 metros across 6 states." The
states (6) and city-name patterns (14) are exact; "8 metros" was a judgment call about how
to collapse the five New York boroughs and the two New Jersey cities, and it is not
recoverable from `config.py`. Stated as states and patterns instead, which is.

*Method:* `pandas` row counts through the project's own `kaggle_data.load_clean()` and
`redfin_data.load_redfin()` (not `wc -l` — the Kaggle CSV has quoted newlines and its
physical line count is wrong by ~500); `json.load` on the committed tables; `geopandas` on
the boundary archive; `chromadb` collection metadata; `config.py` for the scope lists.

---

## 6. Rent model

The rent estimator (U11, decisions #18 / #19). CLAUDE.md's one-line stack description
still says "scikit-learn LR model" — that is stale; it became a gradient-boosted tree
ensemble on 2026-08-30. Every figure in this section is read back from the persisted
artifact and is unchanged since the previous revision.

### Form

| Property | Value |
| --- | --- |
| Estimator | `sklearn.ensemble.GradientBoostingRegressor`, library defaults |
| Hyperparameters | `n_estimators=100`, `max_depth=3`, `learning_rate=0.1`, `loss='squared_error'` |
| Features | `bedrooms`, `bathrooms`, `square_feet` (3 structural features; no market identifier, by design) |
| Target | rent ÷ anchor **ratio**, where anchor = ZORI ZIP rent level × HUD FMR bedroom step |
| Artifact | `data/processed/rent_model.joblib`, 138 KB, trained 2026-08-30 — the one file under `data/` that is committed, so a fresh clone runs without a training pass |

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
| Units delivered | 10 (U1–U9, U11) — U10 folded into U8 on 2026-08-26 |
| pytest tests collected | 107 |
| Changelog | 60 dated entries, 365 rows |

⚠ Two corrections here. **Units:** the previous revision said "11 (U1–U11)"; there are 11
unit *numbers* but 10 units, because U10 was folded into U8 and never shipped under its
own name. **Changelog:** the previous revision said "52 dated entries, 445 rows"; 445 was
the total count of table *lines* including each entry's header and separator row, not data
rows. The changelog now holds 485 table lines = 60 headers + 60 separators + **365 data
rows** across **60** dated `##` entries. On the same method the previous revision's true
figures were 49 entries and 347 rows, so the file grew by 11 entries and 18 rows in the
final four days.

*Method:* `nodes.ALL_NODES` and `graph.NODE_FUNCTIONS` member counts, `state.FlagKind`
member count, `grep` on `implementation_plan.md` / `changelog.md`, `pytest --collect-only`.

---

## 8. What is not derivable from the repository

- **Cost against budget.** The project constraint is a $100 ceiling. Actual OpenRouter +
  paid-API spend is not recorded anywhere in the repo and has to come from the OpenRouter
  dashboard. Worth stating in the report alongside the 70% replay-determinism figure,
  which is the mechanism that kept it low: a demo or an eval batch re-run costs no quota.
- **Decision churn.** 22 decisions across 30 days, several re-opened — #16's rent half
  superseded by #21, #6 / #20 / #22 each held on measurement rather than on argument. A
  "decisions revisited" count would speak directly to the "correcting past mistakes is
  worth the time-investment" working principle, but it needs a reading of
  `decision_log.md` rather than a count.

---

## ⚠ One thing to fix before the repository is read publicly

`docs/private/checkpoints/final/capstone_demo_text.md` is **tracked and pushed to
`origin/main`**, despite `docs/private/` being listed in `.gitignore` — `.gitignore` does
not apply to a file that has already been added. It entered in commit `cc09afe`. Every
other file under `docs/private/` is correctly untracked.

To untrack it while keeping the local copy:

```
git rm --cached docs/private/checkpoints/final/capstone_demo_text.md
git commit -m "Untrack a checkpoint document that belongs under docs/private/"
git push
```

Note that this removes it from the tip of `main` but **not** from history — commits
`cc09afe` onward still contain it, and it remains retrievable from the GitHub remote.
Whether that matters depends on what the file contains; if it needs to be gone entirely,
history has to be rewritten and force-pushed.
