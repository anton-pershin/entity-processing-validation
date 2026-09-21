"""Tests for the subset materialization entrypoint (T6)."""

import json
from pathlib import Path

import scripts.build_subset as build_subset
from validation.datasets.base import DatasetConfig
from validation.datasets.conll04 import parse_conll04

CONLL04_SOURCE = [
    {
        "orig_id": i,
        "tokens": ["Doc", str(i), "mentions", "Acme", "and", "Paris", "."],
        "entities": [
            {"type": "Org", "start": 3, "end": 4},
            {"type": "Loc", "start": 5, "end": 6},
        ],
        "relations": [{"type": "Located_In", "head": 0, "tail": 1}],
    }
    for i in range(20)
]


def test_materialize_writes_input_and_gold(tmp_path: Path) -> None:
    """Row 16: writes under output_dir, leaves workdir and cache untouched."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    (workdir / "canary.txt").write_text("untouched")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "conll04_raw.json").write_text("[]")
    before = sorted(p.name for p in cache.iterdir())

    out = tmp_path / "out"
    config = DatasetConfig(name="conll04_small", source="conll04", sample_size=5, shuffle_seed=7)
    paths = build_subset.materialize(
        config,
        output_dir=out,
        workdir=workdir,
        fetcher=lambda cfg, dest: _write_source(tmp_path),
    )

    assert out.is_dir()
    for key in ("input_path", "gold_path"):
        assert Path(paths[key]).exists()
        assert Path(paths[key]).parent == out

    input_lines = [
        json.loads(line)
        for line in Path(paths["input_path"]).read_text().splitlines()
        if line.strip()
    ]
    gold_lines = [
        json.loads(line)
        for line in Path(paths["gold_path"]).read_text().splitlines()
        if line.strip()
    ]
    assert len(input_lines) == 5
    # gold JSONL holds both gold entities and gold relations: per document
    # 2 entities (Acme, Paris) + 1 relation = 3 lines.
    assert len(gold_lines) == 15

    # workdir untouched, cache not removed or overwritten
    assert sorted(p.name for p in workdir.iterdir()) == ["canary.txt"]
    assert (workdir / "canary.txt").read_text() == "untouched"
    assert sorted(p.name for p in cache.iterdir()) == before


def test_materialize_is_deterministic(tmp_path: Path) -> None:
    """Row 17: two invocations with the same arguments are byte-identical."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    config = DatasetConfig(name="conll04_small", source="conll04", sample_size=5, shuffle_seed=7)

    def fetcher(cfg, dest):
        return _write_source(tmp_path)

    a = build_subset.materialize(
        config, output_dir=tmp_path / "a", workdir=workdir, fetcher=fetcher
    )
    b = build_subset.materialize(
        config, output_dir=tmp_path / "b", workdir=workdir, fetcher=fetcher
    )
    assert Path(a["input_path"]).read_bytes() == Path(b["input_path"]).read_bytes()
    assert Path(a["gold_path"]).read_bytes() == Path(b["gold_path"]).read_bytes()


def _write_source(tmp_path: Path) -> Path:
    raw = tmp_path / "source" / "conll04_raw.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps(CONLL04_SOURCE))
    return raw


def test_materialize_uses_the_real_parser(tmp_path: Path) -> None:
    raw = _write_source(tmp_path)
    config = DatasetConfig(name="conll04", source="conll04")
    ds = parse_conll04(raw, config)
    assert len(ds.input_docs) == 20
