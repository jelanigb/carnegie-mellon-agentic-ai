"""Streamlit demo surface — decision #3 (demo surface), §6 cut-list item 4, built at U9.7.

    .venv/bin/streamlit run app.py        # from src/

**Pure Python over an untouched pipeline.** This module builds no estimate and reaches
no conclusion. It selects a listing, runs the compiled graph, and renders the report the
Summarizer already produced. Everything a reader sees here is the same text `main.py`
prints, arranged for a screen instead of a terminal.

Replay by default, and the surface says which mode it is in
-------------------------------------------------------------
Every demo deal, the retrieval ablation and all three declared faults run from committed
recordings — instant, deterministic, no quota. That default is a direct answer to OQ-17,
which measured this model returning different Tree-of-Thought scores for an identical
prompt at `temperature=0`, at roughly 1 in 15-20 live attempts, on the `los-angeles` deal
specifically. **A demo that replays cannot drift mid-presentation**, and the alternative
is discovering that in front of an audience.

A pasted listing has no recording by construction, so it runs live. The surface states
that before it runs rather than after, which is the same Transparent Degradation rule the
pipeline follows, applied to the surface itself.

Two renderings would be one too many
--------------------------------------
The report is rendered **as the Summarizer emitted it**, split at its own `##` headings so
each section can collapse. The app never re-lays-out the evidence from state, and the one
place it reads typed state — the status strip — displays figures the report also prints
rather than deriving new ones.

That is deliberate and it is the design U9.4 declined on timeline, taken here for a
different reason: two renderings of the same evidence drift the first time either is
edited, and the report is the artifact under review. Progressive detail is bought
mechanically, by splitting text, rather than by re-authoring it.

Streamlit mechanics, named because they are how these demos break
-------------------------------------------------------------------
1. **The script re-runs top to bottom on every interaction.** So the graph is invoked only
   from an explicit button press and its result is held in `st.session_state`; a widget
   click re-renders the stored result rather than re-running the pipeline.
2. **The checkpointer needs a stable `thread_id` per deal run.** Reusing one resumes a
   paused thread instead of starting a deal, which is the single most confusing failure
   this surface could have. A fresh id is minted per run and stored beside the result.
3. **Heavy resources load once.** The compiled graph, the Chroma index behind it and the
   embedding model are `@st.cache_resource`, so only the first run pays for them.
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

import config
import nodes
from demo_deals import DEMO_DEALS
from graph import build_graph, state_serde
from state import RECOMMENDATION_LABEL, DealState, DealTerms, Severity
from tools.llm_client import LlmError, verify_models_live
from tools.tracing import configure_tracing
from tools.faults import Fault, injected
from tools.llm_cache import CacheMode

CHECKPOINT_DB = config.DATA_DIR / "processed" / "checkpoints.sqlite"

# Sections rendered open. Everything else collapses, which is the progressive-detail
# rule from U9.4's template: the recommendation and the written summary first, the
# evidence a click away. `Summary` is not here because it is not an expander at all —
# it renders inline above the strip, since it is the one section a reader is meant to
# meet without deciding to.
_OPEN_BY_DEFAULT = ("Disclosures",)

# Plain language for each simulated failure. §8: reader-facing text carries no internal
# vocabulary, and a demo audience cannot resolve `STALE_RENT_INDEX`. The enum member is
# what the code declares; this is what a person is offered.
_FAULT_LABEL = {
    Fault.LLM_UNAVAILABLE: "The language model is unreachable",
    Fault.GEOCODER_OUTAGE: "The address lookup service is down",
    Fault.STALE_RENT_INDEX: "The market rent index is out of date",
}

_RESUME_PLACEHOLDER = (
    "Reviewed and released for reporting. A real reviewer would resolve the "
    "disclosures in this report before proceeding."
)


# --------------------------------------------------------------------------
# The parts that do not need Streamlit, kept separable so they can be tested
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RunSpec:
    """One thing to run, and everything that decides whether it can be replayed."""

    deal_key: Optional[str] = None
    listing: Optional[str] = None
    retrieval: bool = True
    fault: Optional[Fault] = None

    @property
    def label(self) -> str:
        return self.deal_key or "pasted-listing"


# The combinations recorded and committed, as (deal, retrieval, fault). A run outside
# this set has no recording and must call the model.
#
# **Stated as data rather than inferred, because the honest answer is knowable in
# advance.** The alternative — attempt the replay and catch `CacheMiss` — would tell the
# reader the run was live only *after* it had already failed partway through, and would
# make the surface's mode badge a report on the past rather than a statement about what
# is about to happen. `Fault.LLM_UNAVAILABLE` is recorded against every deal because it
# needs no recording at all: it patches `LlmClient.complete`, which is where the cache is
# consulted, so the patch sits above the lookup (`tools/faults.py`).
_RECORDED: frozenset[tuple[str, bool, Optional[Fault]]] = frozenset(
    [(key, True, None) for key in DEMO_DEALS]
    + [(key, True, Fault.LLM_UNAVAILABLE) for key in DEMO_DEALS]
    + [
        ("chicago", False, None),
        ("los-angeles", True, Fault.GEOCODER_OUTAGE),
        ("los-angeles", True, Fault.STALE_RENT_INDEX),
    ]
)


# The green the report's structural headings are set in. One constant, because it is
# used in three selectors below and a colour repeated by hand is a colour that drifts.
_HEADING_GREEN = "#188038"


def _page_style() -> None:
    """The page's own stylesheet: the typeface, and the report's structural headings.

    **The typeface is loaded here rather than by `config.toml`.** Streamlit's `theme.font`
    setting names a family but does not fetch one; pointing it at a Google Fonts URL was
    tried and quietly fetched nothing, leaving the page in the default face while the
    config claimed Roboto. The `@import` below is what actually loads it, and it is the
    first rule in the sheet because an `@import` anywhere else is ignored.

    **The colour lives here and not in the report, and that is forced rather than
    preferred.** The report is a Markdown file committed to a public repository and
    GitHub strips `style` attributes from Markdown, so a heading coloured at the source
    would render green in this surface, plain on GitHub, and as raw HTML in anyone's
    text editor. Keeping the report pure Markdown and colouring it at the point of
    display costs nothing a reader sees and keeps `docs/sample_reports/` legible in every
    viewer — which is the same reasoning `split_report` rests on: the report is the
    artifact, this module is a lens on it.

    **Three selectors, because the report's `##` headings are not `<h2>` here.**
    `_render_report` turns each one into an expander label, so the section headings a
    reader sees — *Findings*, *Comparable Rentals* — are expander summaries rather than
    headings, and styling `h2` alone would colour nothing. The `#####` used for the lede
    is the third. Sub-headings inside a section (`###` and below) are deliberately left
    alone: the colour marks the report's structure, and colouring everything would mark
    nothing.
    """
    st.markdown(
        f"""
        <style>
          /* The typeface itself. `config.toml` names Roboto as the family; this is
             what actually fetches it. An @import has to be the first rule in the
             sheet, and if it fails the page falls back to Streamlit's Source Sans. */
          @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');

          /* The report title, and this app's own title above it. */
          h1, [data-testid="stMarkdownContainer"] h1 {{ color: {_HEADING_GREEN}; }}
          /* Section headings, which reach the reader as expander labels. */
          [data-testid="stExpander"] summary p {{
              color: {_HEADING_GREEN};
              font-weight: 600;
          }}
          /* The lede, the one section rendered open rather than in an expander. */
          [data-testid="stMarkdownContainer"] h5 {{ color: {_HEADING_GREEN}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def _tracing_enabled() -> bool:
    """Point LangSmith at this project's bucket, once per session.

    `configure_tracing` is idempotent, but Streamlit reruns the whole script on every
    interaction, so an uncached call would print its status line on each one.
    """
    return configure_tracing(verbose=False)


def _tracing_status() -> None:
    """Say in the surface whether this session is being traced.

    In the sidebar rather than the main column because it is a fact about the *session*,
    not about the deal on screen — and stated whichever way it comes out, since the
    absence of a trace is the thing worth knowing during a capture.
    """
    with st.sidebar:
        if _tracing_enabled():
            st.caption(f"Tracing to LangSmith project `{config.LANGSMITH_PROJECT}`.")
        else:
            st.caption("Not tracing. Set `LANGSMITH_TRACING=true` before launching to record this session.")


def is_recorded(spec: RunSpec) -> bool:
    """Whether this exact combination can be served from committed recordings."""
    if spec.deal_key is None:
        return False
    return (spec.deal_key, spec.retrieval, spec.fault) in _RECORDED


# What each agent does, in the order the graph runs them. Plain language, because this
# reaches a demo audience rather than a reader with the repository open.
_NODE_WORK = {
    nodes.PLANNER: ("Planner", "Inspects the deal and decides which steps it needs"),
    nodes.EXTRACTOR: ("Extractor", "Parses the listing into typed terms, geocodes the address, and states what it assumed"),
    nodes.COMPS_RETRIEVAL: ("Retrieval", "Searches 3,880 real rentals for comparables, relaxing one criterion at a time when matches are thin"),
    nodes.VALUATION_RENT: ("Valuation", "Estimates rent against the market index for this property's own ZIP, and cross-checks it against the comparables"),
    nodes.SCENARIO_FORECAST: ("Forecast", "Searches rent and price scenarios, scoring and pruning candidates"),
    nodes.CRITIC: ("Critic", "Checks consistency across agents, scores confidence, and decides report, rework or escalate"),
    nodes.HUMAN_REVIEW: ("Human review", "The graph pauses and waits for a person"),
    nodes.SUMMARIZER: ("Summarizer", "Writes the report, carrying every disclosure into it"),
}

_GRAPH_DIAGRAM = config.REPO_ROOT / "docs" / "diagrams" / "deal_evaluator_graph_lr.png"


def report_markdown(text: str) -> str:
    """Report text adjusted for Streamlit's renderer rather than GitHub's.

    Two differences between the two renderers are silent failures on screen, and both were
    visible in this surface before this function existed.

    1. **Dollar amounts became equations.** Streamlit renders LaTeX inside markdown, so a
       line holding two dollar signs is read as math delimited by them: the figures come
       back as italic symbols run together, and any bold markers caught between them are
       swallowed into the expression instead of making text bold. Replacing each dollar
       sign with its HTML entity puts the same character on screen and leaves the math
       parser nothing to match.
    2. **The disclosure blocks are real HTML.** The report wraps each disclosure in
       `<details>`/`<summary>` so it collapses when read on GitHub. Streamlit escapes HTML
       by default and printed the tags as text; callers below render it instead.

    **Neither is a change to the report.** The file committed to the repository is exactly
    what the Summarizer wrote — this function is the lens, not the artifact, which is the
    same reason the surface splits the report's text rather than re-laying-out its evidence.

    TODO(security): rendering HTML means a `<script>` in report text would execute. Every
    committed report is machine-generated from templates and every demo run replays from a
    fixed recording, so the only reachable path is a pasted listing steering the one
    model-written paragraph into emitting markup, on a surface that runs locally for one
    person. Accepted here; a served deployment would need the report sanitized first, or
    the `<details>` blocks converted to native expanders before rendering.
    """
    return text.replace("$", "&#36;")


def split_report(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """`(top matter, [(heading, body), ...])`, split at the report's own `##` headings.

    The top matter is everything above the first `##` — the title, the two verdict lines
    and the status line — and it is what the surface always shows. Everything below is a
    section that can collapse.

    **Splitting the text rather than re-rendering the state** is the whole design choice
    of this module: the report stays the single source of what a reader is told, and this
    function cannot disagree with it because it does not know what any of it means.
    """
    top: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in markdown.split("\n"):
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            top.append(line)
    return "\n".join(top).strip(), [(h, "\n".join(b).strip()) for h, b in sections]


@contextmanager
def run_environment(spec: RunSpec) -> Iterator[None]:
    """Pin the cache and the retrieval switch for one run, then put them back.

    Assigning `config` directly is the same mechanism `eval/runner._case_environment`
    uses, and restoring in `finally` matters more here than it does there: this process
    outlives the run, so a switch left flipped would silently apply to every later run in
    the session and none of them would say so.
    """
    previous_mode = config.LLM_CACHE_MODE
    previous_dir = config.LLM_CACHE_DIR
    previous_retrieval = config.RETRIEVAL_ENABLED

    if is_recorded(spec):
        config.LLM_CACHE_MODE = CacheMode.REPLAY
        config.LLM_CACHE_DIR = config.EVAL_RECORDINGS_DIR
    else:
        # A live run writes to the development store, never to the committed one.
        # Recording into `eval/data/` is a deliberate act (`main.py` under
        # `LLM_CACHE_DIR=...`), not something a demo click can do by accident.
        config.LLM_CACHE_MODE = CacheMode.READ_WRITE
        config.LLM_CACHE_DIR = config.DATA_DIR / "processed" / "llm_cache"

    config.RETRIEVAL_ENABLED = spec.retrieval
    try:
        with injected(spec.fault, declared_by=spec.label):
            yield
    finally:
        config.LLM_CACHE_MODE = previous_mode
        config.LLM_CACHE_DIR = previous_dir
        config.RETRIEVAL_ENABLED = previous_retrieval


def severity_counts(flags) -> dict[Severity, int]:
    return {s: sum(1 for f in flags if f.severity == s) for s in Severity}


# --------------------------------------------------------------------------
# Streamlit
# --------------------------------------------------------------------------


@st.cache_resource
def _graph():
    """The compiled graph and its checkpointer, built once per process.

    Cached because the first build loads the Chroma index and the embedding model, which
    is the whole of the surface's cold-start cost. `check_same_thread=False` because
    Streamlit runs the script on a worker thread that is not the one this connection was
    opened on; the demo is single-user, which is the assumption that makes one shared
    connection safe here and would not make it safe in a served application.
    """
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    return build_graph(checkpointer=SqliteSaver(connection, serde=state_serde()))


def _agents_ran(ran: list[str], *, working: bool) -> None:
    """The pipeline: the graph it runs on, and which of its steps this deal reached.

    **One place, not two.** The diagram and the per-agent descriptions used to sit in a
    separate explainer above the report, which meant a reader met the seven agents twice
    and in neither place could see which of them this particular deal had actually used.
    Here the picture and the record are the same panel.

    **The diagram shows nodes this run did not reach, and that is deliberate.** It is the
    graph, generated from the compiled pipeline, not a trace — the conditional edges are
    the point, and a deal that stopped at review is easier to understand against the whole
    shape than against a picture cropped to the part it used. The ticks below say which
    steps ran.

    Skipped while the run is in flight: re-rendering an image on every node update buys a
    reader nothing and costs a flicker at exactly the moment the list is worth watching.
    """
    if not working and _GRAPH_DIAGRAM.exists():
        st.image(str(_GRAPH_DIAGRAM), use_container_width=True)
        st.caption(
            "The compiled graph. Dotted arrows are conditional: the Critic can send a deal "
            "back for one bounded round of rework, stop it for human review, or release it "
            "straight to the report — so not every run reaches every node."
        )

    for name in ran:
        label, work = _NODE_WORK.get(name, (name, ""))
        st.markdown(f"✅ &nbsp;**{label}** — {work}", unsafe_allow_html=True)
    if working:
        st.markdown("⏳ &nbsp;*working…*", unsafe_allow_html=True)


def _stream_run(payload, invoke_config: dict, spec: RunSpec) -> dict:
    """Run the graph a node at a time, so the pipeline is visible while it works.

    `invoke()` hands back only the finished state, which on a replayed run means a few
    seconds of spinner and then a report — the seven agents do all of their work
    invisibly, and the one thing a viewer most wants to see is the one thing not shown.

    **Both stream modes are requested at once, and each answers a different question.**
    `updates` names the node that just finished, which is what drives the list on screen.
    `values` carries the whole state after it, so the last one received *is* the finished
    state — there is no second read afterwards that could disagree with what ran.

    Which nodes appear is the path this deal actually took, not a fixed checklist: the
    Planner can skip the Extractor, and `human_review` only appears when a deal is
    stopped. A checklist would have to show steps that will never complete.
    """
    ran: list[str] = list(st.session_state.get("nodes_run", []))
    latest: dict = {}
    interrupt = None
    panel = st.empty()

    with run_environment(spec):
        for mode, chunk in _graph().stream(
            payload, invoke_config, stream_mode=["updates", "values"]
        ):
            if mode == "values":
                latest = chunk
                continue
            for name in chunk:
                if name == "__interrupt__":
                    interrupt = chunk[name]
                    continue
                ran.append(name)
                with panel.container():
                    _agents_ran(ran, working=True)

    panel.empty()
    st.session_state["nodes_run"] = ran

    result = dict(latest)
    if interrupt is not None:
        result["__interrupt__"] = interrupt
    return result


def _invoke(spec: RunSpec, listing_text: str, coords) -> tuple[dict, str]:
    """Run one deal and return `(result, thread_id)`.

    A fresh `thread_id` per run, because reusing one resumes that thread from wherever it
    stopped rather than starting the deal over — mechanic 2 in the module docstring.
    """
    thread_id = f"{spec.label}-{uuid4().hex[:8]}"
    invoke_config = {"configurable": {"thread_id": thread_id}}
    terms = DealTerms()
    if coords is not None:
        terms.latitude, terms.longitude = coords

    st.session_state["nodes_run"] = []
    result = _stream_run(
        DealState(raw_listing_text=listing_text, deal_terms=terms), invoke_config, spec
    )
    return result, thread_id


def report_html(markdown_text: str, title: str) -> str:
    """The report as one self-contained HTML file, for saving or printing.

    **This is the PDF path.** No PDF library is installed and adding one costs a system
    dependency for a document a browser already prints well: open this file and print it
    to PDF. The stylesheet is print-first for that reason.

    Rendered with the markdown parser Streamlit already depends on, so nothing new is
    installed. HTML in the source is passed through, which is what keeps each disclosure
    a real collapsible block; `open` on every one so nothing is hidden in a printout.
    """
    from markdown_it import MarkdownIt

    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(markdown_text)
    body = body.replace("<details>", "<details open>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ max-width: 46rem; margin: 3rem auto; padding: 0 1.5rem;
         font: 16px/1.6 Roboto, system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
         color: #1a1a1a; }}
  h1, h2, h3, h4 {{ color: #188038; line-height: 1.25; }}
  h1 {{ font-size: 1.9rem; }} h2 {{ font-size: 1.35rem; margin-top: 2.2rem; }}
  blockquote {{ border-left: 4px solid #188038; margin: 1.4rem 0; padding: .2rem 0 .2rem 1.1rem;
                color: #22331f; background: #f4f9f5; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1.2rem 0; font-size: .92rem; }}
  th, td {{ border: 1px solid #ddd; padding: .45rem .6rem; text-align: left; vertical-align: top; }}
  th {{ background: #f4f4f2; }}
  code {{ background: #f2f2ef; padding: .1rem .3rem; border-radius: 3px; font-size: .9em; }}
  details {{ margin: .6rem 0; }}
  summary {{ cursor: pointer; }}
  @media print {{ body {{ margin: 0; max-width: none; font-size: 11pt; }}
                  h2 {{ page-break-after: avoid; }} details {{ page-break-inside: avoid; }} }}
</style></head><body>
{body}
</body></html>
"""


def _download_row(result: dict) -> None:
    """Take the report away: as markdown, or as a page a browser can print to PDF.

    Two formats rather than three. Markdown is the report exactly as it was written and
    imports into Google Docs and Word directly. The HTML is the print path — browsers
    make good PDFs and a PDF library would be a system dependency for no gain.
    """
    report = result.get("report_markdown")
    if not report:
        return
    stem = (st.session_state.get("spec").label if st.session_state.get("spec") else "report")
    left, right, _ = st.columns([1, 1, 3])
    left.download_button(
        "Download as Markdown", report, file_name=f"{stem}-evaluation.md",
        mime="text/markdown", width="stretch",
        help="The report exactly as written. Google Docs and Word both import Markdown directly.",
    )
    right.download_button(
        "Download printable HTML", report_html(report, f"Deal Evaluation — {stem}"),
        file_name=f"{stem}-evaluation.html", mime="text/html", width="stretch",
        help="Opens in any browser. Print it (Cmd-P) and choose Save as PDF.",
    )


def _status_strip(result: dict) -> None:
    """Recommendation, confidence, disclosures, comps — the two axes and their evidence.

    **Read from typed state, not parsed back out of the report.** This is the only place
    the surface touches state rather than text, and it is also the first caller anywhere
    in this project to read a typed field off a *resumed* run — which is how U9.7's
    pre-flight found `graph.state_serde()`'s allowlist missing `RecommendationDetail`.
    """
    recommendation = result.get("recommendation")
    flags = result.get("flags", [])
    counts = severity_counts(flags)
    confidence = result.get("confidence_score")

    verdict = "—"
    if recommendation is not None:
        verdict = RECOMMENDATION_LABEL[recommendation.verdict]
        if recommendation.cross_check_disagrees:
            verdict += " ⚖"

    columns = st.columns(4)
    columns[0].metric("Recommendation", verdict, help="Is this a good deal? (axis 2)")
    columns[1].metric(
        "Confidence",
        f"{confidence:.2f}" if confidence is not None else "—",
        help=(
            f"Escalation threshold {config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f}. "
            f"Can the system stand behind its own numbers? (axis 1)"
        ),
    )
    columns[2].metric(
        "Disclosures",
        len(flags),
        help=(
            f"{counts[Severity.CRITICAL]} critical · {counts[Severity.WARN]} warn · "
            f"{counts[Severity.INFO]} informational"
        ),
    )
    columns[3].metric("Comparables", len(result.get("comps", [])))


def _render_report(result: dict) -> None:
    report = result.get("report_markdown")
    if not report:
        st.warning("This run produced no report.")
        return

    top, sections = split_report(report)
    st.markdown(report_markdown(top), unsafe_allow_html=True)
    _status_strip(result)
    _download_row(result)

    ran = st.session_state.get("nodes_run") or []
    if ran:
        with st.expander(f"The agents that ran — {len(ran)} steps, in order", expanded=False):
            _agents_ran(ran, working=False)

    for heading, body in sections:
        if heading == "Summary":
            # The lede is the one section a reader should meet without deciding to.
            st.markdown(f"##### {heading}")
            st.markdown(report_markdown(body), unsafe_allow_html=True)
            continue
        with st.expander(heading, expanded=heading.startswith(_OPEN_BY_DEFAULT)):
            st.markdown(report_markdown(body), unsafe_allow_html=True)


def _resume(note: str) -> None:
    """Release a paused deal with the reviewer's own note and finish the run.

    **The same `run_environment` wraps the resume as wrapped the first invoke**, and it
    has to: a declared fault that lifted between the pause and the resume would produce a
    report whose written summary succeeded during an outage the report says never ended.
    `main.py` makes the same choice for the same reason.
    """
    spec: RunSpec = st.session_state["spec"]
    invoke_config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
    st.session_state["result"] = _stream_run(Command(resume=note), invoke_config, spec)


def _listing_panel(listing: str) -> None:
    """The text the pipeline was given, kept on screen beside whatever it produced.

    Always visible, and not behind a disclosure. Every figure in the report is derived
    from these few sentences, so a reader checking a number against its source should not
    have to remember that the source is one click away.
    """
    if not listing or not listing.strip():
        return
    st.markdown("##### The Listing")
    with st.container(border=True):
        st.markdown(report_markdown(listing.strip()), unsafe_allow_html=True)


def _review_panel(payload: dict) -> None:
    """The `human_review` interrupt, rendered as a request rather than an error.

    **This is the surface's strongest claim and the reason it is not a report viewer.**
    `main.py` auto-resumes with a canned note so one command produces one report; here a
    person reads the grounds, types their own note and releases the deal. The pause is
    genuine either way — LangGraph has persisted the run to the checkpointer and the
    second invoke resumes this node rather than re-running the pipeline — but only here
    is the human actually in the loop.

    **The note replays, which was measured before this was built** (U9.7's pre-flight).
    It reaches no model prompt: the Summarizer renders it directly and
    `_lede_prompt` never reads it. Had it reached a prompt, this box would have forced a
    live call and the surface would have had to choose between honest oversight and a
    deterministic demo.
    """
    st.subheader("⏸ Paused — this deal was escalated to human review")
    st.caption(
        "The system stopped rather than reporting on its own. Nothing below is a "
        "conclusion about the property; it is the grounds for asking a person."
    )

    for desk in payload.get("waiting_on", []):
        st.info(f"**Waiting on:** {desk}")

    confidence = payload.get("confidence_score")
    st.markdown(
        f"**Confidence** {confidence:.2f} against a threshold of "
        f"{config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f}"
        if confidence is not None
        else "**Confidence** not computed"
    )

    flags = payload.get("flags", [])
    if flags:
        st.markdown(f"**What caused it — {len(flags)} at warn or critical**")
        for flag in flags:
            st.markdown(
                report_markdown(
                    f"- `{flag['severity']}` · **{flag['kind']}** — {flag['detail']}"
                ),
                unsafe_allow_html=True,
            )

    ran = st.session_state.get("nodes_run") or []
    if ran:
        with st.expander(
            f"What ran before it stopped — {len(ran)} steps", expanded=False
        ):
            _agents_ran(ran, working=False)

    questions = payload.get("unanswered_questions") or []
    if questions:
        st.markdown("**Unanswered questions**")
        for question in questions:
            st.markdown(report_markdown(f"- {question}"), unsafe_allow_html=True)

    note = st.text_area(
        "Reviewer note — travels into the report verbatim",
        value=_RESUME_PLACEHOLDER,
        height=100,
    )
    if st.button("Release for reporting", type="primary"):
        with st.spinner("Resuming…"):
            _resume(note)
        st.rerun()


def _sidebar() -> tuple[Optional[RunSpec], Optional[str], Optional[tuple], bool]:
    """Build the run spec from the controls. Returns `(spec, listing, coords, run)`.

    **One question decides all four controls: is this combination recorded?** The demo
    deals, the retrieval ablation and the three declared faults are the same mechanism
    with different arguments, and the paste box is the case where the answer is no by
    construction. Answering once, before anything runs, is what lets the surface state
    its mode rather than discover it — which is the pipeline's own Transparent
    Degradation rule turned on the surface.
    """
    st.header("Run a deal")
    source = st.radio(
        "Listing", ["A demo listing", "Paste your own"], label_visibility="collapsed"
    )

    spec: Optional[RunSpec] = None
    listing: Optional[str] = None
    coords: Optional[tuple] = None

    if source == "A demo listing":
        deal_key = st.selectbox(
            "Demo listing", sorted(DEMO_DEALS), index=None,
            placeholder="Choose a listing…",
        )
        retrieval = not st.checkbox(
            "Run without comparable listings",
            help=(
                "The retrieval ablation. Removes the search over 3,880 real rental "
                "listings and runs the identical deal, so the report shows what the "
                "evidence base was contributing. Recorded for the Chicago listing."
            ),
        )
        fault = st.selectbox(
            "Simulate a failure",
            [None, *Fault],
            format_func=lambda f: "Nothing — run normally" if f is None else _FAULT_LABEL[f],
            help=(
                "Each of these covers a path no real listing can reach, and each names "
                "itself in the report it produces so a demonstration cannot be mistaken "
                "for a real incident."
            ),
        )
        if deal_key:
            spec = RunSpec(deal_key=deal_key, retrieval=retrieval, fault=fault)
            listing, coords = DEMO_DEALS[deal_key].listing, DEMO_DEALS[deal_key].supplied_coords
    else:
        listing = st.text_area(
            "Paste a listing", height=220,
            placeholder="Paste the full text of a for-sale listing…",
        )
        if listing and listing.strip():
            spec = RunSpec(listing=listing)

    if spec is None:
        st.button("Run", type="primary", disabled=True)
        return None, None, None, False

    # The mode badge, and the gate. A live run is stated and confirmed, never discovered.
    if is_recorded(spec):
        st.success(
            "**Replayed.** This exact run is served from committed recordings — "
            "instant, identical every time, no model call."
        )
        confirmed = True
    else:
        st.warning(
            "**Live.** Nothing is recorded for this combination, so the model will be "
            "called. Expect roughly a minute, and note that this model has been measured "
            "returning different reasoning for an identical prompt — so this run may not "
            "reproduce exactly."
        )
        confirmed = st.checkbox("Run live anyway")

    return spec, listing, coords, st.button(
        "Run", type="primary", disabled=not confirmed
    )


def main() -> None:
    st.set_page_config(page_title="Deal Evaluator", page_icon="🏘️", layout="wide")
    _page_style()
    st.title("Multi-family deal evaluator")
    st.caption(
        "Seven agents evaluate a small multi-family listing and disclose every point at "
        "which they had to work with less than they wanted."
    )

    # **Tracing is configured here for the same reason `main.py` does it, and the failure
    # it prevents is silent.** LangSmith activates itself from the environment, so a
    # `LANGSMITH_TRACING=true` shell would trace this surface either way — but into the
    # project named `default`, with the key resolved only if it happens to be exported
    # rather than sitting in its file, and with nothing on screen saying which happened.
    # `tracing.py`'s own docstring names that case: a trace you believed was being
    # captured and was not is worse than no trace. Cached so the status line renders
    # once per session rather than on every Streamlit rerun.
    _tracing_status()

    with st.sidebar:
        spec, listing, coords, run_clicked = _sidebar()

    if run_clicked and spec is not None and listing:
        if not is_recorded(spec):
            # Only checked before a run that will actually reach the model. In replay it
            # could add nothing but a network round-trip and a way to fail.
            try:
                verify_models_live()
            except LlmError as exc:
                st.error(f"The model could not be reached, so this live run was not started: {exc}")
                return
        with st.spinner(f"Running '{spec.label}' through the graph…"):
            result, thread_id = _invoke(spec, listing, coords)
        st.session_state.update(
            result=result, thread_id=thread_id, spec=spec, listing=listing
        )

    result = st.session_state.get("result")
    if result is None:
        # Nothing has been run yet. Show whatever is selected rather than an empty
        # page, so the input is on screen before the output exists.
        if listing and listing.strip():
            _listing_panel(listing)
            st.caption("Press **Run** in the sidebar to evaluate this listing.")
        else:
            st.info("Choose a listing in the sidebar and press **Run**.")
        return

    # The listing that produced what is on screen — not whatever the sidebar now
    # points at, which may have been changed without pressing Run.
    _listing_panel(st.session_state.get("listing", ""))

    if "__interrupt__" in result:
        _review_panel(result["__interrupt__"][0].value)
        return

    _render_report(result)


if __name__ == "__main__":
    main()
