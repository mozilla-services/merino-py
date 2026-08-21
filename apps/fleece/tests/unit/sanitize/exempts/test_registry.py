"""Unit tests for the sanitization exempt registry and its lifecycle."""

from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

from merino_fleece.sanitize import exempts
from merino_fleece.sanitize.exempts.amp import AmpExempt


class StubExempt:
    """A `SanitizationExempt` over a fixed set of terms, recording its lifecycle calls."""

    def __init__(self, *terms: str, shutdown_error: Exception | None = None) -> None:
        self.terms = set(terms)
        self.shutdown_error = shutdown_error
        self.initialized = False
        self.shut_down = False

    async def initialize(self) -> None:
        """Mark the exempt as initialized."""
        self.initialized = True

    async def shutdown(self) -> None:
        """Mark the exempt as shut down, or raise the configured error."""
        self.shut_down = True
        if self.shutdown_error is not None:
            raise self.shutdown_error

    def is_exempt(self, search_term: str) -> bool:
        """Return whether the term is one of this stub's."""
        return search_term in self.terms


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Leave the process-wide registry empty around every test."""
    exempts._exempts.clear()
    yield
    exempts._exempts.clear()


def test_is_exempt_without_registered_exempts() -> None:
    """An empty registry exempts nothing, so every term is sanitized normally."""
    assert exempts.is_exempt("firefox") is False


def test_is_exempt_consults_every_registered_exempt() -> None:
    """A term is exempt if any registered exempt covers it."""
    exempts.register(StubExempt("firefox"))
    exempts.register(StubExempt("thunderbird"))

    assert exempts.is_exempt("firefox") is True
    assert exempts.is_exempt("thunderbird") is True
    assert exempts.is_exempt("barack obama") is False


@pytest.mark.asyncio
async def test_initialize_registers_the_amp_exempt(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """With MARS enabled, the AMP exempt is built, initialized, and registered."""
    monkeypatch.setitem(exempts.settings.mars, "enabled", True)
    initialize = mocker.patch.object(AmpExempt, "initialize", return_value=None)

    await exempts.initialize()

    assert initialize.await_count == 1
    assert len(exempts._exempts) == 1
    assert isinstance(exempts._exempts[0], AmpExempt)


@pytest.mark.asyncio
async def test_initialize_skips_the_amp_exempt_when_mars_is_disabled(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """The MARS toggle keeps the AMP exempt from being built at all."""
    monkeypatch.setitem(exempts.settings.mars, "enabled", False)
    initialize = mocker.patch.object(AmpExempt, "initialize", return_value=None)

    await exempts.initialize()

    assert initialize.await_count == 0
    assert exempts._exempts == []


@pytest.mark.asyncio
async def test_initialize_is_a_no_op_once_populated(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """A second `initialize` does not stack a duplicate exempt onto the registry."""
    monkeypatch.setitem(exempts.settings.mars, "enabled", True)
    mocker.patch.object(AmpExempt, "initialize", return_value=None)

    await exempts.initialize()
    await exempts.initialize()

    assert len(exempts._exempts) == 1


@pytest.mark.parametrize(
    ("target", "attribute"),
    [
        pytest.param(exempts, "_build_amp_exempt", id="construction"),
        pytest.param(AmpExempt, "initialize", id="initialization"),
    ],
)
@pytest.mark.asyncio
async def test_a_failing_exempt_is_skipped_rather_than_fatal(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    target: object,
    attribute: str,
) -> None:
    """An exempt that cannot come up is logged and left unregistered.

    Both failure points are covered, since construction and initialization sit under the
    same guard. Startup must not hinge on MARS being reachable: the fallback is that
    nothing is exempt and every search term is sanitized, which is the safe direction.
    """
    monkeypatch.setitem(exempts.settings.mars, "enabled", True)
    mocker.patch.object(target, attribute, side_effect=RuntimeError("boom"))

    await exempts.initialize()

    assert exempts._exempts == []
    assert exempts.is_exempt("firefox") is False
    assert "Failed to initialize the amp sanitization exempt" in caplog.text


@pytest.mark.asyncio
async def test_shutdown_tears_down_and_clears_the_registry() -> None:
    """Every registered exempt is shut down and the registry is emptied."""
    first, second = StubExempt("firefox"), StubExempt("thunderbird")
    exempts.register(first)
    exempts.register(second)

    await exempts.shutdown()

    assert first.shut_down is True
    assert second.shut_down is True
    assert exempts._exempts == []


@pytest.mark.asyncio
async def test_shutdown_continues_past_a_failing_exempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One exempt failing to shut down does not skip the ones after it."""
    failing = StubExempt("firefox", shutdown_error=RuntimeError("boom"))
    healthy = StubExempt("thunderbird")
    exempts.register(failing)
    exempts.register(healthy)

    await exempts.shutdown()

    assert healthy.shut_down is True
    assert exempts._exempts == []
    assert "Failed to shut down a sanitization exempt" in caplog.text
