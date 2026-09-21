"""RuSentNE dataset: fetch and convert to gold JSONL.

RuSentNE evaluation data provides Russian news sentences with entity mentions
and targeted sentiment labels per entity. Source rows are TSV with columns:
sentence, entity, entity_tag, entity_pos_start_rel, entity_pos_end_rel, label.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from validation.base import GoldDataset, GoldEntity, InputDocument
from validation.datasets.base import DatasetConfig, PreparedDataset, prepare_paths, subset_documents
from validation.datasets.cache import DEFAULT_CACHE_DIR, cached_fetch

# Entity tags in RuSentNE that denote common-noun (non-named-entity) mentions.
# Kept tags: named entities (persons, organizations, locations); dropped tags:
# professions, nationalities and other common-noun categories.
NON_NAMED_ENTITY_TAGS = {
    "PROFESSION",
    "NATIONALITY",
    "PROF",
    "NAT",
}

# Secondary guard: bare common-noun tokens (lowercased lemma-ish forms).
NON_NAMED_ENTITY_TOKENS = {
    "компания",
    "фирма",
    "организация",
    "предприятие",
    "завод",
    "банк",
    "город",
    "регион",
    "область",
    "страна",
    "правительство",
    "министерство",
    "рынок",
    "суд",
    "прокуратура",
}

# RuSentNE label encoding (per upstream README): 0 = neutral, -1 = negative, 1 = positive.
LABEL_MAP = {"0": "NEUTRAL", "-1": "NEGATIVE", "1": "POSITIVE"}


class DatasetFetchError(Exception):
    pass


# RuSentNE has no upstream fetch script; the raw labelled file is pulled
# straight from the dataset repository's raw content host.
RUSENTNE_FETCH_URL = (
    "https://raw.githubusercontent.com/dialogue-evaluation/"
    "RuSentNE-evaluation/main/validation_data_labeled.csv"
)


def fetch_rusentne(config: DatasetConfig, dest_dir: Path, cache_dir: Path | None = None) -> Path:
    """Fetch RuSentNE labeled evaluation data (cached across runs)."""
    cache = cache_dir or DEFAULT_CACHE_DIR
    try:
        return cached_fetch(RUSENTNE_FETCH_URL, Path(dest_dir), "rusentne_raw.tsv", cache)
    except RuntimeError as e:
        raise DatasetFetchError(f"RuSentNE fetch failed: {e}") from e


def parse_rusentne(raw_path: Path, config: DatasetConfig) -> GoldDataset:
    """Convert RuSentNE TSV into a GoldDataset.

    Each row is one (sentence, entity, sentiment) triple; consecutive rows with
    the same sentence belong to the same document. Gold entities carry only the
    target sentiment labels used by VM3/VM4.
    """
    entities: list[GoldEntity] = []
    input_docs: list[InputDocument] = []
    # Deduplicate repeated sentence texts: rows with identical sentence text are
    # merged into one document (the same gold entities apply to all its copies).
    doc_id_by_text: dict[str, str] = {}
    counter = 0

    with open(raw_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            text = str(row.get("sentence", "")).strip()
            mention = str(row.get("entity", "")).strip()
            label = str(row.get("label", "")).strip()
            sentiment = LABEL_MAP.get(label, "NEUTRAL")

            if text not in doc_id_by_text:
                if not text:
                    continue
                doc_id = f"rusentne-{counter}"
                counter += 1
                doc_id_by_text[text] = doc_id
            doc_id = doc_id_by_text[text]

            entity_tag = str(row.get("entity_tag", "")).strip().upper()
            if entity_tag in NON_NAMED_ENTITY_TAGS:
                continue
            if not mention or mention.lower() in NON_NAMED_ENTITY_TOKENS:
                continue
            entities.append(
                GoldEntity(doc_id=doc_id, mention=mention, type="OTHER", sentiment=sentiment)
            )

    for text, doc_id in doc_id_by_text.items():
        input_docs.append(InputDocument(doc_id=doc_id, text=text))

    # The shuffled universe is the unique-sentence sequence, not the raw row
    # stream, so a subset is whole sentences rather than a truncated copy of a
    # document's rows (FR4).
    input_docs = subset_documents(input_docs, config.sample_size, config.shuffle_seed)
    keep = {d.doc_id for d in input_docs}
    entities = [e for e in entities if e.doc_id in keep]

    return GoldDataset(name=config.name, entities=entities, input_docs=input_docs)


def write_gold_jsonl(dataset: GoldDataset, gold_path: str, input_path: str) -> None:
    with open(gold_path, "w", encoding="utf-8") as gf:
        for ent in dataset.entities:
            gf.write(ent.model_dump_json() + "\n")
        for rel in dataset.relations:
            gf.write(rel.model_dump_json() + "\n")
    with open(input_path, "w", encoding="utf-8") as inf:
        for doc in dataset.input_docs:
            inf.write(doc.model_dump_json() + "\n")


def prepare_rusentne(
    config: DatasetConfig,
    workdir: Path,
    fetcher: Callable[[DatasetConfig, Path], Path] | None = None,
) -> PreparedDataset:
    raw = (fetcher or fetch_rusentne)(config, Path(workdir))
    dataset = parse_rusentne(raw, config)
    input_path, gold_path = prepare_paths(Path(workdir), config.name)
    write_gold_jsonl(dataset, gold_path, input_path)
    return PreparedDataset(dataset=dataset, input_path=input_path, gold_path=gold_path)
