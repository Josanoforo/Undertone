"""Selected saved-frame grounding. No capture, provider, or HTTP operation."""
import copy, math
from .phase10_common import Phase10Error, parse_ref
from . import phase10_vision

def fail(code,message,status=422): raise Phase10Error(code,message,status)
def png_metadata(image):
    """Read a bounded PNG's actual IHDR; reject unsupported orientation metadata."""
    import base64, binascii, struct, zlib
    try:
        if not isinstance(image,dict) or image.get('mimeType')!='image/png': raise ValueError()
        raw=base64.b64decode(image['data'],validate=True)
        if len(raw)>4*1024*1024 or not raw.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError()
        pos=8; width=height=None; seen_data=False; ended=False
        while pos+12<=len(raw):
            length=struct.unpack_from('>I',raw,pos)[0]; end=pos+12+length
            if end>len(raw): raise ValueError()
            kind=raw[pos+4:pos+8]; data=raw[pos+8:pos+8+length]
            if zlib.crc32(kind+data)&0xffffffff!=struct.unpack_from('>I',raw,pos+8+length)[0]: raise ValueError()
            if pos==8:
                if kind!=b'IHDR' or length!=13: raise ValueError()
                width,height=struct.unpack_from('>II',data)
                if not 1<=width<=16384 or not 1<=height<=16384: raise ValueError()
            elif kind==b'IHDR': raise ValueError()
            if kind in (b'eXIf',b'acTL'): raise ValueError()
            if kind==b'IDAT': seen_data=True
            if kind==b'IEND':
                if length or end!=len(raw): raise ValueError()
                ended=True; break
            pos=end
        if not ended or not seen_data: raise ValueError()
        return {'width':width,'height':height,'orientation':0}
    except (KeyError,TypeError,ValueError,binascii.Error,struct.error):
        fail('image_metadata_unavailable','Supported PNG metadata is unavailable.',409)

def rectangle(box):
    if not isinstance(box,dict) or set(box)!={'x','y','width','height'}: fail('invalid_region','Select a rectangular region.')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in box.values()): fail('invalid_region','Invalid region coordinates.')
    x,y,w,h=(box[k] for k in ('x','y','width','height'))
    if x<0 or y<0 or w<=0 or h<=0 or x+w>1 or y+h>1: fail('invalid_region','Region must fit inside the frame.')
    return dict(box)
