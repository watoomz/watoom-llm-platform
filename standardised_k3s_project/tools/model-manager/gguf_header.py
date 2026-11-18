"""Bounded metadata-only GGUF inspection; never loads tensors or executes models."""
import struct
from pathlib import Path
class HeaderError(ValueError):pass
def context_limit(path):
 with Path(path).open("rb") as f:
  def read(n):
   if n<0 or n>1024*1024 or f.tell()+n>8*1024*1024:raise HeaderError("GGUF metadata exceeds inspection bound")
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
  if read(4)!=b"GGUF" or number("I") not in (2,3):raise HeaderError("Supported GGUF header required")
  tensors=number("Q");count=number("Q")
  if count>100000:raise HeaderError("Oversized GGUF metadata count")
  for _ in range(count):
   key=string();kind=number("I")
   if key.endswith(".context_length"):
    if kind not in (4,10):raise HeaderError("Invalid GGUF context limit")
    value=number("I" if kind==4 else "Q")
    if not 512<=value<=1048576:raise HeaderError("Invalid GGUF context limit")
    return value
   skip(kind)
  return None
