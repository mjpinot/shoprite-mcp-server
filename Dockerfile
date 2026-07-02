# -----------------------------------------------------------------------
# Stage 1 – builder
# -----------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libxml2-dev \
        libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a dedicated prefix
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------------
# Stage 2 – runtime
# -----------------------------------------------------------------------
FROM python:3.11-slim AS runtime

LABEL maintainer="mjpinot" \
      org.opencontainers.image.title="shoprite-mcp-server" \
      org.opencontainers.image.description="MCP server for Shoprite product data" \
      org.opencontainers.image.version="1.0.0"

# Runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create a non-root user
RUN useradd --create-home --shell /bin/bash mcpuser
WORKDIR /app

# Copy application source
COPY src/ ./src/
COPY pyproject.toml .

RUN chown -R mcpuser:mcpuser /app
USER mcpuser

# MCP servers communicate over stdio (stdin/stdout); no TCP port is exposed
# by default.  When used behind a proxy (e.g. nginx TCP stream or the SSE
# transport), set MCP_TRANSPORT=sse and BIND_HOST/BIND_PORT accordingly.
ENV SHOPRITE_BASE_URL="https://www.shoprite.com" \
    REQUEST_TIMEOUT="30" \
    MAX_PRODUCTS="50" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import src.server; print('ok')" || exit 1

CMD ["python", "-m", "src.server"]
