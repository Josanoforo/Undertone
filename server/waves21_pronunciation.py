"""Approved pronunciation metadata and bounded generation preparation.

No engine, provider, persistence, policy or publication is operated here.
"""
import copy
import hashlib
import json
import math
import re

class PronunciationError(ValueError):
    pass

SPOKEN_FORM_REVISION = 'approved-exact-terms-v1'

def prepare_spoken_text(text, language, rules):
    """Prepare literal, approved whole terms once; never interpret markup or recurse.

    The caller must independently authorize the current rule set and language.
    Identical terms with different approved forms are ambiguous and fail closed.
    """
    _text(text, 6000)
    if language not in ('en', 'es') or not isinstance(rules, list):
        raise PronunciationError('invalid_rules')
    terms = {}
    for rule in rules:
        if rule['approved'] and rule['language'] == language:
            term, alias = rule['term'], rule['alias']
            if term in terms and terms[term] != alias:
                raise PronunciationError('ambiguous_spoken_form')
            terms[term] = alias
    if not terms:
        return {'text': text, 'applied': [], 'revision': SPOKEN_FORM_REVISION}
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(t) for t in sorted(terms, key=lambda t: (-len(t), t))) + r')(?!\w)')
    applied = []
    def replace(match):
        term = match.group(0)
        applied.append({'term': term, 'spokenForm': terms[term], 'start': match.start(), 'end': match.end()})
        return terms[term]
    return {'text': pattern.sub(replace, text), 'applied': applied, 'revision': SPOKEN_FORM_REVISION}

def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,160}',value): raise PronunciationError('invalid_id')
    return value

def _text(value, maximum=600):
    if not isinstance(value,str) or not 1 <= len(value.strip()) <= maximum: raise PronunciationError('invalid_text')
    return value

def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def capabilities(engine, model, voice):
    """Controls exposed by current repository adapters, not theoretical engine features."""
    _id(engine); _id(model); _id(voice)
    known = engine in ('sapi','local_neural','elevenlabs')
    state = 'unsupported' if known else 'unknown'
    return {'engine':engine,'model':model,'voice':voice,'aliases':state,'phonemes':state,'rate':'supported' if engine == 'local_neural' else state,'alignment':state,'incremental':state,'output':'buffered_wav' if known else 'unknown'}

def new_rule_set(rule_set_id, owner_id, scope):
    _id(rule_set_id); _id(owner_id)
    if scope not in ('private','shared'): raise PronunciationError('invalid_scope')
    return {'ruleSetId':rule_set_id,'ownerId':owner_id,'scope':scope,'revision':0,'rules':[]}

def update_rules(rule_set, expected_revision, rules, actor, authorize):
    if not callable(authorize) or authorize('manage_rules', actor, copy.deepcopy(rule_set)) is not True: raise PronunciationError('forbidden_or_revoked')
    if type(expected_revision) is not int or expected_revision != rule_set['revision']: raise PronunciationError('stale_rules')
    if not isinstance(rules,list) or len(rules)>100: raise PronunciationError('invalid_rules')
    seen=set(); normalized=[]
    for rule in rules:
        if not isinstance(rule,dict) or set(rule) != {'id','language','term','alias','approved'}: raise PronunciationError('invalid_rule')
        rid=_id(rule['id']); term=_text(rule['term'],100); alias=_text(rule['alias'],100)
        if rid in seen or rule['language'] not in ('en','es') or type(rule['approved']) is not bool: raise PronunciationError('invalid_rule')
        # Explicit creator approval applies only to exact, case-sensitive whole-term occurrences.
        if any(c in term+alias for c in '<>\r\n'): raise PronunciationError('invalid_rule')
        seen.add(rid); normalized.append({'id':rid,'language':rule['language'],'term':term,'alias':alias,'approved':rule['approved']})
    result=copy.deepcopy(rule_set); result['revision']+=1; result['rules']=normalized
    return result

