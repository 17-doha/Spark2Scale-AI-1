# Use an official Python runtime
FROM python:3.11-slim
 
# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for:
# - PDF/PPT generation (libcairo2, libpango)
# - Image processing (libgl1)
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port Azure expects
EXPOSE 80

# Run uvicorn directly on Port 80
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
