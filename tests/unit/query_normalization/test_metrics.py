"""Unit tests for normalization experiment metrics."""

from unittest.mock import MagicMock

from merino.providers.suggest.base import BaseSuggestion, BaseProvider
from merino.utils.api.metrics import emit_normalization_metrics


def _mock_suggestion(provider: str) -> BaseSuggestion:
    """Create a mock suggestion with a given provider name."""
    s = MagicMock(spec=BaseSuggestion)
    s.provider = provider
    return s


def _mock_provider(name: str) -> BaseProvider:
    """Create a mock provider with a given name."""
    p = MagicMock(spec=BaseProvider)
    p.name = name
    return p


def test_emit_normalization_metrics_matched() -> None:
    """Emit metrics when provider matched."""
    client = MagicMock()
    suggestions = [_mock_suggestion("polygon")]
    providers = [_mock_provider("polygon"), _mock_provider("sports")]
    norm_providers = frozenset({"polygon", "sports"})

    emit_normalization_metrics(client, suggestions, providers, norm_providers, query_changed=True)

    assert client.increment.call_count == 2
    client.increment.assert_any_call(
        "normalization.experiment.provider_match",
        tags={"provider": "polygon", "matched": "True", "query_changed": "True"},
    )
    client.increment.assert_any_call(
        "normalization.experiment.provider_match",
        tags={"provider": "sports", "matched": "False", "query_changed": "True"},
    )


def test_emit_normalization_metrics_no_match() -> None:
    """Emit metrics when no provider matched."""
    client = MagicMock()
    suggestions: list[BaseSuggestion] = []
    providers = [_mock_provider("polygon")]
    norm_providers = frozenset({"polygon"})

    emit_normalization_metrics(client, suggestions, providers, norm_providers, query_changed=False)

    client.increment.assert_called_once_with(
        "normalization.experiment.provider_match",
        tags={"provider": "polygon", "matched": "False", "query_changed": "False"},
    )


def test_emit_normalization_metrics_skips_non_norm_providers() -> None:
    """Non-normalization providers should not emit metrics."""
    client = MagicMock()
    suggestions = [_mock_suggestion("adm")]
    providers = [_mock_provider("adm"), _mock_provider("polygon")]
    norm_providers = frozenset({"polygon"})

    emit_normalization_metrics(client, suggestions, providers, norm_providers, query_changed=True)

    assert client.increment.call_count == 1
    client.increment.assert_called_once_with(
        "normalization.experiment.provider_match",
        tags={"provider": "polygon", "matched": "False", "query_changed": "True"},
    )
