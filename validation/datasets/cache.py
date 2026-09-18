"""Shared raw-dataset cache used by dataset fetchers.

Raw dataset downloads are cached in a shared directory (default
``~/.cache/entity_processing_validation/datasets``) and reused across validation
runs; a download is skipped when the cached file already exists and is
non-empty. Downloads are atomic (temp file + rename) so concurrent runs sharing
the cache never observe a partially written file.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "entity_processing_validation" / "datasets"


def cached_fetch(url: str, dest_dir: Path, filename: str, cache_dir: Path) -> Path:
    """Download ``url`` into ``cache_dir/filename`` unless it is already cached.

    Returns the path to the cached file. The file is downloaded atomically
    (temp name + rename) so concurrent runs never see a partial download.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / filename
    if cached_path.exists() and cached_path.stat().st_size > 0:
        return cached_path

    tmp_path = cached_path.with_suffix(cached_path.suffix + ".tmp")
    proc = subprocess.run(
        ["wget", "-q", url, "-O", str(tmp_path)], capture_output=True, text=True, timeout=600
    )
    if proc.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"download failed for {url}: {proc.stderr.strip()}")
    os.replace(tmp_path, cached_path)
    return cached_path
