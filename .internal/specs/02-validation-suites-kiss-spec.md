## Validation suites and dataset subsets

### 1. Requirement analysis

#### 1.1 Motivation

The validation spec (§3.3) defines two validation suites — `full` (CoNLL04: 288 documents, RuSentNE: 2144 documents) and `small` (100 documents of each, drawn by a seeded shuffle) — and requires each suite to cover every acceptance criterion by construction, with the suite selected by name as a property of the validation service invocation. Nothing in the implementation provides suite selection or dataset subsetting: both datasets are always prepared in full, and the only size knob present in the code is a head slice. This spec implements §3.3.

#### 1.2 Functional requirements

**FR1. Suite catalog.** The suite catalog is declarative config: `config/suites/<name>.yaml` files, each mapping the suite's name to the dataset entries it selects. Per the validation spec §3.3 it holds two suites — `full` (entries `conll04`, `rusentne`) and `small` (entries `conll04_small`, `rusentne_small`) — and both cover every dataset class, which is what FR3 enforces.

**FR2. Dataset entries as independent config files.** Dataset entries are one file per entry under `config/datasets/` (`conll04`, `conll04_small`, `rusentne`, `rusentne_small`), replacing the current single file with both datasets as keys. Each entry declares its `name`, `source`, `sample_size`, `shuffle_seed` and `class`; `sample_size: null` means the entire source.

**FR3. Suite resolution and validation.** A suite is selected by name, held in the service's own Hydra config under the key `suite`. Resolution reads the named suite file, resolves each entry name to its dataset entry config file, and rejects a suite that does not select exactly one entry per dataset class. A rejected suite raises before any clone, fetch or solution run and before any acceptance criterion is evaluated.

**FR4. Subset preparation by seeded shuffle.** When an entry's `sample_size` is set, preparation shuffles the source's documents with `shuffle_seed` (Python `random.Random(seed).shuffle`) and takes the first `sample_size`. For CoNLL04 the shuffled universe is the source's 288 document records; relations are kept when both endpoint entities survive the cut, so a subset never acquires a relation whose endpoints it does not contain. A head slice is not an acceptable substitute: KILL occurs in only 46 of the source's 288 documents and in none of its first 100, so a head-sliced sample would drop one of the five relation types from VM5/VM6 entirely. For RuSentNE the shuffled universe is the source's unique-sentence sequence (2144 sentences), not the raw row sequence, so one sentence remains one document. `sample_size` is clamped to the source document count: an oversized request yields the whole source. Identical (source, `sample_size`, `shuffle_seed`) yields identical prepared output across runs, machines and invocations.

**FR5. Per-entry preparation and runs.** Each entry of the resolved suite is prepared and run independently: its input JSONL, gold JSONL, solution output and any temporary run artifacts are named after that entry, so no artifact of one entry can be read or overwritten by another, and a failure in one entry's preparation or run degrades only the metrics that read that entry — the remaining entries are still prepared, run and measured. Stale artifacts of a previous run are swept from the workdir for every entry of the suite, not for a fixed pair of dataset names.

**FR6. Suite selection in the CLI entrypoint.** `scripts/validation_cli.py` accepts `suite=<name>` as a Hydra override (validation spec §4.1) and passes the suite's resolved dataset entries into the orchestrator for that invocation; the suite defaults to the value of the `suite` key in `config/config.yaml`. The HTTP entrypoint of validation spec §4.1 takes the same parameter and resolves it once at startup; that entrypoint does not exist yet (its milestone is unimplemented) and is out of scope for this spec.

**FR7. Subset materialization script.** `scripts/build_subset.py` is a Hydra entrypoint that materializes one dataset entry's prepared input and gold JSONL into an output directory (`entry=<name>` and `output_dir=<path>`, both overridable). It prepares the entry exactly as a validation run does, so it reuses the shared raw-dataset cache but never removes or overwrites an entry already cached, and it never touches the run workdir. No validation run reads its output.

#### 1.3 Non-functional requirements

**NFR1. Offline unit tests.** Suite resolution, subset selection and per-entry orchestration are covered by tests using a locally injected fetch function and a bundled mini-fixture source; the suite of tests added here performs no network access.

**NFR2. Type safety.** New and modified code carries Python type hints; inter-stage data crosses component boundaries as Pydantic models, enforced by linters.

**NFR3. Determinism.** Subset selection depends only on the entry's `source`, `sample_size` and `shuffle_seed` — never on wall-clock time, filesystem order or process state — so `small` prepares identically on every run.

#### 1.4 Expected behavioural variants

