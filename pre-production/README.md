# Pre-production reasoning and memory copies

These files are isolated working copies. The live Mercy/Monday modules are not
modified or routed through this directory.

- `reasoning.py` contains a provenance/evidence guard API for callers to run
  before realization.
- `notus.py` is an unchanged copy of the current durable-memory module.
- `test_grounding_guard.py` exercises the guard without importing the live
  Thalamus.

The guard requires callers to provide Notus records with IDs, evidence stances,
and entity metadata. It checks that metadata contract; it cannot independently
verify that a record is true, that stance labels are correct, or that a language
realizer extracted every entity correctly. It therefore reports `GROUNDED`,
not `VERIFIED`.
