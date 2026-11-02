"""Scoped startup gate for the authoritative database and recovery successor.

This hook is not an operator admission decision and does not establish that
already-running writers participate.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import atexit

_held = None
_held_module = None


def ensure_scoped_startup(data_dir=None):
    """Retain the common admission gate for the authoritative database.

    Other data directories retain their normal behavior. Direct store users
    enter here too, before opening SQLite, and hold admission until exit.
    """
    global _held, _held_module
    if _held is not None:
        return
    data = Path(data_dir if data_dir is not None else
                os.environ.get('APP_DATA_DIR', Path(__file__).resolve().parents[1] / 'data')).resolve()
    roots = (*Path(__file__).resolve().parents, *data.parents)
    root = next((p for p in roots
                 if (p / 'sessions/central/M02_RECOVERY_ADMISSION/continuous-01/current_admission.py').is_file()), None)
    if root is None:
        if any(os.environ.get(k) is not None for k in ('APP_RECOVERY_ADMISSION_MODULE', 'APP_RECOVERY_TRANSFER_TOKEN', 'APP_RECOVERY_CHANNEL_HANDLE', 'APP_RECOVERY_HANDSHAKE_SHA256')):
            raise RuntimeError('Recovery admission project root unavailable')
        return
    target = root / 'sessions/mesa-02/WAVES19_20/M02_PRIMARY/continuous-02/candidate-153/data'
    if data != target.resolve():
        if any(os.environ.get(k) is not None for k in ('APP_RECOVERY_ADMISSION_MODULE', 'APP_RECOVERY_TRANSFER_TOKEN', 'APP_RECOVERY_CHANNEL_HANDLE', 'APP_RECOVERY_HANDSHAKE_SHA256')):
            raise RuntimeError('Recovery admission database differs')
        return
    path = root / 'sessions/central/M02_RECOVERY_ADMISSION/continuous-01/current_admission.py'
    directory = target / '.recovery404-admission'
    directory.mkdir(exist_ok=True)
    expected_directory = os.environ.get('APP_RECOVERY_ADMISSION_DIRECTORY')
    expected_module = os.environ.get('APP_RECOVERY_ADMISSION_MODULE')
    expected_hash = os.environ.get('APP_RECOVERY_ADMISSION_SHA256')
    token = os.environ.get('APP_RECOVERY_TRANSFER_TOKEN')
    channel_handle = os.environ.get('APP_RECOVERY_CHANNEL_HANDLE')
    handshake_hash = os.environ.get('APP_RECOVERY_HANDSHAKE_SHA256')
    if any(v is not None for v in (expected_directory, expected_module, expected_hash, token, channel_handle, handshake_hash)):
        if (not all((expected_directory, expected_module, expected_hash, token, channel_handle, handshake_hash)) or
                Path(expected_directory).resolve() != directory.resolve() or
                Path(expected_module).resolve() != path.resolve() or
                hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash):
            raise RuntimeError('Recovery admission configuration differs')
    handshake_path = root / 'sessions/central/M02_TRANSFER_FIX/continuous-01/transfer_handshake.py'
    if token and hashlib.sha256(handshake_path.read_bytes()).hexdigest() != handshake_hash:
        raise RuntimeError('Recovery handshake source differs')
    name = '_audience_scoped_startup_admission'
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Recovery admission module unavailable')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    admission = module.StartupAdmission(directory, transfer_token=token)
    admission.acquire(blocking=True)
    if token:
        channel = None
        try:
            from multiprocessing.connection import Connection
            handle = int(channel_handle)
            if handle < 0:
                raise ValueError('Invalid inherited channel')
            channel = Connection(handle)
            spec = importlib.util.spec_from_file_location('_audience_recovery_handshake', handshake_path)
            if spec is None or spec.loader is None:
                raise RuntimeError('Recovery handshake unavailable')
            handshake = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(handshake)
            if hashlib.sha256(handshake_path.read_bytes()).hexdigest() != handshake_hash:
                raise RuntimeError('Recovery handshake source changed during load')
            handshake.successor_barrier(admission, channel, os.getpid())
        except BaseException:
            admission.close(clean=False)
            raise
        finally:
            if channel is not None:
                channel.close()
    _held, _held_module = admission, module
    atexit.register(_close_scoped_startup)


def _close_scoped_startup():
    global _held
    if _held is not None:
        admission, _held = _held, None
        admission.close(clean=True)


@contextmanager
def recovery_startup():
    global _held
    ensure_scoped_startup()
    if _held is not None:
        try:
            yield
        except BaseException:
            admission, _held = _held, None
            admission.close(clean=False)
            raise
        return
    keys = ('APP_RECOVERY_ADMISSION_MODULE', 'APP_RECOVERY_ADMISSION_SHA256',
            'APP_RECOVERY_ADMISSION_DIRECTORY', 'APP_RECOVERY_TRANSFER_TOKEN')
    values = [os.environ.get(key) for key in keys]
    if not any(value is not None for value in values):
        yield
        return
    if any(not value for value in values):
        raise RuntimeError('Incomplete recovery startup admission')
    module_path, expected, directory, token = values
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise RuntimeError('Invalid recovery admission source pin')
    path = Path(module_path).resolve(strict=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Recovery admission source changed')
    name = '_audience_recovery_startup_admission'
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Recovery admission module unavailable')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Recovery admission source changed during load')
        admission = module.StartupAdmission(Path(directory).resolve(strict=True),
                                            transfer_token=token)
        admission.acquire(blocking=True)
        clean = False
        try:
            yield
            clean = True
        finally:
            admission.close(clean=clean)
    finally:
        sys.modules.pop(name, None)
