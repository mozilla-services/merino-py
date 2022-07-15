# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.10-slim

# Set app home
ENV APP_HOME /app

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

WORKDIR $APP_HOME

# Copy local code to the container image.
COPY . $APP_HOME

RUN groupadd --gid 10001 app
RUN useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

USER app

ENTRYPOINT ["gunicorn"]

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD ["--worker-class", "uvicorn.workers.UvicornWorker", "--bind", ":8080", "--threads", "8", "merino.server:app"]
