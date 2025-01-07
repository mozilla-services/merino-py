ARG PYTHON_VERSION=3.12

# This stage is used to generate requirements.txt from Poetry
FROM python:${PYTHON_VERSION}-slim AS build

WORKDIR /tmp

# Pin Poetry to reduce image size
RUN pip install --no-cache-dir --quiet poetry-plugin-export

COPY ./pyproject.toml ./poetry.lock /tmp/

# Generating a requirements.txt from Poetry with the main and jobs dependencies i.e:
# [tool.poetry.dependencies] and [tool.poetry.group.jobs.dependencies]
RUN poetry export --no-interaction --with main,jobs --output requirements.txt --without-hashes

FROM python:${PYTHON_VERSION}-slim AS app_base

# Allow statements and log messages to immediately appear
ENV PYTHONUNBUFFERED=True

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set app home
ENV APP_HOME=/app
WORKDIR $APP_HOME

RUN groupadd --gid 10001 app \
  && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

# Copy local code to the container image.
COPY . $APP_HOME

COPY --from=build /tmp/requirements.txt $APP_HOME/requirements.txt

# Install libmaxminddb* to build the MaxMindDB Python client with C extension.
RUN apt-get update && \
  apt-get install --yes build-essential libmaxminddb0 libmaxminddb-dev && \
  pip install uv && \
  uv venv $VIRTUAL_ENV && \
  uv pip install --no-cache-dir --quiet --upgrade -r requirements.txt && \
  apt-get remove --yes build-essential && \
  apt-get -q --yes autoremove && \
  apt-get clean && \
  rm -rf /root/.cache

# Create a build context that can be used for running merino jobs
FROM app_base AS job_runner

ENTRYPOINT ["python", "-m", "merino.jobs.cli"]


# Now create the final context that runs the web api.
FROM app_base AS web_api

EXPOSE 8000

USER app

ENTRYPOINT ["uvicorn"]
# Note:
#   * `--proxy-headers` is used as Merino will be running behind an load balancer.
#   * Only use one Uvicorn worker process per container. Replication and container
#     management will be handled by container orchestration.
CMD ["merino.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
