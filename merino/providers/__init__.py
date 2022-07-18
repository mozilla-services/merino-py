from merino.providers.adm import Provider as AdmProvider
from merino.providers.base import BaseProvider

providers: dict[str, BaseProvider] = {}
default_providers: list[BaseProvider] = []


async def init_providers() -> None:
    """
    Initialize all suggestion providers.

    This should only be called once at the startup of application.
    """
    providers["adm"] = AdmProvider()
    default_providers.extend([p for p in providers.values() if p.enabled_by_default()])


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """
    Return a tuple of all the providers and default providers.
    """
    return providers, default_providers
