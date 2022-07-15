ARG PYTHON_VERSION=3.10

# This stage is used to generate requirements.txt from Poetry
FROM python:${PYTHON_VERSION}-slim as build

WORKDIR /tmp

# Pin Poetry to reduce image size
RUN pip install --no-cache-dir --quiet poetry

COPY ./pyproject.toml ./poetry.lock /tmp/

# Just need the requirements.txt from Poetry
RUN poetry export --no-interaction --output requirements.txt --without-hashes

FROM python:${PYTHON_VERSION}-slim

# Allow statements and log messages to immediately appear
ENV PYTHONUNBUFFERED True

# Set app home
ENV APP_HOME /app
WORKDIR $APP_HOME

RUN groupadd --gid 10001 app \
  && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

# Copy local code to the container image.
COPY . $APP_HOME

COPY --from=build /tmp/requirements.txt $APP_HOME/requirements.txt

RUN pip install --no-cache-dir --quiet --upgrade -r requirements.txt

EXPOSE 8000

USER app

ENTRYPOINT ["uvicorn"]
# Note:
#   * `--proxy-headers` is used as Merino will be running behind an load balancer.
#   * Only use one Uvicorn worker process per container. K8s will take care of
#     replication and container management.
CMD ["merino.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
