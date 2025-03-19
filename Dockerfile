ARG PYTHON_VERSION=3.12

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

# Copy local code to the container image
COPY . $APP_HOME

# Install maxmind db and app dependencies. Clean up build tools after
RUN apt-get update && \
    apt-get install --yes build-essential libmaxminddb0 libmaxminddb-dev && \
    uv sync --frozen --no-cache --no-dev --no-group load && \
    apt-get remove --yes build-essential && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

# Set the PATH environment variable
ENV PATH="$APP_HOME/.venv/bin:$PATH"

# Create a build context that can be used for running merino jobs
FROM app_base AS job_runner

# Set entrypoint to use uv
ENTRYPOINT ["uv", "run", "--no-project", "python", "-m", "merino.jobs.cli"]

# Now create the final context that runs the web api
FROM app_base AS web_api

EXPOSE 8000

USER app

ENTRYPOINT ["uv", "run", "--no-project", "fastapi", "run"]
# Note:
#   * `--proxy-headers` is used as Merino will be running behind an load balancer.
#   * Only use one Uvicorn worker process per container. Replication and container
#     management will be handled by container orchestration.
CMD ["merino/main.py", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
