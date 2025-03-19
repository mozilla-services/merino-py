# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FROM python:3.12-slim-bookworm

LABEL maintainer="Content Discovery Services (DISCO) Team <disco-team@mozilla.com>"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy over app dependencies
COPY ./pyproject.toml ./uv.lock ./

# Add gcc since there are no wheels for some packages for arm64/aarch64
# (g++/make for gevent on pypy)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential python3-dev && \
    uv sync --frozen --no-cache --group load --no-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHON_VENV=/.venv
ENV PATH="${PYTHON_VENV}/bin:${PATH}"

# Add locust as a non-root user
RUN useradd --create-home locust
WORKDIR /home/locust

# Copy application files
COPY ./dev ./dev
COPY ./merino ./merino
COPY ./tests/load/common ./tests/load/common
COPY ./tests/load/data ./tests/load/data
COPY ./tests/load/locustfiles ./tests/load/locustfiles


# Expose ports for the web UI and the locust master
EXPOSE 8089 5557

USER locust
ENTRYPOINT ["uv", "run", "--no-project", "locust", "-f", "tests/load/locustfiles/"]
