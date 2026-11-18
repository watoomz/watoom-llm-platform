#!/usr/bin/env python3
import pathlib,subprocess,sys
s=pathlib.Path(__file__).resolve().parent
for name in ['audit-host.py','audit-runtime.py']:
 try:r=subprocess.run([sys.executable,str(s/name)],timeout=420);print(name+' exit='+str(r.returncode))
 except Exception as e:print('BLOCKED '+name+' '+type(e).__name__)
