from __future__ import annotations

from collections.abc import Callable


VersionSummary = Callable[[], dict[str, str]]


def print_version_info(version_summary: VersionSummary) -> int:
    """Print the shared package/git version view used by both CLI entry points."""

    summary = version_summary()
    print(f"{summary['name']} {summary['version']}")
    print(f"commit: {summary['commit']}")
    print(f"branch: {summary['branch']}")
    print(f"dirty: {summary['dirty']}")
    return 0
