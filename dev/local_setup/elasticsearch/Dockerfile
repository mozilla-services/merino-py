ARG STACK_VERSION=8.18.1
FROM docker.elastic.co/elasticsearch/elasticsearch:${STACK_VERSION}
RUN elasticsearch-plugin install --batch analysis-icu
