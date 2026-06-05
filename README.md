# Spark2Scale — AI Backend

> Intelligent multi-agent AI backend powering Spark2Scale's startup evaluation, pitch analysis, market research, document intelligence, and investor matching pipeline.
>
> Computational Science and Artificial Intelligence School — Data Science and Artificial Intelligence Program — Academic Year 2025–2026

---

## Team Members

| Name | ID | Program |
|---|---|---|
| Doha Hemdan | 202200701 | Data Science & Artificial Intelligence |
| Mariam Yasser | 202200886 | Data Science & Artificial Intelligence |
| Sarah Elsayed | 202200347 | Data Science & Artificial Intelligence |
| Salma Sherif | 202200622 | Data Science & Artificial Intelligence |

**Supervisor:** Associate Professor Dr. Mohamed Maher Ata

---

## Repository Structure

```
Spark2Scale-AI-1/
├── app/
│   ├── api/
│   │   ├── main.py                        # FastAPI app factory and middleware
│   │   ├── schemas.py                     # Global Pydantic request/response schemas
│   │   └── routes/                        # 18 route modules, one per feature
│   ├── graph/
│   │   ├── evaluation_agent/              # 9-dimension parallel evaluation (LangGraph fan-out)
│   │   ├── pitch_analyzer/                # LiveKit real-time voice coaching agent
│   │   ├── market_research_agent/         # Parallel TAM/SAM/SOM market research pipeline
│   │   ├── recommendation_agent/          # Strategic recommendation memo generator
│   │   ├── document_chat/                 # Multi-turn RAG Q&A over uploaded documents
│   │   ├── document_generator/            # SWOT, Competitor Matrix, and document generation
│   │   ├── ppt_generation_agent/          # Iterative PowerPoint pitch deck generator
│   │   ├── idea_check/                    # Conversational idea validation pipeline
│   │   ├── BMC/                           # Business Model Canvas generation and enhancement
│   │   ├── pdf_extractor/                 # Structured data extraction from uploaded PDFs
│   │   ├── feed_recommedation_agent/      # Investor feed ranking (vector + graph + UCB)
│   │   └── chat_summarizer/               # Converts chat history into actionable edit instructions
│   ├── core/
│   │   ├── llm.py                         # Centralized LLM factory (get_llm interface)
│   │   └── logger.py                      # Centralized logging configuration
│   ├── tools/
│   │   ├── database.py                    # Supabase helpers and query wrappers
│   │   └── search.py                      # Web search wrappers (Serper, Tavily)
│   └── utils/
│       └── report_writer.py               # Report formatting and PDF utilities
├── evaluation/
│   └── eval_feed_agent.py                 # Feed recommendation evaluation script
├── tests/                                 # pytest unit and integration test suite
├── docs/                                  # Additional documentation and diagrams
├── main.py                                # Application entry point
├── run_api.py                             # Local development runner
├── requirements.txt                       # Python dependencies
├── Dockerfile                             # Container definition
├── docker-compose.monitoring.yml          # Full stack with Prometheus + Grafana
└── .env.example                           # Environment variable template
```

---

## Problem Statement

The global startup ecosystem faces a critical structural challenge: the majority of early-stage ventures fail not due to poor technology or weak teams, but because founders lack systematic guidance during the earliest and most critical phases of company formation. Without formalized processes for idea validation, market assessment, and strategic planning, entrepreneurs build products that fail to attract customers or investors.

Specifically, early-stage founders frequently face the following unresolved questions without access to structured analytical tools:

- Is my idea suitable for the current market landscape and competitive environment?
- Does a real and defensible market need exist for my proposed solution?
- Do I possess the right team composition and organizational structure to execute?
- What business documents are required to attract institutional sponsors or investors?
- How do I identify competitive gaps and differentiate from incumbents?

Without structured answers to these questions, founders with genuinely promising ideas struggle to move from concept to execution, resulting in avoidable startup failures that slow innovation and weaken the entrepreneurial ecosystem. In the MENA region specifically, where startup investment activity has grown substantially yet remains concentrated among a small number of gatekeepers, this gap is especially pronounced.

