FROM python:3.11-slim-buster

LABEL maintainer="Content Discovery Services (DISCO) Team <disco-team@mozilla.com>"

ENV PYTHON_VENV=/venv
RUN python -m venv ${PYTHON_VENV}
ENV PATH="${PYTHON_VENV}/bin:${PATH}"

RUN python -m pip install --upgrade pip

# Setup poetry and install requirements
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VERSION=1.7
RUN python -m pip install --no-cache-dir --quiet poetry
COPY pyproject.toml poetry.lock ./
RUN poetry install --without client --no-interaction --no-ansi

COPY ./kinto-setup /usr/src/cli
WORKDIR /usr/src/cli

CMD [ "python", "main.py" ]