| # | Situation | Expected behaviour |
|---|-----------|--------------------|
| 1 | `suite=full` | Both full entries are prepared and run; every metric is computed from its own entry |
| 2 | `suite=small` | Both subset entries are prepared and run on 100 documents each |
| 3 | `suite=<unknown name>` | Configuration error before clone/fetch/run |
| 4 | Suite file selects only one dataset class | Configuration error before clone/fetch/run (validation spec §3.3) |
| 5 | Suite file selects two entries of the same dataset class | Configuration error before clone/fetch/run |
| 6 | Suite entry name has no dataset entry file | Configuration error naming the missing entry |
| 7 | `sample_size: null` | Whole source prepared, all documents in source order |
| 8 | `sample_size` larger than the source's document count | Whole source prepared |
| 9 | Entry has `sample_size` < source count | Exactly `sample_size` documents, selected by the seeded shuffle |
| 10 | Same entry prepared twice in one process | Identical documents, in identical order |
| 11 | Subset cut splits a CoNLL04 relation's endpoints | The relation is dropped from the subset's gold set; no dangling endpoint |
| 12 | RuSentNE prepared with `sample_size` < sentence count | `sample_size` unique sentences; no sentence truncated across documents |
| 13 | One entry's preparation raises | The other entry's metrics are still computed; only the failing entry's metrics become `failed_to_compute` |
| 14 | One entry's solution run fails or times out | As row 13, for the run stage |
| 15 | Any suite with two entries | Every metric is computed from documents of exactly one entry; no metric mixes two entries |
| 16 | `build_subset.py entry=conll04_small output_dir=<path>` | Input and gold JSONL written under `<path>`; no cached raw dataset removed or overwritten; run workdir untouched |
| 17 | `build_subset.py` invoked twice with the same arguments | Byte-identical output files |

### 2. Tests

All tests are added to the existing offline suite under `tests/` and use injected local fetchers instead of the network (NFR1).

**T1. `tests/test_suites.py` — suite resolution (FR1, FR2, FR3).** A tmpdir config tree with a valid two-class suite, a suite name with no suite file, a one-class suite, a two-entries-one-class suite and a suite naming a missing entry. Asserts: the valid suite resolves to the two entry names; each of the four broken requests raises `SuiteConfigError` before any clone/fetch/run (rows 3, 4, 5, 6).

**T2. `tests/test_suites.py` — actual catalog (FR1).** Composing the repository's own `config/suites/{full,small}.yaml` against the real `config/datasets/` tree, `full` resolves to `conll04` + `rusentne` and `small` to `conll04_small` + `rusentne_small`, each covering both dataset classes (rows 1, 2).

**T3. `tests/test_datasets.py` — seeded shuffle subsetting (FR4).** On a bundled mini source: `sample_size: null` yields the whole source (row 7); an oversized `sample_size` yields the whole source (row 8); a smaller `sample_size` yields exactly that many documents (row 9); two runs of the same entry in one process yield identical (doc_id, text) sequences (row 10, NFR3); a CoNLL04 subset whose cut orphans relation endpoints contains no relation with a non-subset endpoint (row 11); a RuSentNE subset contains `sample_size` unique sentences by `doc_id` (row 12).

**T4. `tests/test_core.py` — per-entry orchestration (FR5).** Two stub entries, one of which raises during preparation: the other entry's metrics are computed and only the failing entry's metrics are `failed_to_compute` (row 13); the same with a failing solution run (row 14); with both entries succeeding, each metric equals the value computed from its own entry's gold and output, with no cross-entry mixing (row 15).

**T5. `tests/test_cli.py` — suite selection through the CLI (FR6).** `validation_cli.py suite=<name>` resolves that suite and passes its entries into the orchestrator (a fake orchestrator records the suite it received); with no override, the `suite` value from `config/config.yaml` is used (rows 1, 2).

**T6. `tests/test_build_subset.py` — materialization script (FR7).** `entry=conll04_small output_dir=<tmp>` writes the entry's input and gold JSONL under the output directory, creates the directory when absent, leaves the run workdir listing unchanged and removes or overwrites no cached raw dataset (row 16), and produces byte-identical files when invoked twice (row 17).

**T7. `tests/test_datasets.py` — full preparation unchanged (regression).** With an injected local fetch function, preparing the `full` entries reproduces the current parsing results (same entity/relation/input-document counts and ordering), so the existing parsing tests keep their fixtures untouched (row 1).

### 3. Implementation plan

#### 3.1 Implementation repos

`entity-processing-validation`

#### 3.2 Solution design

**Config.** `config/config.yaml` gains `suite: full` and loses `datasets: conll04` from `defaults`. `config/datasets/` becomes four files — `conll04.yaml`, `conll04_small.yaml`, `rusentne.yaml`, `rusentne_small.yaml` — one per entry, each using the `# @package datasets.<name>` header idiom the current single file already applies to its two keys. Every entry declares `name`, `source`, `sample_size`, `shuffle_seed` and `class`. `config/suites/{full,small}.yaml` declares `name` and `entries` only; an entry's dataset class comes from its own `class` key, never from a positional convention in the suite file.

**Models.** `validation/datasets/base.py` extends `DatasetConfig` with `source`, `sample_size`, `shuffle_seed` and `class` (an enum `DatasetClass.ENTITY_RELATION | DatasetClass.SENTIMENT`), keeping `name`. A new `SuiteConfig` model (`name`, `entries: list[str]`) lives next to it. `sample_size: null` stays the "whole source" marker.

