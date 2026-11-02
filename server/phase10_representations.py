"""On-demand private representations of one exact source moment."""
import re
from .phase10_common import Phase10Error, parse_ref
from .phase10_vision import call, frame

LANG=re.compile(r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$',re.ASCII)
KINDS={'concise','detailed','translation','visual_description'}

def selected_evidence(rows, kind):
    """Keep frame context explicitly authored, never relabel it as ASR/vision."""
    row=rows[0]; source=row['source']; moment=row['moment']
    is_frame=bool(source.get('p10Frame'))
    if is_frame: frame(row)
    text=str(source.get('text','') if is_frame else moment.get('text','')).strip()
    basis='creator_frame_context' if is_frame and text else 'selected_frame' if is_frame else 'moment_text'
    original={'ref':row['ref'],'text':text,'language':source.get('language') or 'und','basis':basis}
    if kind!='visual_description':
        if not text:
            raise Phase10Error('context_unavailable','Text for this exact moment is unavailable. Select an authorized text context or request its frame description.',409)
        rows=[{**row,'moment':{**moment,'text':text}}]
    return rows,original

def handle(method,path_parts,body,context):
    if method!='POST' or path_parts!=['representations']: return None
    if not isinstance(body,dict) or set(body)-{'ref','kind','language','clientRequestId'} or not {'ref','kind','clientRequestId'}<=set(body): raise Phase10Error('invalid_field','Select a moment and representation.')
    ref=parse_ref(body['ref']);kind=body['kind'];language=body.get('language','en')
    if not isinstance(kind,str) or kind not in KINDS: raise Phase10Error('invalid_field','The representation kind is invalid.')
    if not isinstance(language,str) or len(language)>35 or not LANG.fullmatch(language): raise Phase10Error('invalid_language','Enter a valid language tag.')
    with context.lock:
        rows=context.resolve([ref])
        if kind=='visual_description': frame(rows[0])
        selected_evidence(rows,kind)
    def invoke(rows):
        images=None
        if kind=='visual_description':
            with context.lock:
                rows=context.resolve([ref]);frame(rows[0]);images=[rows[0]['source']['image']]
        rows,original=selected_evidence(rows,kind)
        instructions={'concise':'Give a concise explanation of the selected moment.','detailed':'Give a detailed explanation of the selected moment.','translation':'Translate the selected source text faithfully, without adding information.','visual_description':'Describe only what is visibly supported by the image. State visual ambiguity.'}
        instruction=instructions[kind]+' Use language tag '+language+'.'
        if original['basis']=='creator_frame_context':
            instruction+=' The source text is creator-authored context for this exact frame, not ASR or a visual observation. Preserve its facts, negation, quantities and dates; do not add a reason or advice.'
        data,name,model=call(rows,instruction,images)
        if images:
            with context.lock:
                fresh=context.resolve([ref]);frame(fresh[0])
                if fresh[0]['source']['image']!=images[0]: raise Phase10Error('stale_context','The selected frame changed during generation.',409)
        return {'representation':{'kind':kind,'language':language,'text':data['text'].strip(),'ref':ref},'original':original,'citations':context.citations(rows),'provider':name,'model':model,'limitations':['Only the selected moment was considered; source alignment and transcription may be uncertain.','Language coverage has not been universally validated.']+(['Frame text is creator-authored context, not ASR or an inferred visual fact.'] if original['basis']=='creator_frame_context' else [])+(['The image evidence is ambiguous.'] if data['uncertain'] else [])}
    return context.generate('representations',body['clientRequestId'],body,[ref],invoke)
