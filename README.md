# entity-processing-validation

Validation service for the [entity-processing](../entity-processing) SDD project.
It validates how well an implementation of the solution subproject satisfies the
acceptance criteria defined in the validation spec (`.internal/validation-spec.md`).

## Validation metrics

| VM | Metric |
|----|--------|
| VM1/VM2 | Entity precision / recall (CoNLL04) |
| VM3/VM4 | Sentiment precision / recall (RuSentNE) |
| VM5/VM6 | Relation precision / recall (CoNLL04) |
| VM7 | Time per 100 documents |
| VM8 | LLM model check (`glm-5.3-flash`) |

## Usage (CLI)

```bash
python scripts/validation_cli.py \
    repo=<clonable link to repo> \
    commit=<commit hash> \
    output_json=<path to output json> \
    solution_overrides="<args separated by whitespaces>"
```

## Usage (HTTP service, M2)

```bash
python scripts/validation_service.py port=8456
# POST {"repo": "...", "commit": "...", "solution_overrides": "..."}
```

## Development

```bash
# Environment
/home/tony/venvs/entity_processing_validation/bin/pip install -e '.[dev]'

# Linters
./run_linters.sh

# Tests
/home/tony/venvs/entity_processing_validation/bin/python -m pytest
```
