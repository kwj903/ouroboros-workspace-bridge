from __future__ import annotations

from collections.abc import Mapping


METADATA_FILTER_KEYS = ("task_id", "client_id", "session_id", "project_id", "workspace_mode")


def active_metadata_filters(filters: Mapping[str, str | None]) -> dict[str, str]:
    active: dict[str, str] = {}
    for key in METADATA_FILTER_KEYS:
        value = filters.get(key)
        if value is None:
            continue

        normalized = value.strip()
        if normalized:
            active[key] = normalized

    return active


def metadata_matches_filters(
    metadata: dict[str, object],
    filters: Mapping[str, str | None],
) -> bool:
    active_filters = active_metadata_filters(filters)
    if not active_filters:
        return True

    for key, expected in active_filters.items():
        actual = metadata.get(key)
        if not isinstance(actual, str) or actual != expected:
            return False

    return True
