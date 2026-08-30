"""Does the ratio the model learns hold still over time? (U11.3's standing assumption)

    .venv/bin/python scripts/anchor_stability.py

**The assumption this tests, stated plainly.** The model does not predict rent. It
predicts a *ratio* — how this unit's rent compares to the typical rent in its own ZIP —
learned from 2018-19 listings, and then multiplies **today's** ZIP-level market rent by
it. That is only valid if a property's position relative to its neighbors is stable over
the ~7 years in between. A 950 sqft two-bedroom that rented at 1.06x its ZIP's typical
rent in 2019 has to still rent at about 1.06x in 2026.

If that is false — if small units have gained on large ones, or the relationship between
floor area and rent has moved — the model applies a stale *structure* to a current
*level* and produces a wrong number that looks entirely ordinary. It is the same failure
shape §2 exists to prevent, one level up: U11.3 fixed the level going stale, and this
asks whether the structure can too.

**Why it cannot be answered directly, and what these two tests do instead.** Answering it
outright needs current-vintage rents for individual units, which this project does not
have — the same wall U8.0 hit. Both tests below are therefore *falsification* tests over
the corpus's own 13-month span. They can show the assumption failing cheaply; they cannot
show it holding over seven years. **A clean pass is weak evidence and is reported as
such.** A failure would be decisive.

**Test 1 — out-of-time split.** Fit on the corpus's earlier months, score on the later
ones, and compare against a random split of the same sizes. If the structure transports
across time, the two errors should be close. If the temporal split is much worse, the
learned relationship is time-dependent and a seven-year extrapolation is unsafe.

**Test 2 — the ratio by listing month.** Track `rent / anchor` across the corpus's own
window. If it wanders over 13 months it will certainly not hold over seven years. Read
per metro as well as pooled, because a shift in *which cities were scraped when* would
move the pooled figure without any property's position changing — a composition effect
masquerading as drift, which is the confound this test is most exposed to.

**The confound is measured rather than assumed**, and is reported first: if the metro mix
differs between the early and late halves, Test 1's temporal split is partly measuring
geography rather than time, and its number has to be read with that in mind.

No model calls; reads the corpus, HUD FMR (cached) and the ZORI panel. Writes nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

import config
from tools import kaggle_data
from tools.model import rent_model


def _dollar_mae(frame: pd.DataFrame, train_idx, test_idx) -> float:
    """Fit on `train_idx`, score on `test_idx`, in dollars at each row's own anchor."""
    features = list(config.RENT_MODEL_FEATURES)
    X = frame[features].to_numpy(dtype=float)
    y = frame["rent_to_anchor"].to_numpy(dtype=float)
    anchor = frame["anchor"].to_numpy(dtype=float)
    model = rent_model._estimator().fit(X[train_idx], y[train_idx])
    predicted = model.predict(X[test_idx])
    return float(np.mean(np.abs((predicted - y[test_idx]) * anchor[test_idx])))


