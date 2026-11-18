#!/usr/bin/env python3
"""Download owner-requested free itch.io archives pinned in sources.json; skips verified downloads, executes nothing."""
import http.cookiejar,json,re,sys,urllib.parse,urllib.request
from pathlib import Path
from archive import sha
spec=json.loads(Path(__file__).with_name('sources.json').read_text());root=Path(spec['root'])/'.downloads'
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
opener.addheaders=[('User-Agent','watoom-game-template-catalogue')]
for e in spec['templates']:
 if 'itch_upload_id' not in e:continue
 d=root/e['id'];d.mkdir(parents=True,exist_ok=True);target=d/e['archive_name']
 if target.is_file() and not target.is_symlink() and sha(target)==e['archive_sha256']:print('VERIFIED '+e['id'],flush=True);continue
 page=opener.open(e['source_url'],timeout=60).read().decode('utf-8','replace')
 token=re.search(r'name="csrf_token" value="([^"]+)"',page)
 if not token or 'data-upload_id="%d"'%e['itch_upload_id'] not in page:raise ValueError('Upload not offered as a free download: '+e['id'])
 body=urllib.parse.urlencode({'csrf_token':token.group(1)}).encode()
 answer=json.load(opener.open(e['source_url'].rstrip('/')+'/file/%d?source=view_game&as_props=1&after_download_lightbox=true'%e['itch_upload_id'],body,timeout=60))
 if answer.get('external') or not str(answer.get('url','')).startswith('https://'):raise ValueError('Unexpected itch download response')
 part=target.with_name(target.name+'.part')
 with opener.open(answer['url'],timeout=600) as r,part.open('wb') as out:
  for block in iter(lambda:r.read(1024*1024),b''):out.write(block)
 digest=sha(part)
 if digest!=e['archive_sha256']:part.unlink();sys.exit('Archive hash differs from pinned source for '+e['id']+': '+digest)
 part.replace(target);print('DOWNLOADED '+e['id'],flush=True)
