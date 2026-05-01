# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – builder: install deps into a venv
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install only what's needed to build
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – runtime: minimal image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root
RUN addgroup --system robot && adduser --system --ingroup robot robot

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/main.py .

# Drop privileges
USER robot

EXPOSE 8080

# Healthcheck (Docker engine will mark container unhealthy if this fails)
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENV PORT=8080

CMD ["python", "main.py"]
