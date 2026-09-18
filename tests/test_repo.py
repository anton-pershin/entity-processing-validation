"""Tests for validation.repo using a local git fixture repository."""

import subprocess
from pathlib import Path

import pytest

from validation.base import ValidationRequest
from validation.repo import RepoPrepError, clone_repo


def _init_fixture_repo(path: Path) -> str:
    """Create a tiny git repo with two commits; return the first commit hash."""
    path.mkdir(parents=True, exist_ok=True)

    def run(*args: str) -> str:
        subprocess.run(args, cwd=path, check=True, capture_output=True)
        return ""

    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    (path / "README.md").write_text("first\n")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "first")
    first_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()
    (path / "README.md").write_text("second\n")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "second")
    return first_hash


def test_clone_and_checkout_first_commit(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture_repo"
    first_hash = _init_fixture_repo(fixture)
    request = ValidationRequest(repo=str(fixture), commit=first_hash)

    clone_path = clone_repo(request, workdir=tmp_path / "work")
    assert (clone_path / "README.md").read_text().strip() == "first"


def test_clone_bad_url_raises(tmp_path: Path) -> None:
    request = ValidationRequest(repo="/nonexistent/repo.git", commit="abc")
    with pytest.raises(RepoPrepError, match="git clone failed"):
        clone_repo(request, workdir=tmp_path / "work")


def test_clone_bad_commit_raises(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture_repo"
    _init_fixture_repo(fixture)
    request = ValidationRequest(repo=str(fixture), commit="deadbeef")
    with pytest.raises(RepoPrepError, match="git checkout"):
        clone_repo(request, workdir=tmp_path / "work")
