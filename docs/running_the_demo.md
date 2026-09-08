# Running the demo surface

**What this document is:** how to launch the Streamlit app (`src/app.py`) over the compiled
pipeline, with and without LangSmith tracing, and how to confirm that tracing actually took.

For *what the app does* once it is running, see the Streamlit section of the
[README](../README.md#running-the-project-in-streamlit). For *what each demo listing exists
to show*, see [`demo.md`](demo.md).

Everything runs from `src/`; the virtualenv is `src/.venv`. Both invocations below carry the
same two `--server.*` flags, explained at the end.

---

## 1. Standard run (no tracing)

```bash
cd src
.venv/bin/streamlit run app.py --server.address localhost --server.headless true
```

Open <http://localhost:8501> by hand once the terminal says the server is up. The sidebar
caption will read *"Not tracing. …"* — expected, and fine for a demo where the trace is not
being captured.

---

## 2. Run with LangSmith tracing

```bash
cd src
LANGSMITH_TRACING=true .venv/bin/streamlit run app.py --server.address localhost --server.headless true
```

`LANGSMITH_TRACING=true` is a shell **environment-variable assignment prefixed to one
command** — bash and zsh place it in that process's environment only, so it is not exported
to the rest of the terminal session. Scoping it this way means *this run* is traced without
every later `pytest` or `python main.py` in the same shell silently shipping data to a
hosted service.

Nothing in the repo turns tracing on. LangChain's own runtime activates it when it sees
`LANGSMITH_TRACING=true` plus a key in the environment; `tools/tracing.py` only (1) forces
the project name to `deal-evaluator` (`config.LANGSMITH_PROJECT`), (2) supplies the key, and
(3) reports status. The switch must therefore be set **before launch** — it cannot be
toggled from the UI, and `configure_tracing` runs once per session behind
`@st.cache_resource`.

**Key resolution** (mirrors the other two credentials): `LANGSMITH_API_KEY` if exported,
otherwise a gitignored file on disk. If neither is found the run proceeds untraced and the
terminal says so.

**Confirm it took:** the sidebar caption should change to *"Tracing to LangSmith project
`deal-evaluator`."* If it still says *"Not tracing"* with the variable set, no key was
found. Note this only confirms a key was *located*, not that it is valid — an expired or
wrong-account key fails silently at ingestion and only shows up as a warning line in the
terminal.

> **The value must be exactly `true`.** LangSmith's tracer matches the string
> case-sensitively (`langsmith/utils.py`, `tracing_is_enabled()`): `LANGSMITH_TRACING=True`,
> `TRUE` or `1` activate nothing. The sidebar status check was made case-sensitive to match
> (Sept 6, 2026) — before that it accepted `True`, and the surface reported "tracing on"
> while no trace was recorded. A wrong spelling now shows as "Not tracing".

---

## The two `--server.*` flags

Both are **optional**. They are also committed to `src/.streamlit/config.toml`, so a bare
`.venv/bin/streamlit run app.py` from `src/` already picks them up — along with
`browser.gatherUsageStats = false` and the light theme. They are written out on the command
line above so the invocation is self-documenting and stays correct if it is ever run from a
copied directory without that config file.

| Flag | What it does | Why this project sets it |
| --- | --- | --- |
| `--server.address localhost` | Binds the web server to the loopback interface only. Streamlit's default is `0.0.0.0` (all interfaces), which makes it print a **Network URL** line carrying the machine's LAN or public IP. | That IP would be visible in a screen recording. Binding to `localhost` suppresses the line and keeps the surface unreachable from other machines. |
| `--server.headless true` | Stops Streamlit from auto-opening a browser tab on launch, **and skips the first-run prompt that asks for an email address**. | The tab is opened by hand, already sized and zoomed. The email prompt is the specific thing worth keeping out of a clean capture. |

---

## Viewing the traces

- **The `deal-evaluator` project does not exist until the first trace lands.** LangSmith
  creates a project automatically on first ingestion — there is nothing to set up in the web
  UI ahead of time. Launch with tracing on (§2), run any deal through the surface, then
  refresh <https://smith.langchain.com> → *Tracing Projects* (a.k.a. *Projects*).
  `deal-evaluator` appears once spans arrive.
- **Replayed demo runs still trace.** The graph still executes node by node, so you get the
  full Planner → … → Summarizer tree. The LLM calls are served from the committed
  recordings, so those spans reflect cache hits, not live model latency.
- **Free-tier retention is 14 days.** Screenshot anything worth keeping as you go — a trace
  captured a month before a write-up is gone by the time the write-up needs it.

### If the project still never appears

1. Watch the launch terminal for LangSmith ingestion warnings (`Failed to multipart ingest
   runs` or similar) — that is an invalid or wrong-account key.
2. Confirm the key on disk matches an **active** key under *Settings → API Keys* of the
   account you are logged into. A key from a different LangSmith account (or an org you are
   no longer in) authenticates as far as "a key was found" but its traces never reach your
   workspace.
3. Confirm you actually ran a deal — opening the app is not enough; no graph invocation
   means no spans.
