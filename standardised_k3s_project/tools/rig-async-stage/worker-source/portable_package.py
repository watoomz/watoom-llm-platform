"""Create a derived glTF copy with local dependency URIs, preserving snapshots."""
import json, pathlib, posixpath, struct, urllib.parse, os

def rebase(source, original, mapping, output):
    source=pathlib.Path(source)
    if source.suffix.lower() not in ('.gltf','.glb'):return source
    chunks=[]
    if source.suffix.lower()=='.glb':
        raw=source.read_bytes();offset=12
        while offset<len(raw):
            size,kind=struct.unpack('<II',raw[offset:offset+8]);chunks.append((kind,raw[offset+8:offset+8+size]));offset+=8+size
        data=json.loads(chunks[0][1])
    else:data=json.loads(source.read_text())
    for item in data.get('buffers',[])+data.get('images',[]):
        uri=item.get('uri','')
        if not uri or uri.startswith('data:'):continue
        parsed=urllib.parse.urlparse(uri);name=urllib.parse.unquote(parsed.path)
        origin=posixpath.normpath(name if name.startswith('/') else posixpath.join(posixpath.dirname(original),name))
        if origin not in mapping:raise ValueError('Missing glTF dependency: '+origin)
        item['uri']=urllib.parse.quote(os.path.relpath(mapping[origin],output).replace('\\','/'),safe='/')
    target=pathlib.Path(output)/('derived-source'+source.suffix)
    if chunks:
        raw=json.dumps(data,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4);chunks[0]=(0x4e4f534a,raw)
        body=b''.join(struct.pack('<II',len(raw),kind)+raw for kind,raw in chunks)
        target.write_bytes(b'glTF'+struct.pack('<II',2,12+len(body))+body)
    else:target.write_text(json.dumps(data))
    return target