Spark2Scale was conceived to address this gap by embedding the analytical rigor of a capital evaluation committee into an AI system accessible to any founder at pre-seed and seed stages, at any time.

---

## Abstract

Spark2Scale is a startup support ecosystem powered by AI designed to help early-stage founders bridge the gap between idea generation and investor readiness. The platform automates market research, startup evaluation across nine investment dimensions, investor-ready document generation, and AI pitch coaching through a voice-interactive agent.

Its AI backbone combines a modified `google/flan-t5-xl` (T5-XL) architecture with RoPE and Dilated Attention, achieving **68.8% higher inference throughput** and **58.6% lower memory usage** than the baseline. Additionally, a fine-tuned `unsloth/gemma-3n-E2B-it` (Gemma 3n) model is integrated for specialized structured JSON reasoning tasks.

Spark2Scale generates structured reports, SWOT analyses, Business Model Canvases, competitor matrices, and pitch decks while leveraging **Supabase** SQL **Qdrant** vector and **Neo4j** graph databases with a recommendation system to match investors with relevant startups. Built on a microservices architecture with LangGraph workflows, Supabase persistence, Azure, Modal, and Hugging Face deployments, the platform provides scalable and democratized access to venture capital evaluation tools for founders across the MENA region.

---

## Features

- **9-agent parallel evaluation pipeline**: Team, Problem, Product, Market, Traction, GTM, Business Model, Vision, and Operations agents run concurrently via LangGraph, each producing a score and evidence-backed analysis. Reduces wall time from 185 s (sequential) to ~80 s.
- **Custom T5-XL transformer**: Modified encoder-decoder architecture with RoPE + Dilated Attention for deep insight generation and contradiction analysis within the evaluation pipeline.
- **Fine-tuned Gemma 3n**: Instruction-tuned `unsloth/gemma-3n-E2B-it` deployed on Modal (NVIDIA A100, vLLM) for strict structured JSON generation in internal agent operations.
- **Live pitch coaching**: LiveKit WebRTC voice agent with Deepgram STT/TTS and Qwen LLM; three-layer interrupt architecture for real-time contradiction detection, grammar checking, and acoustic anomaly detection.
- **Market research agent**: Parallel pipeline generating TAM/SAM/SOM estimates with a `RealisticMarketSizer` correction layer, validates claims via live web search, and identifies regulatory risks.
- **Idea validation agent**: Conversational AI check on startup idea clarity, market urgency, and founder-market fit.
- **Strategic recommendation agent**: Deterministic failure-pattern library (~45 patterns), live Tavily search for market benchmarks, World Bank macro-economic risk indicators, and Gemini synthesis into a founder-facing memo.
- **Document generation suite**: AI generated SWOT + TOWS analysis, Competitor Matrix, Business Model Canvas (nine blocks with `[Validated]` / `[Hypothesis]` citation discipline), and PPT pitch decks.
- **Investor feed ranking**: Semantic vector matching (Qdrant) + Neo4j graph interest modeling + UCB multi-armed bandit exploration for personalized pitch-deck feeds with continuous reinforcement learning from swipe interactions.
- **Document chat (RAG)**: Multi-turn Q&A over uploaded PDFs and PPTX files with spatially-annotated context and chat history injection.
- **PDF extraction**: Tiered extraction (pdfplumber → PyPDF2 → PyMuPDF fallback) with Gemini-powered structured data parsing.
- **Chat summarizer**: Converts free-form founder↔assistant conversation into discrete, actionable change instructions consumed by downstream document agents.

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│         React / Next.js Frontend  (role-specific dashboards)   │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTP REST
┌──────────────────────────▼─────────────────────────────────────┐
│              API Gateway  (.NET MVC Backend)                    │
│       Auth · Business Logic · Notifications · Matching         │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTP REST
┌──────────────────────────▼─────────────────────────────────────┐
│            FastAPI AI Layer  (Python / LangGraph)               │
│         Gunicorn + UvicornWorker  ·  port 80 / 8000             │
├─────────────────────────────────────────────────────────────────┤
│  18 Route Modules                                               │
│  evaluation · pitch_analyzer · market_research · recommend      │
│  idea_check · document_chat · ppt · bmc · swot · competitor     │
│  feed · pdf · chat · chat_summarizer · pdf_extractor            │
├─────────────────────────────────────────────────────────────────┤
│  LangGraph Agent Workflows                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Evaluation Agent  (9 parallel sub-agents via fan-out)  │   │
│  │  Team · Problem · Product · Market · Traction · GTM     │   │
│  │  Business Model · Vision · Operations  → JOIN → Report  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐ ┌─────────────────┐ ┌──────────────────────┐ │
│  │Pitch Analyzer│ │ Market Research │ │ Recommendation Agent │ │
│  │(LiveKit+Qwen)│ │  (5 parallel    │ │ (45 failure patterns │ │
│  │              │ │   nodes)        │ │  + World Bank + LLM) │ │
│  └──────────────┘ └─────────────────┘ └──────────────────────┘ │
│  ┌──────────────┐ ┌─────────────────┐ ┌──────────────────────┐ │
│  │ Doc Chat RAG │ │  PPT Generation │ │  Feed Recommendation │ │
│  │              │ │  (gen→score→    │ │  (Qdrant+Neo4j+UCB)  │ │
│  │              │ │   refine loop)  │ │                      │ │
│  └──────────────┘ └─────────────────┘ └──────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  LLM Providers                                                  │
│  Gemini 2.5 Flash · Gemma 3n (Modal/A100/vLLM)                 │
│  T5-XL (HuggingFace Spaces/Gradio) · Qwen (WebSocket Realtime) │
│  Deepgram STT/TTS · Jina Embeddings                            │
├─────────────────────────────────────────────────────────────────┤
│  Data Storage Layer                                             │
│  Supabase (PostgreSQL + Storage) · Qdrant Cloud (4 collections) │
│  Neo4j Aura (Investor→Tag→SubTag graph + RL weight edges)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technologies Used

