**§9 of the plan of record — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#20) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the **decisions register in §7**,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**Status:** built and verified against the live API, Aug 8, 2026. `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py`, `requirements.txt`, and a dedicated `.venv/` all exist
under `src/` as planned below.

**What the real pull found (corrects an assumption in §2):** the smoke test ran
`get_fmr` for all three candidate counties at both `year=2019` (Kaggle vintage) and
`year=None` (resolved to 2026, the current FY) —

| County | entityid | SAFMR? | 2BR FMR, 2019 | 2BR FMR, 2026 |
| --- | --- | --- | --- | --- |
| New York County, NY | `3606199999` | **No** — flat shape | $1,831 | $2,910 |
| Cook County, IL | `1703199999` | **Yes** — SAFMR list shape | $1,212 | $1,781 |
| Philadelphia County, PA | `4210199999` | **Yes** — SAFMR list shape | $1,200 | $1,810 |

§2 had hypothesized New York was the likely SAFMR metro among the three — reality is
the opposite: New York is flat, and Chicago/Philadelphia are the SAFMR ones. Both
correctly fell back to the `"MSA level"` entry (metro-level default, no `zip_code`
passed), confirming the SAFMR branch is genuinely exercised, not just written
defensively. Cache verified too: an immediate repeat call returned in 0.000s (cache
hit, no second HTTP request).

> **Superseded in part (Aug 8, 2026, later the same day).** Two things changed. The
> inference trio became **Chicago, Los Angeles, Cleveland** (§2 — the NY/Philadelphia
> hypothesis failed a data-density check). More importantly, the framing above — "is
> this county SAFMR?" — is itself wrong: **SAFMR is a property of a county-year**, and
> the same county returns different shapes for 2019 and 2026. See §2 for the measured
> table. This section's data remains valid evidence that the client authenticates and
> handles both response shapes; it should not be read as establishing a fixed SAFMR
> status for any county. U1 confirmed the trio's entityids and both shapes.

**Scope:** deliberately narrow — just the client and a real smoke-test pull, so a
working HUD data pull exists as soon as possible. Explicitly **not** included here:
`config.py`, `state.py`, `agents/`, `tests/`, or the rest of the scaffold — those are
U1 (§7). Kaggle and Redfin data already sit in `data/` (repo root) and don't depend on
any of this.

**Files added:**

```
src/
├── requirements.txt          # requests, python-dotenv
├── .venv/                    # gitignored — dedicated virtualenv for this project
├── tools/
│   ├── __init__.py
│   └── hud_fmr.py            # the client
└── scripts/
    └── pull_fmr_sample.py    # runnable smoke test — a real pull, not a mock
```

**Auth:** a bearer token from a free HUD User account, supplied via the `HUD_FMR_TOKEN`
environment variable with an untracked local file as a fallback. Credentials are never
committed and are not described further here.

**Base URL:** `https://www.huduser.gov/hudapi/public`

**Endpoints wrapped:**

| Function | Endpoint | Purpose |
| --- | --- | --- |
| `list_states()` | `GET /fmr/listStates` | state code ↔ name lookup |
| `list_counties(state_code)` | `GET /fmr/listCounties/{state_code}` | county name → 10-digit FIPS `entityid` lookup |
| `get_fmr(entityid, year=None)` | `GET /fmr/data/{entityid}?year={year}` | raw FMR record for one county/metro + one fiscal year; omitting `year` returns the latest available and the response's own `year` field is read back rather than assumed |
| `get_fmr_for_bedroom(entityid, bedrooms, year=None, zip_code=None)` | wraps `get_fmr` | single rent figure for a given bedroom count |

**Behavior:**

1. **SAFMR response-shape handling — metro-level by default.** `get_fmr` inspects
   whether the response's `basicdata` is a flat dict (ordinary metro/county) or a
   list (Small Area FMR — ZIP-keyed entries plus one `"MSA level"` entry), per §2's
   HUD FMR API notes. Both shapes are normalized into one consistent return shape so
   callers never need to branch on it. **`zip_code` defaults to `None`, so the result
   is always metro-level**, matching the Kaggle and Redfin data (§2) — for a
   non-SAFMR county there's only ever one metro-wide record anyway, and for a SAFMR
   county the client falls back to the `"MSA level"` entry and reports
   `used_msa_fallback=True`. Passing an explicit `zip_code` (if it matches an entry)
   is supported so the SAFMR branch neither errors nor silently misparses, though no
   current caller uses it. It is retained deliberately: ZIP-level lookup is the natural
   extension point if the deferred ZIP-tier work in §2 is ever taken up, and the branch
   is cheaper to keep correct now than to reconstruct later.
2. **Bedroom cap.** `get_fmr_for_bedroom` caps at `four_bedroom` for `bedrooms >= 4`
   and returns `bedroom_cap_exceeded=True` in the result rather than raising. Turning
   this into an actual `Flag` (`kind="fmr_bedroom_cap_exceeded"`) is the Valuation &
   Rent agent's job once `state.py` exists — out of scope for this client.
3. **Year resolution.** Every result carries the `year` HUD actually returned, never
   the caller's requested year, so downstream code can't silently assume a stale or
   wrong year was honored.
4. **Local caching.** On-disk JSON cache at `data/raw/hud_fmr_cache.json` (repo root,
   already gitignored), keyed by `(endpoint, entityid, year)`. Avoids re-hitting the
   API for repeat lookups during dev and later training-data prep.
5. **Rate limiting.** A client-side throttle enforces HUD's 60 requests/minute cap
   (simple minimum interval between calls); cache hits bypass the throttle entirely
   since they never hit the network.
6. **Errors.** A small `HudFmrApiError` is raised on non-200 responses (status +
   body included). No silent state/national-average fallback is implemented yet —
   that logic belongs to the Valuation & Rent agent's flag-aware design in §2, which
   needs `Flag`/`DealState` to exist first.

**Smoke test (`scripts/pull_fmr_sample.py`):** pulls real FMR data for 2-3 counties
across the candidate metros (New York City, Cook County/Chicago, Philadelphia County)
across two years — one Kaggle-vintage year (e.g. 2018) and the current/latest year
(via `year=None`) — and prints/saves the parsed result. This is meant to produce
visible proof the client authenticates correctly and actually exercises both response
shapes, not just pass a unit test against fixture data.

**Verification before calling this done:**

- Real (not mocked) calls to `list_counties` and `get_fmr` succeed against the live
  API using the configured token.
- At least one of the three candidate counties returns a SAFMR (list) shape,
  confirming that code path is actually exercised.
- Running the same query twice hits the on-disk cache on the second call (no second
  HTTP request — verified via a log line or timing), and the cache file lands in
  `data/raw/`, not committed to git.
