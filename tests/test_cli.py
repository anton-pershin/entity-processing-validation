"""Tests for suite selection through the CLI entrypoint (T5)."""

from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from validation.base import ValidationResult

REPO_ROOT = Path(__file__).resolve().parents[1]


def _compose(overrides: list[str]):
    with initialize_config_dir(config_dir=str(REPO_ROOT / "config"), version_base=None):
        return compose(config_name="config", overrides=overrides)


def test_cli_suite_override_reaches_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    """`suite=<name>` is resolved and its entries handed to the orchestrator."""
    import scripts.validation_cli as cli

    captured = {}

    def fake_run_validation(request, config, *args, **kwargs):
        captured["config"] = config
        return ValidationResult(request=request)

    monkeypatch.setattr(cli, "run_validation", fake_run_validation)
    cfg = _compose(["repo=http://example/repo", "commit=abc", "suite=small"])
    cli.run_cli(cfg)

    assert [e.name for e in captured["config"]["entries"]] == ["conll04_small", "rusentne_small"]


def test_cli_default_suite_comes_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no override, the `suite` key of config.yaml selects the suite."""
    import scripts.validation_cli as cli

    captured = {}

    def fake_run_validation(request, config, *args, **kwargs):
        captured["config"] = config
        return ValidationResult(request=request)

    monkeypatch.setattr(cli, "run_validation", fake_run_validation)
    cfg = _compose(["repo=http://example/repo", "commit=abc"])
    cli.run_cli(cfg)

    assert OmegaConf.select(cfg, "suite") == "full"
    assert [e.name for e in captured["config"]["entries"]] == ["conll04", "rusentne"]
