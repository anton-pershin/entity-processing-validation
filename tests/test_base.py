"""Tests for the validation result schema round-trip (validation.base)."""

import json

from validation.base import (
    AcceptanceStatus,
    ACResult,
    ACStatus,
    ComputationStatus,
    GoldDataset,
    GoldEntity,
    GoldRelation,
    InputDocument,
    MetricResult,
    ProducedEntity,
    ProducedRelation,
    SolutionDocument,
    SolutionOutput,
    TimingInfo,
    ValidationRequest,
    ValidationResult,
)


def test_metric_result_computed() -> None:
    r = MetricResult(
        metric_id="VM1",
        computation_status=ComputationStatus.COMPUTED,
        acceptance_status=AcceptanceStatus.ACCEPTED,
        computed_value=0.95,
    )
    data = json.loads(r.model_dump_json())
    assert data["computed_value"] == 0.95
    assert data["error_message"] is None


def test_metric_result_failed() -> None:
    r = MetricResult(
        metric_id="VM7",
        computation_status=ComputationStatus.FAILED_TO_COMPUTE,
        error_message="solution script timed out",
    )
    data = json.loads(r.model_dump_json())
    assert data["computed_value"] is None
    assert data["acceptance_status"] is None
    assert data["error_message"] == "solution script timed out"


def test_validation_result_round_trip() -> None:
    result = ValidationResult(
        request=ValidationRequest(repo="https://example.com/repo.git", commit="abc123"),
        ac_results={
            "AC1": ACResult(
                ac_id="AC1",
                status=ACStatus.ACCEPTED,
                metrics_status={
                    "VM1": {
                        "computation_status": "computed",
                        "acceptance_status": "accepted",
                        "computed_value": 0.9,
                        "error_message": None,
                    }
                },
            )
        },
    )
    data = json.loads(result.model_dump_json())
    assert data["ac_results"]["AC1"]["status"] == "accepted"
    assert data["ac_results"]["AC1"]["metrics_status"]["VM1"]["computed_value"] == 0.9


def test_gold_dataset() -> None:
    ds = GoldDataset(
        name="conll04",
        entities=[GoldEntity(doc_id="d1", mention="France", type="Loc")],
        relations=[GoldRelation(doc_id="d1", relation_type="Located_In", head="e1", tail="e2")],
        input_docs=[InputDocument(doc_id="d1", text="France is a country.")],
    )
    assert ds.entities[0].sentiment is None
    assert ds.input_docs[0].doc_id == "d1"


def test_solution_output() -> None:
    out = SolutionOutput(
        documents=[
            SolutionDocument(
                doc_id="d1",
                entities=[ProducedEntity(entity_id="e1", mention="France", type="LOCATION")],
                relations=[ProducedRelation(relation_type="LOCATED_IN", head="e1", tail="e2")],
            )
        ]
    )
    assert out.documents[0].entities[0].mention == "France"


def test_timing_info() -> None:
    t = TimingInfo(total_minutes=5.0, n_documents=100)
    assert t.total_minutes / (t.n_documents / 100) == 5.0
