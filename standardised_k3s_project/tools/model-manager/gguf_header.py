"""Bounded metadata-only GGUF inspection; never loads tensors or executes models."""
import struct
from pathlib import Path
class HeaderError(ValueError):pass
BOUND=8*1024*1024
def inspect(path):
 """Architecture facts from the GGUF key/value header: general.architecture, general.type ("model"/"adapter"),
 adapter.type, <arch>.context_length and <arch>.nextn_predict_layers (> 0 = an MTP draft head is in the file).
 Reading stops at the inspection bound; the architecture keys precede the large tokenizer arrays, so a bound hit after
 them still yields a usable result (complete=False)."""
 found={"architecture":None,"type":None,"adapter_type":None,"context_length":None,"nextn_predict_layers":0,"complete":True,
        # vision projector (general.type mmproj): clip.has_vision_encoder and clip.vision.projection_dim, which must
        # equal the language model's embedding_length (T-0095)
        "vision_encoder":False,"projection_dim":None,
        # attention shape, for the KV-cache size per token (settings.fit_context)
        "block_count":None,"head_count":None,"head_count_kv":None,"key_length":None,"value_length":None,"embedding_length":None,
        "full_attention_interval":None,"sliding_window":None,"sliding_window_pattern":None}
 SHAPE={".block_count":"block_count",".attention.head_count":"head_count",".attention.head_count_kv":"head_count_kv",
        ".attention.key_length":"key_length",".attention.value_length":"value_length",".embedding_length":"embedding_length",
        ".full_attention_interval":"full_attention_interval",".attention.sliding_window":"sliding_window"}
 with Path(path).open("rb") as f:
  def read(n):
   if n<0 or n>1024*1024 or f.tell()+n>BOUND:raise HeaderError("GGUF metadata exceeds inspection bound")
   raw=f.read(n)
   if len(raw)!=n:raise HeaderError("Incomplete GGUF metadata")
   return raw
  def number(fmt):return struct.unpack("<"+fmt,read(struct.calcsize("<"+fmt)))[0]
  def string():return read(number("Q")).decode("utf-8")
  def skip(kind,depth=0):
   widths={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
   if kind in widths:read(widths[kind]);return
   if kind==8:string();return
   if kind==9 and depth<2:
    element=number("I");count=number("Q")
    if count>1000000:raise HeaderError("Oversized GGUF array")
    for _ in range(count):skip(element,depth+1)
    return
   raise HeaderError("Unsupported GGUF metadata type")
  def unsigned(kind,key):
   if kind not in (4,10):raise HeaderError("Invalid GGUF "+key)
   return number("I" if kind==4 else "Q")
  if read(4)!=b"GGUF" or number("I") not in (2,3):raise HeaderError("Supported GGUF header required")
  tensors=number("Q");count=number("Q")
  if count>100000:raise HeaderError("Oversized GGUF metadata count")
  try:
   for _ in range(count):
    key=string();kind=number("I")
    if key in ("general.architecture","general.type","adapter.type"):
     if kind!=8:raise HeaderError("Invalid GGUF "+key)
     found[{"general.architecture":"architecture","general.type":"type","adapter.type":"adapter_type"}[key]]=string()
    elif key.endswith(".context_length") and found["context_length"] is None:
     value=unsigned(kind,"context limit")
     if not 512<=value<=1048576:raise HeaderError("Invalid GGUF context limit")
     found["context_length"]=value
    elif found["architecture"] and key.startswith(found["architecture"]+".") and key[len(found["architecture"]):] in SHAPE and kind in (4,10):
     found[SHAPE[key[len(found["architecture"]):]]]=unsigned(kind,key)
    elif found["architecture"] and key==found["architecture"]+".attention.sliding_window_pattern" and kind==9:
     element=number("I");count=number("Q")
     if element!=7 or count>1024:raise HeaderError("Invalid GGUF sliding window pattern")
     found["sliding_window_pattern"]=[read(1)!=b"\x00" for _ in range(count)]
    elif key=="clip.has_vision_encoder" and kind==7:
     found["vision_encoder"]=read(1)!=b"\x00"
    elif key=="clip.vision.projection_dim" and kind in (4,10):
     found["projection_dim"]=unsigned(kind,key)
    elif key.endswith(".nextn_predict_layers"):
     value=unsigned(kind,"MTP layer count")
     if value>64:raise HeaderError("Invalid GGUF MTP layer count")
     found["nextn_predict_layers"]=value
    else:skip(kind)
  except HeaderError as error:
   if "inspection bound" not in str(error) or found["architecture"] is None:raise
   found["complete"]=False
 return found
def context_limit(path):
 return inspect(path)["context_length"]
