"""Assemble the final result JSON (validation spec 4.1 schema)."""

from __future__ import annotations

import json

from validation.base import ValidationResult


def build_result_json(result: ValidationResult) -> dict:
    payload: dict = {}
    for ac_id, ac in result.ac_results.items():
        payload[ac_id] = {
            "status": ac.status.value,
            "metrics_status": ac.metrics_status,
        }
    return payload


def write_result_json(result: ValidationResult, output_path: str) -> None:
    payload = build_result_json(result)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
