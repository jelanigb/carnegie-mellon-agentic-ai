"""Generates docs/diagrams/agent_logic_flow.md.

The panels are Unicode box-drawing characters (U+2500–U+257F) on a fixed column grid.
Hand-editing them means recounting spaces every time a label changes, so the columns are
placed programmatically instead: `place()` puts text at named 0-indexed columns and
asserts on overlap, and every box shares one interior width so panels line up with each
other down the page.

Run from `src/`'s parent (the repo root):  python3 docs/diagrams/agent_logic_flow_gen.py
"""

from __future__ import annotations

import io

W = 60  # interior width of every box


def _frame(lines, indent, tl, tr, bl, br, h, v):
    pad = " " * indent
    out = [pad + tl + h * W + tr]
    for line in lines:
        assert len(line) <= W, (len(line), line)
        out.append(pad + v + line.ljust(W) + v)
    out.append(pad + bl + h * W + br)
    return out


def box(lines, indent=4):
    return "\n".join(_frame(lines, indent, "┌", "┐", "└", "┘", "─", "│"))


def dbl(lines, indent=4):
    return "\n".join(_frame(lines, indent, "╔", "╗", "╚", "╝", "═", "║"))


def place(*pairs):
    """place((col, text), ...) -> one line with each text starting at that column."""
    s: list[str] = []
    for col, text in pairs:
        while len(s) < col:
            s.append(" ")
        assert len(s) == col, f"overlap at col {col}"
        s.extend(text)
    return "".join(s).rstrip()


