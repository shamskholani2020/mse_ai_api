FROM python:3.10-slim

WORKDIR /app

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libxss1 libx11-xcb1 libxcb1 libxcb-dri3-0 \
    libatspi2.0-0 libgtk-3-0 \
    fonts-liberation fonts-noto-color-emoji \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# CRITICAL: Set browser path BEFORE installing browsers
# so install and runtime use the same location
ENV PLAYWRIGHT_BROWSERS_PATH=0

# Install Chromium browser into the package directory
RUN playwright install chromium

# Copy app code
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 7777

CMD ["python", "main.py"]
