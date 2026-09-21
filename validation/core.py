"""Orchestrator: request -> repo prep -> dataset prep -> run -> metrics -> acceptance -> result."""

from __future__ import annotations

import shutil
import subprocess
import time
import venv
from collections.abc import Callable
from pathlib import Path

from validation.acceptance import evaluate_ac
from validation.base import (
    ComputationStatus,
    GoldDataset,
    MetricResult,
    SolutionDocument,
    SolutionOutput,
    TimingInfo,
    ValidationRequest,
    ValidationResult,
)
from validation.datasets import prepare_conll04, prepare_rusentne
from validation.datasets.base import PreparedDataset, ResolvedEntry
from validation.datasets.cache import DEFAULT_CACHE_DIR
from validation.metrics import (
    entity_precision_recall,
    relation_precision_recall,
    sentiment_precision_recall,
)
from validation.metrics.llm_check import DEFAULT_VALIDATOR_PYTHON, check_model
from validation.repo import clone_repo

TYPE_LIST_ARGS = {
    "entity_types": "[LOCATION, ORGANIZATION, PEOPLE, OTHER]",
    "relation_types": "[WORK_FOR, KILL, ORGANIZATION_BASED_IN, LIVE_IN, LOCATED_IN]",
    "sentiment_types": "[POSITIVE, NEUTRAL, NEGATIVE]",
}

# Entry name -> its preparation function. The entry's own `source` selects the
# preparer; an injected `dataset_fns` map (keyed by entry name) overrides this
# for tests.
SOURCE_PREPARERS: dict[str, Callable] = {
    "conll04": prepare_conll04,
    "rusentne": prepare_rusentne,
}


def _make_fetcher(source: str, cache_dir: Path):
    """Build a dataset-specific fetcher bound to the shared cache directory."""
    if source == "conll04":
        from validation.datasets.conll04 import fetch_conll04

        return lambda cfg, dest: fetch_conll04(cfg, dest, cache_dir=cache_dir)
    if source == "rusentne":
        from validation.datasets.rusentne import fetch_rusentne

        return lambda cfg, dest: fetch_rusentne(cfg, dest, cache_dir=cache_dir)
    return None


def _ok(metric_id: str, value: float | None) -> MetricResult:
    return MetricResult(
        metric_id=metric_id, computation_status=ComputationStatus.COMPUTED, computed_value=value
    )


def _failed(metric_id: str, message: str) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        computation_status=ComputationStatus.FAILED_TO_COMPUTE,
        error_message=message,
    )


def _ensure_all_acs(result: ValidationResult, metric_results: dict[str, MetricResult]) -> None:
    for ac_id in [f"AC{i}" for i in range(1, 6)]:
        if ac_id not in result.ac_results:
            result.ac_results[ac_id] = evaluate_ac(ac_id, metric_results)


def _entry_preparer(entry: ResolvedEntry, dataset_fns: dict[str, Callable] | None) -> Callable:
    """The preparation function for one resolved entry."""
    if dataset_fns and entry.name in dataset_fns:
        return dataset_fns[entry.name]
    source = entry.config.source_name
    if source not in SOURCE_PREPARERS:
        raise ValueError(f"no preparer registered for dataset source '{source}'")
    return SOURCE_PREPARERS[source]


