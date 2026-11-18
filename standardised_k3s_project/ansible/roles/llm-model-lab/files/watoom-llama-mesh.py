#!/usr/bin/env python3
"""Dependency-free MCP stdio adapter and CLI for the authorized Unix bridge."""
import argparse
import hashlib
import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path

SOCKET = Path(os.environ.get('WATOOM_MESH_SOCKET', str(Path.home() / '.config/opencode/mesh-bridge/bridge.sock')))
ASSET_ROOT = Path(os.environ.get('WATOOM_MESH_ASSET_ROOT', '/assets'))

def call(operation, arguments):
    if operation == 'generate':
        # One CPU tool call spans the GPU handover; no Qwen request while Mesh owns it.
        submitted=call('submit',arguments)
        jid=submitted['job_id']
        deadline=time.monotonic()+3500
        while time.monotonic()<deadline:
            result=call('status',{'job_id':jid})
            if result['state']=='complete':return call('retrieve',{'job_id':jid})
            if result['state']=='failed':raise RuntimeError('Mesh job '+jid+' failed: '+str(result.get('error')))
            time.sleep(2)
        raise TimeoutError('Job remains durable: '+jid+'; use status, never resubmit')
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(30)
        connection.connect(str(SOCKET))
        connection.sendall(json.dumps({'operation': operation, **arguments}, ensure_ascii=False).encode() + b'\n')
        with connection.makefile('rb') as stream:
            data = stream.readline(1048577)
        if len(data) > 1048576:
            raise RuntimeError('Oversized bridge response')
        response = json.loads(data)
    if not response['ok']:
        raise RuntimeError(response['error'])
    result = response['result']
    if operation == 'retrieve':
        destination = Path('/workspace/.watoom/llama-mesh') / arguments['job_id']
        destination.mkdir(parents=True, exist_ok=True)
        if destination.resolve() != destination:
            raise RuntimeError('Refuse symlinked workspace output')
        paths = {}
        for key, value in result['artifacts'].items():
            if not value.startswith('/assets/'):
                raise RuntimeError('Artifact is outside the existing asset contract')
            source = ASSET_ROOT / value[len('/assets/'):]
            if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(ASSET_ROOT.resolve() / 'generated/opencode-mesh'):
                raise RuntimeError('Unsafe or missing artifact')
            target = destination / source.name
            if target.is_symlink():
                raise RuntimeError('Refuse symlinked artifact destination')
            content = source.read_bytes()
            hash_key = {'obj': 'raw_sha256', 'glb': 'glb_sha256'}.get(key)
            if hash_key and hashlib.sha256(content).hexdigest() != result['manifest'][hash_key]:
                raise RuntimeError('Artifact hash mismatch')
            if target.exists() and target.read_bytes() != content:
                raise RuntimeError('Refuse to overwrite differing artifact')
            if not target.exists():
                with target.open('xb') as output:
                    output.write(content)
            paths[key] = str(target)
        result['workspace_paths'] = paths
    return result

TOOLS = [
    {'name': 'submit', 'description': 'Asynchronously submit a geometry prompt to the existing LLaMA-Mesh pipeline. Qwen is temporarily unavailable during GPU switching. Record job ID; poll status later.', 'inputSchema': {'type': 'object', 'properties': {'prompt': {'type': 'string', 'maxLength': 8192}, 'name': {'type': 'string'}, 'seed': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647}, 'temperature': {'type': 'number', 'minimum': 0, 'maximum': 2}, 'max_tokens': {'type': 'integer', 'minimum': 1, 'maximum': 7000}, 'request_id': {'type':'string','pattern':'^[A-Za-z0-9_-]{1,80}$'}}, 'required': ['prompt'], 'additionalProperties': False}},
    *[{'name': name, 'description': description, 'inputSchema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}} for name, description in [('status', 'Read durable owned-job state, stage, errors and validated artifact paths.'), ('manifest', 'Read actual job manifest and validation results.'), ('retrieve', 'Copy completed validated OBJ, GLB, manifest and existing PNG renders into /workspace/.watoom/llama-mesh/JOB_ID; verify OBJ/GLB hashes.')]],
    {'name': 'list', 'description': 'List recent jobs owned by this integration.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]

# Reuse the existing server registration and preserve asynchronous submit.
import copy
generation_tool=copy.deepcopy(TOOLS[0])
generation_tool['name']='generate'
generation_tool['description']='Generate one durable 3D asset and wait without LLM inference until Qwen is restored; return validated assets. Use a stable unique request_id; a lost connection must reuse that ID, never allocate a second job.'
generation_tool['inputSchema']['required']=['prompt','request_id']
TOOLS.insert(0,generation_tool)

def mcp():
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if 'id' not in message:
                continue
            method = message['method']
            if method == 'initialize':
                result = {'protocolVersion': message.get('params', {}).get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'watoom-llama-mesh', 'version': '1.0.0'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = message['params']
                try:
                    value = call(params['name'], params.get('arguments', {}))
                    result = {'content': [{'type': 'text', 'text': json.dumps(value)}]}
                except Exception as error:
                    result = {'isError': True, 'content': [{'type': 'text', 'text': str(error)}]}
            else:
                print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'Unknown method'}}), flush=True)
                continue
            print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
        except Exception as error:
            print(str(error), file=sys.stderr, flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['mcp', 'generate', 'submit', 'status', 'manifest', 'retrieve', 'list'])
    parser.add_argument('--json', default='{}')
    args = parser.parse_args()
    if args.operation == 'mcp':
        mcp()
    else:
        print(json.dumps(call(args.operation, json.loads(args.json)), indent=2))
