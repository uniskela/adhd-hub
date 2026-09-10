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

RUN uv sync --frozen --no-dev \
 && uv build --wheel -o /app/dist

ENV ADHD_HUB_WHEEL_DIR=/app/dist

VOLUME ["/data"]
EXPOSE 8787

# Host/port come from ADHD_HUB_* env (compose/.env), not hardcoded flags.
# Use the synced venv binary so start does not re-resolve against PyPI
# (uv run would fail under UV_OFFLINE=1 / flaky egress).
ENV UV_OFFLINE=1
CMD [".venv/bin/adhd-hub", "serve"]
