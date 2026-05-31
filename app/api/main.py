from dotenv import load_dotenv
load_dotenv()  # must run before any module reads os.getenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import ppt_generation, evaluation, market_research, recommendation, pdf_extraction, chat, swot_generation, competitor_matrix, pitch_analyzer, document_chat, bmc, chat_summarizer, feed_recommedation, vdb_admin
from app.core.limiter import api_limiter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
# from prometheus_fastapi_instrumentator import Instrumentator
from app.api.routes import github_webhook
# from app.core.metrics import metrics_endpoint

app = FastAPI(title="Spark2Scale AI Agent")
app.state.limiter = api_limiter
app.include_router(github_webhook.router, prefix="/api/v1/github", tags=["GitHub"])
# app.add_route("/metrics", metrics_endpoint)

# Instrumentator(
#     should_group_status_codes=True,
#     excluded_handlers=["/metrics"],
# ).instrument(app).expose(app)

@app.exception_handler(RateLimitExceeded)
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )

@app.exception_handler(ValueError)
def value_error_handler(request: Request, exc: ValueError):
    # slowapi raises ValueError when it cannot parse the rate-limit key
    # (e.g. missing/malformed X-Forwarded-For behind Azure's proxy).
    # Return 429 so it doesn't bubble up as a 500.
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://spark2scale-ai-api-server.azurewebsites.net/", "http://localhost:3000", "https://spark2scale-client.azurewebsites.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SlowAPIMiddleware must be added AFTER CORSMiddleware so that CORS headers
# are set even on rate-limited (429) responses.
app.add_middleware(SlowAPIMiddleware)

app.include_router(ppt_generation.router, prefix="/api/v1/ppt", tags=["Presentation Generation"])
app.include_router(evaluation.router, prefix="/api/v1/evaluation", tags=["Evaluation"])
app.include_router(recommendation.router, prefix="/api/v1", tags=["Recommendation"])
app.include_router(market_research.router, prefix="/api/v1/market-research", tags=["Market Research"])
app.include_router(pdf_extraction.router, prefix="/api/v1/pdf", tags=["PDF Extraction"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["AI Chat"])
app.include_router(swot_generation.router, prefix="/api/v1/swot", tags=["SWOT Generation"])
app.include_router(competitor_matrix.router, prefix="/api/v1/competitor-matrix", tags=["Competitor Analysis"])
app.include_router(pitch_analyzer.router, prefix="/api/v1/pitch-analyzer", tags=["Pitch Analyzer"])
app.include_router(document_chat.router, prefix="/api/v1/document-chat", tags=["Document Chat"])
app.include_router(bmc.router, prefix="/api/v1/bmc", tags=["Business Model Canvas"])
app.include_router(chat_summarizer.router, prefix="/api/v1/chat-summarizer", tags=["Chat Summarizer"])

app.include_router(feed_recommedation.router, prefix="/api/v1/feed", tags=["Feed Recommendation"])
app.include_router(vdb_admin.router, prefix="/api/v1/feed", tags=["Vector DB Admin"])

@app.get("/")
def read_root():
    return {"message": "Spark2Scale AI Agent Service is Running now ...ssss"}