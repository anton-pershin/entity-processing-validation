## entity-processing validation spec

### 1. Repo structure

#### 1.1 Solution subproject management repo

`entity-processing`

#### 1.2 Validation subproject implementation repos

`entity-processing-validation`

### 2. Validation metrics

**VM1. Entity precision.** Over all entities produced by the solution (on the entity-relation dataset of the validation suite in use, §3.3), the fraction whose (mention, type) pair matches a gold entity of the same dataset by exact string match of the mention and equality of the type. Returns a value from 0 to 1.

**VM2. Entity recall.** Over all gold entities of the validation suite's entity-relation dataset (§3.3), the fraction matched by a produced entity with the same (mention, type). Returns a value from 0 to 1.

**VM3. Sentiment precision.** Over all produced entities carrying a sentiment label (on the sentiment dataset of the validation suite in use, §3.3), the fraction whose sentiment equals the gold sentiment of the matching gold entity (matching per VM1/VM2). Returns a value from 0 to 1.

**VM4. Sentiment recall.** Over all gold entities carrying a gold sentiment label in the validation suite's sentiment dataset (§3.3), the fraction whose gold sentiment equals the sentiment of a matching produced entity. Returns a value from 0 to 1.

**VM5. Relation precision.** Over all relations produced by the solution (on the entity-relation dataset of the validation suite in use, §3.3), the fraction whose (relation_type, head mention, tail mention) matches a gold relation by exact string match of both mentions and equality of the relation type. Relation head/tail in the solution output are entity ids (constitution spec §3); the validation service resolves each id through the solution's own `entities` list of the same document to the mention string(s) before matching. Relations with unresolvable endpoint ids count as false positives (against precision only). Returns a value from 0 to 1.

**VM6. Relation recall.** Over all gold relations of the validation suite's entity-relation dataset (§3.3), the fraction matched by a produced relation with the same (relation_type, head mention, tail mention). Returns a value from 0 to 1.

**VM7. Time per 100 docs.** Wall-clock time of a solution run (in minutes) divided by that run's number of input documents divided by 100. Computed per dataset entry's run of the validation suite; the metric value is the maximum over the suite's runs (§4.1).

**VM8. LLM model check.** True iff the solution's Hydra configuration as invoked by the validation service (the config inspected in the cloned repo at the specified commit) resolves to the model `glm-5.3-flash`; False otherwise.

| FR/NFR | VMs |
|--------|-----|
| FR1 | VM1, VM2 |
| FR2 | VM3, VM4 |
| FR3 | VM5, VM6 |
| NFR1 | VM7 |
| NFR2 | VM8 |

Each metric reads exactly one dataset class of the validation suite in use (§3.3): VM1, VM2, VM5 and VM6 read its entity-relation dataset; VM3 and VM4 read its sentiment dataset; VM7 aggregates the timing of every run of the suite; VM8 is dataset-independent. Which variant of a class a suite selects is a property of the suite, never of the metric.

### 3. Acceptance criteria

**AC1. Accurate Entity Extraction**: VM1 > 0.8 and VM2 > 0.8

**AC2. Accurate Sentiment Analysis**: VM3 > 0.8 and VM4 > 0.8

**AC3. Accurate Relation Extraction**: VM5 > 0.6 and VM6 > 0.6

**AC4. Satisfactory Time Performance**: VM7 < 10 minutes

**AC5. Correct LLM model**: VM8 = True

| FR/NFR | ACs |
|--------|-----|
| FR1 | AC1 |
| FR2 | AC2 |
| FR3 | AC3 |
| NFR1 | AC4 |
| NFR2 | AC5 |

The validation metrics are computed on two datasets: an open-source dataset **CoNLL04** (entities and their relations) and an open-source dataset **RuSentNE** (sentiment analysis). Each is used either in full or as a 100-document subset, per the selected validation suite (§3.3).

#### 3.1. CoNLL04

