# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Spark2Scale-AI is a FastAPI service that exposes a suite of LangGraph-based multi-agent pipelines for evaluating, researching, and supporting early-stage startups (evaluation, market research, recommendations, SWOT, competitor analysis, PPT/pitch-deck generation, PDF extraction, document Q&A, and a real-time voice "pitch analyzer"). The service is deployed via Docker to Azure App Service.

## Common Commands

Always activate the local venv first (Windows): `venv\Scripts\activate`. Tests and the API depend on `.env` (use `cp .env.example .env`).

- **Run the API locally**: `python run_api.py` (or `python main.py`) — reload-enabled Uvicorn on `:8000`, docs at `/docs`.
- **Run inside Docker (production-style)**: built from `Dockerfile`; CMD uses `gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300`. The `-w 1` is intentional — see "Concurrency model" below.
- **Run all tests**: `pytest` from project root. `conftest.py` adds the repo root to `sys.path` and loads `.env`.
- **Run a single test file**: `pytest tests/evaluation_test.py` (or any of the root-level `test_*.py` scripts, several of which are runnable as `python test_*.py` standalone smoke tests rather than pytest collections).
- **Run only integration (live-network) tests**: `pytest -m integration`. The `integration` marker is registered in `pytest.ini`; default test runs include them unless filtered.
- **Pitch-deck CLI smoke**: `python generate_pitch_deck.py` (reads `app/graph/ppt_generation_agent/input/`, writes to `…/output/`).

## Architecture

### Entry points & routing
- `main.py` / `run_api.py` both bootstrap `app.api.main:app`. `app/api/main.py` mounts every router under `/api/v1/*` and configures CORS + slowapi rate limiting. When adding a new agent, register its router here.
- HTTP routes live in `app/api/routes/` and are thin adapters: parse request → invoke the corresponding LangGraph workflow in `app/graph/<agent>/workflow.py` → serialize the result.

### Multi-agent layout
Each agent in `app/graph/<name>/` follows the same convention:
- `state.py` — TypedDict `*State` describing the LangGraph channel.
- `node.py` / `nodes.py` — node functions (each takes/returns state).
- `tools.py` — external-call helpers (search, scoring, scraping, etc.).
- `workflow.py` — builds and `compile()`s the `StateGraph`; module-level `app` (or `*_app`) is the compiled graph imported by routes.
- `prompts.py`, `schema.py` / `schema.json` — prompt templates and Pydantic/JSON schemas.

Two pipeline shapes recur and matter when modifying graphs:
- **Fan-out / fan-in (parallel)**: `evaluation_agent/workflow.py` dispatches all 9 sub-agents from `planner_node` in parallel and converges at `final_node`. `market_research_agent/workflow.py` does the same for 5 research tasks after `plan_node`. Adding a node here means wiring **both** the `planner → node` edge and the `node → final` edge.
- **Sequential**: `document_generator/workflow.py` deliberately serializes its SWOT and competitor-analysis chains. The serialization is a workaround for LangGraph fan-in collisions and Gemini free-tier 429s — do not "optimize" it back to parallel without revisiting both constraints.

### LLM provider layer (`app/core/llm.py`)
`get_llm(provider=...)` is the single factory used across agents. It supports `"gemini"` (default, via `langchain-google-genai`), `"groq"`, and `"ollama"`. Groq calls go through a thread-safe **round-robin rotator** over `GROQ_API_KEY_1`…`GROQ_API_KEY_4` to multiply effective RPM; falls back to `GROQ_API_KEY` if the numbered keys are absent. There is also a separate `get_t5_insight()` async helper that calls a fine-tuned T5-3B model hosted on the `Dohahemdann/Spark2Scale-Space` HF Space via a lazily-initialized `gradio_client` — used by the evaluation agent's `t5_insight_node`.

### Concurrency model (important)
- `app/core/limiter.py` exposes `concurrency_limiter = asyncio.Semaphore(2)` consumed by every LLM-calling tool. Tests must replace it (`tests/conftest.py` patches every import site with a no-op async context manager) because `asyncio.Semaphore` binds to the loop where it was created — pytest-asyncio's per-test event loops will otherwise deadlock.
- Per-IP HTTP rate limiting uses `slowapi` with default `API_RATE_LIMIT` (env var, e.g. `"60/minute"`).
- Gunicorn must run with `-w 1`. The `pitch_analyzer` workflow stores `worker_process` as a module-level global (it spawns a LiveKit room agent); a second worker would join the same room twice and get stuck in a "connecting" loop. Scale horizontally via Azure container instances, not workers.

### Pitch analyzer specifics
`app/graph/pitch_analyzer/` is the most stateful subsystem: real-time audio (`pyaudio`/LiveKit), Qwen Realtime API over WebSocket, an `InterruptLock` with a priority map for managing semantic vs. acoustic interrupts, and a transient session state file written to `tempfile.gettempdir()`. Edits here must respect:
- `INTERRUPT_PRIORITY` rules (acoustic must not preempt semantic for 15s, 8s global cooldown).
- `ACOUSTIC_GRACE_S` window after calibration.
- Its imports are local (`from state import …`) — the module inserts its own dir at `sys.path[0]`. Use the same pattern when adding files to it; do NOT switch to absolute `app.graph.pitch_analyzer.*` imports without updating the entry shim.

### Output & external state
- Generated artifacts (PPTX, PDFs, JSON reports) land in `output/`, `outputs/`, and per-agent `app/graph/<agent>/output/` directories — all gitignored.
- Supabase is used for persistent storage (see `app/core/supabase_client.py` and `pitch_analyzer/supabase_report.py`); Neo4j Aura settings exist in `Config` but most pipelines don't currently require them.

## Environment variables

Required for most flows: `GEMINI_API_KEY` (and `GEMINI_MODEL`), at least one `GROQ_API_KEY_*`, `SERPER_API_KEY`, `SUPABASE_URL` + `SUPABASE_KEY`. Pitch analyzer additionally needs `DASHSCOPE_API_KEY` (Qwen) and LiveKit/Deepgram/ElevenLabs credentials. Image generation switches between Pollinations and Gemini via `IMAGE_PROVIDER`. The full set is enumerated in `.env.example` and `app/core/config.py`.

## Deployment

Pushes to the `Merging` branch trigger `.github/workflows/deploy.yml`, which builds and pushes `dohahemdan17/spark2scale-ai:v2` to Docker Hub. The Azure App Service pulls that image; it expects the app to bind to `${WEBSITES_PORT:-80}` (handled by the Dockerfile CMD). The CORS allowlist in `app/api/main.py` must include any new frontend origin.
