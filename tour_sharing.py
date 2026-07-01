"""
Tour Sharing — shareable tour ID generation and URL building.
==============================================================
Produces deterministic, URL-safe 8-char IDs for sharing tours.
"""
import hashlib

# Base62 alphabet (URL-safe: A-Z, a-z, 0-9)
_BASE62 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def _to_base62(num: int, length: int = 8) -> str:
    """Convert an integer to a base62 string of fixed length."""
    if num == 0:
        return _BASE62[0] * length
    chars = []
    while num > 0 and len(chars) < length:
        chars.append(_BASE62[num % 62])
        num //= 62
    # Pad to desired length
    while len(chars) < length:
        chars.append(_BASE62[0])
    return "".join(reversed(chars))


def generate_shareable_tour_id(location: str, tour_type: str, total_stops: int) -> str:
    """Generate a deterministic 8-char URL-safe shareable tour ID.

    The ID is derived from SHA256 of the same cache key used by tour_cache_layer1,
    then encoded as base62 (8 chars = ~47 bits of entropy).

    Args:
        location: Tour location string.
        tour_type: Tour category (museum, walking, etc.).
        total_stops: Number of stops.

    Returns:
        8-character alphanumeric string, deterministic per inputs.
    """
    raw = f"{location.strip().lower()}|{tour_type.strip().lower()}|{total_stops}"
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    # Use first 6 bytes (48 bits) as integer for base62 encoding
    num = int.from_bytes(digest[:6], "big")
    return _to_base62(num, 8)


def build_share_url(tour_id: str, base_url: str = "https://audioura.io") -> str:
    """Build the full shareable URL for a tour.

    Args:
        tour_id: The 8-char shareable ID.
        base_url: Base URL (default: https://audioura.io).

    Returns:
        Full share URL: '{base_url}/tour/{tour_id}'
    """
    return f"{base_url.rstrip('/')}/tour/{tour_id}"
