# Preserve and recover local data

This distribution contains source, not sessions or databases. Keep the existing working copy and private data when extracting a new copy. Do not copy an active SQLite file without its transaction state, overwrite a live database, or automatically promote a recovery clone.

From the extracted root, for **this evaluator's own** known database only:

```powershell
python -B scripts/backup_sqlite.py --source data/companion.sqlite3 --destination .runtime/backups/evaluator01.sqlite3
python -B scripts/recover_sqlite.py --source .runtime/backups/evaluator01.sqlite3 --name evaluator-check01
python -B scripts/recover_sqlite.py --source .runtime/backups/evaluator01.sqlite3 --name evaluator-recovered01 --execute
```

The first command uses SQLite online backup and quick_check. The second validates only. The third creates a fresh `.runtime/recovery/evaluator-recovered01/` and checks integrity, foreign keys, supported schema and aggregates across all tables using `sqlite_metadata.py`. Names/destinations must be fresh; no rows are printed. A nonempty WAL or journal on the backup is refused as a non-standalone snapshot. Failed artifacts are retained for inspection.

After stopping only the evaluator process and retaining original data, point `APP_DATA_DIR` at the new recovery directory and use the same startup command from [EVALUATOR_SETUP.md](EVALUATOR_SETUP.md). Never point this procedure at the shared operator service/base. Recovery does not revive revoked/expired access, reconcile unknown provider requests or retry effects.

Browser access and private local data are separate. Use the normal saved-access choice or tab-only form with a still-valid capability; do not extract old bearers, inject storage, or reset missing grants. A lost capability is not recovered by copying a session ID. Local copies cannot be remotely recalled.
