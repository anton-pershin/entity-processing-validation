"""CoNLL04 dataset: fetch via spert scripts and convert to gold JSONL.

SpERT's converted CoNLL04 JSON has documents of the form:
  {"orig_id": N, "tokens": [...],
   "entities": [{"type": "Peop"|"Loc"|"Org"|"Other", "start": i, "end": j}, ...],
   "relations": [{"type": "Work_For"|..., "head": i, "tail": i}, ...]}
where relation head/tail indices refer to positions in the entities list.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from validation.base import GoldDataset, GoldEntity, GoldRelation, InputDocument
from validation.datasets.base import DatasetConfig, PreparedDataset, prepare_paths, subset_documents
from validation.datasets.cache import DEFAULT_CACHE_DIR, cached_fetch

TYPE_MAP = {"Peop": "PEOPLE", "Loc": "LOCATION", "Org": "ORGANIZATION", "Other": "OTHER"}
REL_MAP = {
    "Work_For": "WORK_FOR",
    "Kill": "KILL",
    "OrgBased_In": "ORGANIZATION_BASED_IN",
    "Live_In": "LIVE_IN",
    "Located_In": "LOCATED_IN",
}


class DatasetFetchError(Exception):
    pass


# URL-based equivalent of spert's scripts/fetch_datasets.sh (which would clone
# the whole spert repo); the shell script itself is not executed.
CONLL04_FETCH_URL = (
    "http://lavis.cs.hs-rm.de/storage/spert/public/datasets/conll04/conll04_test.json"
)


def fetch_conll04(config: DatasetConfig, dest_dir: Path, cache_dir: Path | None = None) -> Path:
    """Fetch the raw converted CoNLL04 JSON (cached across runs)."""
    cache = cache_dir or DEFAULT_CACHE_DIR
    try:
        return cached_fetch(CONLL04_FETCH_URL, Path(dest_dir), "conll04_raw.json", cache)
    except RuntimeError as e:
        raise DatasetFetchError(f"CoNLL04 fetch failed: {e}") from e


def parse_conll04(raw_path: Path, config: DatasetConfig) -> GoldDataset:
    """Convert spert-format CoNLL04 JSON into a GoldDataset.

    A subset is taken from the raw document records *before* conversion, so
    relation endpoint indices still refer to entities that survive the cut and
    no relation can outlive its endpoints (FR4).
    """
    docs = json.loads(Path(raw_path).read_text())
    docs = subset_documents(docs, config.sample_size, config.shuffle_seed)

    entities: list[GoldEntity] = []
    relations: list[GoldRelation] = []
    input_docs: list[InputDocument] = []

    for doc in docs:
        doc_id = f"conll04-{doc.get('orig_id')}"
        tokens = doc.get("tokens", [])
        text = " ".join(tokens)
        input_docs.append(InputDocument(doc_id=doc_id, text=text))

        mention_by_idx: dict[int, str] = {}
        for idx, ent in enumerate(doc.get("entities", [])):
            start, end = ent["start"], ent["end"]
            mention = " ".join(tokens[start:end])
            mention_by_idx[idx] = mention
            entities.append(
                GoldEntity(doc_id=doc_id, mention=mention, type=TYPE_MAP.get(ent["type"], "OTHER"))
            )

        for rel in doc.get("relations", []):
            head = mention_by_idx.get(rel["head"])
            tail = mention_by_idx.get(rel["tail"])
            if head is None or tail is None:
                continue
            relations.append(
                GoldRelation(
                    doc_id=doc_id,
                    relation_type=REL_MAP.get(rel["type"], rel["type"].upper()),
                    head=head,
                    tail=tail,
                )
            )

    return GoldDataset(
        name=config.name, entities=entities, relations=relations, input_docs=input_docs
    )


def write_gold_jsonl(dataset: GoldDataset, gold_path: str, input_path: str) -> None:
    with open(gold_path, "w", encoding="utf-8") as gf:
        for ent in dataset.entities:
            gf.write(ent.model_dump_json() + "\n")
        for rel in dataset.relations:
            gf.write(rel.model_dump_json() + "\n")
    with open(input_path, "w", encoding="utf-8") as inf:
        for doc in dataset.input_docs:
            inf.write(doc.model_dump_json() + "\n")


def prepare_conll04(
    config: DatasetConfig,
    workdir: Path,
    fetcher: Callable[[DatasetConfig, Path], Path] | None = None,
) -> PreparedDataset:
    raw = (fetcher or fetch_conll04)(config, Path(workdir))
    dataset = parse_conll04(raw, config)
    input_path, gold_path = prepare_paths(Path(workdir), config.name)
    write_gold_jsonl(dataset, gold_path, input_path)
    return PreparedDataset(dataset=dataset, input_path=input_path, gold_path=gold_path)
