# ==============================================================================
# NAWARI — Central Hub Application Container
# Hardened, non-root, multi-stage production container image
# ==============================================================================

# Build Stage: Dependency compilation & isolation
FROM python:3.13-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Stage: Minimal distroless-like runtime
FROM python:3.13-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="nawari-core" \
      org.opencontainers.image.description="Nawari Central Hub Enterprise Observability & Service Assurance Engine" \
      org.opencontainers.image.vendor="Kenya Airways PLC" \
      org.opencontainers.image.source="https://github.com/SirrPascal/nawari"

# Security: Dedicated unprivileged system user and group
RUN groupadd -g 10001 -r nawari && \
    useradd -u 10001 -r -g nawari -d /app -s /sbin/nologin nawari

# Install only curl for container healthchecking
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /app/.local

# Copy application services and deployment profiles
COPY --chown=nawari:nawari services /app/services
COPY --chown=nawari:nawari deploy/profiles /app/deploy/profiles

# Configure environment and path
ENV PATH="/app/.local/bin:${PATH}" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NAWARI_HOST="0.0.0.0" \
    NAWARI_PORT="8443"

EXPOSE 8443

USER nawari:nawari

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8443/api/v1/health || exit 1

ENTRYPOINT ["python3", "-m", "services.hub_daemon"]