### Custom AI Models

| Model | Base Architecture | Role | Deployment |
|---|---|---|---|
| **Fine-tuned T5-XL** | `google/flan-t5-xl` (~3B params) with RoPE + Dilated Attention | Deep insight generation, contradiction analysis, and semantic cross-validation within the Evaluation Agent. Achieves +68.8% throughput and −58.6% memory vs. baseline. | Hugging Face Spaces (Gradio REST endpoint) |
| **Fine-tuned Gemma 3n** | `unsloth/gemma-3n-E2B-it` (5.4B params, 4-bit quantized) | Structured JSON generation for inner agent operations — enforces strict schema compliance for complex, nested business intelligence payloads that plain text models cannot reliably produce. | Modal serverless (NVIDIA A100 40GB, vLLM AsyncLLMEngine, up to 32 concurrent requests) |

**Why two separate fine-tuned models?** The T5-XL encoder-decoder architecture excels at free-form analytical reasoning and evidence synthesis (used for evaluation insights), while the Gemma 3n decoder-only model was required for strict structured output tasks where JSON schema adherence is critical for downstream agent processing.

### LLM Providers & Inference

| Provider | Models | Primary Use Cases |
|---|---|---|
| **Google Gemini** | `gemini-2.5-flash-lite` | Default LLM for idea check, chat, market research, SWOT/competitor matrix, document generation, recommendation synthesis, and Business Model Canvas |
| **Alibaba Qwen** | `qwen-turbo-2025-04-28`, `qwen-max` (Realtime API over WebSocket) | Pitch Analyzer pre-flight extraction, background analysis tools, and live voice interaction during pitch coaching sessions |
| **Groq** | `llama-3.1-8b` | AI-assisted semantic validation of training data during the data pipeline; fast inference fallback |
| **Ollama** | `gemma3:1b` | Optional local LLM provider for offline development |
| **Pollinations AI** | `gptimage-large` | Dynamic image and diagram generation for PowerPoint slides |
| **Jina AI** | `jina-embeddings-v2-base-en`, `jina-reranker-v1-base-en` | 1024-dimensional dense embeddings for the Feed Recommendation System (investor and pitch-deck vectors); cross-encoder reranking for semantic precision |

