"""Pydantic models exchanged between validation pipeline stages."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComputationStatus(StrEnum):
    """Whether a metric value could be computed."""

    COMPUTED = "computed"
    FAILED_TO_COMPUTE = "failed_to_compute"


class AcceptanceStatus(StrEnum):
    """Whether a computed metric value satisfies its acceptance condition."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ACStatus(StrEnum):
    """Status of an acceptance criterion as a whole."""

    ACCEPTED = "accepted"
    VALID = "valid"
    INVALID = "invalid"


class ValidationRequest(BaseModel):
    """A request to validate a solution implementation."""

    repo: str = Field(description="Clonable link to the solution repository")
    commit: str = Field(description="Commit hash to validate")
    output_json: str | None = Field(
        default=None, description="Path where the result JSON is written (CLI mode)"
    )
    solution_overrides: str = Field(
        default="", description="Whitespace-separated extra args for the solution script"
    )


class GoldEntity(BaseModel):
    """A gold-labeled entity in a dataset."""

    doc_id: str
    mention: str
    type: str
    sentiment: str | None = None


class GoldRelation(BaseModel):
    """A gold-labeled relation between two entities in a document."""

    doc_id: str
    relation_type: str
    head: str
    tail: str


class InputDocument(BaseModel):
    """A document fed to the solution script."""

    doc_id: str
    text: str


class GoldDataset(BaseModel):
    """Gold data prepared from one evaluation dataset."""

    name: str
    entities: list[GoldEntity] = Field(default_factory=list)
    relations: list[GoldRelation] = Field(default_factory=list)
    input_docs: list[InputDocument] = Field(default_factory=list)


class ProducedEntity(BaseModel):
    """An entity produced by the solution."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    mention: str
    type: str
    sentiment: str | None = None


class ProducedRelation(BaseModel):
    """A relation produced by the solution."""

    model_config = ConfigDict(extra="forbid")

    relation_type: str
    head: str
    tail: str


class SolutionDocument(BaseModel):
    """One output record of the solution for a document.

    Unknown fields are rejected: a solution emitting fields outside the
    contract (constitution spec §3) produces output that fails to parse,
    degrading its metrics to failed_to_compute.
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    entities: list[ProducedEntity] = Field(default_factory=list)
    relations: list[ProducedRelation] = Field(default_factory=list)


class SolutionOutput(BaseModel):
    """The parsed output of the solution script for one dataset."""

    model_config = ConfigDict(extra="forbid")

    documents: list[SolutionDocument] = Field(default_factory=list)


class TimingInfo(BaseModel):
    """Wall-clock timing of the solution runs."""

    total_minutes: float = Field(description="Total wall-clock time of all solution runs")
    n_documents: int = Field(description="Total number of documents processed")


class MetricResult(BaseModel):
    """Result of computing a single validation metric."""

    metric_id: str
    computation_status: ComputationStatus
    acceptance_status: AcceptanceStatus | None = None
    computed_value: float | None = None
    error_message: str | None = None


class MetricExpectation(BaseModel):
    """Static expectation attached to a metric by an acceptance criterion."""

    metric_id: str
    expected_value_or_threshold: Any


class ACResult(BaseModel):
    """Result of evaluating a single acceptance criterion."""

    ac_id: str
    status: ACStatus
    metrics_status: dict[str, dict[str, Any]] = Field(
        description="Per-metric results in the validation spec 4.1 schema"
    )


class ValidationResult(BaseModel):
    """Complete result of one validation run."""

    request: ValidationRequest
    ac_results: dict[str, ACResult] = Field(default_factory=dict)