def ground(ctx, frame, regions, metadata, vision=None, ocr=None, stable_interval=None):
    """Resolve and recheck a saved Phase 10 frame; adapters receive row and regions.

    The caller owns paid-call admission, unknown receipts and any storage. No image
    bytes are returned or persisted here. OCR is optional and explicitly labeled.
    """
    if not isinstance(frame,dict) or set(frame)!={'ref','frameId','captureRunId','frameTimeMs','width','height','orientation'}: fail('invalid_frame','Invalid frame metadata.')
    ref=parse_ref(frame['ref'])
    if ref['sessionId']!=ctx.sid or frame['frameId']!=ref['momentId'] or type(frame['frameTimeMs']) is not int or frame['frameTimeMs']!=ref['startMs'] or ref['startMs']!=ref['endMs']: fail('invalid_frame','Frame time or identity does not match the source.')
    if any(type(frame[k]) is not int or not 1<=frame[k]<=16384 for k in ('width','height')) or frame['orientation'] not in (0,90,180,270): fail('invalid_frame','Invalid frame dimensions or orientation.')
    if not isinstance(frame['captureRunId'],str) or not frame['captureRunId'] or len(frame['captureRunId'])>128: fail('invalid_frame','Invalid capture run.')
    if not isinstance(regions,list) or not 1<=len(regions)<=8: fail('invalid_region','Select one to eight regions.')
    checked=[]; ids=set()
    for r in regions:
        if not isinstance(r,dict) or set(r)!={'regionId','box'} or not isinstance(r['regionId'],str) or not 1<=len(r['regionId'])<=128 or r['regionId'] in ids: fail('invalid_region','Invalid region identity.')
        ids.add(r['regionId']); checked.append({'regionId':r['regionId'],'box':rectangle(r['box'])})
    if stable_interval is not None:
        if not isinstance(stable_interval,dict) or set(stable_interval)!={'captureRunId','startMs','endMs'} or stable_interval['captureRunId']!=frame['captureRunId'] or any(type(stable_interval[k]) is not int for k in ('startMs','endMs')) or not 0<=stable_interval['startMs']<=frame['frameTimeMs']<=stable_interval['endMs']: fail('alignment_unavailable','Stable interval does not contain this frame.',409)
    with ctx.lock:
        ctx.check_actor(); row=ctx.resolve([ref])[0]; actual=phase10_vision.frame(row)
        if actual.get('captureRunId')!=frame['captureRunId']: fail('alignment_unavailable','Capture run changed.',409)
        image=copy.deepcopy(row['source']['image'])
        # Source metadata must be trusted and bound by PRIMARY, never client asserted.
        meta=metadata(copy.deepcopy(image))
        if any(meta.get(k)!=frame[k] for k in ('width','height','orientation')): fail('invalid_frame','Verified frame dimensions or orientation unavailable.',409)
    out=[]
    for region in checked:
        entry={'regionId':region['regionId'],'frameId':frame['frameId'],'box':region['box'],'observations':[],'ocr':[],'ocrStatus':'unavailable' if ocr is None else 'available','inferences':[],'uncertainty':['The cause is unknown unless supported by explicit evidence.']}
        if vision is not None:
            # Adapter returns the actual phase10_vision.call result or compatible pair.
            result=vision(row,region['box'])
            data=result[0] if isinstance(result,tuple) else result
            if not isinstance(data,dict) or set(data)!={'text','uncertain'} or not isinstance(data['text'],str) or not 1<=len(data['text'].strip())<=6000 or type(data['uncertain']) is not bool: fail('invalid_vision','Vision output unavailable.',503)
            inference={'text':data['text'].strip(),'evidenceRefs':[ref]}
            if isinstance(result,tuple) and len(result)==3: inference['provider'],inference['model']=result[1:]
            entry['inferences'].append(inference)
            if data['uncertain']: entry['uncertainty'].append('The visual description is uncertain.')
        if ocr is not None:
            values=ocr(row,region['box'])
            if not isinstance(values,list) or len(values)>100: fail('invalid_ocr','OCR output unavailable.',503)
            for v in values:
                if not isinstance(v,dict) or set(v)!={'text','box','confidence'} or not isinstance(v['text'],str) or not 1<=len(v['text'])<=1000 or (v['confidence'] is not None and (type(v['confidence']) not in (int,float) or not math.isfinite(v['confidence']) or not 0<=v['confidence']<=1)): fail('invalid_ocr','OCR output unavailable.',503)
                b=rectangle(v['box']); rb=region['box']
                if b['x']<rb['x'] or b['y']<rb['y'] or b['x']+b['width']>rb['x']+rb['width'] or b['y']+b['height']>rb['y']+rb['height']: fail('invalid_ocr','OCR box is outside the selected region.',503)
                entry['ocr'].append({'text':v['text'],'box':b,'confidence':v['confidence']})
        out.append(entry)
    with ctx.lock:
        ctx.check_actor(); fresh=ctx.resolve([ref])[0]; fresh_frame=phase10_vision.frame(fresh)
        if fresh_frame.get('captureRunId')!=frame['captureRunId'] or fresh['source'].get('image')!=image or metadata(copy.deepcopy(fresh['source']['image']))!=meta: fail('stale_context','Frame changed during inspection.',409)
    return {'frame':copy.deepcopy(frame),'regions':out,'alignment':{'status':'stable_interval' if stable_interval else 'frame_only','interval':copy.deepcopy(stable_interval)},'limitations':['Original frame is the evidence; image descriptions and OCR may be wrong.']}

def project(ctx, result, metadata):
    """Fail closed on every later serialization, including historic projections."""
    try:
        ref=parse_ref(result['frame']['ref'])
        with ctx.lock:
            ctx.check_actor(); row=ctx.resolve([ref])[0]; actual=phase10_vision.frame(row)
            f=result['frame']; meta=metadata(copy.deepcopy(row['source']['image']))
            if actual.get('captureRunId')!=f['captureRunId'] or any(meta.get(k)!=f[k] for k in ('width','height','orientation')): raise ValueError()
            return copy.deepcopy(result)
    except (Phase10Error,KeyError,TypeError,ValueError):
        return {'status':'unavailable'}



def ground_once(ctx, request_id, frame, regions, metadata, vision=None, ocr=None, stable_interval=None):
    """Use the existing Phase 10 generation receipt and admission boundary."""
    ref=parse_ref(frame.get('ref') if isinstance(frame,dict) else None)
    payload={'frame':frame,'regions':regions,'stableInterval':stable_interval}
    def invoke(_rows):
        return ground(ctx,frame,regions,metadata,vision,ocr,stable_interval)
    status,result=ctx.generate('w21.visual.ground',request_id,payload,[ref],invoke)
    safe=project(ctx,result,metadata)
    if safe.get('status')=='unavailable': fail('stale_context','The selected frame is unavailable.',409)
    return status,safe

