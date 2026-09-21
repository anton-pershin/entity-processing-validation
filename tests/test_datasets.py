"""Tests for dataset preparation using bundled mini-fixtures (no network).

Includes seeded-shuffle subsetting (T3) and the full-preparation regression (T7).
"""

import json
from pathlib import Path

from validation.base import GoldDataset, GoldEntity, InputDocument
from validation.datasets.base import DatasetConfig, subset_documents
from validation.datasets.conll04 import parse_conll04, write_gold_jsonl
from validation.datasets.rusentne import parse_rusentne

CONLL04_RAW = [
    {
        "orig_id": 0,
        "tokens": ["John", "works", "at", "Acme", "in", "Paris", "."],
        "entities": [
            {"type": "Peop", "start": 0, "end": 1},
            {"type": "Org", "start": 3, "end": 4},
            {"type": "Loc", "start": 5, "end": 6},
        ],
        "relations": [
            {"type": "Work_For", "head": 0, "tail": 1},
            {"type": "Located_In", "head": 1, "tail": 2},
        ],
    }
]

RUSENTNE_CSV = (
    "sentence\tentity\tentity_tag\tentity_pos_start_rel\tentity_pos_end_rel\tlabel\n"
    "Акционеры обсудили итоги.\tСбербанк\tORG\t0\t8\t1\n"
    "Компания отчиталась о прибыли.\tкомпания\tPROF\t0\t7\t1\n"
)


def _multi_doc_conll04(n: int = 20) -> list[dict]:
    """A mini CoNLL04 source whose relations are spread across docs."""
    docs = []
    for i in range(n):
        docs.append(
            {
                "orig_id": i,
                "tokens": ["Doc", str(i), "mentions", "Acme", "and", "Paris", "."],
                "entities": [
                    {"type": "Org", "start": 3, "end": 4},
                    {"type": "Loc", "start": 5, "end": 6},
                ],
                "relations": [{"type": "Located_In", "head": 0, "tail": 1}],
            }
        )
    return docs


def _multi_sentence_rusentne(n: int = 20) -> str:
    header = "sentence\tentity\tentity_tag\tentity_pos_start_rel\tentity_pos_end_rel\tlabel\n"
    rows = "".join(f"Предложение номер {i}.\tСбербанк\tORG\t0\t8\t1\n" for i in range(n))
    return header + rows


def test_parse_conll04(tmp_path: Path) -> None:
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(CONLL04_RAW))
    config = DatasetConfig(name="conll04")
    ds = parse_conll04(raw, config)
    assert [e.mention for e in ds.entities] == ["John", "Acme", "Paris"]
    assert [e.type for e in ds.entities] == ["PEOPLE", "ORGANIZATION", "LOCATION"]
    assert [(r.relation_type, r.head, r.tail) for r in ds.relations] == [
        ("WORK_FOR", "John", "Acme"),
        ("LOCATED_IN", "Acme", "Paris"),
    ]


