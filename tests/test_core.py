"""Integration tests for the M1 CLI validation pipeline (hermetic, no network)."""

import json
import subprocess
from pathlib import Path

from validation.base import (
    ACStatus,
    GoldDataset,
    GoldEntity,
    InputDocument,
    SolutionOutput,
    ValidationRequest,
)
from validation.core import run_validation
from validation.datasets.base import DatasetConfig, PreparedDataset

STUB_SOLUTION = """
import json, sys, argparse
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
docs = [json.loads(l) for l in open(args["input"]) if l.strip()]
with open(args["output"], "w") as f:
    for d in docs:
        f.write(json.dumps({
            "doc_id": d["doc_id"],
            "entities": [
                {"entity_id": "e1", "mention": "John", "type": "PEOPLE", "sentiment": "POSITIVE"}
            ],
            "relations": [],
        }) + "\\n")
"""


def _make_stub_repo(tmp_path: Path) -> tuple[str, str]:
    repo = tmp_path / "stub_solution"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts" / "extract_entities.py").write_text(STUB_SOLUTION)
    (repo / "requirements.txt").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "stub"], cwd=repo, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return str(repo), commit


def _stub_dataset_fn(name: str):
    def prepare(config: DatasetConfig, workdir: Path, fetcher=None) -> PreparedDataset:
        dataset = GoldDataset(
            name=name,
            entities=[GoldEntity(doc_id="d1", mention="John", type="PEOPLE", sentiment="POSITIVE")],
            input_docs=[InputDocument(doc_id="d1", text="John works here.")],
        )
        input_path = str(Path(workdir) / f"{name}_input.jsonl")
        gold_path = str(Path(workdir) / f"{name}_gold.jsonl")
        with open(input_path, "w") as f:
            f.write(json.dumps({"doc_id": "d1", "text": "John works here."}) + "\n")
        with open(gold_path, "w") as f:
            f.write(
                json.dumps(
                    {"doc_id": "d1", "mention": "John", "type": "PEOPLE", "sentiment": "POSITIVE"}
                )
                + "\n"
            )
        return PreparedDataset(dataset=dataset, input_path=input_path, gold_path=gold_path)

    return prepare


def _stub_runner(clone_path, prepared, request, timeout_s):
    # Simulate a solution run: produce matching output directly.
    output_path = Path(prepared.input_path).with_name("solution_output.jsonl")
    with open(output_path, "w") as f:
        f.write(
            json.dumps(
                {
                    "doc_id": "d1",
                    "entities": [
                        {
                            "entity_id": "e1",
                            "mention": "John",
                            "type": "PEOPLE",
                            "sentiment": "POSITIVE",
                        }
                    ],
                    "relations": [],
                }
            )
            + "\n"
        )
    return 0.1, SolutionOutput.model_validate_json(
        json.dumps({"documents": [json.loads(open(output_path).read().splitlines()[0])]})
    )


def test_run_validation_stub(tmp_path: Path) -> None:
    config = {"workdir": str(tmp_path / "run"), "run_timeout_s": 60}
    dataset_fns = {"stub1": _stub_dataset_fn("stub1")}
    request = ValidationRequest(repo="stub", commit="c", solution_overrides="")
    result = run_validation(
        request,
        config,
        runner_fn=_stub_runner,
        dataset_fns=dataset_fns,
        clone_fn=lambda req, wd: tmp_path,  # skip real clone
        llm_check_fn=lambda clone, req: True,
    )
    assert result.ac_results["AC1"].status == ACStatus.ACCEPTED
    assert result.ac_results["AC4"].status == ACStatus.ACCEPTED
    assert result.ac_results["AC5"].status == ACStatus.ACCEPTED
    assert result.ac_results["AC2"].status == ACStatus.ACCEPTED  # sentiment computed from stub gold
    assert result.ac_results["AC3"].status == ACStatus.INVALID  # no relation gold in stub


def test_run_validation_clone_failure(tmp_path: Path) -> None:
    config = {"workdir": str(tmp_path / "run"), "run_timeout_s": 60}
    request = ValidationRequest(repo="bad", commit="c")

    def bad_clone(req, wd):
        raise RuntimeError("clone exploded")

    result = run_validation(
        request,
        config,
        clone_fn=bad_clone,
        dataset_fns={"stub": _stub_dataset_fn("stub")},
        runner_fn=_stub_runner,
        llm_check_fn=lambda c, r: False,
    )
    for ac in result.ac_results.values():
        assert ac.status == ACStatus.INVALID


def test_run_validation_solution_failure(tmp_path: Path) -> None:
    config = {"workdir": str(tmp_path / "run"), "run_timeout_s": 60}
    request = ValidationRequest(repo="stub", commit="c")

    def bad_runner(clone_path, prepared, request, timeout_s):
        raise RuntimeError("solution exited 1")

    result = run_validation(
        request,
        config,
        runner_fn=bad_runner,
        dataset_fns={"stub": _stub_dataset_fn("stub")},
        clone_fn=lambda req, wd: tmp_path,
        llm_check_fn=lambda c, r: False,
    )
    assert result.ac_results["AC1"].status == ACStatus.INVALID
