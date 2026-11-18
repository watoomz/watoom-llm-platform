"""Independent bounded DBPF container implementation; no typed TS4 codecs.
Format evidence: Kuree/Sims4Tools wiki DBPF-Format and thequux/s4py reader.
Only 2.0/2.1, index v3, shared T/G/instance-high and optional compression tails.
Unknown compressed bytes survive rebuild; only uncompressed and zlib decode.
"""
import hashlib, struct, zlib
from pathlib import Path

class PackageError(ValueError): pass
MAX_ENTRIES = 200000
MAX_INDEX = 16 * 1024 * 1024
MAX_RESOURCE = 64 * 1024 * 1024

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def key(t, g, i): return f'{t:08X}:{g:08X}:{i:016X}'

def parse_key(value):
    if not isinstance(value, str): raise PackageError('Invalid resource key')
    p = value.split(':')
    if len(p) != 3 or [len(x) for x in p] != [8,8,16]: raise PackageError('Use TTTTTTTT:GGGGGGGG:IIIIIIIIIIIIIIII')
    try: result = tuple(int(x,16) for x in p)
    except ValueError: raise PackageError('Invalid hex resource key')
    if any(x < 0 or x >= 1 << bits for x,bits in zip(result,(32,32,64))): raise PackageError('Resource key out of range')
    return result

class Package:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink() or not self.path.is_file(): raise PackageError('Regular package required')
        self.stat = self.path.stat()
        with self.path.open('rb') as f:
            self.header = f.read(96)
            if len(self.header) != 96 or self.header[:4] != b'DBPF': raise PackageError('Invalid DBPF header')
            self.version = struct.unpack_from('<II', self.header,4)
            if self.version not in ((2,0),(2,1)): raise PackageError('Unsupported DBPF version')
            count = struct.unpack_from('<I',self.header,36)[0]
            low, size = struct.unpack_from('<II',self.header,40)
            iv, pos = struct.unpack_from('<II',self.header,60)
            if iv != 3: raise PackageError('Unsupported index version')
            pos = pos or low
            if count > MAX_ENTRIES or size > MAX_INDEX: raise PackageError('Index limit exceeded')
            if count and (pos < 96 or pos + size > self.stat.st_size): raise PackageError('Index out of bounds')
            if not count:
                if size not in (0,4): raise PackageError('Invalid empty index')
                self.entries = []; return
            f.seek(pos); data = f.read(size)
        at = 0
        def u32():
            nonlocal at
            if at + 4 > len(data): raise PackageError('Truncated index')
            v = struct.unpack_from('<I',data,at)[0]; at += 4; return v
        flags = u32()
        if flags & ~7: raise PackageError('Unsupported shared index flags')
        shared = {n:u32() for n in range(3) if flags & (1 << n)}
        entries = []; seen = set(); ranges = []
        for _ in range(count):
            values = [shared[n] if n in shared else u32() for n in range(3)]
            lo, offset, packed, memory = u32(), u32(), u32(), u32()
            tail = u32() if packed & 0x80000000 else 0x00010000
            comp, committed = tail & 65535, tail >> 16
            length = packed & 0x7fffffff
            ident = key(values[0],values[1],(values[2]<<32)|lo)
            if ident in seen: raise PackageError('Duplicate resource key')
            if length and (offset < 96 or offset + length > self.stat.st_size): raise PackageError('Resource out of bounds')
            if length and offset < pos+size and offset+length > pos: raise PackageError('Resource overlaps index')
            seen.add(ident)
            if length: ranges.append((offset,offset+length))
            entries.append(dict(key=ident,offset=offset,stored_size=length,memory_size=memory,compression=comp,committed=committed,extended=bool(packed & 0x80000000)))
        if at != len(data): raise PackageError('Unexpected index trailing bytes')
        ranges.sort()
        if any(b[0] < a[1] for a,b in zip(ranges,ranges[1:])): raise PackageError('Overlapping resource data unsupported')
        self.entries = entries
        self.unchanged()
    def unchanged(self):
        s = self.path.stat()
        if (s.st_size,s.st_mtime_ns) != (self.stat.st_size,self.stat.st_mtime_ns): raise PackageError('Source changed')
    def raw(self, entry, limit=MAX_RESOURCE):
        if entry['stored_size'] > limit: raise PackageError('Resource size limit exceeded')
        self.unchanged()
        with self.path.open('rb') as f: f.seek(entry['offset']); raw = f.read(entry['stored_size'])
        if len(raw) != entry['stored_size']: raise PackageError('Truncated resource')
        return raw
    def decoded(self, entry):
        raw = self.raw(entry); size = entry['memory_size']
        if size > MAX_RESOURCE: raise PackageError('Decompression limit exceeded')
        c = entry['compression']
        if c == 0: result = raw
        elif c == 0x5a42:
            z = zlib.decompressobj(); result = z.decompress(raw,size+1)
            if len(result) > size or z.unconsumed_tail or not z.eof or z.unused_data: raise PackageError('Invalid or oversized zlib payload')
        else: raise PackageError(f'Unsupported compression {c:04X}; raw extraction available')
        if len(result) != size: raise PackageError('Decoded size mismatch')
        return result
    def inventory(self):
        return dict(format='DBPF',version=list(self.version),resources=self.entries,typed_resource_validation='NOT_RUN',game_compatibility='UNVERIFIED')

def rebuild(source, destination, replacements=None):
    """Fresh container; opaque unchanged streams and flags retained exactly."""
    replacements = replacements or {}
    known = {x['key'] for x in source.entries}
    if set(replacements)-known: raise PackageError('Replacement key absent from source')
    out = Path(destination)
    if out.exists() or out.is_symlink(): raise PackageError('Fresh output required')
    index = []; offset = 96
    with out.open('xb') as f:
        f.write(source.header)
        for entry in source.entries:
            e = dict(entry)
            if e['key'] in replacements:
                replacement = Path(replacements[e['key']])
                if replacement.stat().st_size > MAX_RESOURCE: raise PackageError('Replacement too large')
                raw = replacement.read_bytes()
                if len(raw) > MAX_RESOURCE: raise PackageError('Replacement too large')
                e.update(compression=0,memory_size=len(raw),stored_size=len(raw),extended=True,committed=1)
            else: raw = source.raw(e)
            e['offset'] = offset; f.write(raw); offset += len(raw); index.append(e)
        if offset >= 0x100000000: raise PackageError('32-bit offset overflow')
        f.write(struct.pack('<I',0))
        for e in index:
            t,g,i = parse_key(e['key']); packed = e['stored_size'] | (0x80000000 if e['extended'] else 0)
            f.write(struct.pack('<7I',t,g,i>>32,i&0xffffffff,e['offset'],packed,e['memory_size']))
            if e['extended']: f.write(struct.pack('<HH',e['compression'],e['committed']))
        end = f.tell(); header = bytearray(source.header)
        struct.pack_into('<III',header,36,len(index),0,end-offset)
        struct.pack_into('<II',header,60,3,offset)
        # The new compact file has no inherited hole table.
        header[48:60] = bytes(12)
        f.seek(0); f.write(header)
    source.unchanged()
    target = Package(out)
    if [x['key'] for x in target.entries] != [x['key'] for x in source.entries]: raise PackageError('Resource identity changed')
    for a,b in zip(source.entries,target.entries):
        expected = Path(replacements[a['key']]).read_bytes() if a['key'] in replacements else source.raw(a)
        if target.raw(b) != expected: raise PackageError('Roundtrip bytes mismatch')
    return target
