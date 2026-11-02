"""SQLite backup helper for Switch-LocalProvider; writes only under app runtime."""
import argparse, sqlite3
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def backup(source, destination):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    if not source.is_relative_to(ROOT.resolve()) or not destination.is_relative_to((ROOT/'.runtime').resolve()): raise ValueError('paths outside repository')
    if not source.is_file() or destination.exists(): raise ValueError('source missing or destination exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst: src.backup(dst)
    with closing(sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchone()!=('ok',): raise ValueError('backup verification failed')
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'schema_version','objects','credentials'}.issubset(tables): raise ValueError('backup schema invalid')
    return True
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--destination',required=True)
    args=parser.parse_args();backup(args.source,args.destination);print('SQLite backup verified; no rows printed.')