def main() -> None:
    frame, report = rent_model.build_training_frame()
    frame = frame.sort_values("month").reset_index(drop=True)
    months = sorted(frame["month"].unique())
    print(f"Frame {len(frame):,} rows, {len(months)} months "
          f"({months[0][:7]} to {months[-1][:7]}), estimator "
          f"{config.RENT_MODEL_ESTIMATOR}\n")

    # Split at the median row rather than the median date, so the halves are equal in
    # size and the comparison against a 50/50 random split is like-for-like.
    cut = len(frame) // 2
    early, late = np.arange(cut), np.arange(cut, len(frame))
    print(f"=== Composition check — is a temporal split also a geographic one? ===")
    print(f"  {'metro':<14} {'early':>8} {'late':>8}   split at {frame.loc[cut, 'month'][:7]}")
    drift_pp = 0.0
    for state, patterns in config.INDEXED_MARKETS.items():
        mask = (frame["state"] == state) & frame["cityname"].apply(
            lambda c, p=patterns: kaggle_data.city_matches(c, p)
        )
        share_early = float(mask.to_numpy()[early].mean())
        share_late = float(mask.to_numpy()[late].mean())
        drift_pp = max(drift_pp, abs(share_early - share_late) * 100)
        print(f"  {patterns[0]:<14} {share_early:>7.1%} {share_late:>7.1%}")
    print(f"  Largest shift: {drift_pp:.1f} percentage points."
          + ("  Small — Test 1 is measuring time, not geography."
             if drift_pp < 10 else
             "  LARGE — Test 1 is partly measuring geography; read it with that in mind."))

    print("\n=== Test 1 — out-of-time split against a random split of the same size ===")
    print("  Pooled, and confounded — kept because the confound is the finding:")
    forward = _dollar_mae(frame, early, late)
    backward = _dollar_mae(frame, late, early)
    random_scores = []
    splitter = KFold(n_splits=2, shuffle=True, random_state=config.RENT_MODEL_RANDOM_SEED)
    for train_index, test_index in splitter.split(frame):
        random_scores.append(_dollar_mae(frame, train_index, test_index))
    random_mae = float(np.mean(random_scores))

    print(f"  train early -> score late    ${forward:>8,.2f}")
    print(f"  train late  -> score early   ${backward:>8,.2f}")
    print(f"  random 50/50 split           ${random_mae:>8,.2f}   <- the control")
    penalty = (np.mean([forward, backward]) - random_mae) / random_mae
    print(f"  cost of extrapolating in time: {penalty:+.1%}")
    print(
        "  Close to zero would mean the structure transports across the corpus's own\n"
        "  window. Read the composition check above first: where the metro mix moves\n"
        "  between the halves, this number is mostly transfer to a different market."
    )

    # The confound removed by construction: split within each metro and pool the errors,
    # so the train and test halves have the same geographic composition and only the
    # calendar differs. This is the version of Test 1 that answers the question asked.
    print("\n  Within-metro temporal split — the same test with geography held constant:")
    pooled_temporal, pooled_random, pooled_n = [], [], 0
    for state, patterns in config.INDEXED_MARKETS.items():
        mask = (frame["state"] == state) & frame["cityname"].apply(
            lambda c, p=patterns: kaggle_data.city_matches(c, p)
        )
        rows = frame[mask].sort_values("month").reset_index(drop=True)
        if len(rows) < 200:
            print(f"    {patterns[0]:<14} n={len(rows):>5,}  too few rows to split")
            continue
        half = len(rows) // 2
        a, b = np.arange(half), np.arange(half, len(rows))
        temporal = np.mean([_dollar_mae(rows, a, b), _dollar_mae(rows, b, a)])
        control = np.mean([
            _dollar_mae(rows, tr, te)
            for tr, te in KFold(n_splits=2, shuffle=True,
                                random_state=config.RENT_MODEL_RANDOM_SEED).split(rows)
        ])
        pooled_temporal.append(temporal * len(rows))
        pooled_random.append(control * len(rows))
        pooled_n += len(rows)
        print(f"    {patterns[0]:<14} n={len(rows):>5,}  temporal ${temporal:>7,.0f}  "
              f"random ${control:>7,.0f}  {(temporal - control) / control:>+7.1%}")
    if pooled_n:
        gap = (sum(pooled_temporal) - sum(pooled_random)) / sum(pooled_random)
        print(f"    {'POOLED':<14} n={pooled_n:>5,}  cost of extrapolating in time: "
              f"{gap:+.1%}")

    print("\n=== Test 2 — the ratio by listing month ===")
    # **A minimum row count, because without one this test reads its own noise.** The
    # scrape is wildly uneven month to month — some months carry three listings — and a
    # median over three rows swings far more than any real drift would. Months below the
    # floor are printed but excluded from the spread, rather than dropped silently.
    floor = 100
    print(f"  {'month':<9} {'n':>6} {'median':>8} {'mean':>8}")
    by_month = frame.groupby("month")["rent_to_anchor"]
    for month, group in by_month:
        mark = "" if len(group) >= floor else "   (below the floor, excluded)"
        print(f"  {month[:7]:<9} {len(group):>6,} {group.median():>8.3f} "
              f"{group.mean():>8.3f}{mark}")
    counts = by_month.size()
    medians = by_month.median()[counts >= floor]
    covered = int(counts[counts >= floor].sum())
    spread = (medians.max() - medians.min()) / medians.median()
    print(f"\n  Over the {len(medians)} months carrying at least {floor} listings "
          f"({covered:,} of {len(frame):,} rows,")
    print(f"  {covered / len(frame):.0%} of the corpus): peak-to-trough spread "
          f"{spread:.1%}, median ratio {medians.median():.3f}")

    print("\n  Per metro, so a shift in which cities were scraped when cannot masquerade")
    print("  as the ratio itself moving:")
    for state, patterns in config.INDEXED_MARKETS.items():
        mask = (frame["state"] == state) & frame["cityname"].apply(
            lambda c, p=patterns: kaggle_data.city_matches(c, p)
        )
        rows = frame[mask]
        if len(rows) < 50:
            continue
        sizes = rows.groupby("month")["rent_to_anchor"].size()
        monthly = rows.groupby("month")["rent_to_anchor"].median()[sizes >= floor]
        if len(monthly) < 2:
            print(f"    {patterns[0]:<14} n={len(rows):>5,}  "
                  f"only {len(monthly)} month(s) above the floor — no spread to report")
            continue
        own = (monthly.max() - monthly.min()) / monthly.median()
        print(f"    {patterns[0]:<14} n={len(rows):>5,}  {len(monthly)} months "
              f"above the floor  spread {own:>6.1%}")


if __name__ == "__main__":
    main()
