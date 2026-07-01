"""
Storied Release — Version Constants
====================================
Single source of truth for the Storied release version.
No external dependencies. Importable from any service or script.
"""

STORIED_VERSION = "2.2.0"
STORIED_BUILD = 1
STORIED_SERVICE_VERSION = "2.2.0.1"
STORIED_BRANCH = "storied"


def get_version_string() -> str:
    """Return the full version string in 'major.minor.patch+build' format."""
    return f"{STORIED_VERSION}+{STORIED_BUILD}"


def validate_version_consistency() -> bool:
    """Assert that service major.minor matches app major.minor.
    
    Raises AssertionError if versions are inconsistent.
    Returns True on success.
    """
    # Extract major.minor.patch from both
    app_prefix = STORIED_VERSION  # "2.2.0"
    service_prefix = ".".join(STORIED_SERVICE_VERSION.split(".")[:3])  # "2.2.0"
    
    assert app_prefix == service_prefix, (
        f"Version mismatch: app={STORIED_VERSION}, service={STORIED_SERVICE_VERSION} "
        f"(prefixes {app_prefix} != {service_prefix})"
    )
    return True
