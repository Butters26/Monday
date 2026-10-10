# Pre-production reasoning and memory copies

These files are isolated working copies. The live Mercy/Monday modules are not
modified or routed through this directory.

- `reasoning.py` contains a provenance/evidence guard API for callers to run
  before realization.
- `notus.py` is an isolated copy of the durable-memory module. Its SQLite
  adapter returns persistent memory IDs on store and recall.
- `test_grounding_guard.py` runs an isolated SQLite Notus → reasoning guard →
  realization-entity-check flow without importing live Thalamus or routing
  anything through Mercy/Monday.
- `data_checker.py` provides provenance/count validation, protected schema
  filtering, and configured output phrase checks; `test_data_checker.py` covers
  those checks.
- `run_environment.py` starts the isolated environment with JSON-line commands
  or a disposable end-to-end demo; `test_environment.py` covers both startup
  modes.

Run the complete temporary demonstration with:

```sh
python pre-production/run_environment.py --demo
```

Start the interactive harness with:

```sh
python pre-production/run_environment.py
```

The interactive process accepts one JSON object per line. Supported `type`
values are `health`, `store`, `recall`, `evaluate`, `validate_output`, and
`sanitize_schema`. It uses a separate SQLite database under
`~/.local/state/monday-preproduction` by default; set
`MONDAY_PREPRODUCTION_RUNTIME_DIR` or pass `--database` to choose another
isolated location. It does not start or connect to the live daemon.

The harness supplies evidence stances and entity metadata explicitly because
Notus stores memories; it does not determine whether a memory supports or
contradicts a proposition. The guard checks that supplied metadata contract;
it cannot independently verify that a record is true, that stance labels are
correct, or that a language realizer extracted every entity correctly. It
therefore reports `GROUNDED`, not `VERIFIED`. Realization is represented only
by an entity-list check, not a running language model.

The DataChecker validates confidence against the supplied support ratio instead
of banning particular numeric values: a value by itself cannot establish
whether it was hardcoded or calculated. Its schema and phrase checks are utility
functions and are not installed as a continuous monitor on the live pipeline.
