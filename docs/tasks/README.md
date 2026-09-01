# Unit task lists

**One file per unit, so a session loads only the unit it is working on.** This split was
made Aug 24, 2026: a single `task_list.md` meant every session paid the context cost of
every completed unit's plan, and completed plans are exactly the thing a session does not
need.

| File | Unit | Status |
| --- | --- | --- |
| [`task_list_u7.md`](task_list_u7.md) | U7 — Critic / Reviewer | ✅ complete (Aug 27, 2026) |
| [`task_list_u8.md`](task_list_u8.md) | U8 — Evaluation harness | ✅ closed Aug 31, 2026 — U8.M's remainder carried into U9.M rather than left behind |
| [`task_list_u11.md`](task_list_u11.md) | U11 — Rent model v2 | ✅ complete Aug 31, 2026 — U11.5 landed inside U8's close-out |
| [`task_list_u9.md`](task_list_u9.md) | U9 — Summarizer polish + Streamlit demo surface | 🟨 in progress — U9.1, U9.2 done Aug 31, 2026 |
| [`maintenance.md`](maintenance.md) | Not tied to a unit | standing |

Units U1–U6 predate this workflow and have no task file; what they built is in
[`../history/changelog.md`](../history/changelog.md) and why is in
[`../history/decision_log.md`](../history/decision_log.md). Add a file here when a unit
starts, named `task_list_<unit>.md`.

**Per-unit work breakdown, written before coding starts and approved before it does.**
Part of the workflow in
[`engineering_standards.md`](../design/engineering_standards.md#how-a-unit-is-built).

Conventions:

- **Each `###` subsection is one change set** — one commit, reviewable on its own.
- **Maintenance is its own subsection**, never folded into a behavioural one.
- **Unit-level open questions come first** and name the subsection they block. Anything
  that would change the design gets answered before that subsection starts, not during it.
- A subsection may land the system in a **temporarily incomplete state** if the completing
  subsection is named here.
- **A finished unit's file stays here** rather than being trimmed or deleted — it is
  the record of what was planned against what shipped, and it costs nothing now that
  a session loads only the unit it is on. Mark its row above as complete.
