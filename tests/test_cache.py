"""Tests for the shared raw-dataset cache."""

from pathlib import Path

import pytest

from validation.datasets.cache import cached_fetch


def test_cached_fetch_skips_download_when_cached(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cached = cache_dir / "file.json"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text('{"cached": true}')

    # A failing wget must never be invoked because the file is cached.
    result = cached_fetch("http://invalid.example/x.json", tmp_path / "dl", "file.json", cache_dir)
    assert result == cached
    assert result.read_text() == '{"cached": true}'


def test_cached_fetch_downloads_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Stub out subprocess.run to avoid network access.
    calls: list[list[str]] = []

    class Proc:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        dest = Path(cmd[cmd.index("-O") + 1])
        dest.write_text('{"fresh": true}')
        return Proc()

    monkeypatch.setattr("validation.datasets.cache.subprocess.run", fake_run)
    cache_dir = tmp_path / "cache"
    result = cached_fetch("http://example.com/x.json", tmp_path / "dl", "f.json", cache_dir)
    assert result == cache_dir / "f.json"
    assert result.read_text() == '{"fresh": true}'
    assert len(calls) == 1

    # Second call: served from cache, no new download.
    result = cached_fetch("http://example.com/x.json", tmp_path / "dl", "f.json", cache_dir)
    assert result == cache_dir / "f.json"
    assert len(calls) == 1


def test_cached_fetch_empty_cache_file_redownloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "f.json").write_text("")  # empty = not cached

    class Proc:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        dest = Path(cmd[cmd.index("-O") + 1])
        dest.write_text("data")
        return Proc()

    monkeypatch.setattr("validation.datasets.cache.subprocess.run", fake_run)
    result = cached_fetch("http://example.com/f", tmp_path, "f.json", cache_dir)
    assert result.stat().st_size > 0
