"""Validation functions for navigational suggestions job"""

from typing import Optional

import tldextract

from merino.jobs.navigational_suggestions.constants import (
    INVALID_TITLES,
)


def get_second_level_domain(domain: str, suffix: str) -> str:
    """Extract only the second-level domain part (e.g., 'example' from 'www.example.com')."""
    if not domain or not suffix:
        return ""

    # Handle special cases first
    if domain == suffix:
        return ""

    # Check if domain ends with the suffix
    if domain.endswith("." + suffix):
        # Remove the suffix to get everything before it
        domain_without_suffix = domain[: -len("." + suffix)]

        # For cases like "example.co.uk" with suffix "uk", we want "example.co"
        # For cases like "www.example.com" with suffix "com", we want "example"
        parts = domain_without_suffix.split(".")

        # If there are multiple parts, we need to determine what to return
        if len(parts) >= 2:
            # Check if this looks like a second-level domain (like .co.uk)
            # In this case, return the last two parts joined
            if len(parts[-1]) == 2 and parts[-1].isalpha():  # country code-like
                return ".".join(parts[-2:])
            else:
                # Normal case - return just the last part (the actual second-level domain)
                return parts[-1]
        elif len(parts) == 1:
            return parts[0]
        else:
            return ""
    else:
        # Suffix doesn't match - return the full domain
        return domain


def is_domain_blocked(domain: str, suffix: str, blocked_domains: set[str]) -> bool:
    """Check if domain is in the blocked list."""
    if not domain or not blocked_domains:
        return False

    # Check exact domain match first
    if domain in blocked_domains:
        return True

    # Use tldextract to properly parse the domain
    extracted = tldextract.extract(domain)

    # Check if the extracted domain (second-level domain) is blocked
    if extracted.domain in blocked_domains:
        return True

    # Also check second-level domain using our custom logic for backwards compatibility
    second_level_domain: str = get_second_level_domain(domain, suffix)
    return second_level_domain in blocked_domains


def is_valid_title(title: Optional[str]) -> bool:
    """Check if title is valid and not an error message or bot detection."""
    if not title:
        return False

    title_lower = title.casefold()
    return not any(invalid.casefold() in title_lower for invalid in INVALID_TITLES)


def sanitize_title(title: Optional[str]) -> Optional[str]:
    """Normalize whitespace and validate title content."""
    if not title:
        return ""

    # Normalize whitespace
    normalized = " ".join(title.split())

    # Return empty string if normalized is empty
    if not normalized:
        return ""

    # Validate title content
    if is_valid_title(normalized):
        return normalized

    return ""


def get_title_or_fallback(title: Optional[str], fallback: str) -> str:
    """Return valid title or capitalized fallback."""
    sanitized = sanitize_title(title)
    return sanitized if sanitized else fallback.capitalize()
