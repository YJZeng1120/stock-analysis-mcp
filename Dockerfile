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

# MCP stdio: reads from stdin, writes to stdout
CMD ["uv", "run", "--no-sync", "python", "finance.py"]
