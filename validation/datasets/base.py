"""Dataset preparation interfaces and shared models."""

from __future__ import annotations

import random
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from validation.base import GoldDataset


class DatasetClass(StrEnum):
    """Which family of metrics a dataset entry feeds (validation spec §2, §3.3)."""

    ENTITY_RELATION = "entity_relation"
    SENTIMENT = "sentiment"

    def metric_ids(self) -> list[str]:
        """The validation metrics this dataset class feeds (validation spec §2)."""
        if self is DatasetClass.ENTITY_RELATION:
            return ["VM1", "VM2", "VM5", "VM6"]
        return ["VM3", "VM4"]


class DatasetConfig(BaseModel):
    """Per-dataset preparation config, as declared by a dataset entry file.

    ``sample_size: None`` means the entire source. ``source`` names the raw
    dataset to prepare and defaults to the entry name; several entries may share
    one source, which is how a subset variant relates to the full entry feeding
    the same fetcher. ``dataset_class`` comes from the entry's ``class`` key and
    is required for a suite entry (suite resolution rejects an entry without it).
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    source: str | None = None
    dataset_class: DatasetClass | None = Field(default=None, alias="class")
    sample_size: int | None = None
    shuffle_seed: int = 0

    @property
    def source_name(self) -> str:
        """The raw dataset this entry prepares."""
        return self.source or self.name


class SuiteConfig(BaseModel):
    """A named set of dataset entries (validation spec §3.3)."""

    name: str
    entries: list[str]


class ResolvedEntry(BaseModel):
    """A dataset entry selected by a resolved suite."""

    name: str
    dataset_class: DatasetClass
    config: DatasetConfig


class PreparedDataset(BaseModel):
    dataset: GoldDataset
    input_path: str
    gold_path: str


def subset_documents[T](
    documents: Sequence[T], sample_size: int | None, shuffle_seed: int
) -> list[T]:
    """Select a subset of ``documents`` by a seeded shuffle (FR4).

    ``None``, or a size at least as large as the source, keeps the whole source
    in source order; otherwise the source is shuffled with ``shuffle_seed`` and
    the first ``sample_size`` items are taken. Never a head slice: the source
    order carries no guarantee of randomness.
    """
    items = list(documents)
    if sample_size is None or sample_size >= len(items):
        return items
    shuffled = list(items)
    random.Random(shuffle_seed).shuffle(shuffled)
    return shuffled[:sample_size]


def prepare_paths(workdir: Path, entry_name: str) -> tuple[str, str]:
    """Input and gold JSONL paths for one dataset entry."""
    return (
        str(Path(workdir) / f"{entry_name}_input.jsonl"),
        str(Path(workdir) / f"{entry_name}_gold.jsonl"),
    )
