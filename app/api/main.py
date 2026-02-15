from fastapi import FastAPI
from app.api.routes import ppt_generation, evaluation, market_research, recommendation
import uvicorn

app = FastAPI(title="Spark2Scale AI Agent")

app.include_router(ppt_generation.router, prefix="/api/v1/ppt", tags=["PPT Generation"])
app.include_router(evaluation.router, prefix="/api/v1/evaluation", tags=["Evaluation"])

app.include_router(recommendation.router, prefix="/api/v1", tags=["Recommendation"])

app.include_router(market_research.router, prefix="/api/v1/market-research", tags=["Market Research"])


@app.get("/")
def read_root():
    return {"message": "Spark2Scale AI Agent Service is Running"}