Source: https://github.com/lavis-nlp/spert/tree/master (`scripts/fetch_datasets.sh`)

Results are inspected for:
  - Entity precision and recall (VM1, VM2)
  - Relation precision and recall (VM5, VM6)

**Note:** classical dataset for NER + relations is TACRED (and its derivatives) but it is under the fee wall. Another large-scale dataset is FewRel (and its derivatives), it is freely available. However, it is too diverse (it is featured by a huge number of relations which has to be grouped for our purposes). This justifies why we selected CoNLL04.

**Subset variant.** The dataset has a small variant: the same source reduced to `sample_size` documents drawn by a seeded shuffle (§3.3), holding on average 147 relations over 100 documents (sd ≈ 10). A seeded shuffle is mandatory here, not a head slice — KILL occurs in only 46 of the source's 288 documents and in none of its first 100, so a head-sliced small variant would silently drop one of the five relation types from VM5/VM6 entirely.

#### 3.2. RuSentNE

Source: https://github.com/dialogue-evaluation/RuSentNE-evaluation

Results are inspected for:
  - Sentiment precision and recall (VM3, VM4)

Gold entity mentions are taken from the dataset's own entity list; mentions that are common nouns rather than named entities are filtered out from the gold set before metric computation.

**Note:** this is a dataset with Russian news. Strictly speaking, many entities there are just nouns rather than named entities but it is feasible to filter them out.

**Note (known limitation, accepted by design):** the output contract (constitution spec §3) defines entities by mention strings without character offsets, so all entity- and sentiment-based matching is exact mention-string matching. A degenerate solution that flags every gold mention string appearing verbatim in the document text can score substantial recall without genuine extraction. This is accepted as a property of the contract; if gaming resistance becomes necessary, the contract must be amended to require character offsets (a constitution spec revision, not a validation-side change).

**Subset variant.** The same source reduced to `sample_size` documents drawn by a seeded shuffle (§3.3): 100 of the source's 2144 sentences, holding on average 95 gold entities (sd ≈ 7) after the common-noun filter.

#### 3.3. Validation suites and dataset subsets

Two validation suites are defined, and by construction each covers every acceptance criterion:

| Suite | Entity-relation dataset (§3.1) | Sentiment dataset (§3.2) |
|-------|-------------------------------|--------------------------|
| `full` | CoNLL04, all 288 documents | RuSentNE, all 2144 documents |
| `small` | CoNLL04-small, 100 documents | RuSentNE-small, 100 documents |

- **A validation suite is a named set of dataset variants that covers all ACs by definition.** Suites are defined deliberately by us and are never partial: a suite that left a metric family unmeasured would leave the corresponding acceptance criteria unmeasurable, which no suite is allowed to do. Suites are declared under `config/suites/` and selected by name (`suite=full` or `suite=small`); the request payload is unchanged (constitution spec §3 fixes it), so the suite is a property of the validation service invocation, not of the request.
- **A variant is a dataset entry under `config/datasets/`** with `source`, `sample_size` and `shuffle_seed`. `sample_size: null` means all documents of the source; `sample_size: 100` is that source's small variant. Additional variants (other sizes, other seeds) are pure config additions — no code change.
- **Selection is a seeded shuffle, never a head slice**: shuffle the source's documents with `shuffle_seed`, then take the first `sample_size`. Identical (source, `sample_size`, `shuffle_seed`) yields a byte-identical subset across runs, machines and dataset orderings. The universe being shuffled is the source's own document sequence (CoNLL04's 288 spert documents; RuSentNE's 2144 unique sentences).
- **The subset is derived at preparation time** — nothing is committed, and no subset artifact is required for a validation run. `scripts/build_subset.py` materializes a variant's input/gold JSONL into a chosen output directory for inspection and reuse; the validation run does not depend on it.
- **A `small` run is a deliberately imperfect, faster pre-check** (~2.9× on the entity-relation family, ~21× on the sentiment family; the thresholds of §3 are the same for both suites). Its sampling noise is documented, not compensated: a 100-document subset holds on average 147 CoNLL04 relations (binomial SE ≈ 3.3 pp at p = 0.8; sd ≈ 10 relations across seeds) and 95 RuSentNE entities (SE ≈ 4.1 pp; sd ≈ 7), so a small-suite verdict may differ from the full-suite verdict on a borderline implementation. Measured over 500 seeds, every 100-document sample retained all four entity types and all five relation types, so the loss of a whole type — the failure mode a head slice causes — does not occur in practice.

