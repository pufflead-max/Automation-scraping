FROM apache/airflow:2.9.3-python3.11

USER root

# System dependencies for Chromium + Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install scraper dependencies
COPY scraper/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Airflow providers - use constraints to ensure compatibility
RUN pip install --no-cache-dir \
    apache-airflow-providers-mongo==4.1.1 \
    psycopg2-binary==2.9.9

# Runtime environment
ENV PYTHONPATH="/opt/airflow/scraper/src"
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# DO NOT override ENTRYPOINT or CMD - let the base image handle it