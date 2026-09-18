"""Tests for metrics VM1-VM8 using small hand-computed fixtures."""

from validation.base import (
    GoldDataset,
    GoldEntity,
    GoldRelation,
    InputDocument,
    ProducedEntity,
    ProducedRelation,
    SolutionDocument,
    SolutionOutput,
)
from validation.metrics.core import (
    entity_precision_recall,
    relation_precision_recall,
    sentiment_precision_recall,
)


def _gold() -> GoldDataset:
    return GoldDataset(
        name="t",
        entities=[
            GoldEntity(doc_id="d1", mention="John", type="PEOPLE", sentiment="POSITIVE"),
            GoldEntity(doc_id="d1", mention="Acme", type="ORGANIZATION"),
            GoldEntity(doc_id="d1", mention="Paris", type="LOCATION"),
        ],
        relations=[
            GoldRelation(doc_id="d1", relation_type="WORK_FOR", head="John", tail="Acme"),
            GoldRelation(doc_id="d1", relation_type="LIVE_IN", head="John", tail="Paris"),
        ],
        input_docs=[InputDocument(doc_id="d1", text="John works at Acme in Paris.")],
    )


def _output() -> SolutionOutput:
    return SolutionOutput(
        documents=[
            SolutionDocument(
                doc_id="d1",
                entities=[
                    ProducedEntity(
                        entity_id="e1", mention="John", type="PEOPLE", sentiment="POSITIVE"
                    ),
                    ProducedEntity(entity_id="e2", mention="Acme", type="ORGANIZATION"),
                    ProducedEntity(entity_id="e3", mention="London", type="LOCATION"),
                ],
                relations=[
                    # head/tail are entity ids per the constitution contract (§3).
                    ProducedRelation(relation_type="WORK_FOR", head="e1", tail="e2"),
                    ProducedRelation(relation_type="KILL", head="e1", tail="e3"),
                ],
            )
        ]
    )


def test_entity_precision_recall() -> None:
    gold, prod = _gold(), _output()
    # gold: John, Acme, Paris; produced: John, Acme, London
    # tp = {John, Acme} = 2; precision = 2/3; recall = 2/3
    p, r = entity_precision_recall(gold, prod)
    assert abs(p - 2 / 3) < 1e-9
    assert abs(r - 2 / 3) < 1e-9


def test_relation_precision_recall() -> None:
    gold, prod = _gold(), _output()
    # Produced ids resolve: e1->John, e2->Acme, e3->London.
    # WORK_FOR e1,e2 -> (John, Acme) matches gold; KILL e1,e3 -> (John, London) does not.
    # tp = 1; precision = 1/2; recall = 1/2
    p, r = relation_precision_recall(gold, prod)
    assert p == 0.5
    assert r == 0.5


def test_relation_unresolvable_ids_count_against_precision() -> None:
    gold = GoldDataset(
        name="t",
        entities=[],
        relations=[GoldRelation(doc_id="d1", relation_type="WORK_FOR", head="John", tail="Acme")],
    )
    prod = SolutionOutput(
        documents=[
            SolutionDocument(
                doc_id="d1",
                entities=[ProducedEntity(entity_id="e1", mention="John", type="PEOPLE")],
                relations=[
                    # tail id "eX" does not exist in the produced entities list.
                    ProducedRelation(relation_type="WORK_FOR", head="e1", tail="eX")
                ],
            )
        ]
    )
    p, r = relation_precision_recall(gold, prod)
    assert p == 0.0  # unresolvable relation counts as a false positive
    assert r == 0.0


def test_sentiment_precision_recall() -> None:
    gold, prod = _gold(), _output()
    # Only gold John has sentiment POSITIVE; produced John matches with POSITIVE.
    # precision = 1/1 = 1.0; recall = 1/1 = 1.0
    p, r = sentiment_precision_recall(gold, prod)
    assert p == 1.0
    assert r == 1.0


def test_sentiment_mismatch() -> None:
    gold = GoldDataset(
        name="t",
        entities=[GoldEntity(doc_id="d1", mention="John", type="PEOPLE", sentiment="NEGATIVE")],
    )
    prod = SolutionOutput(
        documents=[
            SolutionDocument(
                doc_id="d1",
                entities=[
                    ProducedEntity(
                        entity_id="e1", mention="John", type="PEOPLE", sentiment="POSITIVE"
                    )
                ],
            )
        ]
    )
    p, r = sentiment_precision_recall(gold, prod)
    assert p == 0.0
    assert r == 0.0


def test_empty_outputs_safe() -> None:
    gold = GoldDataset(name="t")
    prod = SolutionOutput()
    assert entity_precision_recall(gold, prod) == (0.0, 0.0)
    assert relation_precision_recall(gold, prod) == (0.0, 0.0)
    assert sentiment_precision_recall(gold, prod) == (0.0, 0.0)
