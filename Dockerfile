# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    ADHD_HUB_HOST=0.0.0.0 \
    ADHD_HUB_PORT=8787 \
    ADHD_HUB_DATA_DIR=/data

COPY pyproject.toml uv.lock README.md LICENSE ATTRIBUTION.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

VOLUME ["/data"]
EXPOSE 8787

# Host/port come from ADHD_HUB_* env (compose/.env), not hardcoded flags.
CMD ["uv", "run", "--no-dev", "adhd-hub", "serve"]
