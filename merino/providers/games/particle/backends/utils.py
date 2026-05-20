"""Utility functions for parsing and validating Particle data."""

import logging

from jsonschema import exceptions, validate
from pydantic import Json


logger = logging.getLogger(__name__)


class ParticleManifestValidationError(Exception):
    """Error validating the Particle manifest JSON."""


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
        error_msg = f"Error validating Particle manifest schema version. Received {schema_version}, expected {manifest_schema_version}."

        logger.error(error_msg)

        ex = ParticleManifestValidationError(error_msg)

        raise ex


def validate_manifest_against_schema(manifest_json: Json, manifest_schema: Json) -> None:
    """Validate the returned manifest JSON conforms to the expected schema."""
    try:
        # if this fails, it should raise a ValidationError
        validate(instance=manifest_json, schema=manifest_schema)
    except exceptions.ValidationError as ex:
        logger.error(f"Schema validation failed for manifest JSON: {ex}")

        raise ParticleManifestValidationError(str(ex)) from ex


def remote_manifest_runtime_is_updated(manifest_remote: Json, manifest_gcs: Json) -> bool:
    """Determine if the JSON manifest from Particle has newer runtime files than the manifest we have stored in GCS"""
    runtime_remote = manifest_remote["channels"]["runtime"]["version"]
    runtime_gcs = manifest_gcs["channels"]["runtime"]["version"]

    return bool(runtime_remote != runtime_gcs)


def remote_manifest_puzzle_is_updated(manifest_remote: Json, manifest_gcs: Json) -> bool:
    """Determine if the JSON manifest from Particle has newer game files than the manifest we have stored in GCS"""
    daily_remote = manifest_remote["channels"]["daily"]["version"]
    daily_gcs = manifest_gcs["channels"]["daily"]["version"]

    return bool(daily_remote != daily_gcs)


async def update_files_puzzle(manifest_remote: Json, manifest_gcs: Json | None) -> bool:
    """Attempt to update the daily puzzle files - partial stub, async operations to come"""
    should_update_puzzle = (
        remote_manifest_puzzle_is_updated(manifest_remote, manifest_gcs) if manifest_gcs else True
    )

    if should_update_puzzle:
        # validate puzzle files SHAs and, if valid, attempt to upload to GCS
        # if the above succeeds, return True, else False
        return True
    else:
        # if the puzzle files don't need to be updated, return False
        return False


async def update_files_runtime(manifest_remote: Json, manifest_gcs: Json | None) -> bool:
    """Attempt to update the runtime files - partial stub, async operations to come"""
    should_update_runtime = (
        remote_manifest_runtime_is_updated(manifest_remote, manifest_gcs) if manifest_gcs else True
    )

    if should_update_runtime:
        # validate runtime files SHAs and, if valid, attempt to upload to GCS
        # if the above succeeds, return True, else False
        return True
    else:
        # if the runtime files don't need to be updated, return False
        return False
