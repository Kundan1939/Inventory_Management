#!/usr/bin/env bash
set -e

PORT="${PORT:-5000}"
BIND_HOST="${BIND_HOST:-0.0.0.0}"

# In production containers, default to min(4, 2 * cores) or 2 workers
NUM_CORES=$(nproc 2>/dev/null || echo 1)
DEFAULT_WORKERS=$(( NUM_CORES > 2 ? 4 : 2 ))
WORKERS="${GUNICORN_WORKERS:-$DEFAULT_WORKERS}"
THREADS="${GUNICORN_THREADS:-4}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"
GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-30}"
MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-1000}"
MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-100}"
LOG_LEVEL="${LOG_LEVEL:-info}"

# Ensure data and certs directory exist
mkdir -p /app/data /app/certs 2>/dev/null || true

# If custom command was supplied, run it (e.g. bash, python, etc.)
if [ "$#" -gt 0 ] && [ "${1:0:1}" != '-' ]; then
    exec "$@"
fi

# Detect SSL/TLS certificates if mounted in container
SSL_ARGS=()
CERT_FILE="${SSL_CERT_PATH:-/app/certs/cert.pem}"
KEY_FILE="${SSL_KEY_PATH:-/app/certs/key.pem}"
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "🔒 SSL Certificates found (${CERT_FILE}, ${KEY_FILE}). Starting with native HTTPS..."
    SSL_ARGS+=(--certfile "$CERT_FILE" --keyfile "$KEY_FILE")
fi

echo "🚀 Starting IT Asset Manager in PRODUCTION mode on ${BIND_HOST}:${PORT} (${WORKERS} worker(s), ${THREADS} thread(s), max-requests=${MAX_REQUESTS})..."
echo "🔒 Restriction Policy: Direct Public IP:Port = Blocked (403) | Local IP & HTTPS = Allowed"

exec gunicorn \
    --bind "${BIND_HOST}:${PORT}" \
    "${SSL_ARGS[@]}" \
    --workers "${WORKERS}" \
    --threads "${THREADS}" \
    --timeout "${TIMEOUT}" \
    --graceful-timeout "${GRACEFUL_TIMEOUT}" \
    --keep-alive 5 \
    --max-requests "${MAX_REQUESTS}" \
    --max-requests-jitter "${MAX_REQUESTS_JITTER}" \
    --log-level "${LOG_LEVEL}" \
    --access-logfile - \
    --error-logfile - \
    app:app "$@"
