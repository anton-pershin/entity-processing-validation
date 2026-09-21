"""Tests for suite resolution and catalog validation (T1, T2)."""

from pathlib import Path

import pytest
import yaml

from validation.datasets.base import DatasetClass
from validation.suites import SuiteConfigError, resolve_suite

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_entry(
    config_dir: Path,
    name: str,
    dataset_class: str,
    source: str = "conll04",
    sample_size: int | None = None,
    shuffle_seed: int = 0,
) -> None:
    datasets_dir = config_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "source": source,
        "class": dataset_class,
        "sample_size": sample_size,
        "shuffle_seed": shuffle_seed,
    }
    (datasets_dir / f"{name}.yaml").write_text(
        "# @package datasets." + name + "\n" + yaml.safe_dump(payload), encoding="utf-8"
    )


def _write_suite(config_dir: Path, name: str, entries: list[str]) -> None:
    suites_dir = config_dir / "suites"
    suites_dir.mkdir(parents=True, exist_ok=True)
    (suites_dir / f"{name}.yaml").write_text(
        yaml.safe_dump({"name": name, "entries": entries}), encoding="utf-8"
    )


def _two_class_tree(config_dir: Path) -> None:
    _write_entry(config_dir, "ent", "entity_relation")
    _write_entry(config_dir, "sent", "sentiment", source="rusentne")
    _write_suite(config_dir, "ok", ["ent", "sent"])


def test_resolve_suite_valid(tmp_path: Path) -> None:
    _two_class_tree(tmp_path)
    entries = resolve_suite("ok", tmp_path)
    assert [e.name for e in entries] == ["ent", "sent"]
    assert [e.dataset_class for e in entries] == [
        DatasetClass.ENTITY_RELATION,
        DatasetClass.SENTIMENT,
    ]


def test_unknown_suite_name(tmp_path: Path) -> None:
    _two_class_tree(tmp_path)
    with pytest.raises(SuiteConfigError):
        resolve_suite("does_not_exist", tmp_path)


def test_suite_missing_a_dataset_class(tmp_path: Path) -> None:
    _write_entry(tmp_path, "ent", "entity_relation")
    _write_suite(tmp_path, "one_class", ["ent"])
    with pytest.raises(SuiteConfigError):
        resolve_suite("one_class", tmp_path)


def test_suite_two_entries_of_one_class(tmp_path: Path) -> None:
    _write_entry(tmp_path, "ent", "entity_relation")
    _write_entry(tmp_path, "ent2", "entity_relation")
    _write_entry(tmp_path, "sent", "sentiment", source="rusentne")
    _write_suite(tmp_path, "dup", ["ent", "ent2", "sent"])
    with pytest.raises(SuiteConfigError):
        resolve_suite("dup", tmp_path)


def test_suite_entry_without_config_file(tmp_path: Path) -> None:
    _write_entry(tmp_path, "sent", "sentiment", source="rusentne")
    _write_suite(tmp_path, "missing", ["ghost", "sent"])
    with pytest.raises(SuiteConfigError) as excinfo:
        resolve_suite("missing", tmp_path)
    assert "ghost" in str(excinfo.value)


def test_real_catalog_resolves() -> None:
    """T2: the repository's own catalog resolves to the two suites of the spec."""
    config_dir = REPO_ROOT / "config"
    full = resolve_suite("full", config_dir)
    small = resolve_suite("small", config_dir)

    assert [e.name for e in full] == ["conll04", "rusentne"]
    assert [e.name for e in small] == ["conll04_small", "rusentne_small"]

    for entries in (full, small):
        assert [e.dataset_class for e in entries] == [
            DatasetClass.ENTITY_RELATION,
            DatasetClass.SENTIMENT,
        ]

    full_er = next(e for e in full if e.dataset_class == DatasetClass.ENTITY_RELATION)
    full_sent = next(e for e in full if e.dataset_class == DatasetClass.SENTIMENT)
    assert full_er.config.sample_size is None
    assert full_sent.config.sample_size is None

    for entry in small:
        assert entry.config.sample_size == 100
