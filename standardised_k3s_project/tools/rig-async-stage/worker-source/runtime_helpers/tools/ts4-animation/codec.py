"""Bounded TS4 CLIP wrapper v14 / _pilC3S_ v2 channel codec.
Format evidence: staged s4animtools serialization/channel/frame implementations.
Independent implementation; no addon imports or third-party runtime dependency.
"""
import struct,math,hashlib
MAX_BYTES=64*1024*1024
class CodecError(ValueError):pass

def finite(value):
 if not math.isfinite(value):raise CodecError('Nonfinite animation value')
 return value

def decode(data):
 if not isinstance(data,bytes) or not 48<=len(data)<=MAX_BYTES:raise CodecError('Clip size budget')
 base=data.find(b'_pilC3S_')
 if base<0:raise CodecError('CLIP codec body missing')
 if base:
  if base<16 or struct.unpack_from('<I',data,0)[0]!=14:raise CodecError('Unsupported CLIP wrapper version; only v14 qualified')
  if struct.unpack_from('<I',data,base-4)[0]!=len(data)-base:raise CodecError('Wrapper codec length mismatch')
  finite(struct.unpack_from('<f',data,8)[0])
 body=data[base:]
 def unpack(fmt,at):
  size=struct.calcsize(fmt)
  if at<0 or at+size>len(body):raise CodecError('Truncated codec data')
  return struct.unpack_from(fmt,body,at)
 magic,version,flags,tick,ticks,padding,count,pcount,channels_at,palette_at,name_at,source_at=unpack('<8sIIfHHIIIIII',0)
 if version!=2 or flags!=0 or padding!=0:raise CodecError('Unsupported codec version/flags')
 if not math.isfinite(tick) or not 0<tick<=1 or not ticks or not 0<=count<=4096 or pcount>1000000:raise CodecError('Clip budgets')
 header_end=channels_at+count*20
 if channels_at!=48 or not header_end<=name_at<source_at<=palette_at<=len(body) or palette_at+pcount*4>len(body):raise CodecError('Invalid header/name/palette ranges')
 def string(at,end):
  stop=body.find(b'\0',at,end)
  if stop<0 or stop-at>4096:raise CodecError('Invalid bounded clip string')
  try:return body[at:stop].decode('utf-8')
  except UnicodeError as error:raise CodecError('Invalid UTF8 clip name') from error
 name=string(name_at,source_at);source=string(source_at,palette_at)
 palette=[finite(x[0]) for x in struct.iter_unpack('<f',body[palette_at:palette_at+pcount*4])]
 tracks=[];regions=[];total=0;seen=set()
 sizes={18:(3,8),20:(4,12)}
 for i in range(count):
  start,bone,offset,scale,n,encoding,semantic=unpack('<IIffHBB',channels_at+20*i)
  finite(offset);finite(scale)
  if encoding not in sizes:raise CodecError('Unsupported channel encoding '+str(encoding))
  dimensions,stride=sizes[encoding];end=start+n*stride;total+=n
  if not n or n>ticks or total>250000 or start<palette_at+pcount*4 or end>len(body):raise CodecError('Channel frame range/budget')
  if (bone,semantic) in seen:raise CodecError('Duplicate target/subtarget channel')
  seen.add((bone,semantic));regions.append((start,end));frames=[];prior=-1
  for j in range(n):
   at=start+j*stride;frame,signs=unpack('<HH',at)
   if not prior<frame<ticks:raise CodecError('Unsorted/out-of-range frame tick')
   prior=frame
   if encoding==18:
    packed=unpack('<I',at+4)[0]
    if packed>>30:raise CodecError('Unsupported packed vector flags')
    values=[((packed>>(10*k))&1023)/1023 for k in range(3)]
   elif encoding==20:
    packed=unpack('<4H',at+4)
    if any(x>4095 for x in packed):raise CodecError('Quaternion quantization out of range')
    values=[x/4095 for x in packed]
   elif encoding in (3,4):
    indices=unpack('<'+'H'*dimensions,at+4)
    if any(x>=len(palette) for x in indices):raise CodecError('Palette index out of range')
    values=[palette[x] for x in indices]
   else:
    scalar=unpack('<H',at+4)[0]
    if scalar>255:raise CodecError('Unsupported scalar packing')
    values=[scalar/255]
   values=[finite(offset+scale*((-x) if signs&(1<<k) else x)) for k,x in enumerate(values)]
   frames.append({'tick':frame,'flags':signs,'values':values})
  tracks.append({'bone_hash':f'{bone:08X}','semantic':semantic,'encoding':encoding,'offset':offset,'scale':scale,'frames':frames})
 regions.sort()
 if any(b[0]<a[1] for a,b in zip(regions,regions[1:])):raise CodecError('Overlapping channel payloads')
 return {'schema':'watoom.ts4.clip.v1','source_sha256':hashlib.sha256(data).hexdigest(),'wrapper_version':14 if base else None,'body_offset':base,'name':name,'source_asset':source,'tick_seconds':tick,'ticks':ticks,'quaternion_order':'XYZW','tracks':tracks,'limits':'Channel codec only; wrapper events/namespaces preserved opaque; game/rig compatibility unverified'}

