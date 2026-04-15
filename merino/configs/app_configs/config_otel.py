# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""OpenTelemetry configuration for local development tracing."""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def configure_otel(app: FastAPI) -> None:  # pragma: no cover
    """Configure OpenTelemetry tracing if OTEL_EXPORTER_OTLP_ENDPOINT is set.

    Reads standard OTEL_* environment variables:
      OTEL_EXPORTER_OTLP_ENDPOINT - collector endpoint (e.g. http://localhost:4318)
      OTEL_SERVICE_NAME            - service name reported in traces (default: merino)
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.getenv("OTEL_SERVICE_NAME", "merino")
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    AioHttpClientInstrumentor().instrument()
    ElasticsearchInstrumentor().instrument()
    logger.info(f"OpenTelemetry tracing enabled: endpoint={endpoint} service={service_name}")
