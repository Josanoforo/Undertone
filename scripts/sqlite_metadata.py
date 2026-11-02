"""Read-only SQLite aggregate fingerprints; no row values leave the process."""
import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def quote_identifier(identifier):
    """Quote an SQLite identifier, including identifiers containing quotes."""
    return '"' + identifier.replace('"', '""') + '"'


def _json_sha256(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _typed_value(value):
    # sqlite3 returns SQLite storage classes as None, str, int, float and bytes.
    # Tags prevent cross-type ambiguity; float.hex() is stable and distinguishes
    # real values from integer values without locale-dependent formatting.
    if value is None:
        return ['null']
    if isinstance(value, bytes):
        return ['blob', value.hex()]
    if isinstance(value, str):
        return ['text', value]
    if isinstance(value, int):
        return ['integer', str(value)]
    if isinstance(value, float):
        if math.isnan(value):
            return ['real', 'nan']
        return ['real', value.hex()]
    raise TypeError('unsupported SQLite value type')


def schema_sha256(db):
    schema = db.execute(
        'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'
    ).fetchall()
    return _json_sha256(schema)


def application_tables(db):
    """Return every user table in the schema, excluding SQLite-reserved names."""
    return [row[0] for row in db.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND lower(substr(name,1,7)) <> 'sqlite_' "
        'ORDER BY name COLLATE BINARY'
    )]


def table_aggregates(db):
    """Hash each application table independent of row order, retaining duplicates."""
    tables = {}
    for table in application_tables(db):
        quoted = quote_identifier(table)
        row_hashes = sorted(
            _json_sha256([_typed_value(value) for value in row])
            for row in db.execute('SELECT * FROM ' + quoted)
        )
        tables[table] = {
            'count': len(row_hashes),
            'aggregate_sha256': _json_sha256(row_hashes),
        }
    return tables


def aggregates(db):
    """Shared schema and application-table fingerprints for both producers."""
    return {'schema_sha256': schema_sha256(db), 'tables': table_aggregates(db)}


def metadata(source):
    source = Path(source).resolve()
    if not source.is_relative_to(ROOT.resolve()) or not source.is_file():
        raise ValueError('invalid database')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        version = [row[0] for row in db.execute('SELECT version FROM "schema_version"')]
        result = {'database': str(source), 'schema_versions': version}
        result.update(aggregates(db))
        return result


def write(source, destination):
    destination = Path(destination).resolve()
    if not destination.is_relative_to((ROOT / '.runtime').resolve()):
        raise ValueError('output outside runtime')
    data = metadata(source)
    with open(destination, 'x', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
        f.flush()
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    write(args.source, args.output)
    print('Read-only aggregate metadata saved.')
