#!/usr/bin/env python3
"""Explicit offline mesh ingestion/preparation; generation never calls the router."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

PROJECT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT / "config/llm/llama-mesh-workflow.json"
CONTROLLER_CONFIG = Path("/data/ai/helper-scripts/config/gpu-controller.json")

class MeshError(ValueError):
    pass

def extract_response(raw):
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        if raw.lstrip().startswith(('{', '[')):
            raise MeshError("Malformed JSON response; export plain OBJ or complete API JSON")
        return raw, None
    if not isinstance(payload, dict) or not payload.get("choices"):
        raise MeshError("Expected complete OpenAI-compatible response JSON")
    if len(payload["choices"]) != 1:
        raise MeshError("Expected one completion")
    choice = payload["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise MeshError("Completion is truncated or incomplete; finish_reason must be stop")
    text = choice.get("message", {}).get("content", choice.get("text"))
    if not isinstance(text, str):
        raise MeshError("Completion has no text content")
    return text, payload.get("model")

def parse_obj(text):
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    if blocks:
        candidates = [b for b in blocks if re.search(r"^\s*v\s+", b, re.M)]
        if len(candidates) != 1:
            raise MeshError("Expected exactly one mesh code block")
        text = candidates[0]
    vertices, faces, warnings = [], [], []
    started = False
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v":
            started = True
            if len(parts) != 4:
                raise MeshError(f"Line {number}: vertex must have three coordinates")
            try:
                xyz = tuple(float(x) for x in parts[1:])
            except ValueError:
                raise MeshError(f"Line {number}: invalid coordinate")
            if not all(math.isfinite(x) and abs(x) <= 1e8 for x in xyz):
                raise MeshError(f"Line {number}: non-finite or excessive coordinate")
            vertices.append(xyz)
        elif tag == "f":
            started = True
            if len(parts) < 4:
                raise MeshError(f"Line {number}: face requires at least three vertices")
            face = []
            for token in parts[1:]:
                try:
                    value = int(token.split('/')[0])
                except ValueError:
                    raise MeshError(f"Line {number}: invalid face index")
                # OBJ negative indices refer to vertices already defined at this line.
                if value < 0:
                    value = len(vertices) + value + 1
                if value <= 0:
                    raise MeshError(f"Line {number}: zero or invalid negative index")
                face.append(value - 1)
            if len(set(face)) != len(face):
                raise MeshError(f"Line {number}: repeated vertex within face")
            faces.append(face)
        elif tag in {"vt", "vn", "o", "g", "s", "mtllib", "usemtl"}:
            warnings.append("Input UVs/normals/material references discarded; this workflow imports geometry only")
        elif started and not line.startswith('```'):
            # Stop at ordinary trailing prose, but reject malformed geometry-looking records.
            if tag.startswith(('v', 'f')) and re.match(r'^[vf]\d', tag):
                raise MeshError(f"Line {number}: malformed OBJ record")
            warnings.append("Non-geometry text ignored")
    if len(vertices) < 3 or not faces:
        raise MeshError("No complete mesh: need at least three vertices and one face")
    if len(vertices) > 100000 or len(faces) > 100000:
        raise MeshError("Mesh exceeds offline validation limits")
    edges = Counter()
    seen = set()
    used = set()
    for face in faces:
        if any(i >= len(vertices) for i in face):
            raise MeshError("Face references a vertex outside the mesh")
        signature = tuple(sorted(face))
        if signature in seen:
            raise MeshError("Duplicate face")
        seen.add(signature)
        used.update(face)
        normal = [0.0, 0.0, 0.0]
        for i, j in zip(face, face[1:] + face[:1]):
            a, b = vertices[i], vertices[j]
            normal[0] += (a[1]-b[1])*(a[2]+b[2])
            normal[1] += (a[2]-b[2])*(a[0]+b[0])
            normal[2] += (a[0]-b[0])*(a[1]+b[1])
            edges[tuple(sorted((i, j)))] += 1
        if sum(n*n for n in normal) <= 1e-24:
            raise MeshError("Zero-area or invalid polygon")
    if any(n == 1 for n in edges.values()):
        warnings.append("Open boundary edges: inspect mesh before using collision")
    if any(n > 2 for n in edges.values()):
        warnings.append("Non-manifold edges: repair geometry before production use")
    if len(used) != len(vertices):
        warnings.append("Unused vertices")
    extent = max(max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in range(3))
    if extent <= 0:
        raise MeshError("Mesh has no spatial extent")
    obj = ''.join('v ' + ' '.join(format(x, '.9g') for x in v) + '\n' for v in vertices)
    obj += ''.join('f ' + ' '.join(str(i+1) for i in f) + '\n' for f in faces)
    return {"vertices": vertices, "faces": faces, "warnings": sorted(set(warnings)), "obj": obj}

def read_limited(path, limit):
    if path.stat().st_size > limit:
        raise MeshError("Input exceeds configured size limit")
    return path.read_text(encoding='utf-8')

def config(args):
    cfg = json.loads(args.config.read_text())
    if cfg.get('schema_version') != 1:
        raise MeshError("Unsupported workflow config")
    root = Path(cfg['output_root'])
    if not root.is_absolute():
        raise MeshError("output_root must be absolute")
    return cfg

def save_run(raw, cfg, label, prompt=None):
    text, model = extract_response(raw)
    mesh = parse_obj(text)  # Validate before creating an asset directory.
    safe = re.sub(r'[^a-zA-Z0-9_-]+', '-', label).strip('-')[:60] or 'mesh'
    root = Path(cfg['output_root']);root.mkdir(parents=True, exist_ok=True)
    folder = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+safe+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(mode=0o750)
    (folder/'response.txt').write_text(raw)
    (folder/'mesh.obj').write_text(mesh['obj'])
    (folder/'geometry.json').write_text(json.dumps({'vertices':mesh['vertices'],'faces':mesh['faces']}))
    metadata = {'schema_version':1, 'state':'validated-geometry', 'model':model, 'expected_model':cfg['model'], 'completion_verified':model is not None, 'created_utc':datetime.now(timezone.utc).isoformat(), 'vertices':len(mesh['vertices']), 'faces':len(mesh['faces']), 'warnings':mesh['warnings'], 'source_sha256':hashlib.sha256(raw.encode()).hexdigest(), 'size_cm':cfg['size_cm'], 'prompt':prompt}
    (folder/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (folder/'UNREAL_IMPORT.md').write_text('Geometry prototype only. Inspect mesh.obj first. Run the workflow prepare command to create unreal.fbx and preview.blend. In Unreal Content Browser, Import unreal.fbx as a Static Mesh, use uniform scale 1, and enable Generate Missing Collision if appropriate. Verify size, pivot, normals, materials and collision in Static Mesh Editor. UVs are a starting point; no textures, rig or animations are generated. Open or non-manifold meshes require manual inspection.\n')
    return folder

def prepare(folder, cfg, size_cm=None):
    folder = folder.resolve()
    root = Path(cfg['output_root']).resolve()
    if folder.parent != root or not (folder/'manifest.json').is_file():
        raise MeshError("Run directory must be a direct child of configured output_root")
    if any((folder/name).exists() for name in ['unreal.fbx','preview.blend','blender-report.json']):
        raise MeshError("Prepared files already exist; ingest again to create a fresh run")
    mesh = parse_obj(read_limited(folder/'mesh.obj',cfg['maximum_response_bytes']))
    (folder/'geometry.json').write_text(json.dumps({'vertices':mesh['vertices'],'faces':mesh['faces']}))
    size = size_cm if size_cm is not None else cfg['size_cm']
    if not math.isfinite(size) or not 0.01 <= size <= 100000:
        raise MeshError("size_cm must be between 0.01 and 100000")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='-1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    cmd = [cfg['blender'],'--background','--factory-startup','--threads','1','--python-exit-code','1','--python',str(Path(__file__).with_name('llama_mesh_blender.py')),'--',str(folder),str(size)]
    with (folder/'blender.log').open('w') as log:
        result = subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    if result.returncode or not (folder/'unreal.fbx').is_file() or not (folder/'blender-report.json').is_file():
        raise MeshError("Blender preparation failed; inspect blender.log")
    metadata=json.loads((folder/'manifest.json').read_text());metadata.update(state='prepared-for-unreal',size_cm=size,fbx_sha256=hashlib.sha256((folder/'unreal.fbx').read_bytes()).hexdigest());(folder/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')

def request_json(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as response:
        raw=response.read(8388609)
    if len(raw)>8388608:
        raise MeshError("Backend response too large")
    return json.loads(raw)

def generate(args, cfg):
    if CONTROLLER_CONFIG.is_file():
        raise MeshError('Use the authorized OpenCode LLaMA-Mesh MCP generate tool with a stable request_id; direct backend generation is retired on controller-managed hosts.')
    if not args.confirm_idle:
        raise MeshError("Generation requires --confirm-idle after checking all jobs are finished")
    # Discover and contact only the dedicated backend. Never call a router or change replicas.
    service=json.loads(subprocess.run(['kubectl','-n',cfg['namespace'],'get','service',cfg['backend_service'],'-o','json'],check=True,capture_output=True,text=True).stdout)
    url='http://'+service['spec']['clusterIP']+':8000'
    health=request_json(url+'/health')
    if health.get('status')!='ok':
        raise MeshError("Mesh backend is not ready; this command never activates it")
    if health.get('slots_processing',0):
        raise MeshError("Mesh backend is busy")
    models=request_json(url+'/v1/models')
    if cfg['model'] not in [m['id'] for m in models.get('data',[])]:
        raise MeshError("Dedicated backend loaded an unexpected model")
    prompt=read_limited(args.prompt_file,8192).strip()
    if not prompt:
        raise MeshError("Prompt file is empty")
    payload={'model':cfg['model'],'messages':[{'role':'user','content':prompt+'\nReturn one complete Wavefront OBJ mesh using v and f records.'}], 'max_tokens':cfg['max_tokens'],'stream':False}
    response=request_json(url+'/v1/chat/completions',payload)
    return save_run(json.dumps(response),cfg,args.name,prompt)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,default=CONFIG)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('validate',help='Offline geometry validation; writes nothing');p.add_argument('input',type=Path)
    p=commands.add_parser('ingest',help='Save a complete exported response/OBJ as a new validated asset run');p.add_argument('input',type=Path);p.add_argument('--name',default='mesh');p.add_argument('--prepare',action='store_true')
    p=commands.add_parser('prepare',help='Offline CPU-only Blender cleanup/export of an existing run');p.add_argument('run_dir',type=Path);p.add_argument('--size-cm',type=float)
    p=commands.add_parser('generate',help='Explicit future generation, only against an already-running dedicated mesh backend');p.add_argument('--prompt-file',type=Path,required=True);p.add_argument('--name',default='mesh');p.add_argument('--confirm-idle',action='store_true');p.add_argument('--prepare',action='store_true')
    args=parser.parse_args()
    try:
        cfg=config(args)
        if args.command=='validate':
            text,_=extract_response(read_limited(args.input,cfg['maximum_response_bytes']));mesh=parse_obj(text);print(json.dumps({'vertices':len(mesh['vertices']),'faces':len(mesh['faces']),'warnings':mesh['warnings']},indent=2));return
        if args.command=='prepare':prepare(args.run_dir,cfg,args.size_cm);print(args.run_dir.resolve());return
        folder=generate(args,cfg) if args.command=='generate' else save_run(read_limited(args.input,cfg['maximum_response_bytes']),cfg,args.name)
        print(folder,flush=True)
        if args.prepare:prepare(folder,cfg)
    except (MeshError,OSError,subprocess.SubprocessError,ValueError,KeyError) as error:
        parser.exit(1,'ERROR: '+str(error)+'\n')

if __name__=='__main__':main()
