"""Data models for navigational suggestions job"""

from typing import Any, Optional

from pydantic import BaseModel


class FaviconData(BaseModel):
    """Data model for favicon information extracted from a website."""

    links: list[dict[str, Any]]
    metas: list[dict[str, Any]]
    manifests: list[dict[str, Any]]


class DomainMetadata(BaseModel):
    """Metadata extracted for a domain."""

    url: Optional[str]
    title: Optional[str]
    icon: Optional[str]
    domain: Optional[str]


class ProcessingResult(BaseModel):
    """Result of processing a domain."""

    domain: str
    success: bool
    metadata: Optional[DomainMetadata] = None
    error: Optional[str] = None
    error_reason: Optional[str] = None


class DomainError(BaseModel):
    """Error information for a domain that failed processing."""

    domain: str
    error_reason: str
