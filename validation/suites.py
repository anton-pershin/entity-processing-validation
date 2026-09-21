"""Suite resolution and validation (FR1, FR3).

A validation suite is a named set of dataset entries that must cover every
dataset class exactly once (validation spec §3.3). Suites are declarative
config (``config/suites/<name>.yaml``), dataset entries are config files under
``config/datasets/``, and this module turns a suite name into the resolved
entries the orchestrator prepares and runs.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

from validation.datasets.base import (
    DatasetClass,
    DatasetConfig,
    ResolvedEntry,
    SuiteConfig,
)


class SuiteConfigError(Exception):
    """A suite is unknown, malformed, or does not cover every dataset class."""


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise SuiteConfigError(f"config file not found: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SuiteConfigError(f"unparseable config file {path}: {e}") from e
    if not isinstance(payload, dict):
        raise SuiteConfigError(f"config file {path} does not hold a mapping")
    return payload


def resolve_suite(name: str, config_dir: Path) -> list[ResolvedEntry]:
    """Resolve suite ``name`` into its dataset entries, validating its coverage.

    Raises ``SuiteConfigError`` when the suite file is missing, names a dataset
    entry without a config file, or does not select exactly one entry per
    dataset class.
    """
    config_dir = Path(config_dir)
    suite_path = config_dir / "suites" / f"{name}.yaml"
    if not suite_path.exists():
        raise SuiteConfigError(f"unknown suite '{name}': no suite file at {suite_path}")
    try:
        suite = SuiteConfig.model_validate(_load_yaml(suite_path))
    except ValidationError as e:
        raise SuiteConfigError(f"invalid suite file {suite_path}: {e}") from e

    entries: list[ResolvedEntry] = []
    for entry_name in suite.entries:
        entry_path = config_dir / "datasets" / f"{entry_name}.yaml"
        if not entry_path.exists():
            raise SuiteConfigError(
                f"suite '{name}' names dataset entry '{entry_name}' "
                f"but no entry file exists at {entry_path}"
            )
        try:
            entry_config = DatasetConfig.model_validate(_load_yaml(entry_path))
        except ValidationError as e:
            raise SuiteConfigError(
                f"invalid dataset entry '{entry_name}' ({entry_path}): {e}"
            ) from e
        if entry_config.name != entry_name:
            raise SuiteConfigError(
                f"dataset entry '{entry_name}' declares name '{entry_config.name}' in {entry_path}"
            )
        if entry_config.dataset_class is None:
            raise SuiteConfigError(
                f"dataset entry '{entry_name}' ({entry_path}) declares no dataset class"
            )
        entries.append(
            ResolvedEntry(
                name=entry_config.name,
                dataset_class=entry_config.dataset_class,
                config=entry_config,
            )
        )

    counts = Counter(entry.dataset_class for entry in entries)
    missing = [c.value for c in DatasetClass if counts[c] == 0]
    if missing:
        raise SuiteConfigError(
            f"suite '{name}' does not cover every dataset class; missing: "
            f"{', '.join(sorted(missing))}"
        )
    duplicated = [c.value for c, n in counts.items() if n > 1]
    if duplicated:
        raise SuiteConfigError(
            f"suite '{name}' selects more than one dataset entry for: "
            f"{', '.join(sorted(duplicated))}"
        )
    return entries
