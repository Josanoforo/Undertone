"""Load an explicitly verified private account profile; never infer verification."""
import hashlib, json, os, re
from pathlib import Path
from . import waves17_tts_elevenlabs as adapter
from . import waves17_hosted_facade as facade
from . import waves17_elevenlabs_transport as transport

def configure():
    root=Path(__file__).resolve().parent.parent
    runtime=root/'.runtime'
    profile=runtime/'credentials'/'verified-account.json'
    for item in (runtime,profile.parent,profile):
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():
            raise ValueError('private profile reparse path')
    expected=os.environ.get('APP_HOSTED_PROFILE_SHA256','')
    if not re.fullmatch(r'[0-9a-f]{64}',expected):
        raise ValueError('verified profile digest required')
    if profile.stat().st_size>16384: raise ValueError('profile too large')
    raw=profile.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('profile revision mismatch')
    data=json.loads(raw)
    config=data.pop('config')
    config['languages']=tuple(config['languages'])
    account=facade.VerifiedAccount(config=adapter.Config(**config),**data)
    facade.validate(account,1)
    facade.configure_verified(account,transport.transport)
    return facade.binding(account)
