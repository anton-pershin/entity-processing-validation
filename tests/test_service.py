"""Tests for the M2 HTTP validation service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hydra import compose, initialize_config_dir

from validation.base import (
    AcceptanceStatus,
    ACResult,
    ACStatus,
    ComputationStatus,
    MetricResult,
    ValidationRequest,
    ValidationResult,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _compose(overrides: list[str] | None = None):
    with initialize_config_dir(config_dir=str(REPO_ROOT / "config"), version_base=None):
        return compose(config_name="config", overrides=overrides or [])


def _result(request: ValidationRequest, *, failed: bool = False) -> ValidationResult:
    metric = MetricResult(
        metric_id="VM1",
        computation_status=(
            ComputationStatus.FAILED_TO_COMPUTE if failed else ComputationStatus.COMPUTED
        ),
        acceptance_status=None if failed else AcceptanceStatus.ACCEPTED,
        computed_value=None if failed else 0.9,
        error_message="dataset failed" if failed else None,
    )
    ac = ACResult(
        ac_id="AC1",
        status=ACStatus.INVALID if failed else ACStatus.ACCEPTED,
        metrics_status={"VM1": metric.model_dump(mode="json")},
    )
    return ValidationResult(request=request, ac_results={"AC1": ac})


def test_valid_request_maps_to_orchestrator_and_returns_result(monkeypatch: pytest.MonkeyPatch):
    import scripts.validation_service as service

    calls = []

    def fake_run(request, config):
        calls.append((request, config))
        return _result(request)

    app = service.create_app(
        entries=[], run_config={"port": 8456}, run_validation_fn=fake_run
    )
    client = TestClient(app)
    payload = {"repo": "https://example/repo", "commit": "abc123", "solution_overrides": "x=y"}

    response = client.post("/validate", json=payload)

    assert response.status_code == 200
    assert response.json() == _result(ValidationRequest(**payload)).model_dump(mode="json")
    assert len(calls) == 1
    assert calls[0][0] == ValidationRequest(**payload)
    assert calls[0][0].output_json is None
    assert calls[0][1]["port"] == 8456
    assert "entries" in calls[0][1]

    second_payload = {"repo": "https://example/other", "commit": "def456"}
    second = client.post("/validate", json=second_payload)
    assert second.status_code == 200
    assert len(calls) == 2
    assert calls[1][0] == ValidationRequest(**second_payload)
    assert calls[1][0].solution_overrides == ""


def test_validation_errors_are_returned_as_results():
    import scripts.validation_service as service

    request = ValidationRequest(repo="repo", commit="commit")
    app = service.create_app(
        entries=[],
        run_config={},
        run_validation_fn=lambda _request, _config: _result(request, failed=True),
    )

    response = TestClient(app).post("/validate", json=request.model_dump())

    assert response.status_code == 200
    body = response.json()
    assert body["ac_results"]["AC1"]["status"] == "invalid"
    assert body["ac_results"]["AC1"]["metrics_status"]["VM1"]["error_message"] == "dataset failed"


@pytest.mark.parametrize(
    "payload",
    [
        {"commit": "abc"},
        {"repo": "repo"},
        {"repo": 123, "commit": "abc"},
        ["repo", "commit"],
    ],
)
def test_invalid_request_is_rejected_without_orchestrator(payload, monkeypatch: pytest.MonkeyPatch):
    import scripts.validation_service as service

    calls = []
    app = service.create_app(
        entries=[],
        run_config={},
        run_validation_fn=lambda request, config: calls.append((request, config)),
    )

    response = TestClient(app).post("/validate", json=payload)

    assert 400 <= response.status_code < 500
    assert calls == []


def test_malformed_json_is_rejected_without_orchestrator():
    import scripts.validation_service as service

    calls = []
    app = service.create_app(
        entries=[],
        run_config={},
        run_validation_fn=lambda request, config: calls.append((request, config)),
    )

    response = TestClient(app).post(
        "/validate", content='{"repo": "repo",', headers={"content-type": "application/json"}
    )

    assert 400 <= response.status_code < 500
    assert calls == []


def test_unexpected_orchestrator_error_is_server_error():
    import scripts.validation_service as service

    def fail(_request, _config):
        raise RuntimeError("unexpected")

    app = service.create_app(entries=[], run_config={}, run_validation_fn=fail)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/validate", json={"repo": "repo", "commit": "commit"})

    assert response.status_code == 500
    assert "ac_results" not in response.text


def test_route_and_method_handling(monkeypatch: pytest.MonkeyPatch):
    import scripts.validation_service as service

    calls = []
    app = service.create_app(
        entries=[],
        run_config={},
        run_validation_fn=lambda request, config: calls.append((request, config)),
    )
    client = TestClient(app)

    assert client.post("/unknown", json={}).status_code == 404
    assert client.get("/validate").status_code == 405
    assert calls == []


def test_hydra_config_and_startup_wiring(monkeypatch: pytest.MonkeyPatch):
    import scripts.validation_service as service

    cfg = _compose(["port=9123"])
    captured = {}

    def fake_uvicorn_run(app, *, host, port):
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr(service.uvicorn, "run", fake_uvicorn_run)
    service.run_service(cfg)

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9123
    assert "/validate" in {route.path for route in captured["app"].routes}


def test_dependency_metadata_declares_http_runtime():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    requirements = (REPO_ROOT / "requirements.txt").read_text()
    assert '"fastapi' in pyproject
    assert '"uvicorn' in pyproject
    assert "fastapi" in requirements
    assert "uvicorn" in requirements


def test_response_is_json():
    import scripts.validation_service as service

    app = service.create_app(
        entries=[],
        run_config={},
        run_validation_fn=lambda request, _config: _result(request),
    )
    response = TestClient(app).post("/validate", json={"repo": "repo", "commit": "commit"})
    json.loads(response.text)
    assert response.headers["content-type"].startswith("application/json")
