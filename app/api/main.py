from dotenv import load_dotenv
load_dotenv()  # must run before any module reads os.getenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import ppt_generation, evaluation, market_research, recommendation, pdf_extraction, chat, swot_generation, competitor_matrix, feed_recommedation, vdb_admin
from app.core.limiter import api_limiter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Spark2Scale AI Agent")

# Configure slowapi rate limiting (per-IP).
app.state.limiter = api_limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://spark2scale-client.azurewebsites.net/", "http://localhost:3000"], # For production, replace "*" with your specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ppt_generation.router, prefix="/api/v1/ppt", tags=["Presentation Generation"])
app.include_router(evaluation.router, prefix="/api/v1/evaluation", tags=["Evaluation"])

app.include_router(recommendation.router, prefix="/api/v1", tags=["Recommendation"])

app.include_router(market_research.router, prefix="/api/v1/market-research", tags=["Market Research"])

app.include_router(pdf_extraction.router, prefix="/api/v1/pdf", tags=["PDF Extraction"])

app.include_router(chat.router, prefix="/api/v1/chat", tags=["AI Chat"])

app.include_router(swot_generation.router, prefix="/api/v1/swot", tags=["SWOT Generation"])

app.include_router(competitor_matrix.router, prefix="/api/v1/competitor-matrix", tags=["Competitor Analysis"])

app.include_router(feed_recommedation.router, prefix="/api/v1/feed", tags=["Feed Recommendation"])
app.include_router(vdb_admin.router, prefix="/api/v1/feed", tags=["Vector DB Admin"])

@app.get("/")
def read_root():
    return {"message": "Spark2Scale AI Agent Service is Running"}
