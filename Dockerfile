FROM python:3.10-slim

# Install system deps + Playwright deps
RUN apt-get update && apt-get install -y \
    wget gnupg \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium (arm64 compatible)
RUN playwright install chromium

# Copy app
COPY . .

# Docker runtime optimizations
ENV PLAYWRIGHT_BROWSERS_PATH=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 7777

CMD ["python", "main.py"]
