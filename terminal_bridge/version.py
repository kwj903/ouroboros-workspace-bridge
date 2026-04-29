from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _project_version() -> str:
    try:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"

    project = data.get("project")
    if not isinstance(project, dict):
        return "unknown"

    version = project.get("version")
    return version if isinstance(version, str) and version else "unknown"


__version__ = _project_version()


def _git_output(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None

    if completed.returncode != 0:
        return None

    value = completed.stdout.strip()
    return value or None


def get_git_commit() -> str:
    return _git_output(["rev-parse", "--short", "HEAD"]) or "unknown"


def get_git_branch() -> str:
    return _git_output(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"


def is_git_dirty() -> bool | None:
    output = _git_output(["status", "--short"])
    if output is None:
        return None
    return output != ""


def version_summary() -> dict[str, str]:
    dirty = is_git_dirty()
    if dirty is None:
        dirty_label = "unknown"
    else:
        dirty_label = "yes" if dirty else "no"

    return {
        "name": "Ouroboros Workspace Bridge",
        "version": __version__,
        "commit": get_git_commit(),
        "branch": get_git_branch(),
        "dirty": dirty_label,
    }