def encode(original,document):
 current=decode(original)
 if document==current:return original
 if set(document)!=set(current):raise CodecError('Document fields changed')
 if any(document[k]!=current[k] for k in current if k!='tracks'):raise CodecError('Only existing keyframe values may be edited')
 if not isinstance(document['tracks'],list) or len(document['tracks'])!=len(current['tracks']):raise CodecError('Track identity/count changed')
 result=bytearray(original);base=current['body_offset'];body=original[base:];channels_at=struct.unpack_from('<I',body,32)[0]
 for i,(before,after) in enumerate(zip(current['tracks'],document['tracks'])):
  if set(before)!=set(after) or any(before[k]!=after[k] for k in before if k!='frames') or len(before['frames'])!=len(after['frames']):raise CodecError('Track metadata changed')
  if before==after:continue
  encoding=before['encoding']
  if encoding not in (18,20):raise CodecError('Editing palette/scalar tracks is not qualified')
  dims,stride=(3,8) if encoding==18 else (4,12);maximum=1023 if encoding==18 else 4095;values=[]
  for a,b in zip(before['frames'],after['frames']):
   if set(a)!=set(b) or a['tick']!=b['tick'] or a['flags']!=b['flags'] or not isinstance(b['values'],list) or len(b['values'])!=dims:raise CodecError('Only frame values may change')
   for x in b['values']:
    if type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1000000:raise CodecError('Invalid edited channel value')
   if encoding==20 and not 0.98<=sum(x*x for x in b['values'])<=1.02:raise CodecError('Edited quaternion must be near unit length')
   values+=b['values']
  offset=(min(values)+max(values))/2;scale=(max(values)-min(values))/2 or 1.0
  offset,scale=struct.unpack('<ff',struct.pack('<ff',offset,scale));header=base+channels_at+i*20;start=base+struct.unpack_from('<I',result,header)[0];struct.pack_into('<ff',result,header+8,offset,scale)
  for j,frame in enumerate(after['frames']):
   normalized=[max(-1,min(1,(x-offset)/scale)) for x in frame['values']];signs=frame['flags']&~((1<<dims)-1)
   for k,x in enumerate(normalized):
    if x<0:signs|=1<<k
   packed=[int(math.floor(abs(x)*maximum)) for x in normalized];at=start+j*stride;struct.pack_into('<HH',result,at,frame['tick'],signs)
   if encoding==18:struct.pack_into('<I',result,at+4,packed[0]|packed[1]<<10|packed[2]<<20)
   else:struct.pack_into('<4H',result,at+4,*packed)
 decoded=decode(bytes(result))
 for target,actual in zip(document['tracks'],decoded['tracks']):
  tolerance=max(abs(actual['scale'])/(1023 if actual['encoding']==18 else 4095)*1.02,1e-6)
  for a,b in zip(target['frames'],actual['frames']):
   if any(abs(x-y)>tolerance for x,y in zip(a['values'],b['values'])):raise CodecError('Encoded channel failed roundtrip tolerance')
 return bytes(result)
