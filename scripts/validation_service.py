#!/usr/bin/env python
"""Hydra/FastAPI entrypoint for the entity-processing validation service."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import hydra
import uvicorn
from fastapi import FastAPI
from omegaconf import DictConfig

from validation.base import ValidationRequest, ValidationResult
from validation.core import run_validation
from validation.datasets.base import ResolvedEntry
from validation.suites import resolve_suite

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
RunValidation = Callable[[ValidationRequest, dict[str, Any]], ValidationResult]


def create_app(
    entries: Sequence[ResolvedEntry],
    run_config: dict[str, Any],
    run_validation_fn: RunValidation = run_validation,
) -> FastAPI:
    """Create the HTTP application for one configured validation suite."""
    app = FastAPI(title="entity-processing validation service")

    @app.post("/validate", response_model=ValidationResult)
    def validate(request: ValidationRequest) -> ValidationResult:
        """Validate one solution repository and return its complete result."""
        http_request = request.model_copy(update={"output_json": None})
        config = {**run_config, "entries": list(entries)}
        return run_validation_fn(http_request, config)

    return app


def _run_config(cfg: DictConfig, entries: Sequence[ResolvedEntry]) -> dict[str, Any]:
    """Build the same orchestrator settings used by the CLI entrypoint."""
    return {
        "workdir": cfg.workdir,
        "run_timeout_s": cfg.run_timeout_s,
        "datasets_cache_dir": cfg.datasets_cache_dir,
        "validator_python": cfg.validator_python,
        "entries": list(entries),
    }


def run_service(cfg: DictConfig) -> None:
    """Resolve the configured suite and start the HTTP server."""
    entries = resolve_suite(cfg.suite, CONFIG_DIR)
    app = create_app(entries, _run_config(cfg, entries))
    uvicorn.run(app, host=str(cfg.host), port=int(cfg.port))


@hydra.main(config_path="../config", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    """Hydra entrypoint."""
    run_service(cfg)


if __name__ == "__main__":
    main()
