import os,pathlib,sqlite3,sys
root=pathlib.Path(sys.argv[1]);target=root/'application.sqlite';source=root/'home/.local/share/opencode/opencode-b769c8b4c9e3.db'
if not target.exists() and source.exists():
 with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:src.backup(dst)
 os.chown(target,1001,1001);os.chmod(target,0o600);print('ADOPTED')
else:print('UNCHANGED')
