#!/usr/bin/env python
"""Hydra CLI entrypoint for the entity-processing validation service."""

from __future__ import annotations

import json
from pathlib import Path

import hydra
from omegaconf import DictConfig

from validation.base import ValidationRequest
from validation.core import run_validation
from validation.reporting import write_result_json
from validation.suites import resolve_suite

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def run_cli(cfg: DictConfig) -> None:
    """Run one validation of the solution named by ``cfg``."""
    entries = resolve_suite(cfg.suite, CONFIG_DIR)
    request = ValidationRequest(
        repo=cfg.repo,
        commit=cfg.commit,
        output_json=cfg.output_json,
        solution_overrides=cfg.get("solution_overrides", "") or "",
    )
    run_cfg = {
        "workdir": cfg.workdir,
        "run_timeout_s": cfg.run_timeout_s,
        "datasets_cache_dir": cfg.datasets_cache_dir,
        "validator_python": cfg.validator_python,
        "entries": entries,
    }
    result = run_validation(request, run_cfg)
    if request.output_json:
        write_result_json(result, request.output_json)
        print(f"Validation result written to {request.output_json}")
    else:
        print(json.dumps(result.model_dump(mode="json"), indent=2))


@hydra.main(config_path="../config", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    run_cli(cfg)


if __name__ == "__main__":
    main()