### 4. Overall validation service design

#### 4.1 High-level design

The validation service is a hydra-backed repository following the same repo rules as the solution subproject: executable Hydra entrypoints in `scripts/`, all parameters configurable via Hydra YAML configs in `config/` (no hardcoded values), type-hinted code enforced by linters.

Any validation run proceeds through the following stages:

```mermaid
flowchart TD
    subgraph Entry["Entry points (Hydra apps)"]
        C["scripts/validation_cli.py"]
        H["scripts/validation_service.py (HTTP POST)"]
    end

    subgraph Prep["Preparation"]
        P0["suite.py: resolve the selected validation suite<br/>(suite name -> dataset entries + subset params)"]
        P1["repo.py: clone solution repo at commit"]
        P2["datasets/: fetch each dataset entry of the suite and convert it<br/>to gold JSONL (seeded shuffle + sample_size for subset variants)"]
        P3["Build solution input JSONL + type list args"]
    end

    subgraph Run["Run solution"]
        R["runner.py: run scripts/extract_entities.py once per dataset entry<br/>with input=, output=, type lists and solution_overrides;<br/>measure wall-clock time"]
    end

    subgraph Measure["Compute metrics"]
        M1["metrics/entity.py: VM1, VM2"]
        M2["metrics/sentiment.py: VM3, VM4"]
        M3["metrics/relation.py: VM5, VM6"]
        M4["VM7: wall-clock time of the runs"]
        M5["metrics/llm_check.py: VM8 (resolve effective Hydra config of the solution)"]
    end

    subgraph Decide["Acceptance and reporting"]
        A1["acceptance.py: evaluate AC1-AC5 statuses"]
        A2["reporting.py: assemble result JSON"]
    end

    C --> P0
    H --> P0
    P0 --> P1 --> P2 --> P3 --> R
    R --> M1 & M2 & M3 & M4 & M5
    M1 & M2 & M3 & M4 & M5 --> A1 --> A2
    A2 --> O1["output_json file (CLI)"]
    A2 --> O2["HTTP response (service)"]
```

Both entry points provide the same validation procedure, and both take the validation suite from their own Hydra configuration (`suite=full|small`, §3.3):
1. CLI
  - There should be an executable script `validation_cli.py` which a user/agent would run via `python validation_cli.py repo=<clonable link to repo> commit=<commit hash> output_json=<path to output json> solution_overrides="<args separated by whitespaces>" suite=<full|small>` where `repo` and `commit` point at the solution implementation to validate, `output_json` points at the output file where the acceptance results will be saved to (see the json format in the "HTTP service" part), `solution_overrides` points at the arguments to be used to run the solution, and `suite` selects the validation suite of §3.3.
2. HTTP service
  - There should be an executable script `validation_service.py` which a user would run via `python validation_service.py port=<port> suite=<full|small>` expecting that it will listen to the specified port (its suite is fixed at startup, since the payload below is fixed by the constitution spec §3) and accept HTTP POST requests with a json payload `{"repo": "<clonable link to repo>", "commit": "<commit hash>", "solution_overrides": "<args separated by whitespaces>"}`. The expected answer is a json 