def test_rusentne_filters_common_nouns(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(RUSENTNE_CSV, encoding="utf-8")
    config = DatasetConfig(name="rusentne")
    ds = parse_rusentne(raw, config)
    # "компания" is a common noun and must be filtered out.
    assert [e.mention for e in ds.entities] == ["Сбербанк"]
    assert ds.entities[0].sentiment == "POSITIVE"


def test_write_gold_jsonl(tmp_path: Path) -> None:
    ds = GoldDataset(
        name="t",
        entities=[GoldEntity(doc_id="d1", mention="X", type="OTHER")],
        input_docs=[InputDocument(doc_id="d1", text="X here.")],
    )
    gold = tmp_path / "g.jsonl"
    inp = tmp_path / "i.jsonl"
    write_gold_jsonl(ds, str(gold), str(inp))
    gold_lines = [json.loads(line) for line in gold.read_text().splitlines() if line]
    input_lines = [json.loads(line) for line in inp.read_text().splitlines() if line]
    assert gold_lines[0]["mention"] == "X"
    assert input_lines[0]["text"] == "X here."


# --- T3: seeded-shuffle subsetting (FR4, rows 7-12) --------------------------


def test_subset_null_keeps_whole_source_in_order() -> None:
    """Row 7: sample_size null -> whole source in source order."""
    docs = _multi_doc_conll04()
    kept = subset_documents(docs, sample_size=None, shuffle_seed=1)
    assert kept == docs


def test_subset_oversized_keeps_whole_source() -> None:
    """Row 8: sample_size > source count -> whole source."""
    docs = _multi_doc_conll04()
    kept = subset_documents(docs, sample_size=1000, shuffle_seed=1)
    assert kept == docs


def test_subset_selects_exactly_sample_size() -> None:
    """Row 9: a smaller sample_size yields exactly that many documents."""
    docs = _multi_doc_conll04()
    kept = subset_documents(docs, sample_size=5, shuffle_seed=7)
    assert len(kept) == 5
    assert all(d in docs for d in kept)


def test_subset_is_deterministic() -> None:
    """Row 10: same entry prepared twice -> identical documents and order."""
    docs = _multi_doc_conll04()
    first = subset_documents(docs, sample_size=5, shuffle_seed=7)
    second = subset_documents(docs, sample_size=5, shuffle_seed=7)
    assert [d["orig_id"] for d in first] == [d["orig_id"] for d in second]


def test_subset_different_seed_differs() -> None:
    docs = _multi_doc_conll04(50)
    a = [d["orig_id"] for d in subset_documents(docs, sample_size=10, shuffle_seed=1)]
    b = [d["orig_id"] for d in subset_documents(docs, sample_size=10, shuffle_seed=2)]
    assert a != b


def test_conll04_subset_drops_orphaned_relations(tmp_path: Path) -> None:
    """Row 11: no relation outlives the entities its endpoints refer to."""
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(_multi_doc_conll04(20)))
    full = parse_conll04(raw, DatasetConfig(name="conll04"))
    assert len(full.relations) == 20

    for seed in (1, 2, 3):
        ds = parse_conll04(raw, DatasetConfig(name="conll04", sample_size=5, shuffle_seed=seed))
        assert len(ds.input_docs) == 5
        doc_ids = {d.doc_id for d in ds.input_docs}
        assert {r.doc_id for r in ds.relations} <= doc_ids
        # every relation endpoint is a gold entity of the same document
        by_doc = {(e.doc_id, e.mention) for e in ds.entities}
        for rel in ds.relations:
            assert (rel.doc_id, rel.head) in by_doc
            assert (rel.doc_id, rel.tail) in by_doc


def test_rusentne_subset_is_unique_sentences(tmp_path: Path) -> None:
    """Row 12: subset contains sample_size unique sentences, none truncated."""
    raw = tmp_path / "raw.csv"
    raw.write_text(_multi_sentence_rusentne(20), encoding="utf-8")
    ds = parse_rusentne(raw, DatasetConfig(name="rusentne", sample_size=5, shuffle_seed=3))
    assert len(ds.input_docs) == 5
    assert len({d.doc_id for d in ds.input_docs}) == 5
    assert len({d.text for d in ds.input_docs}) == 5


# --- T7: full preparation is unchanged (row 1) ------------------------------


def test_full_conll04_preparation_unchanged(tmp_path: Path) -> None:
    raw = tmp_path / "raw.json"
    source = _multi_doc_conll04(20)
    raw.write_text(json.dumps(source))
    ds = parse_conll04(raw, DatasetConfig(name="conll04"))
    assert [d.doc_id for d in ds.input_docs] == [f"conll04-{i}" for i in range(20)]
    assert len(ds.entities) == 40
    assert len(ds.relations) == 20


def test_full_rusentne_preparation_unchanged(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(_multi_sentence_rusentne(20), encoding="utf-8")
    ds = parse_rusentne(raw, DatasetConfig(name="rusentne"))
    assert [d.doc_id for d in ds.input_docs] == [f"rusentne-{i}" for i in range(20)]
    assert len(ds.entities) == 20
