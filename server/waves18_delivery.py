"""Additive actor-independent delivery checks for marked materials."""
from . import store
from .phase10_common import Phase10Error

def guard_delivery(sid, material):
    with store.LOCK:
        for marker, name in (('w18Segment','waves18_segments'), ('w18Assistance','waves18_assistance'), ('w18Record','waves18_records')):
            if marker not in material:
                continue
            try:
                from importlib import import_module
                module = import_module('.' + name, __package__)
                guard = module.guard_delivery
            except (ImportError, AttributeError):
                raise Phase10Error('stale_context', 'The material is unavailable.', 409)
            guard(sid, material)
        return True