```
{
  "AC1": {
    "status": "<accepted, valid or invalid>",
    "metrics_status": {
      "VM1": {
        "computation_status": "<computed or failed_to_compute>",
        "acceptance_status": "<accepted or rejected>",
        "computed_value": <computed metric value if computation_status == computed and null otherwise>,
        "expected_value_or_threshold": "<expected value or threshold based on the acceptance criterion condition>",
        "error_message": "<null if computation_status == computed and the actual error message otherwise>"
      },
      "VM2": ...,
      "VM3": ...
    }
  },
  "AC2": ...,
  "AC3": ...
}
```
Here is an explanation of the acceptance criterion status:
- status "accepted" means that all the criterion metrics have acceptance_status "accepted" 
- status "valid" means that all the criterion metrics have computation_status "computed" and at least one has acceptance_status "rejected"
- status "invalid" means that at least one criterion metric has computation_status "failed_to_compute"

Behavioral rules:

- **Hydra configuration**: both entrypoints are Hydra apps. All service parameters (port, working directory, suite selection, dataset entries, fetch behavior, timeouts) are configurable via Hydra YAML configs under `config/`; credentials and endpoints, if needed, go to `config/user_settings/`.
- **Validation suite selection**: as specified in §3.3 — a suite is named in the service's own Hydra configuration, resolves to one dataset entry per dataset class, and an incomplete suite is a configuration error that stops the run before it starts.
- **Runs, one per dataset entry of the suite**: the runner executes `scripts/extract_entities.py` once per dataset entry of the resolved suite against the same clone of the solution repo (per the invocation contract in the constitution spec §3: hydra-style `input=`, `output=` and the three type-list arguments). VM7 is computed as the maximum over per-entry values: for each entry's run, wall-clock time divided by that entry's document count divided by 100; the criterion uses the slowest run.
- **VM8**: the runner resolves the effective Hydra configuration of the solution (static config composed with the invocation arguments, including `solution_overrides`), e.g. via the solution's own config composition (`--cfg job` or equivalent), and reads the model field.
- **Failure handling**: if the solution script exits with a non-zero code, produces unparseable output, or dataset preparation fails, all affected metrics get computation_status `failed_to_compute` (making the corresponding criteria `invalid`), with the error message propagated to `error_message`.
- **Run directory**: each validation run works in a self-contained working directory (clone, datasets, solution output, intermediate artifacts) configured via Hydra, so runs are reproducible and parallelizable.

#### 4.2 Core components

Repository layout (python modules):

```
entity-processing-validation/
├── pyproject.toml
├── requirements.txt
├── requirements_dev.txt
├── run_linters.sh
├── config/
│   ├── config.yaml                # defaults: port, workdir, suite, dataset paths, timeouts
│   ├── datasets/conll04.yaml      # one file per dataset entry: source, fetch params,
│   │                              # gold conversion params, sample_size, shuffle_seed
│   ├── datasets/conll04_small.yaml
│   ├── datasets/rusentne.yaml
│   ├── datasets/rusentne_small.yaml
│   ├── suites/                    # one file per validation suite: name -> dataset entries
│   │   ├── full.yaml              # conll04 + rusentne
│   │   └── small.yaml             # conll04_small + rusentne_small
│   └── user_settings/             # credentials/endpoints if needed (gitignored)
├── validation/
│   ├── __init__.py
│   ├── base.py                    # Pydantic models: ValidationRequest, GoldDataset, SolutionOutput, MetricResult, ACResult, ValidationResult
│   ├── core.py                    # orchestrator: request -> repo prep -> dataset prep -> run -> metrics -> acceptance -> result
│   ├── repo.py                    # clone/checkout of the solution repo at the given commit
│   ├── suites.py                  # resolve a suite name -> dataset entries; reject incomplete suites
│   ├── datasets/
│   │   ├── base.py                # dataset preparation interface (incl. seeded-shuffle subsetting)
│   │   ├── conll04.py             # fetch the spert-hosted JSON + convert to gold JSONL
│   │   └── rusentne.py            # fetch + convert to gold JSONL (entity filter included)
│   ├── runner.py                  # run scripts/extract_entities.py in the cloned repo; measure wall-clock
│   ├── metrics/
│   │   ├── base.py                # metric interface over (gold dataset, solution output)
│   │   ├── entity.py              # VM1, VM2
│   │   ├── sentiment.py           # VM3, VM4
│   │   ├── relation.py            # VM5, VM6
│   │   └── llm_check.py           # VM8
│   ├── acceptance.py              # AC1-AC5: metric values + thresholds -> statuses
│   └── reporting.py               # assemble the result JSON (schema above)
├── scripts/
│   ├── validation_cli.py          # Hydra entrypoint (CLI mode)
│   ├── validation_service.py      # Hydra entrypoint (HTTP mode)
│   └── build_subset.py            # Hydra entrypoint: materialize a subset variant's JSONL for inspection
└── tests/
```

