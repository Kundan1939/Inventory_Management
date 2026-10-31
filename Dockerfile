FROM python:3.12-slim-bookworm

LABEL maintainer="IT Asset Manager Team" \
      description="IT Asset Manager v2 — Automated Hardware & Barcode Tracking Container"

# Network & Security Access Restrictions:
# - RESTRICT_PUBLIC_HTTP=true: Blocks direct HTTP access via public IP and port (HTTP 403 Forbidden).
# - ALLOW_LOCAL_IP=true: Permits unencrypted access only from local private networks (127.0.0.1, 192.168.x.x, 10.x.x.x).
# - Access via public internet is strictly enforced to require HTTPS (reverse proxy or SSL certs).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    BIND_HOST=0.0.0.0 \
    RESTRICT_PUBLIC_HTTP=true \
    ALLOW_LOCAL_IP=true \
    SSL_CERT_PATH=/app/certs/cert.pem \
    DB_TYPE=mysql \
    MYSQL_HOST=127.0.0.1 \
    MYSQL_PORT=3306

# Install essential system runtime libraries for OpenCV, RapidOCR, ONNX Runtime, and Healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create application user with fixed UID/GID for secure non-root execution
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

WORKDIR /app

# Create directory for mounting SSL/TLS certificates and application data
RUN mkdir -p /app/certs /app/data && \
    chown -R appuser:appgroup /app/certs /app/data

# Cache layer: install dependencies first
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and assets
COPY --chown=appuser:appgroup . .

RUN chmod +x /app/docker-entrypoint.sh

# Expose HTTP (port 5000) and HTTPS (port 443)
EXPOSE 5000 443

# Health check verifies web application responsiveness locally
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:5000/api/health || exit 1

USER appuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]
