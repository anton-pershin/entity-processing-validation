"""Metrics for entity, sentiment, and relation extraction (VM1-VM6)."""

from __future__ import annotations

from validation.base import GoldDataset, SolutionDocument, SolutionOutput


def _entity_match_key(doc_id: str, mention: str, type_: str) -> tuple:
    return (doc_id, mention.strip().lower(), type_.strip().upper())


def entity_sets(gold: GoldDataset, output: SolutionOutput) -> tuple[set, set]:
    gold_set = {_entity_match_key(e.doc_id, e.mention, e.type) for e in gold.entities}
    prod_set = {
        _entity_match_key(d.doc_id, e.mention, e.type) for d in output.documents for e in d.entities
    }
    return gold_set, prod_set


def _safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def entity_precision_recall(gold: GoldDataset, output: SolutionOutput) -> tuple[float, float]:
    gold_set, prod_set = entity_sets(gold, output)
    tp = len(gold_set & prod_set)
    precision = _safe_div(tp, len(prod_set))
    recall = _safe_div(tp, len(gold_set))
    return precision, recall


def _relation_match_key(doc_id: str, rtype: str, head: str, tail: str) -> tuple:
    return (doc_id, rtype.strip().upper(), head.strip().lower(), tail.strip().lower())


def _resolve_mentions(document: SolutionDocument) -> dict[str, set[str]]:
    """Map entity id -> set of normalized mentions for one solution document.

    The contract (constitution spec §3) defines relation head/tail as entity
    ids; gold relations reference mention strings. A document may map one id
    to several mentions (duplicate ids), so the value is a set; a relation
    whose endpoint mentions all resolve is matched, matching gold semantics.
    """
    mapping: dict[str, set[str]] = {}
    for e in document.entities:
        mapping.setdefault(e.entity_id.strip(), set()).add(e.mention.strip().lower())
    return mapping


def relation_sets(gold: GoldDataset, output: SolutionOutput) -> tuple[set, set]:
    gold_set = {
        _relation_match_key(r.doc_id, r.relation_type, r.head, r.tail) for r in gold.relations
    }
    prod_set: set[tuple] = set()
    for d in output.documents:
        id_to_mentions = _resolve_mentions(d)
        for r in d.relations:
            head_mentions = id_to_mentions.get(r.head.strip())
            tail_mentions = id_to_mentions.get(r.tail.strip())
            if head_mentions is None or tail_mentions is None:
                # Unresolvable endpoint ids: relation counts against precision only.
                prod_set.add(
                    (
                        d.doc_id,
                        r.relation_type.strip().upper(),
                        f"__unresolved__{r.head}",
                        f"__unresolved__{r.tail}",
                    )
                )
                continue
            for head in head_mentions:
                for tail in tail_mentions:
                    prod_set.add(_relation_match_key(d.doc_id, r.relation_type, head, tail))
    return gold_set, prod_set


def relation_precision_recall(gold: GoldDataset, output: SolutionOutput) -> tuple[float, float]:
    gold_set, prod_set = relation_sets(gold, output)
    tp = len(gold_set & prod_set)
    precision = _safe_div(tp, len(prod_set))
    recall = _safe_div(tp, len(gold_set))
    return precision, recall


def _sentiment_matches(gold: GoldDataset, output: SolutionOutput) -> tuple[int, int, int]:
    """Return (sentiment_tp, produced_with_sentiment, gold_with_sentiment)."""
    gold_by_key: dict[tuple, str] = {}
    for e in gold.entities:
        if e.sentiment:
            gold_by_key[_entity_match_key(e.doc_id, e.mention, e.type)] = e.sentiment

    prod_by_key: dict[tuple, str] = {}
    for d in output.documents:
        for e in d.entities:
            if e.sentiment:
                prod_by_key[_entity_match_key(d.doc_id, e.mention, e.type)] = e.sentiment

    tp = sum(
        1 for key, sent in prod_by_key.items() if key in gold_by_key and gold_by_key[key] == sent
    )
    return tp, len(prod_by_key), len(gold_by_key)


def sentiment_precision_recall(gold: GoldDataset, output: SolutionOutput) -> tuple[float, float]:
    tp, n_prod, n_gold = _sentiment_matches(gold, output)
    precision = _safe_div(tp, n_prod)
    recall = _safe_div(tp, n_gold)
    return precision, recall