**Suite resolution.** New module `validation/suites.py`: `resolve_suite(name, config_dir) -> list[ResolvedEntry]` where `ResolvedEntry` is a Pydantic model carrying the entry name, its `DatasetConfig` and its dataset class. It reads `<config_dir>/suites/<name>.yaml`, loads each named entry from `<config_dir>/datasets/<entry>.yaml`, then enforces the two structural rules: both dataset classes present, at most one entry per class. Any violation raises `SuiteConfigError`, whose message names the suite, the entry or the missing class.

**Subsetting.** A shared helper in `validation/datasets/base.py`, applied to a document sequence with an explicit seed: shuffle with `random.Random(seed).shuffle`, then slice `[:sample_size]`. CoNLL04 applies it to its 288 raw document records *before* entity/relation conversion, so relation endpoint indices still refer to surviving entities and no dangling relation can be produced. RuSentNE applies it to its unique-sentence sequence after the existing dedup pass, so the subset is `sample_size` whole sentences rather than a truncated copy of the row stream.

**Orchestration.** `validation/core.py` accepts the resolved entries as a list of `ResolvedEntry` values in its run config, replacing the module-level `DATASET_PREPARERS` registry and the `dataset_configs` dict. Per-entry preparation stays injectable through the existing `dataset_fns` parameter, keyed by entry name, which is what the tests drive. Entry names drive the workdir sweep, the artifact paths and the metric stage's existing per-entry scoping, so a failure is confined to one entry. `DatasetConfig.max_docs` and its two read sites are deleted.

**Entrypoints.** `scripts/validation_cli.py` resolves the suite from `cfg.suite` and passes the entries into `run_cfg`. `scripts/build_subset.py` resolves the named entry, prepares it with the shared subsetting helper and writes input/gold JSONL into `output_dir`, printing the two paths. The HTTP entrypoint is untouched here; it will resolve its suite once at startup when its own milestone is implemented.

#### 3.3 Todo list

1. [ ] Write the tests (T1–T7)
2. [ ] Run all the tests and ensure that they fail
3. [ ] Split `config/datasets/` into one file per entry and add `config/suites/{full,small}.yaml` (FR1, FR2)
4. [ ] Extend `DatasetConfig` and add `SuiteConfig` + `DatasetClass` (FR2)
5. [ ] Implement `validation/suites.py` with the two structural rules (FR3)
6. [ ] Implement seeded-shuffle subsetting in both dataset modules (FR4)
7. [ ] Convert `validation/core.py` to per-entry preparation, runs and sweep; delete `max_docs` (FR5)
8. [ ] Wire `suite=` through the CLI entrypoint (FR6)
9. [ ] Implement `scripts/build_subset.py` (FR7)
10. [ ] Run `run_linters.sh` (ruff check + ruff format --check, NFR2) and the full test suite
11. [ ] Update `README.md` with suite selection and the subset script

#### 3.4 Modification summary

| File | Action |
|------|--------|
| `config/config.yaml` | Modified: add `suite: full`, drop `datasets: conll04` from `defaults` |
| `config/datasets/conll04.yaml` | Modified: entry-only, `@package datasets.conll04`, add `source`/`sample_size`/`shuffle_seed`/`class`, drop `max_docs` |
| `config/datasets/conll04_small.yaml` | New: `sample_size: 100` + `shuffle_seed` |
| `config/datasets/rusentne.yaml` | Modified: RuSentNE entry extracted from the current shared file |
| `config/datasets/rusentne_small.yaml` | New: `sample_size: 100` + `shuffle_seed` |
| `config/suites/full.yaml` | New: entries `conll04`, `rusentne` |
| `config/suites/small.yaml` | New: entries `conll04_small`, `rusentne_small` |
| `validation/datasets/base.py` | Modified: `DatasetClass`, extended `DatasetConfig`, `SuiteConfig`, seeded-shuffle helper |
| `validation/suites.py` | New: suite resolution and validation |
| `validation/core.py` | Modified: per-entry prep/run/sweep, suite in run config, `max_docs` removed |
| `validation/datasets/conll04.py` | Modified: subsetting before conversion, seeded shuffle, `max_docs` removed |
| `validation/datasets/rusentne.py` | Modified: subsetting on the unique-sentence sequence, `max_docs` removed |
| `scripts/validation_cli.py` | Modified: `suite=` override, resolve and pass entries |
| `scripts/build_subset.py` | New: materialize one entry's input/gold JSONL |
| `tests/test_suites.py` | New: T1, T2 |
| `tests/test_build_subset.py` | New: T6 |
| `tests/test_cli.py` | New: T5 |
| `tests/test_datasets.py` | Modified: T3, T7 |
| `tests/test_core.py` | Modified: T4 |
| `README.md` | Modified: suite selection and `build_subset.py` usage |
