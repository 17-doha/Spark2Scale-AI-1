from fastapi import FastAPI
from app.api.routes import ppt_generation, evaluation, market_research, recommendation, pdf_extraction
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Spark2Scale AI Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://spark2scale-client.azurewebsites.net/"], # For production, replace "*" with your specific frontend URL
    allow_credentials=True,
    allow_methods=["*"], # This will allow the OPTIONS method
    allow_headers=["*"],
)
app.include_router(ppt_generation.router, prefix="/api/v1/ppt", tags=["PPT Generation"])
app.include_router(evaluation.router, prefix="/api/v1/evaluation", tags=["Evaluation"])

app.include_router(recommendation.router, prefix="/api/v1", tags=["Recommendation"])

app.include_router(market_research.router, prefix="/api/v1/market-research", tags=["Market Research"])

app.include_router(pdf_extraction.router, prefix="/api/v1/pdf", tags=["PDF Extraction"])


@app.get("/")
def read_root():
    return {"message": "Spark2Scale AI Agent Service is Running"}
