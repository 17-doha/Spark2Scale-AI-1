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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (since the library is used and missing browsers cause timeouts)
RUN playwright install --with-deps chromium

# Copy the application code
COPY . .

# Expose the port Azure expects
EXPOSE 80

# Use Gunicorn with a high timeout to allow for T5 and LangGraph processing
# Adding logging flags so Azure can capture crash logs, and binding dynamically so Azure proxy port mapping succeeds.
CMD sh -c "gunicorn -w 2 -k uvicorn.workers.UvicornWorker --timeout 300 --access-logfile - --error-logfile - --bind 0.0.0.0:${WEBSITES_PORT:-80} main:app"