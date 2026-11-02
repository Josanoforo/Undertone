"""Bounded, deterministic interactive models for session audiences."""
import math
import re
from . import store
from .phase10_common import Context, Phase10Error


def fail(message, status=400):
    raise Phase10Error('invalid_model' if status == 400 else 'not_found', message, status)


def number(value):
    return type(value) in (int, float) and abs(value) <= 1000000 and math.isfinite(value)


def handle(handler, sid, actor, method, parts):
    ctx = Context(handler, sid, actor)
    with store.LOCK:
        ctx.check_actor()
        if parts == ['models'] and method == 'GET':
            return 200, {'models': [m for m in store.all('w13model', sid) if m.get('status', 'published') == 'published']}
        if (parts == ['models'] and method == 'POST') or (len(parts) == 2 and parts[0] == 'models' and method == 'PATCH'):
            if actor['role'] != 'creator':
                raise Phase10Error('forbidden', 'Only the creator can publish a model.', 403)
            body = handler.body()
            editing = method == 'PATCH'
            if not isinstance(body, dict) or set(body) != ({'title', 'parameters', 'base', 'revision'} if editing else {'title', 'parameters', 'base'}):
                fail('A title, parameters and base are required.')
            title, params, base = body['title'], body['parameters'], body['base']
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160 or not number(base):
                fail('Invalid title or base.')
            if not isinstance(params, list) or not 1 <= len(params) <= 6:
                fail('Provide one to six parameters.')
            names = set()
            for p in params:
                if not isinstance(p, dict) or set(p) != {'name', 'min', 'max', 'step', 'weight'}:
                    fail('Invalid parameter.')
                name = p['name']
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', name) or name in names:
                    fail('Parameter names must be unique identifiers.')
                names.add(name)
                if not all(number(p[k]) for k in ('min', 'max', 'step', 'weight')) or p['min'] >= p['max'] or p['step'] <= 0 or p['step'] > p['max'] - p['min']:
                    fail('Invalid parameter bounds.')
            if editing:
                model = store.get('w13model', parts[1], sid)
                if not model or model.get('status', 'published') != 'published': fail('Model unavailable.', 404)
                if type(body['revision']) is not int or body['revision'] != model['_revision']:
                    raise Phase10Error('version_conflict', 'The model changed.', 409)
                model.update(title=title.strip(), parameters=params, base=base, demonstration=None)
                store.save('w13model', model, revision=body['revision'])
                return 200, {'model': store.get('w13model', parts[1], sid)}
            model = store.put('w13model', sid, {'title': title.strip(), 'parameters': params, 'base': base, 'status': 'published'}, owner=actor['owner'])
            return 201, {'model': model}
        if len(parts) == 2 and parts[0] == 'models' and method == 'DELETE':
            if actor['role'] != 'creator': raise Phase10Error('forbidden', 'Only the creator can withdraw a model.', 403)
            model = store.get('w13model', parts[1], sid)
            if not model or model.get('status', 'published') != 'published': fail('Model unavailable.', 404)
            body = handler.body()
            if not isinstance(body, dict) or set(body) != {'revision'} or type(body['revision']) is not int: fail('A revision is required.')
            if body['revision'] != model['_revision']: raise Phase10Error('version_conflict', 'The model changed.', 409)
            model['status'] = 'withdrawn'; model['demonstration'] = None
            store.save('w13model', model, revision=body['revision'])
            return 200, {'withdrawn': True}
        if len(parts) == 3 and parts[0] == 'models' and parts[2] in ('evaluate', 'demonstrate') and method == 'POST':
            if parts[2] == 'demonstrate' and actor['role'] != 'creator': raise Phase10Error('forbidden', 'Only the creator can present a demonstration.', 403)
            model = store.get('w13model', parts[1], sid)
            if not model or model.get('status', 'published') != 'published':
                fail('Model unavailable.', 404)
            body = handler.body()
            if not isinstance(body, dict) or set(body) != {'values', 'prediction'} or not isinstance(body['values'], dict) or not number(body['prediction']):
                fail('Values and prediction are required.')
            values = body['values']
            if set(values) != {p['name'] for p in model['parameters']}:
                fail('Values must match the model parameters.')
            outcome = model['base']
            for p in model['parameters']:
                value = values[p['name']]
                if not number(value) or value < p['min'] or value > p['max']:
                    fail('A parameter is outside its bounds.')
                steps = (value - p['min']) / p['step']
                if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
                    fail('A parameter does not match its step.')
                outcome += p['weight'] * value
            result = {'prediction': body['prediction'], 'outcome': outcome, 'difference': outcome - body['prediction']}
            if parts[2] == 'demonstrate':
                model['demonstration'] = dict(result, values=values)
                store.save('w13model', model, revision=model['_revision'])
                result['model'] = store.get('w13model', parts[1], sid)
            return 200, result
        raise Phase10Error('not_found', 'Model route unavailable.', 404)

