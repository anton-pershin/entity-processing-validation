"""Tests for acceptance criteria evaluation and reporting."""

from validation.acceptance import evaluate_ac
from validation.base import (
    ACStatus,
    ComputationStatus,
    MetricResult,
    ValidationRequest,
    ValidationResult,
)
from validation.reporting import build_result_json


def _m(mid: str, value: float | None, failed: bool = False) -> MetricResult:
    if failed:
        return MetricResult(
            metric_id=mid,
            computation_status=ComputationStatus.FAILED_TO_COMPUTE,
            error_message="boom",
        )
    return MetricResult(
        metric_id=mid, computation_status=ComputationStatus.COMPUTED, computed_value=value
    )


def test_ac1_accepted() -> None:
    r = evaluate_ac("AC1", {"VM1": _m("VM1", 0.9), "VM2": _m("VM2", 0.85)})
    assert r.status == ACStatus.ACCEPTED


def test_ac1_valid_when_rejected() -> None:
    r = evaluate_ac("AC1", {"VM1": _m("VM1", 0.9), "VM2": _m("VM2", 0.5)})
    assert r.status == ACStatus.VALID
    ms = r.metrics_status["VM2"]
    assert ms["acceptance_status"] == "rejected"
    assert ms["expected_value_or_threshold"] == 0.8


def test_ac_invalid_when_failed() -> None:
    r = evaluate_ac("AC1", {"VM1": _m("VM1", 0.9), "VM2": _m("VM2", None, failed=True)})
    assert r.status == ACStatus.INVALID
    assert r.metrics_status["VM2"]["error_message"] == "boom"


def test_ac4_time_threshold() -> None:
    r = evaluate_ac("AC4", {"VM7": _m("VM7", 9.9)})
    assert r.status == ACStatus.ACCEPTED
    r = evaluate_ac("AC4", {"VM7": _m("VM7", 10.5)})
    assert r.status == ACStatus.VALID


def test_ac5_model_check() -> None:
    r = evaluate_ac("AC5", {"VM8": _m("VM8", 1.0)})
    assert r.status == ACStatus.ACCEPTED
    r = evaluate_ac("AC5", {"VM8": _m("VM8", 0.0)})
    assert r.status == ACStatus.VALID


def test_missing_metric_is_invalid() -> None:
    r = evaluate_ac("AC3", {"VM5": _m("VM5", 0.7)})
    assert r.status == ACStatus.INVALID
    assert r.metrics_status["VM6"]["error_message"] == "metric not evaluated"


def test_build_result_json() -> None:
    res = ValidationResult(
        request=ValidationRequest(repo="r", commit="c"),
        ac_results={
            "AC4": evaluate_ac("AC4", {"VM7": _m("VM7", 8.0)}),
        },
    )
    payload = build_result_json(res)
    assert payload["AC4"]["status"] == "accepted"
