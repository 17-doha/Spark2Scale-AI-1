from fastapi import FastAPI
import uvicorn
from app.api.main import app  # Ensure this import path is correct based on your folder structure
from app.core.logger import get_logger

logger = get_logger("main")

# This wrapper function isn't strictly necessary for Docker but is fine to keep
def main():
    logger.info("Starting Spark2Scale AI API Server...")
    # In Docker, we usually let the CMD handle execution, but this is fine for local debug
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    # In Docker, the CMD command triggers uvicorn directly.
    # This block is only used if you run `python main.py` manually.
    main()