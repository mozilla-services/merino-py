"""Unit tests for the sanitized search term log data creator."""

from merino_common.models.suggest_logging import (
    SanitizedSearchTermLog,
    SuggestRequestParams,
)

from merino_fleece.utils.log_data_creator import create_search_term_log


def test_every_field_maps_across() -> None:
    """Each logged field is taken from its `SuggestRequestParams` counterpart.

    `rid` is renamed to `request_id` on the way out, which is the one mapping a
    field-for-field copy would not catch.
    """
    params = SuggestRequestParams(
        query="the weather today",
        code=200,
        rid="request-id",
        session_id="session-id",
        sequence_no=3,
        client_variants="variant",
        requested_providers="adm",
        country="US",
        region="CA",
        city="San Francisco",
        dma=807,
        browser="Firefox(120)",
        os_family="macos",
        form_factor="desktop",
    )

    log_data = create_search_term_log(params)

    assert log_data == SanitizedSearchTermLog(
        query="the weather today",
        request_id="request-id",
        session_id="session-id",
        sequence_no=3,
        country="US",
        region="CA",
        city="San Francisco",
        dma=807,
        browser="Firefox(120)",
        os_family="macos",
        form_factor="desktop",
    )


def test_sensitive_is_set_without_the_caller_passing_it() -> None:
    """The record is flagged sensitive even though the source params never mention it.

    The flag lives on the model as a default rather than being passed at the call
    site, so no future caller can emit an unflagged record.
    """
    params = SuggestRequestParams(
        query="the weather today",
        code=200,
        rid="request-id",
        client_variants="",
        requested_providers="",
        browser="Firefox",
        os_family="macos",
        form_factor="desktop",
    )

    assert create_search_term_log(params).model_dump()["sensitive"] is True


def test_request_only_fields_are_dropped() -> None:
    """Fields that are not part of the search terms data log do not reach the record."""
    params = SuggestRequestParams(
        query="the weather today",
        code=200,
        rid="request-id",
        client_variants="variant",
        requested_providers="adm",
        browser="Firefox",
        os_family="macos",
        form_factor="desktop",
    )

    dumped = create_search_term_log(params).model_dump()

    assert "code" not in dumped
    assert "client_variants" not in dumped
    assert "requested_providers" not in dumped


def test_optional_fields_default_to_none() -> None:
    """Unset optional request params stay unset on the record rather than erroring."""
    params = SuggestRequestParams(
        query="the weather today",
        code=200,
        rid="request-id",
        client_variants="",
        requested_providers="",
        browser="Firefox",
        os_family="macos",
        form_factor="desktop",
    )

    log_data = create_search_term_log(params)

    assert log_data.session_id is None
    assert log_data.sequence_no is None
    assert log_data.country is None
    assert log_data.region is None
    assert log_data.city is None
    assert log_data.dma is None


def test_missing_query_becomes_empty_string() -> None:
    """A `None` query is coerced, since the log model requires a string.

    Callers skip queryless terms, so this is defensive: it keeps the creator total
    rather than letting it raise a validation error.
    """
    params = SuggestRequestParams(
        query=None,
        code=200,
        rid="request-id",
        client_variants="",
        requested_providers="",
        browser="Firefox",
        os_family="macos",
        form_factor="desktop",
    )

    assert create_search_term_log(params).query == ""
