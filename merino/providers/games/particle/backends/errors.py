"""Custom errors for the Particle game provider."""

from merino.exceptions import FilemanagerError


class ParticleManifestValidationError(Exception):
    """Error validating the Particle manifest JSON."""


class ParticleRemoteFileProcessError(Exception):
    """Error processing a remote Particle file."""


class ParticleFileManagerError(FilemanagerError):
    """Error loading local Particle manifest schema validator file."""
