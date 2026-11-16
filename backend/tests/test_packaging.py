"""Deployment manifests stay consistent with each other."""

from __future__ import annotations

import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_pyproject_dependencies_match_requirements() -> None:
    requirements = [
        line.strip()
        for line in (BACKEND / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    assert project["project"]["dependencies"] == requirements
    assert project["tool"]["vercel"]["entrypoint"] == "app.main:app"


def test_python_version_is_supported_on_vercel() -> None:
    assert (BACKEND / ".python-version").read_text().strip() in {"3.12", "3.13", "3.14"}