def resolve_rules(rule_set, request, actor, authorize):
    if not callable(authorize) or authorize('use_rules',actor,copy.deepcopy(rule_set),copy.deepcopy(request)) is not True: raise PronunciationError('forbidden_or_revoked')
    if request.get('ruleSetRevision') != rule_set['revision'] or type(request.get('ruleSetRevision')) is not int: raise PronunciationError('stale_rules')
    if request.get('scope') != rule_set['scope']: raise PronunciationError('scope_mismatch')
    text=_text(request.get('text')); language=request.get('language')
    if language not in ('en','es'): raise PronunciationError('invalid_language')
    for k in ('requestId','engine','model','modelVersion','voiceId','voiceVersion','adapterVersion','sourceId'): _id(request.get(k))
    if request.get('outputFormat') != 'audio/wav': raise PronunciationError('unsupported_output_format')
    if type(request.get('sourceRevision')) is not int or not 1 <= request['sourceRevision'] <= 1000000: raise PronunciationError('invalid_revision')
    rate=request.get('rate',1.0)
    if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not math.isfinite(rate) or not .5 <= rate <= 2: raise PronunciationError('invalid_rate')
    caps=capabilities(request['engine'],request['model'],request['voiceId'])
    matches=[]
    for rule in rule_set['rules']:
        if rule['approved'] and rule['language']==language and re.search(r'(?<!\w)'+re.escape(rule['term'])+r'(?!\w)',text): matches.append(copy.deepcopy(rule))
    controls=request.get('controls',[])
    if not isinstance(controls,list) or len(controls)>5 or any(not isinstance(x,str) or x not in ('aliases','phonemes','rate','alignment','incremental') for x in controls) or len(set(controls)) != len(controls): raise PronunciationError('invalid_controls')
    needed=set(controls)
    if matches: needed.add('aliases')
    if rate != 1: needed.add('rate')
    unavailable={k:caps[k] for k in sorted(needed) if (k != 'aliases' or k in controls) and caps[k] != 'supported'}
    if caps['output'] == 'unknown': unavailable['engine'] = 'unknown'
    identity={'ruleSetId':rule_set['ruleSetId'],'ruleSetRevision':rule_set['revision'],'ruleDigest':_hash(rule_set['rules']),'scope':request['scope'],'engine':request['engine'],'model':request['model'],'modelVersion':request['modelVersion'],'voiceId':request['voiceId'],'voiceVersion':request['voiceVersion'],'adapterVersion':request['adapterVersion'],'outputFormat':request['outputFormat'],'language':language,'rate':rate,'sourceId':request['sourceId'],'sourceRevision':request['sourceRevision'],'textHash':hashlib.sha256(text.encode()).hexdigest(),'controls':sorted(needed)}
    prepared = prepare_spoken_text(text, language, rule_set['rules'])
    if any(rule['approved'] for rule in rule_set['rules']):
        identity['spokenFormRevision'] = SPOKEN_FORM_REVISION
    return {'requestId':request['requestId'],'originalText':text,'spokenText':prepared['text'],'spokenFormPreparation':prepared,'matchedRules':matches,'capabilities':caps,'unavailableControls':unavailable,'identity':identity,'generationKey':_hash(identity),'ready':not unavailable,'alignment':None}

def prepare_preview(rule_set, request, actor, authorize, existing=None):
    """Pure preparation: PRIMARY atomically stores intent and invokes its existing admission."""
    result=resolve_rules(rule_set,request,actor,authorize)
    intent={'requestId':result['requestId'],'generationKey':result['generationKey'],'ruleSetRevision':rule_set['revision'],'scope':rule_set['scope'],'status':'prepared'}
    if existing is not None and existing != intent: raise PronunciationError('duplicate_conflict')
    if not result['ready']: raise PronunciationError('unsupported_or_unknown_controls')
    return intent,result

def check_fence(rule_set, intent, request, actor, authorize):
    """Call under PRIMARY's transaction immediately before dispatch and delivery/reuse."""
    result=resolve_rules(rule_set,request,actor,authorize)
    if not result['ready'] or intent.get('requestId') != result['requestId'] or intent.get('generationKey') != result['generationKey'] or intent.get('scope') != rule_set['scope']: raise PronunciationError('stale_or_ineligible')
    return result

