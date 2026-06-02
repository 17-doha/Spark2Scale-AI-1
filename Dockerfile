# Use an official Python runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    curl \
    portaudio19-dev \
    libasound2-dev \
    python3-dev \
    ffmpeg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb-dri3-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binary directly (dependencies are installed above)
RUN playwright install chromium

# Copy the application code
COPY . .

# Expose the port Azure expects
EXPOSE 80

# Use Gunicorn with a high timeout to allow for T5 and LangGraph processing
# -w 1: single worker is required because worker_process is a module-level global.
#        With -w 2, each worker has its own NULL copy and spawns a second agent
#        into the same LiveKit room, causing the "connecting" loop.
#        Use Azure horizontal scaling (multiple container instances) for traffic load.
# Adding logging flags so Azure can capture crash logs, and binding dynamically so Azure proxy port mapping succeeds.
CMD sh -c "gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 900 --access-logfile - --error-logfile - --bind 0.0.0.0:${WEBSITES_PORT:-80} main:app"