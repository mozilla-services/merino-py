"""Manifest Data management traits for Skeletons

Manifests are collections of site metadata that are collected up by Merino jobs and stored in GCS buckets.
The manifest is later published by the `/vi/manifest` endpoint(?), and created by a `cron`'d call to `backend.fetch_manifest_data()`
"""

from merino.providers.manifest.backends.protocol import ManifestData


class SkeletonManifest(ManifestData):
    """Metadata about the Emoji provider (?)"""

    @staticmethod
    def fetch_manifest_data():
        """Regularly fetch and update site metadata for this provider."""
        pass

    def build_and_upload_manifest_file(self) -> None:
        """Fetch the data and then upload it to GCS. This is called from a merino job"""
        pass
