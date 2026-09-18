"""Tests for dataset preparation using bundled mini-fixtures (no network)."""

import json
from pathlib import Path

from validation.base import GoldDataset, GoldEntity, InputDocument
from validation.datasets.base import DatasetConfig
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
