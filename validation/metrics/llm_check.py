"""VM8: verify the model configured in the solution's effective Hydra config."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from validation.base import ValidationRequest

EXPECTED_MODEL = "glm-5.3-flash"

# Python used to run the solution's config composition; configurable via Hydra.
DEFAULT_VALIDATOR_PYTHON = "/home/tony/venvs/entity_processing_validation/bin/python"


class ConfigResolveError(Exception):
    pass


def _find_model_value(node: object) -> str:
    """Extract the ``model`` value from a resolved config tree.

    Searches ``model`` keys at any nesting depth. Fails closed on ambiguity:
    multiple differently-valued ``model`` keys raise instead of guessing.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).strip().lower() == "model" and not isinstance(value, (dict, list)):
                    found.append(str(value).strip())
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(node)
    if not found:
        raise ConfigResolveError("model field not found in resolved config")
    distinct = {v for v in found}
    if len(distinct) > 1:
        raise ConfigResolveError(f"ambiguous model values in config: {sorted(distinct)}")
    return distinct.pop()


def resolve_effective_model(
    clone_path: Path, request: ValidationRequest, python_bin: str | None = None
) -> str:
    """Resolve the solution's effective Hydra config model field.

    Uses the solution's own config composition (`--cfg job`) so that
    solution_overrides are honored, then reads the model value from the
    printed YAML config.
    """
    cmd = [
        python_bin or DEFAULT_VALIDATOR_PYTHON,
        str(Path("scripts") / "extract_entities.py"),
        "--cfg",
        "job",
    ]
    overrides = request.solution_overrides.split() if request.solution_overrides else []
    cmd += overrides
    try:
        proc = subprocess.run(cmd, cwd=clone_path, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as e:
        raise ConfigResolveError(f"config resolution timed out: {e}") from e
    if proc.returncode != 0:
        raise ConfigResolveError(f"config resolution failed: {proc.stderr.strip()}")

    try:
        config = yaml.safe_load(proc.stdout)
    except yaml.YAMLError as e:
        raise ConfigResolveError(f"resolved config is not valid YAML: {e}") from e
    if config is None:
        raise ConfigResolveError("resolved config is empty")
    return _find_model_value(config)


def check_model(
    clone_path: Path, request: ValidationRequest, python_bin: str | None = None
) -> bool:
    try:
        return (
            resolve_effective_model(clone_path, request, python_bin).lower()
            == EXPECTED_MODEL.lower()
        )
    except ConfigResolveError:
        return False