def run_validation(
    request: ValidationRequest,
    config: dict,
    runner_fn: Callable | None = None,
    dataset_fns: dict | None = None,
    clone_fn: Callable | None = None,
    llm_check_fn: Callable | None = None,
) -> ValidationResult:
    """Orchestrate a full validation run; always returns a ValidationResult.

    ``config["entries"]`` holds the resolved suite (``ResolvedEntry`` values).
    Each entry is prepared and run independently, so a failure in one entry
    degrades only the metrics that read it (FR5).
    """
    workdir = Path(config.get("workdir", "/tmp/entity_processing_validation"))
    workdir.mkdir(parents=True, exist_ok=True)
    timeout_s = config.get("run_timeout_s", 3600)
    entries: list[ResolvedEntry] = list(config.get("entries", []))
    clone_fn = clone_fn or clone_repo
    llm_check_fn = llm_check_fn or check_model

    result = ValidationResult(request=request)
    metric_results: dict[str, MetricResult] = {}
    timing = TimingInfo(total_minutes=0.0, n_documents=0)
    outputs: dict[str, SolutionOutput] = {}
    golds: dict[str, GoldDataset] = {}

    # Stage 1: clone
    try:
        clone_path = clone_fn(request, workdir)
    except Exception as e:
        _ensure_all_acs(
            result,
            {f"VM{i}": _failed(f"VM{i}", f"clone failed: {e}") for i in range(1, 9)},
        )
        return result

    # Stage 2: sweep stale artifacts of a previous run (every entry of this
    # suite, not a fixed pair of names), then prepare each entry.
    cache_dir = Path(config.get("datasets_cache_dir", str(DEFAULT_CACHE_DIR))).expanduser()
    for pattern in ("*_input.jsonl", "*_gold.jsonl", "*_solution_output.jsonl"):
        for stale in workdir.glob(pattern):
            stale.unlink(missing_ok=True)
    for stale in workdir.glob("*_solution_venv"):
        shutil.rmtree(stale, ignore_errors=True)

    prepared_datasets: dict[str, PreparedDataset] = {}
    for entry in entries:
        try:
            preparer = _entry_preparer(entry, dataset_fns)
            fetcher = _make_fetcher(entry.config.source_name, cache_dir)
            prepared = preparer(entry.config, workdir, fetcher=fetcher)
        except Exception as e:
            _fail_metrics(
                metric_results,
                f"dataset prep failed for entry '{entry.name}': {e}",
                entry.dataset_class.metric_ids(),
            )
            continue
        prepared_datasets[entry.name] = prepared
        golds[entry.name] = prepared.dataset
        timing.n_documents += len(prepared.dataset.input_docs)

    # Stage 3: run the solution once per prepared entry.
    per_entry_timing: dict[str, tuple[float, int]] = {}
    run_fn = runner_fn or _default_run_solution
    for entry in entries:
        prepared = prepared_datasets.get(entry.name)
        if prepared is None:
            continue
        try:
            elapsed_s, output = run_fn(clone_path, entry, prepared, request, timeout_s)
            outputs[entry.name] = output
            n_docs = len(prepared.dataset.input_docs)
            per_entry_timing[entry.name] = (elapsed_s / 60.0, n_docs)
            timing.total_minutes += elapsed_s / 60.0
        except Exception as e:
            _fail_metrics(
                metric_results,
                f"solution run failed for entry '{entry.name}': {e}",
                entry.dataset_class.metric_ids(),
            )

    # Stage 4: compute metrics, scoped to the dataset class each entry feeds.
    def _try_setdefault(metric_id: str, compute) -> None:
        try:
            metric_results.setdefault(metric_id, _ok(metric_id, compute()))
        except Exception as e:
            metric_results.setdefault(
                metric_id, _failed(metric_id, f"metric computation failed: {e}")
            )

    for name, output in outputs.items():
        gold = golds.get(name)
        if gold is None:
            continue
        if gold.entities:
            _try_setdefault(
                "VM1", lambda gold=gold, output=output: entity_precision_recall(gold, output)[0]
            )
            _try_setdefault(
                "VM2", lambda gold=gold, output=output: entity_precision_recall(gold, output)[1]
            )
        if gold.relations:
            _try_setdefault(
                "VM5", lambda gold=gold, output=output: relation_precision_recall(gold, output)[0]
            )
            _try_setdefault(
                "VM6", lambda gold=gold, output=output: relation_precision_recall(gold, output)[1]
            )
        if any(e.sentiment for e in gold.entities):
            _try_setdefault(
                "VM3", lambda gold=gold, output=output: sentiment_precision_recall(gold, output)[0]
            )
            _try_setdefault(
                "VM4", lambda gold=gold, output=output: sentiment_precision_recall(gold, output)[1]
            )

    # VM7: per-entry speed; the criterion uses the slowest entry run.
    if per_entry_timing:
        worst = max(
            minutes / (docs / 100) if docs else float("inf")
            for minutes, docs in per_entry_timing.values()
        )
        if worst != float("inf"):
            _try_setdefault("VM7", lambda: worst)
        else:
            metric_results.setdefault("VM7", _failed("VM7", "no documents processed"))
    else:
        metric_results.setdefault("VM7", _failed("VM7", "no documents processed"))

    validator_python = config.get("validator_python", DEFAULT_VALIDATOR_PYTHON)

    def _llm_check() -> float:
        try:
            return 1.0 if llm_check_fn(clone_path, request, validator_python) else 0.0
        except TypeError:
            # Custom checkers with the legacy (clone, request) signature.
            return 1.0 if llm_check_fn(clone_path, request) else 0.0

    _try_setdefault("VM8", _llm_check)

    # Ensure missing metrics fail explicitly.
    for i in range(1, 9):
        metric_results.setdefault(f"VM{i}", _failed(f"VM{i}", "metric not evaluated"))

    # Stage 5: acceptance
    _ensure_all_acs(result, metric_results)
    return result


