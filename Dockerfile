FROM python:3.10-slim

# Install ALL Playwright dependencies + fonts for stable browser rendering
RUN apt-get update && apt-get install -y \
    # Playwright core deps
    wget gnupg ca-certificates \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    # Additional deps for headless stability
    libxss1 libxrandr2 libasound2 libpangocairo-1.0-0 libatk-bridge2.0-0 \
    libxkbcommon-x11-0 libgtk-3-0 libgdk-pixbuf2.0-0 libdbus-glib-1-2 \
    # Fonts for proper text rendering
    fonts-liberation fonts-noto-color-emoji ttf-ubuntu-font-family \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + ONLY Chromium (arm64 compatible)
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Essential Docker environment variables for Playwright
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=0 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    NODE_VERSION=18 \
    DISPLAY="" \
    DBUS_SESSION_BUS_ADDRESS="" \
    QT_X11_NO_MITSHM=1

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7777

CMD ["python", "main.py"]