def centered(col, text):
    return (col - len(text) // 2, text)


def sep(label, col, tail="", after=6):
    s = "  " + label + " "
    s = s + "─" * (col - len(s)) + "▼" + "─" * after
    return s + ("  " + tail if tail else "")


# ------------------------------------------------------------------ The scaffold

SW = 64   # interior width of a stage box
IND = 6   # left indent, so the connector sits under the box centre
CONN = IND + 1 + SW // 2


def stage(title, sub, entry=False):
    """One stage box: a heading over one or more lines of sub-headline."""
    subs = [sub] if isinstance(sub, str) else list(sub)
    lines = ["  " + title] + ["  " + t for t in subs]
    return dbl(lines, indent=IND) if entry else box(lines, indent=IND)


RAIL = 2  # column the loop-back edge runs up


def chain(stages):
    """Stack stages vertically, joined by a single connector.

    Returns the lines plus each stage's (first, last) row, so `loop_back` can find the
    rows it needs to draw a back edge between.
    """
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    for i, s in enumerate(stages):
        if i:
            out.append(place((CONN, "│")))
            out.append(place((CONN, "▼")))
        start = len(out)
        out.extend(s.split("\n"))
        spans.append((start, len(out) - 1))
    return out, spans


def _overlay(line, col, text):
    line = line.ljust(col + len(text))
    return line[:col] + text + line[col + len(text):]


def loop_back(lines, spans, frm, to, back_label, fwd_label):
    """Draw a back edge from below stage `frm` up into the left edge of stage `to`."""
    junction = spans[frm][1] + 2          # after the box, after its connector
    lines.insert(junction, place((RAIL, "└" + "─" * (CONN - RAIL - 1) + "┤"),
                                 (CONN + 3, back_label)))
    lines[junction + 1] = _overlay(lines[junction + 1], CONN + 3, fwd_label)

    title = spans[to][0] + 1              # the target box's heading row
    lines[title] = _overlay(lines[title], RAIL, "┌──►")
    for r in range(title + 1, junction):
        lines[r] = _overlay(lines[r], RAIL, "│")
    return "\n".join(lines)


def stack(stages):
    lines, _ = chain(stages)
    return "\n".join(lines)


# ------------------------------------------------------------------ Planner
_saved_W = W
W = SW
planner = stack(
    [
        stage("ENTRY POINT", "first pass, or rework pass from the Critic", entry=True),
        stage("REASON", "decide whether the Extractor is needed"),
        stage("ACT", "construct the plan"),
        stage("OBSERVE", "increment counters"),
        stage("EXIT", "plan lands on `state`", entry=True),
    ]
)
W = _saved_W

# ------------------------------------------------------------------ Extractor
_saved_W = W
W = SW
extractor = stack(
    [
        stage("ENTRY POINT", "from the Planner", entry=True),
        stage("REASON", "decide what the listing states, infers, or omits"),
        stage("ACT", "LLM term extraction; geocoding to derive coordinates + county"),
        stage("OBSERVE", "check schema validity, geocoding tier, missing fields"),
        stage("DECIDE", "raise a disclosure + question per gap"),
        stage("EXIT", "deal terms and disclosures land on `state`", entry=True),
    ]
)
W = _saved_W

# ------------------------------------------------------------------ Comps Retrieval
_saved_W = W
W = SW
_stages, _spans = chain(
    [
        stage("ENTRY POINT", "from the Planner, or from the Extractor", entry=True),
        stage("REASON", "set the comp match criteria"),
        stage("ACT", "query the vector store"),
        stage("OBSERVE", "count the comps that qualify"),
        stage("DECIDE", "stop, or relax one criterion and search again"),
        stage("DISCLOSE", "grade the set: too few, too clustered, too loose"),
        stage("EXIT", "comps and disclosures land on `state`", entry=True),
    ]
)
comps = loop_back(_stages, _spans, frm=4, to=1,
                  back_label="not enough", fwd_label="enough, or cap reached")
W = _saved_W


# ------------------------------------------------------------------ Valuation & Rent
_saved_W = W
W = SW
valuation = stack(
    [
        stage("ENTRY POINT", "from Comps Retrieval", entry=True),
        stage(
            "REASON",
            [
                "validate 4 preconditions needed for rent calculation;",
                "exit early + disclose if failed",
            ],
        ),
        stage("ACT", "predict the rent-to-anchor ratio; multiply by today's anchor"),
        stage("OBSERVE", "restate comp rents in current dollars; compare the median"),
        stage("DECIDE", "emit the estimate + every approximation it rests on"),
        stage("EXIT", "rent estimate and disclosures land on `state`", entry=True),
    ]
)
W = _saved_W

# ------------------------------------------------------------------ Scenario Forecast
_saved_W = W
W = SW
forecast = stack(
    [
        stage("ENTRY POINT", "from Valuation & Rent", entry=True),
        stage(
            "REASON",
            [
                "validate 4 preconditions needed for forward projection;",
                "exit early + disclose if failed",
            ],
        ),
        stage(
            "ACT",
            [
                "depth 1: score 4 framings, prune",
                "depth 2: score 9 pairings under the survivors, prune",
            ],
        ),
        stage("RECONCILE", "label optimistic / base / pessimistic"),
        stage("OBSERVE", "check the 3 scenarios are materially distinct"),
        stage("DECIDE", "emit scenarios + a ledger of every hypothesis rejected"),
        stage("EXIT", "scenarios and disclosures land on `state`", entry=True),
    ]
)
W = _saved_W

# ------------------------------------------------------------------ Critic
_saved_W = W
W = SW
critic = stack(
    [
        stage("ENTRY POINT", "from Scenario Forecast", entry=True),
        stage("REASON", "evaluate upstream outputs; weight accumulated disclosures"),
        stage(
            "ACT",
            [
                "run consistency checks; generate confidence score;",
                "set the deal verdict; LLM cross-check",
            ],
        ),
        stage("OBSERVE", "compare score to threshold; check the rework budget"),
        stage("DECIDE", "report, rework, or escalate"),
        stage("EXIT", "confidence, verdict + disclosures land on `state`", entry=True),
    ]
)
W = _saved_W

# ------------------------------------------------------------------ Summarizer
_saved_W = W
W = SW
summarizer = stack(
    [
        stage("ENTRY POINT", "from the Critic or Human Review", entry=True),
        stage("OBSERVE", "take stock of what the run established and what it did not"),
        stage("ACT", "render escalation, findings, comp evidence (disclosure-first)"),
        stage("EXIT", "report markdown + run status land on `state`", entry=True),
    ]
)
W = _saved_W

DOC = """# Agent logic flow — internal diagrams

One panel per specialist agent, showing what happens *inside* the node rather than how the
nodes connect. Graph-level topology lives in `deal_evaluator_graph.png`; this file is the
other half of that picture.

Every panel uses the same four-stage scaffold — **Reason, Act, Observe, Decide** — that the
agents' own docstrings are written to. Double-ruled boxes are the graph boundary —
where control enters the agent and where it leaves.

Seven specialists: Planner, Extractor, Comps Retrieval, Valuation & Rent, Scenario
Forecast, Critic, Summarizer. `human_review` is a graph node but not a specialist — it
makes no estimate and reaches no conclusion — so it has no panel here.

Panels are Unicode box-drawing characters, generated by `agent_logic_flow_gen.py` so the
columns stay aligned. Edit the generator, not this file.

---

## 1 · Planner

Source: `src/agents/planner.py` · plan of record §3, decision #9

```
%s
```

- Logic for extractor calls is dependent on caller + available data; multiple callers
  have access to Planner.

---

## 2 · Extractor

Source: `src/agents/extractor.py` · plan of record §3, Checkpoint 2.1 Loop 1

```
%s
```

- A caller supplying complete terms but no geography takes a model-free path that only
  geocodes.
- Retry exhaustion writes no deal terms at all, rather than a half-parsed set.
- Values the model inferred rather than read are recorded as assumptions, with the basis
  for each.

---

## 3 · Comps Retrieval

Source: `src/agents/comps_retrieval.py` · plan of record §3, Checkpoint 2.1 Loop 2

```
%s
```

- Relaxation concedes one criterion per pass, in a fixed order: square-footage band,
  then radius, then bedroom tolerance.
- Reaching the iteration cap exits with whatever was found, plus a disclosure.
- Two conditions skip the loop entirely: retrieval disabled for the ablation run, or a
  subject with no coordinates.

---

## 4 · Valuation & Rent

Source: `src/agents/valuation_rent.py` · plan of record §2, decision #19

```
%s
```

- Any of four unmet preconditions — no trained model, missing bed/bath/sqft, no county,
  no local schedule — exits with a named disclosure and no rent figure at all.
- Rent is always a modelled ratio times a current local reference, never an average of
  comp rents.
- The comps are a cross-check on the estimate, not an input to it.

---

## 5 · Scenario Forecast

Source: `src/agents/scenario_forecast.py` · plan of record §4, decisions #16 and #21

```
%s
```

- The search space is enumerated rather than sampled, so the run stays deterministic
  end to end.
- Only the first two levels are a search; the labels are assigned by arithmetic.
- A near-tie at the top means the selection was arbitrary, and the report says so.
- Rent and price project from separate series, ZORI and Redfin, and are never mixed.

---

## 6 · Critic

Source: `src/agents/critic.py` · plan of record §3, §5

```
%s
```

- Two independent outputs: a confidence score about the system, and a verdict about the
  deal.
- The verdict is set by rule; a second LLM reading can annotate it but never change it.
- Escalation is decided here but acted on by the outgoing edge, so no agent invokes
  another.

---

## 7 · Summarizer

Source: `src/agents/summarizer.py` · plan of record §1, §6

```
%s
```

- Disclosures print above the numbers they qualify, and every one is rendered rather
  than counted.
- A section with no data says so rather than disappearing.
- Nothing is re-derived here; a Summarizer that computed could disagree with the agent
  that did.
- The run closes as complete, except that a reviewed deal keeps its reviewed status.
""" % (planner, extractor, comps, valuation, forecast, critic, summarizer)

if __name__ == "__main__":
    with io.open("docs/diagrams/agent_logic_flow.md", "w", encoding="utf-8") as f:
        f.write(DOC)
    print("wrote docs/diagrams/agent_logic_flow.md")
