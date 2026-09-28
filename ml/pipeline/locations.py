"""Location of a channel from its SMVU tag.

Tags look like "16-2.1.1.4.22.": object id, then the engineering-system tree.
Three levels (object and two sections) keep one collector section together; the
backend groups incidents by the same key.
"""

LOCATION_LEVELS = 3


def location_group(tag):
    if not isinstance(tag, str) or not tag.strip():
        return None
    parts = [part for part in tag.strip().rstrip(".").split(".") if part]
    return ".".join(parts[:LOCATION_LEVELS]) if parts else None
