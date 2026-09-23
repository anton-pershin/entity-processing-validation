## M2 HTTP validation service

### 1. Requirement analysis

#### 1.1 Motivation

The validation spec requires an HTTP entrypoint in addition to the existing CLI: a long-running Hydra application must accept the fixed validation request payload and expose the same validation procedure to callers over localhost. M1 provides the reusable `run_validation` orchestrator and CLI, but no `scripts/validation_service.py` or HTTP route.

#### 1.2 Functional requirements

**FR1. Hydra service entrypoint.** `scripts/validation_service.py` is a Hydra application that starts an HTTP server on the configured `port` and host, with the port overridable by a Hydra command-line argument. The service exposes `POST /validate`.

**FR2. Request contract.** `POST /validate` accepts a JSON object with required string fields `repo` and `commit`, plus optional string field `solution_overrides` defaulting to the empty string. The request is converted to the existing `ValidationRequest` model; `output_json` is not required in HTTP mode.

**FR3. Shared validation procedure.** For every valid request, the endpoint invokes the existing `run_validation` orchestrator with the service's configured validation settings and returns its `ValidationResult` serialized as JSON. The HTTP path must not implement a second clone, preparation, runner, metric, acceptance, or reporting procedure.

**FR4. Validation-result failures remain results.** If the solution clone, dataset preparation, solution run, metric computation, or acceptance evaluation fails inside the orchestrator, the endpoint returns the orchestrator's normal result containing the corresponding `failed_to_compute`/`invalid` information rather than converting that solution-level failure into an HTTP transport error.

**FR5. Request errors are HTTP errors.** Malformed JSON, missing required fields, or fields with invalid types are rejected as client errors and do not invoke `run_validation`. An unsupported HTTP method or unknown path is rejected by the web framework.

**FR6. Synchronous request handling.** One HTTP request performs one complete validation run synchronously and the response is sent only after the result has been assembled. No queue, background worker, or second validation process is introduced.

#### 1.3 Non-functional requirements

**NFR1. Reuse and compatibility.** The service uses the same `config/config.yaml` settings and validation models as the CLI, and the existing CLI behavior remains unchanged.

**NFR2. Offline testability.** HTTP tests use a test client and an injected/fake orchestrator; they perform no network access, repository clone, dataset download, LLM call, or real listening socket operation.

**NFR3. Declared dependencies and type safety.** Runtime HTTP dependencies are declared in the project's dependency configuration, new code is type-hinted, and the existing Ruff checks remain applicable.

#### 1.4 Expected behavioural variants

| # | Situation | Expected behaviour |
|---|-----------|--------------------|
| 1 | Service starts with the default configuration | HTTP server listens on the configured default host and port and exposes `/validate` |
| 2 | Service starts with `port=<value>` | HTTP server uses the overridden port |
| 3 | `POST /validate` contains `repo`, `commit`, and no `solution_overrides` | Request is accepted; `solution_overrides` is passed as `""` |
| 4 | `POST /validate` contains all three request fields | All values are passed unchanged to `ValidationRequest` and `run_validation` |
| 5 | `POST /validate` omits `repo` or `commit` | Client error; orchestrator is not called |
| 6 | A request field has a non-string value | Client error; orchestrator is not called |
| 7 | Request body is malformed JSON or not a JSON object | Client error; orchestrator is not called |
| 8 | Valid request and orchestrator returns an accepted/valid result | HTTP success response contains the complete serialized `ValidationResult` |
| 9 | Valid request and orchestrator returns a result with failed metrics/invalid ACs | HTTP success response preserves that result and its failure details |
| 10 | Valid request and orchestrator raises an unexpected service-side exception | HTTP server returns a server error without fabricating a validation result |
| 11 | Request uses an unknown path or unsupported method | Framework-level client error; orchestrator is not called |
| 12 | Two requests arrive sequentially | Each request runs independently with its own `ValidationRequest` and result; no result state leaks between requests |

### 2. Tests

All HTTP tests belong in `tests/test_service.py`. They use FastAPI's in-process test client and monkeypatch the service's orchestrator, so they do not open a real socket and do not clone repositories, fetch datasets, call an LLM, or access the network (NFR2).

**T1. `tests/test_service.py` — valid request mapping and response (FR2, FR3, FR6; rows 3, 4, 8, 12).** Inject a fake `run_validation` that records its `ValidationRequest` and config and returns a `ValidationResult` containing representative AC data. Send a request with all fields and assert HTTP success, unchanged `repo`, `commit`, and `solution_overrides`, no `output_json`, exactly one orchestrator call, and a response JSON equal to the serialized result. Send a second request with a different payload and assert it produces a second independent request and result.

**T2. `tests/test_service.py` — omitted optional overrides (FR2; row 3).** Send only `repo` and `commit`; assert HTTP success and that the orchestrator receives `solution_overrides=""`.