Notes on conventions:

- **Types**: request/response and inter-stage data are Pydantic models defined in `validation/base.py`; no plain dicts or lists cross component boundaries.
- **Component interface**: pipeline stages are `Function[InputT, OutputT]` subclasses (per the mourat architectural invariant), keeping stages independently usable and composable; metric functions in `metrics/` map to VMs (grouped one module per requirement).
- **Independence**: each validation run is self-contained in its configured working directory; no state is shared between runs except through explicit config.

Implementation details of key components:

- **`scripts/validation_service.py`** — HTTP host. Implemented with **FastAPI + uvicorn**: the script is a Hydra app whose `port` override is passed to `uvicorn.run(app, host="localhost", port=...)`; the app exposes a single `POST /validate` endpoint that accepts the json payload, converts it to `ValidationRequest`, runs the same orchestrator (`validation/core.py`) as the CLI, and returns the result JSON. Validation runs triggered by HTTP requests are executed synchronously per request (one request = one full validation run); no job queue or background workers unless a KISS spec adds them later.
- **`validation/runner.py`** — sandboxed execution of the solution script.
  - **Environment**: each validation run creates an isolated **venv** in the run's working directory, installs the solution repo's dependencies from its `requirements.txt`/`pyproject.toml` into it (the venv is created with the system Python, packages installed via pip from the solution's own dependency declarations), and runs `scripts/extract_entities.py` with that venv's interpreter. This guarantees the solution's dependencies never leak into the validation service's environment and different solution commits are isolated from each other. The venv is temporary and is deleted after the validation run.
  - **Execution**: the script is launched as a subprocess (`subprocess.run`) with: cwd = the cloned solution repo, env = the venv's environment, timeout from the Hydra config (a hard upper bound well above the NFR1 threshold so that a hanging solution fails with `failed_to_compute` rather than blocking the service), and stdout/stderr captured for the `error_message` on failure. No network isolation or containerization is assumed at this stage — the solution legitimately needs network access to call the LLM API; confinement (e.g. Docker) is out of scope unless a future spec requires it.

### 5. Roadmap

The implementation is organized as two milestones. M1 delivers the full validation procedure behind the CLI; M2 adds the HTTP service on top of the already working pipeline.

| ID | Name | Status | Expected result | Duration | Strong scaling efficiency |
|----|------|--------|-----------------|----------|---------------------------|
| M1 | CLI implementation | Done | Repository scaffold (`pyproject.toml`, `requirements*.txt`, `run_linters.sh`, Hydra `config/`). Dataset preparation for CoNLL04 and RuSentNE (fetch + gold JSONL conversion). Solution runner (venv sandbox, subprocess execution, timing). Metrics VM1–VM8 and acceptance criteria AC1–AC5 evaluation. `scripts/validation_cli.py` validating a solution repo end-to-end from the command line, producing the result JSON. | 2 | 0.5 |
| M2 | HTTP service implementation | To do | `scripts/validation_service.py` exposing the same validation procedure via HTTP (FastAPI + uvicorn, `POST /validate`), reusing the M1 orchestrator unchanged. | 0.5 | 0.8 |

```mermaid
flowchart TD
  M1 --> M2
```
