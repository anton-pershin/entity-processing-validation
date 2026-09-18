"""Acceptance criteria evaluation (AC1-AC5) and result JSON assembly."""

from __future__ import annotations

from validation.base import (
    AcceptanceStatus,
    ACResult,
    ACStatus,
    ComputationStatus,
    MetricResult,
)

# AC id -> (metric ids, comparator, threshold)
AC_THRESHOLDS: dict[str, tuple[list[str], str, float]] = {
    "AC1": (["VM1", "VM2"], ">", 0.8),
    "AC2": (["VM3", "VM4"], ">", 0.8),
    "AC3": (["VM5", "VM6"], ">", 0.6),
    "AC4": (["VM7"], "<", 10.0),
    "AC5": (["VM8"], "=", 1.0),
}


def _metric_acceptance(
    computation_status: ComputationStatus,
    value: float | None,
    comparator: str,
    threshold: float,
) -> AcceptanceStatus | None:
    if computation_status != ComputationStatus.COMPUTED or value is None:
        return None
    if comparator == ">":
        ok = value > threshold
    elif comparator == "<":
        ok = value < threshold
    elif comparator == "=":
        ok = value == threshold
    else:
        raise ValueError(f"unknown comparator: {comparator}")
    return AcceptanceStatus.ACCEPTED if ok else AcceptanceStatus.REJECTED


def evaluate_ac(ac_id: str, results: dict[str, MetricResult]) -> ACResult:
    """Evaluate one acceptance criterion from its metrics' results."""
    if ac_id not in AC_THRESHOLDS:
        raise ValueError(f"unknown acceptance criterion: {ac_id}")
    metric_ids, comparator, threshold = AC_THRESHOLDS[ac_id]

    metrics_status: dict[str, dict] = {}
    statuses: list[ComputationStatus] = []
    acceptances: list[AcceptanceStatus] = []

    for mid in metric_ids:
        res = results.get(mid)
        if res is None or res.computation_status == ComputationStatus.FAILED_TO_COMPUTE:
            comp = ComputationStatus.FAILED_TO_COMPUTE
            acceptance = None
        else:
            comp = ComputationStatus.COMPUTED
            acceptance = _metric_acceptance(
                res.computation_status, res.computed_value, comparator, threshold
            )
        statuses.append(comp)
        if acceptance is not None:
            acceptances.append(acceptance)
        metrics_status[mid] = {
            "computation_status": comp.value,
            "acceptance_status": acceptance.value if acceptance else None,
            "computed_value": res.computed_value if res else None,
            "expected_value_or_threshold": threshold,
            "error_message": res.error_message if res else "metric not evaluated",
        }

    if any(s == ComputationStatus.FAILED_TO_COMPUTE for s in statuses):
        status = ACStatus.INVALID
    elif any(a == AcceptanceStatus.REJECTED for a in acceptances):
        status = ACStatus.VALID
    else:
        status = ACStatus.ACCEPTED

    return ACResult(ac_id=ac_id, status=status, metrics_status=metrics_status)
