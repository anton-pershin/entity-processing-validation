#!/usr/bin/env python
"""Materialize one dataset entry's prepared JSONL for inspection (FR7).

Writes the entry's solution input and gold JSONL into an output directory.
No validation run reads this output; the command exists to inspect and reuse a
subset. It prepares the entry exactly as a validation run does, so it reuses the
shared raw-dataset cache but never removes or overwrites a cached download.
"""

from __future__ import annotations

import sys
from pathlib import Path

import hydra
from omegaconf import DictConfig

from validation.core import _make_fetcher
from validation.datasets.base import DatasetConfig
from validation.datasets.cache import DEFAULT_CACHE_DIR

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def load_entry_config(entry: str) -> DatasetConfig:
    """Load one dataset entry config from ``config/datasets/<entry>.yaml``."""
    import yaml

    path = CONFIG_DIR / "datasets" / f"{entry}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no dataset entry config at {path}")
    return DatasetConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def materialize(
    config: DatasetConfig,
    output_dir: Path,
    workdir: Path,
    fetcher=None,
    cache_dir_override: str | None = None,
) -> dict:
    """Prepare ``config`` and write its input/gold JSONL under ``output_dir``.

    Returns the two written paths. ``workdir`` is used only as the fetcher's
    destination for a cache miss; it is never written to otherwise.
    """
    from validation.datasets import prepare_conll04, prepare_rusentne

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    preparers = {"conll04": prepare_conll04, "rusentne": prepare_rusentne}
    preparer = preparers.get(config.source_name)
    if preparer is None:
        raise ValueError(f"no preparer registered for dataset source '{config.source_name}'")

    if fetcher is None:
        cache_dir = Path(cache_dir_override or DEFAULT_CACHE_DIR).expanduser()
        fetcher = _make_fetcher(config.source_name, cache_dir)

    prepared = preparer(config, output_dir, fetcher=fetcher)
    return {"input_path": prepared.input_path, "gold_path": prepared.gold_path}


@hydra.main(config_path="../config", config_name="config_build_subset", version_base=None)
def main(cfg: DictConfig) -> None:
    entry = cfg.get("entry")
    if not entry:
        print("set entry=<dataset entry name>, e.g. entry=conll04_small", file=sys.stderr)
        raise SystemExit(2)
    output_dir = Path(cfg.get("output_dir") or ".")
    entry_config = load_entry_config(entry)
    paths = materialize(
        entry_config,
        output_dir=output_dir,
        workdir=Path(cfg.workdir),
        cache_dir_override=cfg.get("datasets_cache_dir"),
    )
    for key, value in paths.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
