FROM python:3.12-slim-bookworm

LABEL maintainer="Content Discovery Services (DISCO) Team <disco-team@mozilla.com>"

ENV PYTHON_VENV=/.venv
RUN python -m venv ${PYTHON_VENV}
ENV PATH="${PYTHON_VENV}/bin:${PATH}"

RUN python -m pip install --upgrade pip

# Setup poetry and install requirements
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VERSION=1.7
RUN python -m pip install --no-cache-dir --quiet poetry
COPY pyproject.toml poetry.lock ./
RUN poetry install --without kinto --no-interaction --no-ansi --no-root

COPY ./client /usr/src/client
WORKDIR /usr/src/client

CMD [ "pytest" ]
