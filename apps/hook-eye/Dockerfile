ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim AS app_base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV UV_COMPILE_BYTECODE=1
ENV APP_HOME=/app

# Set working directory
WORKDIR $APP_HOME

RUN groupadd --gid 10001 app \
  && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

# uv needs every workspace manifest, but only this service and its shared package.
COPY pyproject.toml uv.lock LICENSE version.json ./
COPY apps/hook-eye ./apps/hook-eye
COPY packages/merino-common ./packages/merino-common
COPY apps/merino/pyproject.toml ./apps/merino/pyproject.toml
COPY apps/fleece/pyproject.toml ./apps/fleece/pyproject.toml
COPY tools/load-tests/pyproject.toml ./tools/load-tests/pyproject.toml

# Every dependency ships a wheel for this image, so no build tools are needed.
RUN uv sync --frozen --no-cache --no-dev --package merino-common --package merino-hook-eye && \
    rm -rf /root/.cache

# Set the PATH environment variable
ENV PATH="$APP_HOME/.venv/bin:$PATH"

FROM app_base AS web_api

EXPOSE 8000

USER app

ENTRYPOINT ["uv", "run", "--no-project", "fastapi", "run"]
# Note:
#   * Only use one Uvicorn worker process per container, and run a single replica: every
#     replica scrapes the cluster and reports the same series.
#   * The HTTP server exists for the Dockerflow endpoints (Kubernetes probes); it serves no API.
CMD ["apps/hook-eye/merino_hook_eye/main.py", "--host", "0.0.0.0", "--port", "8000"]