### Multi-Agent Orchestration

| Technology | Role |
|---|---|
| **LangGraph** | Stateful cyclic agent workflows with parallel fan-out support; drives all 10 principal AI subsystems |
| **LangChain** | LLM abstraction layer, prompt templates, chains, and tool wrappers |

### Real-Time Voice Infrastructure

| Technology | Role |
|---|---|
| **LiveKit** | WebRTC infrastructure for real-time audio transport during pitch coaching sessions |
| **Deepgram** (`nova-2`) | Real-time Speech-to-Text (STT) and Text-to-Speech (TTS) within the Pitch Analyzer |
| **Silero VAD** | Voice Activity Detection — speech gate preventing non-speech audio from reaching the LLM |
| **PyAudio** | Low-level audio stream capture in the pitch analyzer agent |

### Web Framework & API Layer

| Technology | Role |
|---|---|
| **FastAPI** | ASGI REST API framework; 18 route modules; BackgroundTasks for async evaluation jobs |
| **Uvicorn / Gunicorn** (UvicornWorker) | ASGI production server |
| **Pydantic v2** | Request/response validation and agent state schemas |
| **SlowAPI** | IP-based per-route rate limiting with 429 responses and `Retry-After` headers |

### Databases & Storage

| Technology | Role |
|---|---|
| **Supabase** (PostgreSQL + Storage) | Relational data (startups, users, documents, sessions); PPTX storage bucket; JSONB session reports |
| **Qdrant Cloud** | Vector database; 4 collections: `tags` (1024-dim), `investors`, `pitchdecks`, `investor_sub_vectors`; cosine similarity ANN search |
| **Neo4j Aura** | Property graph database modeling the `Investor → MainTag → SubTag` interest hierarchy; RL weight edges with exponential time-decay timestamps for the recommendation engine |
| **Python dict (JOBS)** | In-memory background evaluation job status store (Redis recommended for production) |

### Document & Presentation Generation

| Technology | Role |
|---|---|
| **python-pptx** | PowerPoint `.pptx` generation with structured `PPTSection` objects |
| **ReportLab / FPDF** | PDF report generation for evaluation and market research outputs |
| **Pillow** | Image processing for report assets |
| **matplotlib** | Chart generation embedded in pitch decks |

### PDF & Document Intelligence

| Technology | Role |
|---|---|
| **pdfplumber** | Primary PDF text and table extraction |
| **PyPDF2** | Secondary PDF extraction fallback |
| **PyMuPDF (fitz)** | Tertiary PDF extraction fallback |
| **python-pptx** | PPTX content parsing for document chat |
| **aiohttp** | Async fetching of remote URL documents for document chat |

### Web Intelligence & Search

| Technology | Role |
|---|---|
| **Serper API** | Google search results for market validation, competitor research, and funding benchmarks |
| **Tavily API** | Deep web search (advanced depth) for the Recommendation Agent's external intelligence gathering |
| **World Bank API** | Macro-economic indicators (inflation, GDP growth, unemployment, government debt) for country-level risk assessment in the Recommendation Agent |
| **Playwright** | Headless browser for website screenshots and tech-stack analysis |
| **Builtwith** | Tech-stack detection for startup product evaluation |
| **BeautifulSoup4** | HTML parsing and content extraction |

### DevOps, Hosting & MLOps

| Technology | Role |
|---|---|
| **Azure App Service** | Cloud hosting for the .NET backend and AI FastAPI layer; native CI/CD integration |
| **Modal** | Serverless GPU infrastructure (NVIDIA A100 40GB) for Gemma 3n model deployment with vLLM |
| **Hugging Face Spaces** | T5-XL model hosting via Gradio; serves as a scalable REST inference endpoint |
| **vLLM** | High-throughput inference engine for Gemma 3n; manages KV cache with 90% GPU memory allocation and 8192-token context |
| **Docker** | Containerized deployment for environment consistency |
| **GitHub Actions** | CI/CD pipeline: automated testing, Docker build, and push to Docker Hub on merge to `main` |

