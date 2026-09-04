"""Export the architecture diagram from the compiled graph.

Run: .venv/bin/python scripts/export_graph_diagram.py

§3 rationale item 3: the diagram is *generated from the graph*, so documentation cannot
silently drift from the system it describes. That is the whole point — a hand-drawn
diagram is a claim about the code, while this one is a rendering of it. The hand-drawn
placeholder in `docs/private/lang_graph_onboarding.md` §4 was labelled "delete at U2"
for exactly this reason, and keeping both would reintroduce the drift the generated one
prevents.

That also makes this script a **review instrument**, not only an illustration. Decision
#9 commits the design to three checkable properties, and this script asserts all three
rather than leaving them to be eyeballed:

  1. `Critic → Planner` is the only loop-closing (back) edge in the graph.
  2. Exactly two nodes have conditional (multi-target) outgoing edges.
  3. Every node declared in `nodes.ALL_NODES` is actually reachable and registered.

A failure here means the topology drifted from the decision, which is a design defect
surfaced before review rather than during it.

Four files are written: a top-down pair and a left-right pair. The `.mmd` sources are the
authoritative artifacts and are produced offline. The `.png`s are a convenience for the
report and the video and require a network call to mermaid.ink; failure to render one is
reported and does not fail the export.

**Why a second orientation exists.** LangGraph emits `graph TD`, which renders this
eight-node pipeline as a 277x928 strip — correct, and unusable in a README or on a 16:9
slide, where it becomes a thin column down the page. The left-right variant is the same
graph with its flow direction rewritten (`_to_left_right`), so both files still derive
from the compiled graph and neither can drift from it. That is the whole reason the
orientation is a transform on generated text rather than a hand-drawn second diagram.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nodes
from graph import build_graph

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "diagrams"
MMD_PATH = OUT_DIR / "deal_evaluator_graph.mmd"
PNG_PATH = OUT_DIR / "deal_evaluator_graph.png"
MMD_LR_PATH = OUT_DIR / "deal_evaluator_graph_lr.mmd"
PNG_LR_PATH = OUT_DIR / "deal_evaluator_graph_lr.png"

# What LangGraph emits, and what the wide variant rewrites it to. Kept as constants
# because they are the only two strings that make the two files different.
MERMAID_TOP_DOWN = "graph TD;"
MERMAID_LEFT_RIGHT = "graph LR;"

# The one loop-closing edge decision #9 (Planner topology) permits, as a (source, target) pair.
EXPECTED_CYCLE = (nodes.CRITIC, nodes.PLANNER)

# LangGraph's entry sentinel. Traversal starts here rather than at an arbitrary node so
# that "reachable" means reachable in a real run.
START_NODE = "__start__"

# The two nodes decision #9 (Planner topology) permits to branch. Everything else is a static edge,
# because the pipeline order is forced by data dependency.
EXPECTED_BRANCHING_NODES = {nodes.PLANNER, nodes.CRITIC}


def _edge_pairs(drawable) -> list[tuple[str, str]]:
    return [(edge.source, edge.target) for edge in drawable.edges]


def _find_back_edges(edges: list[tuple[str, str]], start: str) -> set[tuple[str, str]]:
    """Every edge that closes a loop — i.e. points back to a node already on the path.

    **Back edges, not simple cycles**, and the distinction is the reason this function
    was rewritten on first run. Counting simple cycles reported *two* against a graph
    that has exactly one loop-closing edge: the Planner's skip branch means
    `planner → extractor → comps → … → critic → planner` and
    `planner → comps → … → critic → planner` are two distinct simple cycles traversing
    the same single `critic → planner` back edge. Decision #9's claim — "`Critic →
    Planner` is the only cycle" — is about that back edge, and simple-cycle count grows
    combinatorially with every legal skip branch added, so it was measuring branch
    count as if it were loop count.

    The check is stated in back edges because that is what the design decision actually
    constrains: one back edge is one place the graph can loop, whatever the number of
    routes into it.

    Written out rather than pulled from `networkx` — the graph has eight nodes, and a
    dependency for a twenty-line traversal is a poor trade on a project whose stated
    constraint is review capacity.
    """
    adjacency: dict[str, list[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)

    back_edges: set[tuple[str, str]] = set()
    finished: set[str] = set()

    def walk(node: str, on_path: set[str]) -> None:
        on_path = on_path | {node}
        for neighbour in adjacency.get(node, []):
            if neighbour in on_path:
                back_edges.add((node, neighbour))
            elif neighbour not in finished:
                walk(neighbour, on_path)
        finished.add(node)

    walk(start, set())
    return back_edges


def _to_left_right(mermaid: str) -> str:
    """The same diagram, flowing left to right.

    A single-token rewrite of the flow-direction header, deliberately: everything else in
    the file — nodes, edges, edge styles, the class definitions LangGraph emits — is
    orientation-independent, so a transform that touched anything more would be editing
    the topology rather than the layout of it.

    Raises rather than silently returning the input if the header is not where it is
    expected. A wide diagram that is quietly the tall one is exactly the drift this whole
    script exists to prevent, and it would be invisible in review — the file would be
    present, non-empty, and wrong.
    """
    if MERMAID_TOP_DOWN not in mermaid:
        raise ValueError(
            f"Expected {MERMAID_TOP_DOWN!r} in the generated mermaid source; LangGraph's "
            f"emitted header has changed and the left-right rewrite no longer applies."
        )
    return mermaid.replace(MERMAID_TOP_DOWN, MERMAID_LEFT_RIGHT, 1)


def _render_png(mermaid: str, path: Path) -> None:
    """Render one mermaid source to PNG, reporting failure rather than raising.

    Rendering calls mermaid.ink over the network. That makes it the one part of this
    script that can fail for reasons having nothing to do with the graph, so it is
    isolated here and treated as a convenience — the `.mmd` beside it is the artifact.

    The import is local for the same reason the failure is caught: this helper is the
    only thing in the export that depends on a LangChain rendering path, and a rename
    upstream should degrade the PNG rather than take the topology check with it.
    """
    from langchain_core.runnables.graph_mermaid import draw_mermaid_png

    try:
        path.write_bytes(draw_mermaid_png(mermaid))
        print(f"Wrote {path}")
    except Exception as exc:  # noqa: BLE001 - rendering is a convenience, not the artifact
        print(f"PNG render skipped for {path.name} ({type(exc).__name__}: {exc}).")
        print("The .mmd source is the authoritative diagram; PNG rendering calls "
              "mermaid.ink and needs network access.")


def verify_topology(drawable) -> list[str]:
    """Check the compiled graph against decision #9 (Planner topology). Returns a list of violations."""
    edges = _edge_pairs(drawable)
    violations: list[str] = []

    back_edges = _find_back_edges(edges, START_NODE)
    if back_edges != {EXPECTED_CYCLE}:
        violations.append(
            f"Loop-closing edges are {sorted(back_edges)}; decision #9 (Planner topology) permits only "
            f"{EXPECTED_CYCLE}. A second one means the topology drifted toward the "
            f"supervisor pattern that decision rejected."
        )

    out_degree: dict[str, int] = {}
    for source, _ in edges:
        out_degree[source] = out_degree.get(source, 0) + 1
    branching = {
        source for source, degree in out_degree.items()
        if degree > 1 and source in nodes.ALL_NODES
    }
    if branching != EXPECTED_BRANCHING_NODES:
        violations.append(
            f"Branching nodes are {sorted(branching)}; decision #9 (Planner topology) permits only "
            f"{sorted(EXPECTED_BRANCHING_NODES)}."
        )

    registered = {name for name in drawable.nodes if name in nodes.ALL_NODES}
    missing = set(nodes.ALL_NODES) - registered
    if missing:
        violations.append(f"Declared in nodes.ALL_NODES but absent from the graph: {sorted(missing)}")

    return violations


def main() -> int:
    graph = build_graph()
    drawable = graph.get_graph()

    print("Compiled graph")
    print(f"  nodes: {len(drawable.nodes)}")
    for source, target in sorted(_edge_pairs(drawable)):
        print(f"    {source} -> {target}")

    violations = verify_topology(drawable)
    print()
    if violations:
        print("TOPOLOGY CHECK: FAILED")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("TOPOLOGY CHECK: passed")
    print(f"  exactly one loop-closing edge: {EXPECTED_CYCLE[0]} -> {EXPECTED_CYCLE[1]}")
    print(f"  branching nodes: {sorted(EXPECTED_BRANCHING_NODES)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    top_down = drawable.draw_mermaid()
    left_right = _to_left_right(top_down)

    print()
    for path, source in ((MMD_PATH, top_down), (MMD_LR_PATH, left_right)):
        path.write_text(source)
        print(f"Wrote {path}")

    for path, source in ((PNG_PATH, top_down), (PNG_LR_PATH, left_right)):
        _render_png(source, path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
