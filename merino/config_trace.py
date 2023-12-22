"""Configure Trace"""
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

from merino.config import settings


def configure_trace() -> None:
    """Configure the tracer to export traces to the appropriate place."""
    provider = TracerProvider()
    external_exporter: SpanExporter | None = None

    if settings.debug and settings.enable_trace:
        external_exporter = ConsoleSpanExporter()
    elif settings.enable_trace:
        external_exporter = CloudTraceSpanExporter()  # type: ignore

    if external_exporter:
        processor = BatchSpanProcessor(external_exporter)
        provider.add_span_processor(processor)

        # Sets the global default tracer provider
        trace.set_tracer_provider(provider)
