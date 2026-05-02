from prometheus_client import Counter, Histogram, Gauge

# Agent invocation counters
ppt_generations = Counter(
    "ppt_generation_total",
    "Total PPT generation requests",
    ["status"]  # success / error
)

market_research_requests = Counter(
    "market_research_total",
    "Total market research requests",
    ["status"]
)

evaluation_requests = Counter(
    "evaluation_total",
    "Total evaluation requests",
    ["status"]
)

bmc_requests = Counter(
    "bmc_generation_total",
    "Total BMC generation requests",
    ["status"]
)

# LangGraph execution latency
langgraph_duration = Histogram(
    "langgraph_execution_seconds",
    "Time spent in LangGraph workflows",
    ["workflow"],  # market_research, evaluation, bmc, swot, etc.
    buckets=[1, 5, 15, 30, 60, 120, 300]
)

# Qdrant metrics
qdrant_query_duration = Histogram(
    "qdrant_query_seconds",
    "Qdrant ANN search latency",
    ["collection"],  # investors, pitchdecks, tags
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

qdrant_upsert_duration = Histogram(
    "qdrant_upsert_seconds",
    "Qdrant upsert latency",
    ["collection"]
)

# Neo4j metrics
neo4j_query_duration = Histogram(
    "neo4j_query_seconds",
    "Neo4j query latency",
    ["query_type"],  # subtag_fetch, weight_update, sync
    buckets=[0.05, 0.1, 0.5, 1.0, 5.0]
)

# Rate limiting
rate_limit_hits = Counter(
    "rate_limit_hits_total",
    "Total rate limit hits",
    ["endpoint"]
)

# Active LiveKit sessions
active_pitch_sessions = Gauge(
    "active_pitch_sessions",
    "Currently active pitch analyzer sessions"
)

# LLM provider errors
llm_errors = Counter(
    "llm_errors_total",
    "LLM API errors",
    ["provider", "error_type"]  # groq/gemini, 429/503/timeout
)