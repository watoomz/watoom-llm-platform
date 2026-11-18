"""Stdlib-only, fresh-output TS4 package extraction and bounded CLIP codec CLI."""
import argparse,json,sys,hashlib
from pathlib import Path
from dbpf import Package
from codec import decode,encode,MAX_BYTES

def read(path):
 p=Path(path).resolve(strict=True)
 if p.stat().st_size>MAX_BYTES:raise ValueError('Input size budget exceeded')
 return p.read_bytes()
def save(path,data):
 with Path(path).open('xb') as f:f.write(data)
def js(value):return (json.dumps(value,ensure_ascii=True,separators=(',',':'))+'\n').encode()
def main():
 a=argparse.ArgumentParser();sub=a.add_subparsers(dest='operation',required=True)
 for name in ('inspect','extract','decode','encode'):
  p=sub.add_parser(name);p.add_argument('--source',required=True)
  if name!='inspect':p.add_argument('--output',required=True)
  if name=='extract':p.add_argument('--decode-clips',action='store_true')
  if name=='encode':p.add_argument('--document',required=True)
 x=a.parse_args()
 if x.operation in ('inspect','extract'):
  p=Package(Path(x.source).resolve(strict=True));inventory=p.inventory()
  if x.operation=='inspect':p.unchanged();print(json.dumps(inventory));return 0
  out=Path(x.output);out.mkdir(parents=False,exist_ok=False);save(out/'inventory.json',js(inventory));failures=[];clips=0
  try:
   for e in p.entries:
    key=e['key'].replace(':','-');save(out/(key+'.stored'),p.raw(e))
    try:
     payload=p.decoded(e);save(out/(key+'.resource'),payload)
     if x.decode_clips and e['key'].startswith('6B20C4F3:'):
      doc=decode(payload);save(out/(key+'.clip.json'),js(doc));clips+=1
    except ValueError as error:failures.append({'key':e['key'],'error':str(error)})
   p.unchanged();receipt={'result':'PARTIAL' if failures else 'PASS','source':str(p.path),'resources':len(p.entries),'decoded_clips':clips,'errors':failures,'source_unchanged':True,'game_compatibility':'UNVERIFIED'}
   save(out/'result.json',js(receipt));print(json.dumps(receipt));return 2 if failures else 0
  except BaseException:
   save(out/'INCOMPLETE',b'Interrupted or failed. Preserve this directory; use a fresh output after diagnosis.\n');raise
 if x.operation=='decode':save(x.output,js(decode(read(x.source))))
 else:save(x.output,encode(read(x.source),json.loads(read(x.document))))
 print(json.dumps({'result':'PASS','output':str(Path(x.output).resolve()),'game_compatibility':'UNVERIFIED'}));return 0
if __name__=='__main__':
 try:sys.exit(main())
 except (ValueError,OSError,KeyError,TypeError) as error:print(json.dumps({'result':'BLOCKED','error':str(error)}),file=sys.stderr);sys.exit(1)
