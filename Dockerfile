ARG PYTHON_VERSION=3.12

# Use the base Python image
FROM python:${PYTHON_VERSION}-slim AS app_base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app

WORKDIR $APP_HOME

RUN groupadd --gid 10001 app \
  && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

# Copy local code to the container image.
COPY . $APP_HOME

# Install libmaxminddb* to build the MaxMindDB Python client with C extension.
# Set virtual environment and sync all dependencies. Remove unnecessary artifacts after
RUN apt-get update && \
    apt-get install --yes build-essential libmaxminddb0 libmaxminddb-dev && \
    uv sync --frozen --no-cache --no-dev --no-group load && \
    apt-get remove --yes build-essential && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

# Set the PATH environment variable
ENV PATH="$APP_HOME/.venv/bin:$PATH"

# Create a separate image for running jobs
FROM app_base AS job_runner
ENTRYPOINT ["uv", "run", "python", "-m", "merino.jobs.cli"]

# Create a separate image for the web app
FROM app_base AS web_api
EXPOSE 8000
USER app
ENTRYPOINT ["fastapi"]
# Note:
#   * fastapi uses uvicorn under the hood as the default ASGI server runner.
#   * `--proxy-headers` is used as Merino will be running behind an load balancer.
#   * Only use one Uvicorn worker process per container. Replication and container
#     management will be handled by container orchestration.

# Run the application.
CMD ["run", "merino/main.py", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
