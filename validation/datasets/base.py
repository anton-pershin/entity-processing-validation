"""Dataset preparation interfaces and shared models."""

from __future__ import annotations

from pydantic import BaseModel

from validation.base import GoldDataset


class DatasetConfig(BaseModel):
    """Per-dataset preparation config.

    Only knobs the implementation actually reads. Fetch URLs are module
    constants next to the fetchers (documented there); see FR2.
    """

    name: str
    max_docs: int | None = None


class PreparedDataset(BaseModel):
    dataset: GoldDataset
    input_path: str
    gold_path: str
