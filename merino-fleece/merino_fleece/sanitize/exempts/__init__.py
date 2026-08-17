"""Public interface for search term sanitization exempts.

An exempt names a class of search terms that carry no PII risk and can therefore skip
sanitization altogether. Exempts are held in a process-wide registry so the background
sanitization handler can consult all of them through one synchronous predicate, and are
brought up and torn down with the app via :func:`initialize` and :func:`shutdown`.
"""

import logging
from collections.abc import Callable

from merino_fleece.configs import settings
from merino_fleece.sanitize.exempts.amp import AmpExempt
from merino_fleece.sanitize.exempts.protocol import SanitizationExempt

__all__ = ["SanitizationExempt", "register", "initialize", "shutdown", "is_exempt"]

logger = logging.getLogger(__name__)

# The registered exempts. Use `initialize()` and `shutdown()` to manage their lifecycle.
_exempts: list[SanitizationExempt] = []


def register(exempt: SanitizationExempt) -> None:
    """Add an already-initialized exempt to the registry.

    Called by `initialize()` for each configured exempt. Also the seam for tests, which
    register a stub instead of standing up a real one.
    """
    _exempts.append(exempt)


async def initialize() -> None:
    """Build, initialize, and register every enabled exempt. Call once at startup.

    An exempt that fails to come up is logged and left unregistered rather than failing
    startup: the cost is that its search terms are sanitized as non-exempt, which is the
    safe direction. No-op if any exempt is already registered.
    """
    if _exempts:
        return

    for name, factory in _enabled_factories():
        try:
            exempt = factory()
            await exempt.initialize()
        except Exception as e:
            logger.warning(
                f"Failed to initialize the {name} sanitization exempt, it will be skipped",
                extra={"error message": f"{e}"},
            )
            continue
        register(exempt)


async def shutdown() -> None:
    """Shut down and drop every registered exempt. Call once at shutdown.

    Each shutdown is guarded so one failing exempt does not skip the rest.
    """
    for exempt in _exempts:
        try:
            await exempt.shutdown()
        except Exception as e:
            logger.warning(
                "Failed to shut down a sanitization exempt",
                extra={"error message": f"{e}"},
            )
    _exempts.clear()


def is_exempt(search_term: str) -> bool:
    """Return whether any registered exempt covers the search term.

    Reports False when nothing is registered, so an unavailable or disabled exempt leaves
    every search term to be sanitized normally.
    """
    return any(exempt.is_exempt(search_term) for exempt in _exempts)


def _build_amp_exempt() -> SanitizationExempt:
    """Construct the AMP exempt from settings."""
    return AmpExempt(
        base_url=settings.mars.base_url,
        suggestion_url_path=settings.mars.suggestion_url_path,
        countries=settings.mars.countries,
        form_factors=settings.mars.form_factors,
        connect_timeout_sec=settings.mars.connect_timeout_sec,
        request_timeout_sec=settings.mars.request_timeout_sec,
        resync_interval_sec=settings.mars.resync_interval_sec,
        cron_interval_sec=settings.mars.cron_interval_sec,
    )


def _enabled_factories() -> list[tuple[str, Callable[[], SanitizationExempt]]]:
    """Return a `(name, factory)` pair for each enabled exempt, in registration order.

    Construction is deferred to a factory so that `initialize()` can guard it alongside
    the exempt's own initialization.
    """
    factories: list[tuple[str, Callable[[], SanitizationExempt]]] = []
    if settings.mars.enabled:
        factories.append(("amp", _build_amp_exempt))
    return factories
