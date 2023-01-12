# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FROM python:3.9-slim

LABEL maintainer "Contextual Services Team <contextual-services-team@mozilla.com>"

# Add gcc since there are no wheels for some packages for arm64/aarch64
RUN apt-get update && apt-get install -y git
RUN if [ -n "$(arch | grep 'arm64\|aarch64')" ]; then apt install -y --no-install-recommends gcc python3-dev; fi

# Expose ports for the web UI and the locust master
EXPOSE 8089 5557

RUN useradd --create-home locust
WORKDIR /home/locust

ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1

ENV PYTHON_VENV=/venv
RUN python -m venv ${PYTHON_VENV}
ENV PATH="${PYTHON_VENV}/bin:${PATH}"

RUN python -m pip install --upgrade pip

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install -r /tmp/requirements.txt

COPY locust_tests ./

USER locust
ENTRYPOINT [ "locust" ]