### Backend & Frontend

| Technology | Role |
|---|---|
| **.NET (C# MVC)** | Core backend API, business logic, user management, notification services, and API gateway |
| **React / Next.js** | Frontend UI with role-specific dashboards for Founders, Investors, and Contributors |

### Training & Evaluation Frameworks

| Technology | Role |
|---|---|
| **PyTorch** | Model training, LoRA fine-tuning, and custom architecture implementation |
| **Hugging Face Transformers** | Pre-trained model loading, tokenizers, and training utilities |
| **Unsloth** | Efficient fine-tuning framework for Gemma 3n with automatic precision patching |
| **PEFT / LoRA** | Parameter-efficient fine-tuning (`r=16, α=32`) across all attention projections |
| **SentenceTransformers** | Semantic similarity evaluation (all-MiniLM-L6-v2) |
| **RAGAS** | Claim-level hallucination evaluation |
| **NLTK** | METEOR score computation |
| **RoBERTa-MNLI** | NLI entailment-based faithfulness evaluation |

---

## API Documentation

The FastAPI application registers **18 route modules** covering all platform capabilities. Interactive Swagger UI is available at `http://localhost:8000/docs` when running locally, and at `https://spark2scale-server.azurewebsites.net/swagger/index.html` in production.

All endpoints require JWT Bearer token authentication via the `Authorization: Bearer <token>` header. Administrative endpoints additionally require the `X-Admin-Secret` header.

### Evaluation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/evaluation/evaluate/all` | Start the 9-dimension parallel evaluation (async); returns `job_id` |
| `GET` | `/api/v1/evaluation/evaluate/status/{job_id}` | Poll evaluation job status and fetch `full_report` when complete |
| `POST` | `/api/v1/evaluation/generate-report` | Render evaluation results into founder + investor PDF reports (returned as ZIP) |

### PowerPoint Generation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/ppt/generate` | Generate a pitch-deck PPTX from structured startup JSON |
| `POST` | `/api/v1/ppt/generate/upload` | Generate a deck from an uploaded source file |
| `POST` | `/api/v1/ppt/edit` | Apply founder-requested edits to an existing deck |

### Strategic Recommendation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/recommend` | Generate a strategic recommendation memo from evaluation scores |
| `GET` | `/api/v1/investors/{user_id}/subtags` | Retrieve an investor's interest sub-tags from Neo4j |

### Market Research

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/market-research/research` | Run the full parallel market-research pipeline (TAM/SAM/SOM, competitors, trends, finance) |
| `POST` | `/api/v1/market-research/validate-idea` | Lightweight idea and problem validation |

### Document Generation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/swot/generate` | Generate a SWOT + TOWS analysis document |
| `POST` | `/api/v1/competitor-matrix/generate` | Build a competitor analysis matrix |
| `POST` | `/api/v1/bmc/generate` | Generate a 9-block Business Model Canvas |
| `POST` | `/api/v1/bmc/enhance` | Apply founder-requested changes to an existing BMC |

### AI Chat & Document Intelligence

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Conversational startup assistant (Gemini) |
| `POST` | `/api/v1/chat/update-startup-data` | Extract only changed startup fields from chat history |
| `POST` | `/api/v1/document-chat/test-document-qa` | Multi-turn Q&A over an uploaded document (PDF / PPTX / JSON / URL) |
| `POST` | `/api/v1/chat-summarizer/summarize` | Extract actionable document changes from a founder conversation |

### PDF & Data Extraction

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/pdf/extract-from-pdf` | Extract structured startup data from an uploaded PDF |

### Pitch Analyzer (Live Voice Coaching)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/pitch-analyzer/env-check` | Verify required pitch-analyzer environment variables |
| `POST` | `/api/v1/pitch-analyzer/extract` | LLM pre-flight extraction — compresses startup documents into a cached VC cheat sheet |
| `GET` | `/api/v1/pitch-analyzer/worker-status` | Check whether the AI worker is running |
| `POST` | `/api/v1/pitch-analyzer/start` | Spawn the LiveKit real-time agent worker |
| `POST` | `/api/v1/pitch-analyzer/stop` | Gracefully stop the AI agent worker |
| `POST` | `/api/v1/pitch-analyzer/token` | Generate a LiveKit JWT for the pitch session |
| `POST` | `/api/v1/pitch-analyzer/generate-report` | Build the Investment-Readiness report from session state |
| `GET` | `/api/v1/pitch-analyzer/get-report` | Retrieve the last generated pitch report |

### Feed Recommendation Engine

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/feed/recommend/{investor_id}` | Ranked pitch-deck feed (graph + embeddings + UCB) |
| `POST` | `/api/v1/feed/interactions` | Record a swipe/like interaction to update investor preferences |
| `GET` | `/api/v1/feed/similar-investors/{investor_id}` | Find investors similar to a given investor |
| `GET` | `/api/v1/feed/investors/{user_id}/subtags` | Investor's interested sub-tags (feed-side) |
| `POST` | `/api/v1/feed/investor-embedding` | Compute and store one investor's embedding |
| `POST` | `/api/v1/feed/pitchdeck-embedding` | Compute and store one pitch deck's embedding |
| `POST` | `/api/v1/feed/investor-embedding/batch` | Batch-embed all investors |
| `POST` | `/api/v1/feed/pitchdeck-embedding/batch` | Batch-embed all pitch decks |
| `POST` | `/api/v1/feed/sub-vectors/build/{investor_id}` | Rebuild an investor's per-sub-tag preference vectors |
| `GET` | `/api/v1/feed/health` | Vector DB and feed health check |

### Administration & Webhooks

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/feed/collections/init` | Initialize vector collections |
| `DELETE` | `/api/v1/feed/collections` | Drop and reset vector collections |
| `POST` | `/api/v1/feed/admin/sync-neo4j` | Sync the interest graph into Neo4j |
| `GET` | `/api/v1/feed/admin/verify-sync` | Verify the Neo4j sync state |
| `POST` | `/api/v1/feed/neo4j/sync` | Admin-trigger a full Neo4j graph sync |
| `POST` | `/api/v1/feed/webhook/investor` | Webhook: upsert or refresh an investor |
| `POST` | `/api/v1/feed/webhook/pitchdeck` | Webhook: upsert or refresh a pitch deck |

### Request / Response Format

All endpoints accept and return `application/json`. Evaluation endpoints accept a `startup_data` object matching the startup schema. See `app/api/schemas.py` for the full input schema.

**Example — start evaluation:**

```python
import requests

payload = {
    "startup_data": {
        "startupname": "TechVenture",
        "field": "FinTech",
        "idea_description": "AI-powered micro-lending for underserved SMEs in MENA",
        "region": "Egypt",
        "startup_stage": "pre-seed",
        "founder_profiles": [...],
        "product": {...},
        "market": {...}
    }
}

# Start evaluation — returns job_id
response = requests.post(
    "http://localhost:8000/api/v1/evaluation/evaluate/all",
    json=payload,
    headers={"Authorization": "Bearer <token>"}
)
job_id = response.json()["job_id"]

# Poll until complete
import time
while True:
    status = requests.get(
        f"http://localhost:8000/api/v1/evaluation/evaluate/status/{job_id}",
        headers={"Authorization": "Bearer <token>"}
    ).json()
    if status["status"] == "completed":
        report = status["full_report"]
        break
    time.sleep(5)
```

---

## Environment Requirements

### Prerequisites

- **Python 3.11**
- **Docker** (for containerized deployment)
- API keys for: Google Gemini, Qwen, LiveKit, Supabase, Serper, Tavily, Deepgram, Jina AI, Qdrant Cloud, Neo4j Aura

### Environment Variables

Create a `.env` file in the project root:

```env
# Core LLM
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
QWEN_API_KEY=your_qwen_api_key

# Custom Model Endpoints
T5_SPACE_URL=your_huggingface_space_gradio_url
GEMMA_MODAL_URL=your_modal_gemma_endpoint_url

# Relational Database
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key

# Vector Database
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key

# Graph Database
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password

# Embeddings & Reranking
JINA_API_KEY=your_jina_api_key

# Real-time voice (pitch sessions)
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
DEEPGRAM_API_KEY=your_deepgram_api_key

# Web search
SERPER_API_KEY=your_serper_api_key
TAVILY_API_KEY=your_tavily_api_key

# Security
ADMIN_SECRET=your_admin_shared_secret
JWT_SECRET=your_jwt_secret

# Monitoring (optional)
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true
```

---

## Setup Instructions

### Local Setup (without Docker)

```bash
# 1. Clone the repository
git clone https://github.com/17-doha/Spark2Scale-AI-1.git
cd Spark2Scale-AI-1

# 2. Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright browser
playwright install chromium

# 5. Configure environment variables
cp .env.example .env
# Edit .env with your API keys

# 6. Start Qdrant locally via Docker (or point QDRANT_URL to Qdrant Cloud)
docker run -p 6333:6333 qdrant/qdrant

# 7. Run the API server
python run_api.py
# or
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## Deployment

### Docker

```bash
# Build the image
docker build -t spark2scale-ai .

# Run the container
docker run -p 80:80 --env-file .env spark2scale-ai
```

### Docker Compose with Monitoring

```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

### Azure App Service

1. Build and push the Docker image to Azure Container Registry or Docker Hub.
2. Create an Azure App Service (Linux, Docker container).
3. Set all `.env` keys as **Application Settings** in the Azure portal.
4. Enable **Always On** and set the HTTP timeout to at least 300 seconds (LangGraph pipelines are long-running).

> The container uses a single Gunicorn worker (`-w 1`) by design — the LiveKit agent runs as a module-level process and multiple workers cause room duplication. Scale horizontally via multiple container instances instead.

---

## Testing

### Unit & Integration Tests

```bash
pytest tests/ -v
```

Key test coverage by module:

| Component | Coverage | Test Type |
|---|---|---|
| Document Chat | 98% | Unit + Integration |
| Idea Check | 100% | Unit + Integration |
| PDF Extractor | 87% | Unit + Integration |
| PPT Generation | 86% | Unit + Integration |
| Competitor Analysis | 85% | Unit |
| SWOT | 85% | Unit |
| Chat Summarizer | 90% | Unit |
| Gemma Model | 70% | Unit + Integration |
| Evaluation Agent | 70% | Unit + Integration |
| Recommendation | 51% | Unit + Integration |
| Feed Recommendation | 36% | Unit + Integration |
| Market Research | 21% | Unit + Integration |
| Pitch Analyzer | 21% | Unit |

### CI/CD Pipeline

The GitHub Actions pipeline runs automatically on every push to `main`:

1. Installs system dependencies and injects API keys from GitHub Secrets.
2. Runs the full offline test suite (live model tests skipped by default; add `test-gemma` to the commit message to include Gemma endpoint tests).
3. On all tests passing, builds the Docker image and pushes to Docker Hub.
4. On any test failure, deployment is aborted.

### API Testing

All 32 tested endpoints pass with a 100% pass rate. Average response time: ~24,866 ms (dominated by long-running market research and competitor matrix pipelines). Run the full API test suite with:

```bash
python api_test_runner.py
```

---

## Live Platform

| Resource | URL |
|---|---|
| Frontend | https://spark2scale-client.azurewebsites.net |
| API Swagger | https://spark2scale-server.azurewebsites.net/swagger/index.html |
| GitHub Repository | https://github.com/mariamelghandoor/Spark2scale_ |
| T5-XL Model (HuggingFace) | https://huggingface.co/Dohahemdann/Spark2Scale-Space |
| Training Dataset | https://huggingface.co/datasets/Spark2scale/business-qa-analysis |
| Gemma 3n Fine-tuned | https://huggingface.co/Spark2scale/gemma_3n_spark2scale-4500-5 |
