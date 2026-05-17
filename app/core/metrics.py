# # app/core/metrics.py  — paste this file into your project

# from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
# from fastapi import Response
# import time

# # === COUNTERS ===
# evaluation_requests_total = Counter(
#     "evaluation_requests_total",
#     "Total number of evaluation pipeline runs",
#     ["stage"]  # label: Pre-Seed or Seed
# )

# agent_runs_total = Counter(
#     "agent_runs_total",
#     "Total calls per agent node",
#     ["agent_name", "status"]  # status: success | error
# )

# llm_calls_total = Counter(
#     "llm_calls_total",
#     "Total LLM API calls",
#     ["provider", "status"]  # provider: groq | gemini
# )

# # === HISTOGRAMS ===
# evaluation_duration_seconds = Histogram(
#     "evaluation_duration_seconds",
#     "Full pipeline duration in seconds",
#     ["stage"],
#     buckets=[10, 20, 30, 45, 60, 90, 120, 180, 240, 300]
# )

# agent_duration_seconds = Histogram(
#     "agent_duration_seconds",
#     "Per-agent execution time",
#     ["agent_name"],
#     buckets=[1, 2, 5, 10, 15, 20, 30, 60]
# )

# llm_latency_seconds = Histogram(
#     "llm_latency_seconds",
#     "LLM API call latency",
#     ["provider"],
#     buckets=[0.5, 1, 2, 3, 5, 10, 20, 30]
# )

# # === GAUGES ===
# active_evaluations = Gauge(
#     "active_evaluations",
#     "Number of evaluations currently running"
# )

# weighted_score_gauge = Gauge(
#     "evaluation_weighted_score",
#     "Weighted score of last completed evaluation",
#     ["stage"]
# )

# # === /metrics ENDPOINT ===
# def metrics_endpoint():
#     return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)