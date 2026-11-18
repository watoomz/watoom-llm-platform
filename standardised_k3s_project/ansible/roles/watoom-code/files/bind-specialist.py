import hashlib,json,pathlib,sys
root,uid,image,revision=sys.argv[1:];p=pathlib.Path(root)/'config/opencode.json';config=json.loads(p.read_text());changed=False
for entry in config.get('watoom_specialists',{}).get('entries',[]):
 if entry['descriptor']['id']!='local-toolkit':continue
 descriptor=entry['descriptor'];model=dict(descriptor['model'],deploymentUID=uid,modelSha256=image.split('@sha256:')[1]);model['configurationSha256']=hashlib.sha256(json.dumps({'image':image,'backend':entry['backend'],'url':entry['url'],'capabilities':descriptor['capabilities'],'resources':descriptor['resources']},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 if model!=descriptor['model'] or descriptor['sourceCommit']!=revision:descriptor['model']=model;descriptor['sourceCommit']=revision;changed=True
if changed:p.write_text(json.dumps(config,indent=2)+'\n')
print('CHANGED' if changed else 'UNCHANGED')
