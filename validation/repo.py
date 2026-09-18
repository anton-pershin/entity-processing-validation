"""Cloning and checkout of solution repositories."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from validation.base import ValidationRequest


class RepoPrepError(Exception):
    """Raised when cloning or checkout fails."""


def clone_repo(request: ValidationRequest, workdir: Path) -> Path:
    """Clone ``request.repo`` into ``workdir`` and checkout ``request.commit``.

    Returns the path to the cloned repository.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    clone_path = workdir / "solution_repo"
    if clone_path.exists():
        shutil.rmtree(clone_path)

    clone_cmd = ["git", "clone", request.repo, str(clone_path)]
    try:
        proc = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as e:
        raise RepoPrepError(f"git clone timed out: {e}") from e
    if proc.returncode != 0:
        raise RepoPrepError(f"git clone failed: {proc.stderr.strip()}")

    checkout_cmd = ["git", "checkout", request.commit]
    try:
        proc = subprocess.run(
            checkout_cmd, cwd=clone_path, capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired as e:
        raise RepoPrepError(f"git checkout timed out: {e}") from e
    if proc.returncode != 0:
        raise RepoPrepError(f"git checkout {request.commit!r} failed: {proc.stderr.strip()}")

    return clone_path
