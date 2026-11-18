#!/usr/bin/env python3
"""Read-only intent search across installed game templates."""
import argparse,json,re
from pathlib import Path

def search(entries,query,engine=None,category=None,limit=8):
 if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=32:raise ValueError('limit must be integer 1..32')
 terms=set(re.findall(r'[a-z0-9]+',query.lower()));out=[]
 for e in entries:
  if engine and e['engine']!=engine:continue
  if category and e['category']!=category:continue
  title=set(re.findall(r'[a-z0-9]+',' '.join([e['id'],e['name'],e['category'],*e['tags']]).lower()))
  body=set(re.findall(r'[a-z0-9]+',e['description'].lower()))
  score=sum(4 if t in title else 1 if t in body else 0 for t in terms)
  if not terms or score:out.append(dict(e,score=score))
 return sorted(out,key=lambda e:(-e['score'],e['id']))[:limit]
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('query');p.add_argument('--engine',choices=['godot','unreal']);p.add_argument('--category',choices=['rpg','fps','horror']);p.add_argument('--limit',type=int,default=8);p.add_argument('--catalogue',type=Path,default=Path('/data/ai/game_templates/catalogue.json'));a=p.parse_args()
 if not 1<=a.limit<=32:p.error('limit must be 1..32')
 print(json.dumps({'matches':search(json.loads(a.catalogue.read_text())['templates'],a.query,a.engine,a.category,a.limit)},indent=2))
