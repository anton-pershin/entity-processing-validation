"""Dataset package: fetch and convert evaluation datasets to gold JSONL."""

from validation.datasets.base import DatasetConfig, PreparedDataset
from validation.datasets.conll04 import prepare_conll04
from validation.datasets.rusentne import prepare_rusentne

__all__ = ["DatasetConfig", "PreparedDataset", "prepare_conll04", "prepare_rusentne"]
