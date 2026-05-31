"""Validation helpers for Discord Image Data payloads."""

from __future__ import annotations

import base64
import binascii
import re

DISCORD_EVENT_IMAGE_MAX_BYTES = 8 * 1024 * 1024
_IMAGE_DATA_PATTERN = re.compile(
    r"\Adata:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=\s]+)\Z",
    re.IGNORECASE,
)


def validate_discord_event_image_data(value: object) -> str | None:
    """Validate a Discord scheduled-event image Data URI."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Event image must be a PNG or JPEG data URI")

    image_data = value.strip()
    match = _IMAGE_DATA_PATTERN.match(image_data)
    if match is None:
        raise ValueError("Event image must be a PNG or JPEG data URI")

    content_type = match.group(1).lower()
    encoded_payload = "".join(match.group(2).split())
    try:
        image_bytes = base64.b64decode(encoded_payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Event image data is not valid base64") from exc

    if not image_bytes:
        raise ValueError("Event image data is empty")
    if len(image_bytes) > DISCORD_EVENT_IMAGE_MAX_BYTES:
        raise ValueError("Event image must be 8 MiB or smaller")

    if content_type == "image/png" and not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Event image data does not match PNG format")
    if content_type == "image/jpeg" and not image_bytes.startswith(b"\xff\xd8\xff"):
        raise ValueError("Event image data does not match JPEG format")

    return f"data:{content_type};base64,{encoded_payload}"