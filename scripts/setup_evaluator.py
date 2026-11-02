"""Compatibility adapter for the current local evaluator ZIP packager."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / 'scripts' / 'waves30-package.py'


def _builder():
    """Load the authoritative builder, whose filename contains a hyphen."""
    spec = importlib.util.spec_from_file_location('waves30-package', BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError('could not load scripts/waves30-package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export(destination):
    """Preserve the old callable while delegating all policy and inventory."""
    return _builder().build(ROOT, Path(destination))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            'Compatibility adapter for the current evaluator format: '
            'evaluator.zip plus an external MANIFEST.json. The old ready-to-run '
            'directory tree format is retired.'
        ),
        epilog=(
            'Destinations under repository .runtime are no longer accepted. '
            'Use --destination docs/delivery/waves30/exports/evaluator-ola2-01, '
            'then extract evaluator.zip to a new private directory before running it. '
            'The ZIP and external manifest are created by scripts/waves30-package.py.'
        ),
    )
    parser.add_argument(
        '--destination', required=True,
        help='new permitted output directory for evaluator.zip and external MANIFEST.json',
    )
    args = parser.parse_args()
    try:
        result = export(args.destination)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(
            2,
            'Format changed: this command creates evaluator.zip plus an external '
            'MANIFEST.json; extract the ZIP into a new private directory before use. '
            'Export refused: ' + str(exc) + '\n',
        )
    print(
        f"Format changed: wrote evaluator.zip and external MANIFEST.json "
        f"({len(result['files'])} files; SHA-256 {result['archive_sha256']}). "
        'Extract the ZIP into a new private directory before running it. '
        'Legacy .runtime destinations are not accepted.'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
