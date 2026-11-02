"""Build a bounded, hash-addressed local evaluator snapshot (never installs or runs it)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 1
BASE_FILES = (
    '.env.example', 'docs/architecture/REPOSITORY_MAP.md',
    'docs/delivery/waves30/EVALUATOR_SETUP.md', 'contracts/API.md',
    'docs/delivery/waves30/RECOVERY.md', 'docs/delivery/waves30/CAPABILITIES.md',
    'docs/delivery/waves30/CONFIGURATION.example.ps1',
    'scripts/waves30-package.py', 'scripts/setup_evaluator.py',
    'scripts/shared_api_budget.py',
    'docs/delivery/package/runtime_sources.json',
    'contracts/STACK.md', 'contracts/GATEWAY.md',
    'scripts/backup_sqlite.py', 'scripts/recover_sqlite.py', 'scripts/sqlite_metadata.py',
    'scripts/gateway_preflight.py', 'scripts/Start-Gateway.ps1',
    'scripts/Run-TemporaryViewer.ps1', 'scripts/temporary_viewer_smoke.py',
    'scripts/Start-Local.ps1', 'scripts/LocalProvider-Ops.ps1', 'scripts/Invoke-DetachedLocal.ps1',
    'scripts/Readiness-Local.ps1', 'scripts/local_readiness_probe.py',
    'scripts/Provision-ClaudeCredential.ps1',
    'scripts/Setup-Asr.ps1', 'scripts/Download-AsrModel.py', 'scripts/ASR_MODEL_MANIFEST.json',
    'scripts/ASR_REQUIREMENTS_LOCK.txt', 'scripts/THIRD_PARTY_NOTICES.md',
)
# Current coherent additions not yet recorded in PRIMARY's legacy runtime inventory.
# Keep this supplemental list finite; it is input to packaging, not a source-manifest edit.
CURRENT_RUNTIME_FILES = (
    'server/channel_authority.py', 'server/practice_review_delivery.py',
    'server/recovery_startup.py',
    'server/waves17_hosted_facade.py', 'server/waves18_assistance.py',
    'server/waves18_delivery.py', 'server/waves18_records.py', 'server/waves18_segments.py',
    'server/waves20_practice_http.py', 'server/waves20_review.py',
    'server/waves20_runtime.py', 'server/waves20_scheduler.py',
    'server/waves21_impact_runtime.py', 'server/waves21_speech_runtime.py',
    'server/waves21_visual_grounding.py', 'server/waves21_visual_runtime.py',
    'server/waves22_claims.py', 'server/waves22_lifecycle.py', 'server/waves22_runtime.py',
    'server/waves23_moment_index.py', 'server/waves23_moment_media.py',
    'server/waves23_speech_profiles.py', 'server/waves24_activity_handoff.py',
    'server/waves24_channel_pack.py', 'server/waves25_listening_preferences.py',
    'server/waves25_listening_recovery.py',
    'server/source_translation_delivery.py',
    'server/waves20_delivery.py', 'server/waves20_job_bridge.py',
    'server/waves20_policy_access.py', 'server/waves20_practice.py',
    'server/waves20_practice_adapter.py', 'server/waves20_source_access.py',
    'server/waves20_worker_pool.py', 'server/waves21_correction_impact.py',
    'server/waves21_pronunciation.py', 'server/waves21_speech_stream.py',
    'server/waves22_adoption.py', 'server/waves22_coedit.py',
    'server/waves22_coedit_auth.py', 'server/waves22_edition.py',
    'server/waves22_model_auth.py', 'server/waves22_models.py',
    'client/assets/waves22-edition.js', 'client/assets/waves19-20-delivery.js',
    'client/assets/waves21-speech-view.js', 'client/assets/waves21-visual-view.js',
    'client/assets/waves21-impact-connected.js', 'client/assets/waves23-24-moments.js',
    'client/assets/waves23-24-listening.js', 'client/assets/waves23-24-pack.js',
    'client/assets/waves23-24-activities.js', 'client/assets/waves23-24-guide.js',
    'client/assets/waves23-24-desk.js', 'client/assets/waves22-claims-query.js',
    'client/assets/waves22-coedit.js', 'client/assets/waves22-model-history.js',
    'client/assets/waves22-representations.js', 'client/assets/waves19-20-policy.js',
    'client/assets/waves19-20-receipts.js', 'client/assets/waves22-claims.js',
    'client/assets/waves19-20-library.js', 'client/assets/waves19-20-practice.js',
    'client/assets/waves19-20-entry.js', 'client/assets/waves19-20-inbox.js',
    'client/assets/waves19-20-operator.js', 'client/assets/waves18-record.js',
    'client/assets/waves18-segment.js', 'client/assets/waves18-assistance.js',
    'client/assets/waves17-18-return.js', 'client/assets/waves17-18-templates.js',
    'client/assets/waves15-cues.js', 'client/assets/waves15-16-formats.js',
    'client/assets/waves15-16-journeys.js', 'client/assets/waves17-18-controls.js',
    'client/assets/waves23-24-moments.css', 'client/assets/waves23-24-listening.css',
    'client/assets/waves23-24-pack.css', 'client/assets/waves23-24-activities.css',
    'client/assets/waves23-24-guide.css', 'client/assets/waves23-24-desk.css',
    'client/assets/waves19-20-operator.css', 'client/assets/waves19-20-entry.css',
    'client/assets/waves19-20-library.css', 'client/assets/waves19-20-practice.css',
    'client/assets/waves19-20-delivery.css', 'client/assets/waves19-20-policy.css',
    'client/assets/waves18-segment.css', 'client/assets/waves18-assistance.css',
    'client/assets/waves17-18-return.css', 'client/assets/waves17-18-templates.css',
    'client/assets/waves22-edition.css', 'client/assets/waves30-resume-access.css',
    'client/assets/waves30-resume-access.js', 'client/assets/waves19-20-resume-verify.js',
    'server/waves22_chapter_commit.py', 'server/waves25_listening_authorities.py',
    'server/waves26_flag_contribution.py', 'server/waves26_meaning.py',
    'server/waves26_term_inspection.py', 'server/waves26_visual_association.py',
    'server/waves27_chapter_draft.py', 'server/waves27_export.py', 'server/waves27_moment_trail.py',
    'server/waves28_handoff_status.py', 'server/waves28_segment_setup.py',
    'server/waves29_quality_presets.py', 'server/waves29_operating_status.py',
    'client/assets/waves21-captions.css', 'client/assets/waves21-captions.js',
    'client/assets/waves21-impact.css', 'client/assets/waves21-impact.js',
    'client/assets/waves21-pronunciation.css', 'client/assets/waves21-pronunciation.js',
    'client/assets/waves21-region.css', 'client/assets/waves21-region.js',
    'client/assets/waves22-claims.css', 'client/assets/waves22-coedit.css',
    'client/assets/waves22-protected-journal.js', 'client/assets/waves22-representations.css',
    'client/assets/waves25-listening-continuity.css', 'client/assets/waves25-listening-continuity.js',
    'client/assets/waves26-accessibility.css', 'client/assets/waves26-accessibility.js',
    'client/assets/waves26-meaning.css', 'client/assets/waves26-meaning.js',
    'client/assets/waves26-terms.css', 'client/assets/waves26-terms.js',
    'client/assets/waves27-chapters.css', 'client/assets/waves27-chapters.js',
    'client/assets/waves27-moment-trail.css', 'client/assets/waves27-moment-trail.js',
    'client/assets/waves28-conflict.css', 'client/assets/waves28-conflict.js',
    'client/assets/waves28-handoff.css', 'client/assets/waves28-handoff.js',
    'client/assets/waves28-segment-setup.css', 'client/assets/waves28-segment-setup.js',
    'client/assets/waves29-operating-view.css', 'client/assets/waves29-operating-view.js',
)
# Explicit current public client source selection. Finite, source-only, and never
# reads sessions/ or generated dist/ outputs.
CLIENT_SOURCE_ID = 'repository-current-public-client-v1'
CURRENT_CLIENT_FILES = (
    'client/index.html', 'client/overlay.html',
    'client/assets/invitation-input.mjs',
    'client/assets/waves30-quality-choice.js',
    'client/assets/waves30-workspace-guide.js',
    'client/assets/waves30-saved-translations.js',
    'client/assets/waves29-operating-presets.js',
    'client/assets/app.css', 'client/assets/app.js', 'client/assets/live-audio.js',
    'client/assets/overlay.css', 'client/assets/overlay.js',
    'client/assets/phase6.css', 'client/assets/phase6.js',
    'client/assets/phase10.css', 'client/assets/phase10.js',
    'client/assets/phase11.css', 'client/assets/phase11.js',
    'client/assets/phase12-collaboration.css', 'client/assets/phase12-collaboration.js',
    'client/assets/phase12-controller.js', 'client/assets/phase12-typed.js',
    'client/assets/phase12-wire.js', 'client/assets/phase12.css', 'client/assets/phase12.js',
    'client/assets/waves13-14-drafts.js', 'client/assets/waves13-14-formats.js',
    'client/assets/waves13-14-model.js', 'client/assets/waves13-14-production.js',
    'client/assets/waves13-14-questions.js', 'client/assets/waves13-14-reasons.js',
    'client/assets/waves15-16-formats.js', 'client/assets/waves15-16-journeys.js',
    'client/assets/waves15-cues.js', 'client/assets/waves17-18-controls.js',
    'client/assets/waves17-18-return.css', 'client/assets/waves17-18-return.js',
    'client/assets/waves17-18-templates.css', 'client/assets/waves17-18-templates.js',
    'client/assets/waves18-assistance.css', 'client/assets/waves18-assistance.js',
    'client/assets/waves18-record.js', 'client/assets/waves18-segment.css',
    'client/assets/waves18-segment.js', 'client/assets/waves19-20-delivery.css',
    'client/assets/waves19-20-delivery.js', 'client/assets/waves19-20-entry.css',
    'client/assets/waves19-20-entry.js', 'client/assets/waves19-20-inbox.js',
    'client/assets/waves19-20-library.css', 'client/assets/waves19-20-library.js',
    'client/assets/waves19-20-operator.css', 'client/assets/waves19-20-operator.js',
    'client/assets/waves19-20-policy.css', 'client/assets/waves19-20-policy.js',
    'client/assets/waves19-20-practice.css', 'client/assets/waves19-20-practice.js',
    'client/assets/waves19-20-receipts.js', 'client/assets/waves19-20-resume-verify.js',
    'client/assets/waves21-captions.css', 'client/assets/waves21-captions.js',
    'client/assets/waves21-impact-connected.js', 'client/assets/waves21-impact.css',
    'client/assets/waves21-impact.js', 'client/assets/waves21-pronunciation.css',
    'client/assets/waves21-pronunciation.js', 'client/assets/waves21-region.css',
    'client/assets/waves21-region.js', 'client/assets/waves21-speech-view.js',
    'client/assets/waves21-visual-view.js', 'client/assets/waves22-claims-query.js',
    'client/assets/waves22-claims.css', 'client/assets/waves22-claims.js',
    'client/assets/waves22-coedit.css', 'client/assets/waves22-coedit.js',
    'client/assets/waves22-edition.css', 'client/assets/waves22-edition.js',
    'client/assets/waves22-model-history.js', 'client/assets/waves22-protected-journal.js',
    'client/assets/waves22-representations.css', 'client/assets/waves22-representations.js',
    'client/assets/waves23-24-activities.css', 'client/assets/waves23-24-activities.js',
    'client/assets/waves23-24-desk.css', 'client/assets/waves23-24-desk.js',
    'client/assets/waves23-24-guide.css', 'client/assets/waves23-24-guide.js',
    'client/assets/waves23-24-listening.css', 'client/assets/waves23-24-listening.js',
    'client/assets/waves23-24-moments.css', 'client/assets/waves23-24-moments.js',
    'client/assets/waves23-24-pack.css', 'client/assets/waves23-24-pack.js',
    'client/assets/waves25-listening-continuity.css', 'client/assets/waves25-listening-continuity.js',
    'client/assets/waves26-accessibility-connected.js', 'client/assets/waves26-accessibility.css',
    'client/assets/waves26-accessibility.js', 'client/assets/waves26-meaning.css',
    'client/assets/waves26-meaning.js', 'client/assets/waves26-terms.css',
    'client/assets/waves26-terms.js', 'client/assets/waves27-chapters.css',
    'client/assets/waves27-chapters.js', 'client/assets/waves27-export.css',
    'client/assets/waves27-export.js', 'client/assets/waves27-moment-trail.css',
    'client/assets/waves27-moment-trail.js', 'client/assets/waves28-conflict.css',
    'client/assets/waves28-conflict.js', 'client/assets/waves28-handoff-connected.js',
    'client/assets/waves28-handoff.css', 'client/assets/waves28-handoff.js',
    'client/assets/waves28-segment-setup.css', 'client/assets/waves28-segment-setup.js',
    'client/assets/waves29-operating-connected.js', 'client/assets/waves29-operating-view.css',
    'client/assets/waves29-operating-view.js', 'client/assets/waves30-resume-access.css',
    'client/assets/waves30-resume-access.js', 'client/assets/creator-speech-setup.js',
)
RUNTIME_PATH = re.compile(r'(?:server/(?!test_)[a-z0-9_]+\.(?:py|ps1|json)|client/(?:index|overlay)\.html|client/assets/[a-z0-9-]+\.(?:m?js|css))\Z')
SENSITIVE = re.compile(r'(^|/)(?:\.runtime|sessions|\.git|\.venv|venv|node_modules|__pycache__|profiles?|cookies?)(/|$)|(^|/)\.env$|(^|/)(?:secrets?|credentials?|tokens?|auth|private|browser-profile|cookies?)(?:\.[^/]*)?$|\.(?:sqlite3?|db|wal|shm|cookie|log)$', re.I)


def reject_reparse(path: Path) -> None:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('symlink or reparse point in path')


def safe_name(name: str) -> bool:
    p = Path(name)
    return (name == p.as_posix() and not p.is_absolute() and '..' not in p.parts
            and not SENSITIVE.search(name))


def check_references(root: Path, included: set[str], blobs: dict[str, bytes] | None = None) -> None:
    """Fail if shipped Python, HTML, or launcher source references escape the bundle."""
    import ast
    def read_text(name: str) -> str:
        data = blobs[name] if blobs is not None and name in blobs else (root / name).read_bytes()
        return data.decode('utf-8-sig')
    for name in sorted(n for n in included if n.startswith('server/') and n.endswith('.py')):
        tree = ast.parse(read_text(name), filename=name)
        for node in ast.walk(tree):
            candidates = []
            if isinstance(node, ast.Import):
                candidates = [alias.name.replace('.', '/') + '.py' for alias in node.names if alias.name.startswith(('server.', 'scripts.'))]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = list(Path(name).with_suffix('').parts[:-1])
                    package = package[:len(package) - node.level + 1]
                    if node.module:
                        package.extend(node.module.split('.'))
                    candidates = ['/'.join(package + ([alias.name] if not node.module else [])) + '.py' for alias in node.names]
                elif node.module in ('server', 'scripts'):
                    candidates = [node.module + '/' + alias.name + '.py' for alias in node.names]
                elif node.module and node.module.startswith(('server.', 'scripts.')):
                    candidates = [node.module.replace('.', '/') + '.py']
            for candidate in candidates:
                if candidate.startswith(('server/', 'scripts/')) and candidate not in included and (root / candidate).is_file():
                    raise ValueError(f'{name} imports omitted module: {candidate}')
    for html in ('client/index.html', 'client/overlay.html'):
        if html not in included:
            continue
        content = read_text(html)
        for ref in re.findall(r'(?:src|href)=["\']([^"\']+\.(?:js|css))(?:\?[^"\']*)?["\']', content, re.I):
            if ref.startswith(('http:', 'https:', '//', 'data:')):
                continue
            target = ('client' + ref) if ref.startswith('/') else (Path(html).parent / ref).as_posix()
            if target not in included:
                raise ValueError(f'{html} references omitted asset: {target}')
    for name in sorted(n for n in included if n.startswith('client/assets/') and n.endswith(('.js', '.mjs', '.css'))):
        content = read_text(name)
        if name.endswith(('.js', '.mjs')):
            refs = re.findall(r'(?:\bfrom\s+|\bimport\s*\()\s*["\']([^"\']+)["\']', content)
        else:
            refs = re.findall(r'@import\s+(?:url\()?\s*["\']?([^"\')\s;]+)', content, re.I)
        for ref in refs:
            if ref.startswith(('http:', 'https:', '//', 'data:', '#')):
                continue
            target = (Path(name).parent / ref.split('?', 1)[0]).as_posix()
            if target not in included:
                raise ValueError(f'{name} references omitted asset/module: {target}')
    # Resolve literal source-file Join-Path edges in the delivered local launchers.
    # Paths to .runtime state, credentials, optional ASR models, and generated logs
    # are not source dependencies and are intentionally outside this static check.
    startup_scripts = (
        'scripts/Start-Local.ps1', 'scripts/LocalProvider-Ops.ps1',
        'scripts/Invoke-DetachedLocal.ps1', 'scripts/Readiness-Local.ps1',
    )
    source_join = re.compile(
        r"Join-Path\s+\$(?:PSScriptRoot|AppRoot)\s+['\"]([^'\"]+\.(?:ps1|py))['\"]",
        re.I,
    )
    for name in startup_scripts:
        if name not in included:
            continue
        content = read_text(name)
        for raw_ref in source_join.findall(content):
            ref = raw_ref.replace('\\', '/')
            target = (Path(name).parent / ref).as_posix()
            # The app-root Join-Path references are rooted at the repository root.
            if re.search(r"Join-Path\s+\$AppRoot\s+['\"]" + re.escape(raw_ref) + r"['\"]", content, re.I):
                target = ref
            target = os.path.normpath(target).replace('\\', '/')
            if target not in included:
                raise ValueError(f'{name} references omitted startup source: {target}')


def allowed_files(root: Path) -> list[str]:
    manifest_path = root / 'docs/delivery/package/runtime_sources.json'
    reject_reparse(manifest_path)
    data = manifest_path.read_bytes()
    manifest = json.loads(data)
    names = manifest.get('files') if isinstance(manifest, dict) else None
    if not isinstance(names, list) or not all(isinstance(n, str) and RUNTIME_PATH.fullmatch(n) and safe_name(n) for n in names):
        raise ValueError('invalid runtime allowlist')
    # The source list is positive and finite. No directory walk is ever archived.
    if not all((RUNTIME_PATH.fullmatch(n) or re.fullmatch(r'client/assets/[a-z0-9-]+\.(?:js|css)', n)) and safe_name(n) for n in CURRENT_RUNTIME_FILES):
        raise ValueError('invalid supplemental runtime allowlist')
    # A complete explicit local snapshot can be packaged without consulting the
    # changing checkout. Small legacy synthetic source roots keep their old scope.
    selected_client = CURRENT_CLIENT_FILES if (Path(os.path.abspath(root)) == ROOT or
        all((root / name).is_file() for name in CURRENT_CLIENT_FILES)) else ()
    return sorted(set((*BASE_FILES, *names, *CURRENT_RUNTIME_FILES, *selected_client)))


def client_release_inputs(root: Path) -> dict[str, bytes]:
    """Read the explicitly selected finite current public client source set."""
    if Path(os.path.abspath(root)) != ROOT and not all((root / name).is_file() for name in CURRENT_CLIENT_FILES):
        return {}
    inputs = {}
    for name in CURRENT_CLIENT_FILES:
        if not RUNTIME_PATH.fullmatch(name) or not safe_name(name):
            raise ValueError('invalid selected current client path: ' + name)
        candidate = root / name
        reject_reparse(candidate)
        if not candidate.is_file():
            raise ValueError('selected current client input is missing: ' + name)
        data = candidate.read_bytes()
        inputs[name] = data
    return inputs


def read_input(root: Path, name: str, client_inputs: dict[str, bytes] | None = None) -> bytes:
    if client_inputs is not None and name in client_inputs:
        return client_inputs[name]
    return (root / name).read_bytes()


def inventory(root: Path) -> dict:
    client_inputs = client_release_inputs(root)
    files = {}
    for name in allowed_files(root):
        src = root / name
        reject_reparse(src)
        if not src.is_file():
            raise ValueError('allowlisted input is missing: ' + name)
        blob = read_input(root, name, client_inputs)
        files[name] = {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
    # Validate references from known entry points against this exact finite inventory.
    included = set(files)
    for required in ('server/__init__.py', 'server/__main__.py', 'server/http.py', 'server/store.py',
                     'server/provider.py', 'server/claude_provider.py', 'server/asr.py',
                     'server/admission.py', 'server/lifecycle.py', 'server/gateway.py',
                     'client/index.html', 'client/overlay.html', 'client/assets/app.js',
                     'client/assets/app.css', 'client/assets/overlay.js', 'client/assets/overlay.css'):
        if required not in included:
            raise ValueError('required runtime module/style missing from allowlist: ' + required)
    check_references(root, included, client_inputs)
    return files


def build(source: Path, destination: Path) -> dict:
    source = Path(os.path.abspath(source))
    destination = Path(os.path.abspath(destination))
    reject_reparse(source)
    reject_reparse(destination)
    if not source.is_dir():
        raise ValueError('source root must be a directory')
    if not source.is_relative_to(ROOT):
        raise ValueError('source root must be inside this repository')
    permitted = (ROOT / 'docs/delivery/waves30', ROOT / 'sessions/mesa-05/WAVES25_30/M05_PACKAGE30/continuous-01',
                 ROOT / 'sessions/central/NIGHT_PACKAGE/continuous-01')
    if not any(destination.is_relative_to(p) for p in permitted):
        raise ValueError('output must remain in the M05 documentation or business directory')
    if destination.exists():
        raise ValueError('output must be a new path')
    entries = inventory(source)
    client_inputs = client_release_inputs(source)
    blobs = {n: read_input(source, n, client_inputs) for n in entries}
    if any(hashlib.sha256(blobs[n]).hexdigest() != entries[n]['sha256'] for n in entries):
        raise ValueError('source changed while staging')
    destination.parent.mkdir(parents=True, exist_ok=True)
    reject_reparse(destination.parent)
    destination.mkdir()
    archive = destination / 'evaluator.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(blobs):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, blobs[name])
    client_inputs_after = client_release_inputs(source)
    for name, before in entries.items():
        source_path = (source / name)
        reject_reparse(source_path)
        current = client_inputs_after.get(name) if name in client_inputs else read_input(source, name, client_inputs)
        if not source_path.is_file() or current != blobs[name]:
            raise ValueError('source changed during archive creation: ' + name)
    snapshot = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    import sys, zlib
    result = {'format': FORMAT, 'status': 'PREPARED_NOT_ACCEPTED',
              'snapshot_sha256': snapshot,
              'build_environment': {'python': sys.version.split()[0], 'zlib': zlib.ZLIB_RUNTIME_VERSION},
              'source_identity': 'working-source snapshot; no immutable accepted release asserted',
              'client_source_identity': (CLIENT_SOURCE_ID + '; current repository public source paths, bounded by CURRENT_CLIENT_FILES'
                                        if client_inputs else 'synthetic or explicit source-root input'),
              'archive': archive.name,
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'files': [{'path': n, **entries[n]} for n in sorted(entries)]}
    (destination / 'MANIFEST.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(args.source, args.destination)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, 'Package refused: ' + str(exc) + '\n')
    print(f"{result['status']}: {len(result['files'])} allowlisted files; SHA-256 {result['archive_sha256']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
