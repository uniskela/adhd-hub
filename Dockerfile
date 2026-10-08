# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Do not leave a uv package archive cache in the final image — Trivy would
    # inventory those wheels as well as the installed .venv (duplicate CVEs).
    UV_NO_CACHE=1 \
    ADHD_HUB_HOST=0.0.0.0 \
    ADHD_HUB_PORT=8787 \
    ADHD_HUB_DATA_DIR=/data

COPY pyproject.toml uv.lock README.md LICENSE ATTRIBUTION.md ./
COPY src ./src
# Canonical sync sources must be present for hatch force-include → adhd_hub/share/.
COPY skills ./skills
COPY adapters ./adapters

# Pull current Debian security fixes into the final runtime image rather than
# inheriting stale OS packages from a cached base-image build.
RUN apt-get update \
 && apt-get upgrade -y \
 && rm -rf /var/lib/apt/lists/*

RUN uv sync --locked --no-dev \
 && uv build --wheel -o /app/dist \
 && rm -rf /root/.cache/uv /root/.cache/pip

ENV ADHD_HUB_WHEEL_DIR=/app/dist

VOLUME ["/data"]
EXPOSE 8787

# Host/port come from ADHD_HUB_* env (compose/.env), not hardcoded flags.
# Use the synced venv binary so start does not re-resolve against PyPI
# (uv run would fail under UV_OFFLINE=1 / flaky egress).
ENV UV_OFFLINE=1
CMD [".venv/bin/adhd-hub", "serve"]
