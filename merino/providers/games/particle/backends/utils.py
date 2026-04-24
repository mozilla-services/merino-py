"""Utility functions for parsing and validating Particle data."""

import logging

from jsonschema import exceptions, validate
from pydantic import Json

from merino.configs import settings

logger = logging.getLogger(__name__)

_manifest_schema_version = settings.games_providers.particle.manifest_schema_version


def validate_manifest_schema_version(manifest_json: Json) -> None:
    """Validate schema version exists in the JSON and is of the expected value."""
    try:
        schema_version = manifest_json["schemaVersion"]
    except KeyError:
        logger.error("JSON error retrieving 'schemaVersion' from manifest JSON.")
        schema_version = None

    if schema_version != _manifest_schema_version:
        logger.error(
            f"Schema version mismatch when validating manifest JSON. Received {schema_version}, expected {_manifest_schema_version}."
        )
        raise Exception(
            f"Error validating Particle manifest schema version. Received {schema_version}, expected {_manifest_schema_version}."
        )


def validate_manifest_against_schema(manifest_json: Json, manifest_schema: Json) -> None:
    """Validate the returned manifest JSON conforms to the expected schema."""
    try:
        # if this fails, it should raise a ValidationError
        validate(instance=manifest_json, schema=manifest_schema)
    except exceptions.ValidationError as ex:
        logger.error(f"Schema validation failed for manifest JSON: {ex}")
        raise ex
    # in case the above validation fails in an unexpected way
    except Exception as ex:
        logger.error(f"Unexpected error when validation manifest JSON schema: {ex}")
        raise Exception(f"Unexpected error when validation manifest JSON schema: {ex}")
