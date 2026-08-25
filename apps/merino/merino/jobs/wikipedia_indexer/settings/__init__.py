"""Index mapping & settings"""

from merino.jobs.wikipedia_indexer.settings import v1

SETTING_VERSIONS = {"v1": v1}


def get_settings_for_version(version: str):
    """Return the module specific to the specific version"""
    return SETTING_VERSIONS.get(version)
