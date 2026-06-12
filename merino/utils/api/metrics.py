"""A utility module for merino API metrics."""

from collections import Counter
from aiodogstatsd import Client

from merino.providers.suggest.base import BaseProvider, BaseSuggestion


def emit_suggestions_per_metrics(
    metrics_client: Client,
    suggestions: list[BaseSuggestion],
    searched_providers: list[BaseProvider],
) -> None:
    """Emit metrics for suggestions per request and suggestions per request by provider."""
    metrics_client.histogram("suggestions-per.request", value=len(suggestions))

    suggestion_counter = Counter(suggestion.provider for suggestion in suggestions)

    for provider in searched_providers:
        provider_name = provider.name
        suggestion_count = suggestion_counter[provider_name]
        metrics_client.histogram(
            f"suggestions-per.provider.{provider_name}",
            value=suggestion_count,
        )


def emit_normalization_metrics(
    metrics_client: Client,
    suggestions: list[BaseSuggestion],
    searched_providers: list[BaseProvider],
    normalization_providers: frozenset[str],
    query_changed: dict[str, bool],
) -> None:
    """Emit metrics for query normalization.

    For each normalized provider, tracks whether the normalized query produced
    a suggestion and whether that provider's pipeline changed the query.
    """
    suggestion_providers = {s.provider for s in suggestions}
    for provider in searched_providers:
        if provider.name in normalization_providers:
            metrics_client.increment(
                "normalization.experiment.provider_match",
                tags={
                    "provider": provider.name,
                    "matched": str(provider.name in suggestion_providers),
                    "query_changed": str(query_changed.get(provider.name, False)),
                },
            )
