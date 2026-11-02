# Install the source evaluator

Follow [the root README](../../../README.md) and [setup](../../SETUP.md) from the source root. Use Windows, Python3.12 and a fresh private data directory. No database, credential, model or runtime profile is supplied. This is source preparation, not deployment or full functional acceptance.

The finite packager and source inventory are included. `python -B scripts/setup_evaluator.py --destination docs/delivery/waves30/exports/new-evaluator01` creates a new local ZIP only; do not overwrite a destination. A rebuild from this public derivative has different documentation bytes from the historical Ola30 ZIP and must receive its own manifest/hash. No ZIP was rebuilt for this preparation.

The included legacy finite packager selects270baseline paths rather than every file of this larger Git tree. Use the source checkout directly for the setup above; no claim is made that its ZIP includes the additional released component/notice files.
