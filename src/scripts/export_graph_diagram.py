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

Two files are written. The `.mmd` source is the authoritative artifact and is produced
offline. The `.png` is a convenience for the report and the video and requires a network
call to mermaid.ink; failure to render it is reported and does not fail the export.
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

# The one loop-closing edge decision #9 permits, as a (source, target) pair.
EXPECTED_CYCLE = (nodes.CRITIC, nodes.PLANNER)

# LangGraph's entry sentinel. Traversal starts here rather than at an arbitrary node so
# that "reachable" means reachable in a real run.
START_NODE = "__start__"

# The two nodes decision #9 permits to branch. Everything else is a static edge,
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


def verify_topology(drawable) -> list[str]:
    """Check the compiled graph against decision #9. Returns a list of violations."""
    edges = _edge_pairs(drawable)
    violations: list[str] = []

    back_edges = _find_back_edges(edges, START_NODE)
    if back_edges != {EXPECTED_CYCLE}:
        violations.append(
            f"Loop-closing edges are {sorted(back_edges)}; decision #9 permits only "
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
            f"Branching nodes are {sorted(branching)}; decision #9 permits only "
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
    MMD_PATH.write_text(drawable.draw_mermaid())
    print(f"\nWrote {MMD_PATH.relative_to(Path.cwd()) if MMD_PATH.is_relative_to(Path.cwd()) else MMD_PATH}")

    try:
        PNG_PATH.write_bytes(drawable.draw_mermaid_png())
        print(f"Wrote {PNG_PATH}")
    except Exception as exc:  # noqa: BLE001 - rendering is a convenience, not the artifact
        print(f"PNG render skipped ({type(exc).__name__}: {exc}).")
        print("The .mmd source above is the authoritative diagram; PNG rendering calls "
              "mermaid.ink and needs network access.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
