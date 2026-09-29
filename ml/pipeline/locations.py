LOCATION_LEVELS = 3


def location_group(tag):
    if not isinstance(tag, str) or not tag.strip():
        return None
    parts = [part for part in tag.strip().rstrip(".").split(".") if part]
    return ".".join(parts[:LOCATION_LEVELS]) if parts else None