def _fail_metrics(
    metric_results: dict[str, MetricResult], message: str, metric_ids: list[str] | None = None
) -> None:
    """Mark ``metric_ids`` (or every metric) failed_to_compute."""
    ids = metric_ids if metric_ids else [f"VM{i}" for i in range(1, 9)]
    for metric_id in ids:
        metric_results.setdefault(metric_id, _failed(metric_id, message))


def _default_run_solution(
    clone_path: Path,
    entry: ResolvedEntry,
    prepared: PreparedDataset,
    request: ValidationRequest,
    timeout_s: int,
) -> tuple[float, SolutionOutput]:
    """Run scripts/extract_entities.py in a fresh venv; return (elapsed_s, SolutionOutput).

    The venv is temporary and deleted after the run (success, failure, timeout
    or parse error) via try/finally; the output path is per entry so solutions
    appending to their output cannot contaminate another entry's run.
    """
    venv_dir = Path(prepared.input_path).parent / f"{entry.name}_solution_venv"
    venv.create(str(venv_dir), with_pip=True)
    python_bin = venv_dir / "bin" / "python"
    try:
        for dep_file in ("requirements.txt", "pyproject.toml"):
            if (clone_path / dep_file).exists():
                if dep_file == "requirements.txt":
                    subprocess.run(
                        [str(python_bin), "-m", "pip", "install", "-q", "-r", dep_file],
                        cwd=clone_path,
                        capture_output=True,
                        timeout=1200,
                    )
                else:
                    subprocess.run(
                        [str(python_bin), "-m", "pip", "install", "-q", "."],
                        cwd=clone_path,
                        capture_output=True,
                        timeout=1200,
                    )
                break

        output_path = str(
            Path(prepared.input_path).with_name(f"{entry.name}_solution_output.jsonl")
        )
        args = [
            str(python_bin),
            "scripts/extract_entities.py",
            f"input={prepared.input_path}",
            f"output={output_path}",
        ]
        for key, val in TYPE_LIST_ARGS.items():
            args.append(f"{key}={val}")
        if request.solution_overrides:
            args += request.solution_overrides.split()

        start = time.time()
        try:
            proc = subprocess.run(
                args, cwd=clone_path, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"solution run timed out after {timeout_s}s") from e
        elapsed_s = time.time() - start

        if proc.returncode != 0:
            raise RuntimeError(f"solution exited {proc.returncode}: {proc.stderr.strip()}")

        documents: list[SolutionDocument] = []
        try:
            with open(output_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        documents.append(SolutionDocument.model_validate_json(line))
        except FileNotFoundError as e:
            raise RuntimeError(f"solution output file missing: {e}") from e
        except Exception as e:
            raise RuntimeError(f"solution output unparseable: {e}") from e

        return elapsed_s, SolutionOutput(documents=documents)
    finally:
        shutil.rmtree(venv_dir, ignore_errors=True)
