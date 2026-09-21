# entity-processing-validation

Validation service for the [entity-processing](../entity-processing) SDD project.
It validates how well an implementation of the solution subproject satisfies the
acceptance criteria defined in the validation spec (`.internal/validation-spec.md`).

## Validation metrics

| VM | Metric | Dataset class |
|----|--------|---------------|
| VM1/VM2 | Entity precision / recall | entity-relation |
| VM3/VM4 | Sentiment precision / recall | sentiment |
| VM5/VM6 | Relation precision / recall | entity-relation |
| VM7 | Time per 100 documents (max over the suite's runs) | all entries |
| VM8 | LLM model check (`glm-5.3-flash`) | – |

## Validation suites

A validation suite is a named, AC-complete set of dataset entries
(validation spec §3.3). Two are defined:

| Suite | Entity-relation dataset | Sentiment dataset |
|-------|-------------------------|-------------------|
| `full` | CoNLL04, 288 documents | RuSentNE, 2144 documents |
| `small` | CoNLL04-small, 100 documents | RuSentNE-small, 100 documents |

Suite config lives in `config/suites/<name>.yaml` and dataset entries in
`config/datasets/<entry>.yaml`; a suite is selected with `suite=<name>` and
defaults to the `suite` key of `config/config.yaml`. Adding a variant is a
config change: a new dataset entry (`source`, `sample_size`, `shuffle_seed`,
`class`) plus a suite listing it — no code change.

Subset variants are drawn by a **seeded shuffle** of the source's documents,
never a head slice: CoNLL04's KILL relation appears in only 46 of 288 documents
and in none of the first 100. Subsets are derived at preparation time and are
byte-identical for identical `(source, sample_size, shuffle_seed)`.

## Usage (CLI)

```bash
python scripts/validation_cli.py \
    repo=<clonable link to repo> \
    commit=<commit hash> \
    output_json=<path to output json> \
    solution_overrides="<args separated by whitespaces>" \
    suite=<full|small>
```

## Usage (HTTP service, M2)

```bash
python scripts/validation_service.py port=8456
# POST {"repo": "...", "commit": "...", "solution_overrides": "..."}
```

## Materializing a subset variant

```bash
python scripts/build_subset.py entry=conll04_small output_dir=/tmp/conll04_small
```

Writes the entry's solution input and gold JSONL into `output_dir` for
inspection; no validation run reads this output.

## Development

```bash
# Environment
/home/tony/venvs/entity_processing_validation/bin/pip install -e '.[dev]'

# Linters
./run_linters.sh

# Tests
/home/tony/venvs/entity_processing_validation/bin/python -m pytest
```
