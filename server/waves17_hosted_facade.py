"""Private hosted speech configuration boundary and conservative budget reservation.

No account is configured by default. Only a trusted in-process verifier may supply
an account snapshot, pricing and transport. Secrets must stay inside the transport.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib, json, re, uuid
from . import waves17_tts_elevenlabs as adapter
from scripts import shared_api_budget as budget

@dataclass(frozen=True)
class VerifiedAccount:
    config: adapter.Config
    account_verified: bool
    quota_verified: bool
    credential_available: bool
    quota_characters: int
    usd_per_character: str
    max_usd: str
    pricing_revision: str
    verification_revision: str

_account = None
_transport = None

def configure_verified(account, transport):
    """Trusted internal boundary: caller is responsible for actual account verification."""
    global _account, _transport
    validate(account, 1)
    if not callable(transport): raise ValueError('transport unavailable')
    _account, _transport = account, transport

def clear():
    global _account, _transport
    _account, _transport = None, None

def configure_released_profile():
    """Load the operator-released, integrity-checked profile in this process.

    This is opt-in at server startup and does not contact the provider or reserve
    funds. The released loader validates the profile digest before installing it.
    """
    import importlib.util
    from pathlib import Path
    loader = (Path(__file__).resolve().parent.parent /
              'sessions/mesa-02/WAVES21_22/M02_HOSTED/continuous-02/turn-04/load_profile.py')
    spec = importlib.util.spec_from_file_location('_released_hosted_profile', loader)
    if spec is None or spec.loader is None:
        raise RuntimeError('Released hosted profile loader unavailable')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.configure()
    except Exception:
        clear()
        raise RuntimeError('Released hosted profile unavailable or invalid') from None

def validate(account, characters):
    try:
        if not isinstance(account, VerifiedAccount) or any(x is not True for x in (account.account_verified, account.quota_verified, account.credential_available)):
            raise ValueError()
        c=account.config
        if not isinstance(c,adapter.Config) or c.available is not True or c.stock_voice_verified is not True or c.rights_verified is not True or c.format_verified is not True or c.model!=adapter.MODEL or not re.fullmatch(r'[A-Za-z0-9]{20}',c.voice_id) or not isinstance(c.model_version,str) or not 1<=len(c.model_version)<=160 or not isinstance(c.voice_version,str) or not 1<=len(c.voice_version)<=160 or not isinstance(c.languages,tuple) or not c.languages or any(x not in ('en','es') for x in c.languages): raise ValueError()
        if type(account.quota_characters) is not int or type(characters) is not int or characters<1 or account.quota_characters<characters: raise ValueError()
        if not all(isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',x) for x in (account.pricing_revision,account.verification_revision)): raise ValueError()
        rate=budget.money(account.usd_per_character); maximum=budget.money(account.max_usd)
        if rate<=0 or maximum<=0: raise ValueError()
        amount=(rate*characters).quantize(Decimal('.000001'),rounding=ROUND_CEILING)
        if amount<=0 or amount>maximum: raise ValueError()
        return format(amount,'f')
    except (ValueError,TypeError,InvalidOperation,budget.Refusal):
        raise ValueError('hosted configuration unavailable') from None

def current(characters):
    if _transport is None: raise ValueError('hosted configuration unavailable')
    return _account, _transport, validate(_account,characters)

def options():
    try:
        a,_,_=current(1)
        # The profile establishes a bounded configuration, not that this key
        # can synthesize or has an unexhausted key-specific allowance.
        return {'id':'elevenlabs','configured':True,'available':None,'reason':'synthesis_not_verified','languages':list(a.config.languages),'voices':[{'id':a.config.voice_id}],'model':a.config.model}
    except ValueError:
        return {'id':'elevenlabs','configured':False,'available':False,'reason':'account_or_pricing_not_verified','languages':['en','es']}

def binding(account):
    c=account.config
    return {'engine':'elevenlabs','voice':c.voice_id,'voiceVersion':c.voice_version,'model':c.model,'modelVersion':c.model_version,'adapterVersion':adapter.ADAPTER_REVISION,'outputFormat':adapter.FORMAT,'pricingRevision':account.pricing_revision,'verificationRevision':account.verification_revision}

def claim_id(row):
    raw=json.dumps([row['session_id'],row['actor_id'],row['credential_hash'],row['request_id'],row['fingerprint'],row['payload'],row['ref']],ensure_ascii=False,separators=(',',':')).encode()
    return 'tts-'+hashlib.sha256(raw).hexdigest()

def _source_binding(ref):
    """Return distinct opaque identities for a direct source and its revision.

    Direct moment refs carry both fields. Keep their values private and hash them
    before placing them in adapter metadata. Other typed selections are bound as
    an exact selection snapshot because their resolver owns the underlying rights.
    """
    try:
        value=json.loads(ref)
    except (TypeError,ValueError):
        raise ValueError('invalid source reference') from None
    if not isinstance(value,dict):
        raise ValueError('invalid source reference')
    source_id=value.get('sourceId')
    source_revision=value.get('sourceRevision')
    if (isinstance(source_id,str) and source_id and type(source_revision) is int
        and source_revision>0):
        identity={'sessionId':value.get('sessionId'),'sourceId':source_id}
        revision={'sourceRevision':source_revision}
        for key in ('momentId','startMs','endMs'):
            if key in value: revision[key]=value[key]
        return (hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                hashlib.sha256(json.dumps(revision,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    digest=hashlib.sha256(json.dumps({'sessionId':value.get('sessionId'),'selection':value},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return digest,digest

def reserve(cid,amount):
    return budget.operate(budget.DEFAULT,'reserve',cid=cid,amount=amount,posts=1)

def request(row,parent,text,payload):
    source_id,source_revision=_source_binding(row['ref'])
    revisions={'text_revision':hashlib.sha256(text.encode()).hexdigest(),'source_id':source_id,'source_revision':source_revision,'translation_id':parent['request_id'],'translation_revision':parent['fingerprint'],'terminology_revision':hashlib.sha256(parent['payload'].encode()).hexdigest()}
    rid=str(uuid.UUID(claim_id(row)[4:36]))
    return adapter.Request(text=text,language=payload['language'],voice_id=payload['voice'],model=payload['model'],settings={'stability':0.5,'similarity_boost':0.75,'style':0.0,'use_speaker_boost':True},revisions=revisions,request_id=rid)
