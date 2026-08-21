# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FROM python:3.14-slim-bookworm

LABEL maintainer="Content Discovery Services (DISCO) Team <disco-team@mozilla.com>"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy over app dependencies
COPY ./pyproject.toml ./uv.lock ./

# Copy application files (this needs to be done prior to `uv sync` below)
COPY ./dev ./dev
COPY ./apps/merino ./apps/merino
COPY ./apps/fleece/pyproject.toml ./apps/fleece/pyproject.toml
COPY ./packages/merino-common ./packages/merino-common
COPY ./tools/load-tests/pyproject.toml ./tools/load-tests/pyproject.toml

# Add gcc since there are no wheels for some packages for arm64/aarch64
# (g++/make for gevent on pypy)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential libxml2-dev libxslt-dev libzmq3-dev python3-dev libffi-dev && \
    uv sync --frozen --no-cache --no-dev --package merino-load-tests && \
    apt-get remove --yes build-essential libxml2-dev libxslt-dev python3-dev libffi-dev libzmq3-dev && \
    apt-get clean && \
    rm -rf /root/.cache && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHON_VENV=/app/.venv
ENV PATH="${PYTHON_VENV}/bin:${PATH}"
ENV PYTHONPATH="/home/locust/tools/load-tests"

# Add locust as a non-root user
RUN useradd --create-home locust
WORKDIR /home/locust
RUN ln -s /app/dev dev && \
    ln -s /app/apps/merino/merino merino && \
    ln -s /app/packages/merino-common merino-common

COPY ./tools/load-tests/common ./tools/load-tests/common
COPY ./tools/load-tests/data ./tools/load-tests/data
COPY ./tools/load-tests/locustfiles ./tools/load-tests/locustfiles


# Expose ports for the web UI and the locust master
EXPOSE 8089 5557

USER locust
ENTRYPOINT ["uv", "run", "--no-project", "locust", "-f", "tools/load-tests/locustfiles/"]
