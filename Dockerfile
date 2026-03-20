FROM python:3.10-slim

WORKDIR /app

# Install ONLY essential Playwright deps (no broken packages)
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libxss1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium only (arm64 compatible)
RUN playwright install chromium

# Copy app code
COPY . .

# Docker + Playwright optimized environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=0

EXPOSE 7777

CMD ["python", "main.py"]