**T3. `tests/test_service.py` — request validation (FR5; rows 5, 6, 7).** Parameterize missing `repo`, missing `commit`, non-string values, malformed JSON, and a non-object JSON body. Assert a client-error status and that the fake orchestrator is never called.

**T4. `tests/test_service.py` — validation failures are returned as results (FR4; row 9).** Make the fake orchestrator return a `ValidationResult` containing a `failed_to_compute` metric and an `invalid` acceptance criterion. Assert HTTP success and preservation of both statuses and error details in the response JSON.

**T5. `tests/test_service.py` — unexpected orchestrator exception (FR3; row 10).** Make the fake orchestrator raise an unexpected exception. Assert the test client receives a server-error response and that the service does not fabricate a `ValidationResult`.

**T6. `tests/test_service.py` — route and method handling (FR1, FR5; row 11).** Send a request to an unknown path and use an unsupported method on `/validate`. Assert framework-level client errors and no orchestrator call. Assert `POST /validate` is registered.

**T7. `tests/test_service.py` — Hydra configuration and startup wiring (FR1; rows 1, 2; NFR1).** Compose the repository's `config/config.yaml`, verify the service's default port/host settings, and invoke the patched server runner with a `port=<value>` Hydra override. Assert the runner receives the configured host and overridden port without starting a real server.

**T8. `tests/test_service.py` — dependency and regression checks (NFR1, NFR3).** Import the service module and compose its Hydra entrypoint using the existing configuration. Run the existing CLI tests unchanged and assert the project's dependency metadata declares the HTTP runtime packages required by the service. Run the full test suite and Ruff checks after implementation.

### 3. Implementation plan

#### 3.1 Implementation repos

`entity-processing-validation`

#### 3.2 Solution design

**HTTP application.** Add `scripts/validation_service.py` with a `create_app(...)` factory that returns a FastAPI application. The factory receives the already-resolved suite entries and the validation run settings, and accepts an injectable `run_validation` callable for offline tests. The `POST /validate` handler validates the JSON body through the existing `ValidationRequest` model, forcing `output_json=None`, invokes the injected/default orchestrator synchronously, and returns the result through FastAPI's JSON serialization. Unexpected orchestrator exceptions are not converted into fabricated validation results.

**Hydra entrypoint.** The module's `main` function uses the existing `config/config.yaml`, resolves `cfg.suite` once at startup with `resolve_suite`, builds the same run configuration as `scripts/validation_cli.py`, and calls `uvicorn.run` with the configured `host` and `port`. The service's suite is therefore fixed for its process lifetime, while every request supplies its own repository, commit, and overrides.

**Configuration and dependencies.** Add explicit `host` and `port` keys to `config/config.yaml`, with localhost and the validation spec's port 8456 as defaults. Add FastAPI and uvicorn to both runtime dependency declarations (`pyproject.toml` and `requirements.txt`); do not add a separate configuration file or modify user settings.

**Tests.** Add `tests/test_service.py`. Use an in-process FastAPI test client and `create_app` with fake run-validation and server-runner callables. Construct representative `ValidationResult` and `MetricResult` Pydantic models rather than exercising clone, dataset, subprocess, or LLM code. Keep the existing CLI entrypoint and tests unchanged.

**Documentation.** Update the existing HTTP usage section in `README.md` with the endpoint URL, request body, response behavior, and configurable port command.

#### 3.3 Todo list

1. [ ] Write `tests/test_service.py` covering T1–T8.
2. [ ] Run the full test suite and ensure the new tests fail for the missing service/dependencies.
3. [ ] Add FastAPI and uvicorn to `pyproject.toml` and `requirements.txt`.
4. [ ] Add `host` and `port` defaults to `config/config.yaml`.
5. [ ] Implement the FastAPI application factory and synchronous `/validate` handler in `scripts/validation_service.py`.
6. [ ] Implement the Hydra startup path: resolve the configured suite, build the existing orchestrator configuration, and invoke uvicorn with Hydra-overridable host and port.
7. [ ] Update `README.md` with the HTTP invocation and request contract.
8. [ ] Run the full pytest suite and Ruff checks; verify the CLI behavior remains unchanged.
9. [ ] Review the final diff for accidental settings, credential, swap, or generated files before committing.

#### 3.4 Modification summary

| File | Action |
|------|--------|
| `scripts/validation_service.py` | New: FastAPI app factory, `/validate` handler, Hydra entrypoint, and uvicorn startup |
| `tests/test_service.py` | New: HTTP contract, error handling, orchestration reuse, startup wiring, and regression tests |
| `config/config.yaml` | Modified: add configurable localhost `host` and default `port: 8456` |
| `pyproject.toml` | Modified: declare FastAPI and uvicorn runtime dependencies |
| `requirements.txt` | Modified: declare FastAPI and uvicorn runtime dependencies |
| `README.md` | Modified: document the HTTP endpoint, payload, response, and port override |
