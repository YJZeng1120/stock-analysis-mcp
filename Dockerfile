FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no project itself, just deps)
RUN uv sync --frozen --no-install-project

# Copy source
COPY finance.py ./

ENV PYTHONUNBUFFERED=1
ENV MCP_TRANSPORT=http
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000

EXPOSE 8000

# Default: HTTP transport for external access via ngrok
# For local stdio mode: docker run --rm -i -e MCP_TRANSPORT=stdio stock-analysis-mcp:latest
CMD ["uv", "run", "--no-sync", "python", "finance.py"]
