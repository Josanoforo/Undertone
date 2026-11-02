"""Validate or rehearse restoration of a private, standalone SQLite backup."""
import argparse
import hashlib
import json
import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

try:  # Support both `python scripts/recover_sqlite.py` and package imports.
    from .sqlite_metadata import aggregates
except ImportError:  # pragma: no cover - exercised by direct script execution.
    from sqlite_metadata import aggregates

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
RECOVERY = RUNTIME / 'recovery'
EXPECTED = {
    'schema_version': [('version', 'INTEGER', 1, 0)],
    'objects': [('kind', 'TEXT', 1, 1), ('id', 'TEXT', 1, 2),
                ('session_id', 'TEXT', 1, 0), ('owner_id', 'TEXT', 0, 0),
                ('revision', 'INTEGER', 1, 0), ('data', 'TEXT', 1, 0),
                ('created_at', 'TEXT', 1, 0)],
    'credentials': [('hash', 'TEXT', 0, 1), ('role', 'TEXT', 1, 0),
                    ('session_id', 'TEXT', 1, 0), ('owner_id', 'TEXT', 1, 0),
                    ('created_at', 'TEXT', 1, 0)],
}


class RecoveryRefusal(ValueError):
    """An operator-facing refusal containing only a fixed, sanitized literal."""


def checked_path(path, base):
    path = Path(os.path.abspath(path))
    base = Path(os.path.abspath(base))
    if not path.is_relative_to(base):
        raise RecoveryRefusal('path outside allowed runtime')
    # Inspect every existing ancestor, including the repository and runtime roots.
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RecoveryRefusal('symlink or reparse point in path')
    return path


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def connect(path):
    return sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)


def fingerprint(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RecoveryRefusal('integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise RecoveryRefusal('foreign key check failed')
    if db.execute('SELECT version FROM schema_version').fetchall() != [(1,)]:
        raise RecoveryRefusal('unsupported schema version')
    for table, expected in EXPECTED.items():
        cols = db.execute('PRAGMA table_info(' + table + ')').fetchall()
        actual = [(r[1], r[2].upper(), r[3], r[5]) for r in cols]
        if actual != expected:
            raise RecoveryRefusal('unsupported application table structure')
    result = aggregates(db)
    result['schema_version'] = 1
    return result


def recover(source, name, execute=False):
    source = checked_path(source, RUNTIME)
    if not source.is_file():
        raise RecoveryRefusal('backup is missing or not a file')
    if not name or name in ('.', '..') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
        raise RecoveryRefusal('invalid output name')
    target = checked_path(RECOVERY / name, RECOVERY)
    active = Path(os.path.abspath(os.environ.get('APP_DATA_DIR', ROOT / 'data')))
    if source.is_relative_to(active) or target.is_relative_to(active) or active.is_relative_to(target):
        raise RecoveryRefusal('path overlaps configured active data directory')
    if target.exists():
        raise RecoveryRefusal('output already exists')
    # A read-only inspection can leave an empty WAL and shared-memory sidecar.
    # A nonempty WAL or rollback journal requires recovery and is not a standalone snapshot.
    wal = Path(str(source) + '-wal')
    journal = Path(str(source) + '-journal')
    def check_sidecars():
        for path in (wal, Path(str(source) + '-shm'), journal):
            checked_path(path, RUNTIME)
        if journal.exists() or (wal.exists() and wal.stat().st_size != 0):
            raise RecoveryRefusal('backup has uncheckpointed sidecars')
    check_sidecars()
    before = file_hash(source)
    with closing(connect(source)) as db:
        db.execute('BEGIN')
        original = fingerprint(db)
        check_sidecars()
        if file_hash(source) != before:
            raise RecoveryRefusal('backup changed during validation')
        if not execute:
            return {'mode': 'validation only', 'source_sha256': before, 'aggregate': original}
        checked_path(RECOVERY, RUNTIME)
        RECOVERY.mkdir(exist_ok=True)
        checked_path(target, RECOVERY)
        target.mkdir()  # exclusive claim; never reuse or remove a failed artifact
        output = target / 'companion.sqlite3'
        with open(output, 'xb'):
            pass
        with closing(sqlite3.connect(output)) as dest:
            db.backup(dest)
    with closing(connect(output)) as restored:
        restored.execute('BEGIN')
        result = fingerprint(restored)
    check_sidecars()
    if file_hash(source) != before or original != result:
        raise RecoveryRefusal('source changed or restored aggregates differ')
    return {'mode': 'executed', 'source_sha256': before, 'restored_sha256': file_hash(output),
            'aggregate': result, 'output': str(output), 'source_unchanged': True, 'aggregates_equal': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--name', required=True, help='fresh output directory name')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(recover(args.source, args.name, args.execute), indent=2))
    except RecoveryRefusal as exc:
        print('Recovery refused: ' + str(exc))
        return 1
    except sqlite3.Error:
        print('Recovery refused: SQLite validation failed; use a valid compatible backup.')
        return 1
    except OSError:
        print('Recovery refused: filesystem access failed; check source and fresh destination.')
        return 1
    except ValueError:
        print('Recovery refused: validation failed.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
