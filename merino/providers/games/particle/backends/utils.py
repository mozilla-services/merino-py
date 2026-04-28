"""Utility functions for parsing and validating Particle data."""

import logging

from jsonschema import exceptions, validate
from pydantic import Json


logger = logging.getLogger(__name__)


def validate_manifest_schema_version(manifest_json: Json, manifest_schema_version: int) -> None:
    """Validate schema version exists in the JSON and is of the expected value."""
    try:
        schema_version = manifest_json["schemaVersion"]
    except KeyError:
        logger.error("JSON key error retrieving 'schemaVersion' from manifest JSON.")
        schema_version = None
    except Exception:
        logger.error("JSON error retrieving 'schemaVersion' from manifest JSON.")
        schema_version = None

    if schema_version != manifest_schema_version:
        logger.error(
            f"Schema version mismatch when validating manifest JSON. Received {schema_version}, expected {manifest_schema_version}."
        )
        raise Exception(
            f"Error validating Particle manifest schema version. Received {schema_version}, expected {manifest_schema_version}."
        )


def validate_manifest_against_schema(manifest_json: Json, manifest_schema: Json) -> None:
    """Validate the returned manifest JSON conforms to the expected schema."""
    try:
        # if this fails, it should raise a ValidationError
        validate(instance=manifest_json, schema=manifest_schema)
    except exceptions.ValidationError as ex:
        logger.error(f"Schema validation failed for manifest JSON: {ex}")
        raise ex


def remote_manifest_runtime_is_updated(manifest_remote: Json, manifest_gcs: Json) -> bool:
    """Determine if the JSON manifest from Particle has newer runtime files than the manifest we have stored in GCS"""
    runtime_remote = manifest_remote["channels"]["runtime"]["version"]
    runtime_gcs = manifest_gcs["channels"]["runtime"]["version"]

    return True if runtime_remote != runtime_gcs else False


def remote_manifest_daily_is_updated(manifest_remote: Json, manifest_gcs: Json) -> bool:
    """Determine if the JSON manifest from Particle has newer game files than the manifest we have stored in GCS"""
    daily_remote = manifest_remote["channels"]["daily"]["version"]
    daily_gcs = manifest_gcs["channels"]["daily"]["version"]

    return True if daily_remote != daily_gcs else False
